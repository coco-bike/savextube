# -*- coding: utf-8 -*-
"""
URL download queue processor.

Provides ``UrlDownloadQueue`` – an asyncio queue with bounded concurrency,
timeout protection, and URL deduplication for URL-based downloads (YouTube,
X, Bilibili, etc.).  Mirrors the ``MediaBatchProcessor`` design used for
Telegram media downloads so both paths share the same queue discipline.
"""

import asyncio
import logging
import time
from typing import Optional, Tuple

logger = logging.getLogger("savextube.url_queue")


class UrlDownloadQueue:
    """Queue-based URL download processor with bounded concurrency."""

    def __init__(
        self,
        bot_instance,
        max_concurrent: int = 3,
        timeout: float = 3.0,
        queue_maxsize: int = 200,
        download_timeout: float = 3600.0,
    ):
        self.bot = bot_instance
        self.max_concurrent = max(1, int(max_concurrent))
        self.timeout = float(timeout)
        self.download_timeout = float(download_timeout)

        self.queue: asyncio.Queue[Tuple] = asyncio.Queue(maxsize=max(1, int(queue_maxsize)))
        self._semaphore = asyncio.Semaphore(self.max_concurrent)
        self._active_workers = 0
        self._active_lock = asyncio.Lock()
        self._processor_task: Optional[asyncio.Task] = None
        self._running = False
        # URL dedup: track in-flight URLs to reject duplicates
        self._inflight_urls: set[str] = set()
        self._inflight_lock = asyncio.Lock()

        logger.info(
            "UrlDownloadQueue initialized | max_concurrent=%s queue_maxsize=%s download_timeout=%ss",
            self.max_concurrent,
            self.queue.maxsize,
            self.download_timeout,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        if self._running:
            return
        self._running = True
        self._processor_task = asyncio.create_task(self._process_queue())
        logger.info("UrlDownloadQueue started")

    def stop(self):
        self._running = False
        if self._processor_task:
            self._processor_task.cancel()
            logger.info("UrlDownloadQueue stopped")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def add_to_queue(
        self,
        update,
        context,
        url: str,
        status_message,
        persisted_task_id: str | None = None,
    ) -> bool:
        """Enqueue a URL download request.

        Returns ``True`` if enqueued, ``False`` if the queue is full.
        Duplicate in-flight URLs are silently rejected (returns ``True``
        with a notice edit on *status_message*).
        """
        # --- dedup ---
        normalised = url.strip()
        async with self._inflight_lock:
            if normalised in self._inflight_urls:
                logger.info("URL already in-flight, skipping duplicate: %s", normalised[:80])
                if status_message:
                    try:
                        await status_message.edit_text(
                            "⚠️ 该链接正在下载中，请勿重复发送。",
                            parse_mode=None,
                        )
                    except Exception:
                        pass
                return True
            self._inflight_urls.add(normalised)

        item = (update, context, url, status_message, persisted_task_id)
        try:
            self.queue.put_nowait(item)
            return True
        except asyncio.QueueFull:
            # roll back dedup tracking
            async with self._inflight_lock:
                self._inflight_urls.discard(normalised)
            return False

    async def get_runtime_metrics(self) -> dict:
        """Return queue/runtime counters for diagnostics."""
        async with self._active_lock:
            active = self._active_workers
        queued = self.queue.qsize()
        return {
            "queued": queued,
            "active": active,
            "total": queued + active,
            "max_concurrent": self.max_concurrent,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _process_queue(self):
        while self._running:
            try:
                item = await asyncio.wait_for(self.queue.get(), timeout=self.timeout)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Queue receive failed: %s", e, exc_info=True)
                await asyncio.sleep(0.5)
                continue

            asyncio.create_task(self._run_one(item))

    async def _run_one(self, item: Tuple):
        update, context, url, status_message, persisted_task_id = item
        normalised = url.strip()

        async with self._semaphore:
            async with self._active_lock:
                self._active_workers += 1
            try:
                await asyncio.wait_for(
                    self.bot._process_download_async(
                        update,
                        context,
                        url,
                        status_message,
                        persisted_task_id=persisted_task_id,
                    ),
                    timeout=self.download_timeout,
                )
            except asyncio.TimeoutError:
                logger.error("URL download timed out after %ss: %s", self.download_timeout, url[:120])
                if status_message:
                    try:
                        await status_message.edit_text(
                            f"❌ 下载超时（>{int(self.download_timeout)}s），任务已终止。",
                            parse_mode=None,
                        )
                    except Exception:
                        pass
            except Exception as e:
                logger.error("URL download worker failed: %s", e, exc_info=True)
                if status_message:
                    try:
                        await status_message.edit_text(f"❌ 下载失败：{e}", parse_mode=None)
                    except Exception:
                        pass
            finally:
                async with self._active_lock:
                    if self._active_workers > 0:
                        self._active_workers -= 1
                async with self._inflight_lock:
                    self._inflight_urls.discard(normalised)
