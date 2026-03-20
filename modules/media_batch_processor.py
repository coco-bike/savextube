# -*- coding: utf-8 -*-
"""
Media queue processor used by main.py.

This module provides `MediaBatchProcessor` so existing imports keep working:
    from modules.media_batch_processor import MediaBatchProcessor
"""

import asyncio
import logging
from typing import Optional, Tuple

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger("savextube.media_batch")


class MediaBatchProcessor:
    """Queue-based media download processor with bounded concurrency."""

    def __init__(
        self,
        bot_instance,
        max_concurrent: int = 3,
        timeout: float = 3.0,
        queue_maxsize: int = 200,
        download_timeout: float = 1800.0,
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

        logger.info(
            "MediaBatchProcessor initialized | max_concurrent=%s queue_maxsize=%s download_timeout=%ss",
            self.max_concurrent,
            self.queue.maxsize,
            self.download_timeout,
        )

    def start(self):
        if self._running:
            return
        self._running = True
        self._processor_task = asyncio.create_task(self._process_queue())
        logger.info("MediaBatchProcessor started")

    def stop(self):
        self._running = False
        if self._processor_task:
            self._processor_task.cancel()
            logger.info("MediaBatchProcessor stopped")

    async def add_to_queue(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        message,
        status_message,
        attachment,
        persisted_task_id: str | None = None,
    ) -> bool:
        item = (update, context, message, status_message, attachment, persisted_task_id)
        try:
            self.queue.put_nowait(item)
            return True
        except asyncio.QueueFull:
            return False

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

    async def _run_one(self, item: Tuple):
        update, context, _message, status_message, _attachment, persisted_task_id = item
        async with self._semaphore:
            async with self._active_lock:
                self._active_workers += 1
            try:
                await asyncio.wait_for(
                    self.bot.download_user_media(
                        update,
                        context,
                        persisted_task_id=persisted_task_id,
                        from_queue=True,
                        status_message=status_message,
                    ),
                    timeout=self.download_timeout,
                )
            except asyncio.TimeoutError:
                logger.error("Media download timed out after %ss", self.download_timeout)
                if status_message:
                    try:
                        await status_message.edit_text(
                            f"❌ 下载超时（>{int(self.download_timeout)}s），任务已终止。"
                        )
                    except Exception:
                        pass
            except Exception as e:
                logger.error("Media download worker failed: %s", e, exc_info=True)
                if status_message:
                    try:
                        await status_message.edit_text(f"❌ 下载失败：{e}")
                    except Exception:
                        pass
            finally:
                async with self._active_lock:
                    if self._active_workers > 0:
                        self._active_workers -= 1
