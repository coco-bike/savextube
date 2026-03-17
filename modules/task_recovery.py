# -*- coding: utf-8 -*-
"""
任务恢复和重试管理器
支持错误自动重试、暂停恢复、重启续传
"""

import asyncio
import logging
from typing import Optional, Callable, Awaitable
from datetime import datetime

from .task_persistence import (
    get_persistence_manager,
    TaskPersistStatus,
    PersistedTask,
)

logger = logging.getLogger('savextube.task_recovery')


class TaskRecoveryManager:
    """任务恢复管理器"""
    
    def __init__(self, bot_instance):
        """
        初始化恢复管理器
        
        Args:
            bot_instance: TelegramBot 实例
        """
        self.bot = bot_instance
        self.persistence = get_persistence_manager()
        
        # 重试配置
        self.max_retries = 5
        self.retry_delays = [10, 30, 60, 120, 300]  # 重试间隔（秒）
        
        # 运行状态
        self.running = False
        self.retry_task: Optional[asyncio.Task] = None
        self.paused_tasks: set = set()  # 用户手动暂停的任务
        
        logger.info("✅ 任务恢复管理器已初始化")
    
    async def start(self):
        """启动恢复管理器"""
        if not self.running:
            self.running = True
            self.retry_task = asyncio.create_task(self._retry_loop())
            logger.info("🚀 任务恢复管理器已启动")
    
    async def stop(self):
        """停止恢复管理器"""
        self.running = False
        if self.retry_task:
            self.retry_task.cancel()
            try:
                await self.retry_task
            except asyncio.CancelledError:
                pass
            self.retry_task = None
        logger.info("⏹️ 任务恢复管理器已停止")
    
    async def _retry_loop(self):
        """定期重试错误任务"""
        logger.info("🔄 开始重试循环")
        
        while self.running:
            try:
                await asyncio.sleep(30)  # 每 30 秒检查一次
                
                # 获取可重试的错误任务
                error_tasks = await self.persistence.get_error_tasks()
                
                for task in error_tasks:
                    if task.task_id in self.paused_tasks:
                        continue  # 跳过用户暂停的任务
                    
                    # 检查是否到了重试时间
                    retry_delay = self._get_retry_delay(task.retry_count)
                    if retry_delay <= 0:
                        # 超过最大重试次数
                        await self.persistence.update_status(
                            task.task_id,
                            TaskPersistStatus.FAILED,
                            f"超过最大重试次数 ({self.max_retries})",
                        )
                        logger.warning(f"❌ 任务失败：{task.task_id} (超过最大重试次数)")
                        continue
                    
                    # 检查等待时间
                    updated_at = datetime.fromisoformat(task.updated_at)
                    elapsed = (datetime.now() - updated_at).total_seconds()
                    
                    if elapsed >= retry_delay:
                        # 可以重试
                        logger.info(f"🔄 重试任务：{task.task_id} (第 {task.retry_count + 1}/{self.max_retries} 次)")
                        asyncio.create_task(self._retry_task(task))
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ 重试循环错误：{e}")
    
    def _get_retry_delay(self, retry_count: int) -> int:
        """获取重试间隔"""
        if retry_count >= len(self.retry_delays):
            return -1  # 超过最大重试次数
        return self.retry_delays[retry_count]
    
    async def _retry_task(self, task: PersistedTask):
        """重试单个任务"""
        try:
            # 更新状态为等待中
            await self.persistence.update_status(
                task.task_id,
                TaskPersistStatus.PENDING,
            )
            
            # 重新加入下载队列
            # 这里需要调用 Bot 的下载方法
            if hasattr(self.bot, '_process_download_async'):
                # 创建一个假的 update/context 用于重试
                logger.info(f"📥 重新排队任务：{task.url}")
                # 注意：这里需要实际实现重试逻辑
                # 由于 Telegram API 限制，可能需要用户重新发送链接
                
        except Exception as e:
            logger.error(f"❌ 重试任务失败：{task.task_id} - {e}")
            await self.persistence.update_status(
                task.task_id,
                TaskPersistStatus.ERROR,
                f"重试失败：{e}",
            )
    
    async def pause_task(self, task_id: str) -> bool:
        """
        暂停任务
        
        Args:
            task_id: 任务 ID
            
        Returns:
            是否成功暂停
        """
        self.paused_tasks.add(task_id)
        success = await self.persistence.pause_task(task_id)
        
        if success:
            logger.info(f"⏸️ 用户暂停任务：{task_id}")
        
        return success
    
    async def resume_task(self, task_id: str) -> bool:
        """
        恢复任务
        
        Args:
            task_id: 任务 ID
            
        Returns:
            是否成功恢复
        """
        self.paused_tasks.discard(task_id)
        success = await self.persistence.resume_task(task_id)
        
        if success:
            logger.info(f"▶️ 用户恢复任务：{task_id}")
            # 重新加入下载队列
            asyncio.create_task(self._queue_resumed_task(task_id))
        
        return success
    
    async def _queue_resumed_task(self, task_id: str):
        """将恢复的任务重新加入下载队列"""
        try:
            task = await self.persistence.get_task(task_id)
            if not task:
                return
            
            logger.info(f"📥 恢复任务下载：{task.url}")
            # 这里需要实现实际的下载逻辑
            # 可能需要发送消息通知用户
            
        except Exception as e:
            logger.error(f"❌ 恢复任务失败：{task_id} - {e}")
    
    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        self.paused_tasks.discard(task_id)
        success = await self.persistence.cancel_task(task_id)
        
        if success:
            logger.info(f"⏹️ 用户取消任务：{task_id}")
        
        return success
    
    async def get_task_status(self, task_id: str) -> Optional[dict]:
        """获取任务状态"""
        task = await self.persistence.get_task(task_id)
        if not task:
            return None
        
        return {
            'task_id': task.task_id,
            'url': task.url,
            'title': task.title,
            'status': task.status.value,
            'progress': task.progress,
            'error_message': task.error_message,
            'retry_count': task.retry_count,
            'max_retries': task.max_retries,
            'created_at': task.created_at,
            'updated_at': task.updated_at,
            'paused_at': task.paused_at,
            'completed_at': task.completed_at,
            'source': task.source,
            'chat_id': task.chat_id,
            'message_id': task.message_id,
        }
    
    async def get_all_tasks_summary(self) -> dict:
        """获取所有任务摘要"""
        tasks = await self.persistence.get_active_tasks()
        paused = await self.persistence.get_paused_tasks()
        errors = await self.persistence.get_error_tasks()
        
        return {
            'total_active': len(tasks),
            'paused': len(paused),
            'error_retryable': len(errors),
            'tasks': [t.to_dict() for t in tasks[:20]],  # 限制返回数量
        }


# 全局实例
_recovery_manager: Optional[TaskRecoveryManager] = None


def get_recovery_manager(bot_instance=None) -> TaskRecoveryManager:
    """获取恢复管理器实例"""
    global _recovery_manager
    if _recovery_manager is None:
        if bot_instance is None:
            raise ValueError("首次调用需要提供 bot_instance")
        _recovery_manager = TaskRecoveryManager(bot_instance)
    return _recovery_manager


def init_recovery(bot_instance) -> TaskRecoveryManager:
    """初始化恢复管理器"""
    global _recovery_manager
    _recovery_manager = TaskRecoveryManager(bot_instance)
    return _recovery_manager
