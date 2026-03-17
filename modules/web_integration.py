# -*- coding: utf-8 -*-
"""
TG 机器人与 Web UI 任务集成模块
将 Telegram 机器人的下载任务同步到 Web UI
"""

import logging
import asyncio
from typing import Optional, Dict, Any

logger = logging.getLogger('savextube.web_integration')

# 全局 Web 任务管理器引用
_web_task_manager = None
_bot_instance = None
_persistence = None


def init_web_integration(bot_instance, task_manager, persistence=None):
    """
    初始化 Web 集成
    
    Args:
        bot_instance: Telegram Bot 实例
        task_manager: Web TaskManager 实例
        persistence: TaskPersistenceManager 实例（可选）
    """
    global _web_task_manager, _bot_instance, _persistence
    _web_task_manager = task_manager
    _bot_instance = bot_instance
    _persistence = persistence
    
    # 如果没有提供 persistence，尝试获取
    if _persistence is None:
        try:
            from modules.task_persistence import get_persistence_manager
            _persistence = get_persistence_manager()
        except Exception:
            pass
    
    logger.info("Web 集成已初始化")


def get_web_task_manager():
    """获取 Web 任务管理器"""
    return _web_task_manager


def get_bot_instance():
    """获取 Bot 实例"""
    return _bot_instance


def create_task_from_message(message, url: str, task_type: str = "single") -> Optional[str]:
    """
    从 Telegram 消息创建任务
    
    Args:
        message: Telegram 消息
        url: 下载链接
        task_type: 任务类型
    
    Returns:
        任务 ID
    """
    if not _web_task_manager:
        return None
    
    # 生成任务 ID
    task_id = f"tg_{message.chat_id}_{message.message_id}"
    
    # 提取标题
    title = url
    if message.text and len(message.text) < 100:
        title = message.text.split('\n')[0]
    
    # 获取频道/用户信息
    channel = ""
    if hasattr(message, 'chat') and message.chat:
        channel = getattr(message.chat, 'username', '') or getattr(message.chat, 'title', '')
    
    # 创建 Web 任务
    _web_task_manager.create_task(
        task_id=task_id,
        title=title,
        url=url,
        task_type=task_type,
        source="telegram",
        channel=channel,
        message_id=message.message_id,
    )
    
    # 同时创建持久化任务
    if _persistence:
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            loop.run_until_complete(_persistence.create_task(
                task_id=task_id,
                url=url,
                title=title,
                source="telegram",
                chat_id=message.chat_id,
                message_id=message.message_id,
                user_id=message.from_user.id if hasattr(message, 'from_user') else None,
            ))
        except Exception as e:
            logger.debug(f"持久化任务创建失败：{e}")
    
    logger.info(f"创建 TG 任务：{task_id}")
    return task_id


def update_task_progress(task_id: str, progress_data: dict):
    """
    更新任务进度
    
    Args:
        task_id: 任务 ID
        progress_data: 进度数据 (yt-dlp 格式)
    """
    if not _web_task_manager:
        return
    
    asyncio.create_task(_web_task_manager.broadcast_task_progress(task_id, progress_data))


def complete_task(task_id: str, success: bool = True, error: str = ""):
    """
    完成任务
    
    Args:
        task_id: 任务 ID
        success: 是否成功
        error: 错误信息
    """
    if not _web_task_manager:
        return
    
    _web_task_manager.complete_task(task_id, success, error)
    
    # 更新持久化状态
    if _persistence:
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            status = __import__('modules.task_persistence', fromlist=['TaskPersistStatus']).TaskPersistStatus
            loop.run_until_complete(_persistence.update_status(
                task_id,
                status.COMPLETED if success else status.FAILED,
                error_message=error if not success else "",
            ))
        except Exception as e:
            logger.debug(f"持久化任务更新失败：{e}")
    
    logger.info(f"TG 任务完成：{task_id} - {'成功' if success else '失败'}")


class WebProgressCallback:
    """
    Web 进度回调包装器
    将进度回调同步到 Web UI
    """
    
    def __init__(self, task_id: str):
        self.task_id = task_id
    
    async def __call__(self, progress_data: dict):
        """进度回调"""
        if not isinstance(progress_data, dict):
            return
        
        status = progress_data.get('status', '')
        
        if status == 'downloading':
            update_task_progress(self.task_id, progress_data)
        elif status == 'finished':
            # 处理完成
            pass
        elif status == 'error':
            complete_task(self.task_id, success=False, error=progress_data.get('error', '未知错误'))


def create_web_progress_callback(task_id: str) -> WebProgressCallback:
    """创建 Web 进度回调"""
    return WebProgressCallback(task_id)


# 装饰器：自动创建 Web 任务
def track_download_task(func):
    """
    装饰器：跟踪下载任务并同步到 Web UI
    
    用法:
        @track_download_task
        async def download_video(url, ...):
            ...
    """
    import functools
    
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        # 尝试从参数中提取 url 和 message
        url = kwargs.get('url') or (args[0] if args else None)
        message = kwargs.get('message') or kwargs.get('update')
        
        if not url or not _web_task_manager:
            return await func(*args, **kwargs)
        
        # 确定任务类型
        task_type = "single"
        if kwargs.get('auto_playlist'):
            task_type = "playlist"
        elif kwargs.get('is_batch'):
            task_type = "batch"
        
        # 创建任务
        if message:
            task_id = create_task_from_message(message, url, task_type)
            if task_id:
                # 注入进度回调
                callback = create_web_progress_callback(task_id)
                kwargs['progress_callback'] = callback
        
        return await func(*args, **kwargs)
    
    return wrapper
