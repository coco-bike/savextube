# -*- coding: utf-8 -*-
"""
Task recovery manager.

Provides retry scheduling and startup resume for persisted tasks.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from .task_persistence import (
    PersistedTask,
    TaskPersistStatus,
    get_persistence_manager,
)

logger = logging.getLogger("savextube.task_recovery")


class TaskRecoveryManager:
    """Manage persisted task retries and resume flows."""

    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.persistence = get_persistence_manager()

        self.max_retries = 5
        self.retry_delays = [10, 30, 60, 120, 300]

        self.running = False
        self.retry_task: Optional[asyncio.Task] = None
        self.paused_tasks: set[str] = set()
        self.inflight_task_ids: set[str] = set()

        logger.info("Task recovery manager initialized")

    async def start(self):
        """Start the retry loop."""
        if self.running:
            return
        self.running = True
        self.retry_task = asyncio.create_task(self._retry_loop())
        logger.info("Task recovery manager started")

    async def stop(self):
        """Stop the retry loop."""
        self.running = False
        if not self.retry_task:
            return
        self.retry_task.cancel()
        try:
            await self.retry_task
        except asyncio.CancelledError:
            pass
        self.retry_task = None
        logger.info("Task recovery manager stopped")

    async def _retry_loop(self):
        """Retry error tasks on a backoff schedule."""
        logger.info("Task recovery retry loop running")

        while self.running:
            try:
                await asyncio.sleep(30)
                error_tasks = await self.persistence.get_error_tasks()

                for task in error_tasks:
                    if task.task_id in self.paused_tasks:
                        continue
                    if task.task_id in self.inflight_task_ids:
                        continue
                    if self._is_non_retryable_error(task):
                        await self.persistence.update_status(
                            task.task_id,
                            TaskPersistStatus.FAILED,
                            task.error_message or "Marked as non-retryable error",
                        )
                        logger.warning("Task marked non-retryable and failed: %s", task.task_id)
                        continue

                    retry_delay = self._get_retry_delay(task.retry_count)
                    if retry_delay < 0:
                        await self.persistence.update_status(
                            task.task_id,
                            TaskPersistStatus.FAILED,
                            f"Exceeded max retries ({self.max_retries})",
                        )
                        logger.warning("Task exceeded max retries: %s", task.task_id)
                        continue

                    updated_at = datetime.fromisoformat(task.updated_at or task.created_at)
                    elapsed = (datetime.now() - updated_at).total_seconds()
                    if elapsed < retry_delay:
                        continue

                    self.inflight_task_ids.add(task.task_id)
                    asyncio.create_task(self._retry_task(task))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Task recovery retry loop failed: %s", e)

    def _get_retry_delay(self, retry_count: int) -> int:
        if retry_count >= len(self.retry_delays):
            return -1
        return self.retry_delays[retry_count]

    def _is_non_retryable_error(self, task: PersistedTask) -> bool:
        error_text = (task.error_message or "").lower()
        non_retryable_signatures = (
            "no matched telethon message found",
            "无法找到匹配的telethon消息",
            "无法找到匹配的媒体消息",
        )
        return any(signature in error_text for signature in non_retryable_signatures)

    async def _retry_task(self, task: PersistedTask):
        """Retry a single task by asking the bot to resume it."""
        try:
            await self.persistence.update_status(task.task_id, TaskPersistStatus.PENDING)
            if not hasattr(self.bot, "resume_persisted_task"):
                raise RuntimeError("Bot does not implement resume_persisted_task")

            resumed = await self.bot.resume_persisted_task(task, notify=True)
            if not resumed:
                raise RuntimeError("resume_persisted_task returned False")
        except Exception as e:
            logger.error("Retry task failed: %s - %s", task.task_id, e)
            await self.persistence.update_status(
                task.task_id,
                TaskPersistStatus.ERROR,
                f"Retry failed: {e}",
            )
        finally:
            self.inflight_task_ids.discard(task.task_id)

    async def pause_task(self, task_id: str) -> bool:
        self.paused_tasks.add(task_id)
        return await self.persistence.pause_task(task_id)

    async def resume_task(self, task_id: str) -> bool:
        self.paused_tasks.discard(task_id)
        success = await self.persistence.resume_task(task_id)
        if not success:
            return False

        self.inflight_task_ids.add(task_id)
        asyncio.create_task(self._queue_resumed_task(task_id))
        return True

    async def _queue_resumed_task(self, task_id: str):
        """Queue a resumed paused task."""
        try:
            task = await self.persistence.get_task(task_id)
            if not task:
                return
            if not hasattr(self.bot, "resume_persisted_task"):
                raise RuntimeError("Bot does not implement resume_persisted_task")

            resumed = await self.bot.resume_persisted_task(task, notify=True)
            if not resumed:
                raise RuntimeError("resume_persisted_task returned False")
        except Exception as e:
            logger.error("Resume task failed: %s - %s", task_id, e)
            await self.persistence.update_status(
                task_id,
                TaskPersistStatus.ERROR,
                f"Resume failed: {e}",
            )
        finally:
            self.inflight_task_ids.discard(task_id)

    async def resume_pending_tasks(self) -> dict:
        """Resume recoverable tasks after startup."""
        active_tasks = await self.persistence.get_active_tasks()
        resumable_statuses = {TaskPersistStatus.PENDING, TaskPersistStatus.ERROR}
        success_count = 0
        fail_count = 0

        for task in active_tasks:
            if task.status not in resumable_statuses:
                continue
            if task.status == TaskPersistStatus.ERROR:
                if task.retry_count >= task.max_retries:
                    await self.persistence.update_status(
                        task.task_id,
                        TaskPersistStatus.FAILED,
                        f"Exceeded max retries ({task.max_retries}) before startup resume",
                    )
                    logger.warning(
                        "Skip startup resume for over-retried task: %s (retry_count=%s, max=%s)",
                        task.task_id,
                        task.retry_count,
                        task.max_retries,
                    )
                    continue
                if self._is_non_retryable_error(task):
                    await self.persistence.update_status(
                        task.task_id,
                        TaskPersistStatus.FAILED,
                        task.error_message or "Marked as non-retryable before startup resume",
                    )
                    logger.warning("Skip startup resume for non-retryable task: %s", task.task_id)
                    continue
            if task.task_id in self.paused_tasks:
                continue
            if task.task_id in self.inflight_task_ids:
                continue

            self.inflight_task_ids.add(task.task_id)
            try:
                resumed = await self.bot.resume_persisted_task(task, notify=True)
                if resumed:
                    success_count += 1
                else:
                    fail_count += 1
                    await self.persistence.update_status(
                        task.task_id,
                        TaskPersistStatus.ERROR,
                        "Startup resume returned False",
                    )
            except Exception as e:
                fail_count += 1
                logger.error("Startup resume failed: %s - %s", task.task_id, e)
                await self.persistence.update_status(
                    task.task_id,
                    TaskPersistStatus.ERROR,
                    f"Startup resume failed: {e}",
                )
            finally:
                self.inflight_task_ids.discard(task.task_id)

        return {"success_count": success_count, "fail_count": fail_count}

    async def cancel_task(self, task_id: str) -> bool:
        self.paused_tasks.discard(task_id)
        return await self.persistence.cancel_task(task_id)

    async def get_task_status(self, task_id: str) -> Optional[dict]:
        task = await self.persistence.get_task(task_id)
        if not task:
            return None

        return {
            "task_id": task.task_id,
            "url": task.url,
            "title": task.title,
            "status": task.status.value,
            "progress": task.progress,
            "error_message": task.error_message,
            "retry_count": task.retry_count,
            "max_retries": task.max_retries,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "paused_at": task.paused_at,
            "completed_at": task.completed_at,
            "source": task.source,
            "chat_id": task.chat_id,
            "message_id": task.message_id,
        }

    async def get_all_tasks_summary(self) -> dict:
        tasks = await self.persistence.get_active_tasks()
        paused = await self.persistence.get_paused_tasks()
        errors = await self.persistence.get_error_tasks()

        return {
            "total_active": len(tasks),
            "paused": len(paused),
            "error_retryable": len(errors),
            "tasks": [t.to_dict() for t in tasks[:20]],
        }


_recovery_manager: Optional[TaskRecoveryManager] = None


def get_recovery_manager(bot_instance=None) -> TaskRecoveryManager:
    """Get the singleton recovery manager."""
    global _recovery_manager
    if _recovery_manager is None:
        if bot_instance is None:
            raise ValueError("bot_instance is required on first call")
        _recovery_manager = TaskRecoveryManager(bot_instance)
    return _recovery_manager


def init_recovery(bot_instance) -> TaskRecoveryManager:
    """Initialize the singleton recovery manager."""
    global _recovery_manager
    _recovery_manager = TaskRecoveryManager(bot_instance)
    return _recovery_manager
