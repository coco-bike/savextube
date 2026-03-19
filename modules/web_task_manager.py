# -*- coding: utf-8 -*-
"""
Web UI 任务管理器
与 GlobalProgressManager 集成，提供任务查询和 WebSocket 推送
"""

import asyncio
import time
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum

logger = logging.getLogger('savextube.web.task_manager')


class TaskStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskInfo:
    """任务信息"""
    id: str
    title: str = ""
    url: str = ""
    type: str = "single"  # single, batch, playlist, channel
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0
    downloaded_bytes: int = 0
    total_bytes: int = 0
    speed: float = 0.0  # bytes/s
    eta: int = 0  # seconds
    filename: str = ""
    error: str = ""
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    source: str = ""  # 来源：telegram, web, api
    channel: str = ""  # Telegram 频道/用户
    message_id: Optional[int] = None  # Telegram 消息 ID
    
    # 额外信息
    extra: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        data = asdict(self)
        data['status'] = self.status.value
        # 计算友好显示
        data['progress_percent'] = round(self.progress, 1)
        data['speed_text'] = self._format_speed(self.speed)
        data['eta_text'] = self._format_eta(self.eta)
        data['duration_text'] = self._format_duration()
        data['created_at_text'] = datetime.fromtimestamp(self.created_at).strftime('%Y-%m-%d %H:%M:%S')
        return data
    
    @staticmethod
    def _format_speed(speed: float) -> str:
        if speed <= 0:
            return "-"
        if speed < 1024:
            return f"{speed:.1f} B/s"
        elif speed < 1024 * 1024:
            return f"{speed / 1024:.1f} KB/s"
        else:
            return f"{speed / (1024 * 1024):.1f} MB/s"
    
    @staticmethod
    def _format_eta(eta: int) -> str:
        if eta <= 0:
            return "-"
        if eta < 60:
            return f"{eta}s"
        elif eta < 3600:
            return f"{eta // 60}m {eta % 60}s"
        else:
            return f"{eta // 3600}h {(eta % 3600) // 60}m"
    
    def _format_duration(self) -> str:
        if self.started_at is None:
            return "-"
        end_time = self.completed_at or time.time()
        duration = end_time - self.started_at
        if duration < 60:
            return f"{duration:.1f}秒"
        elif duration < 3600:
            return f"{duration // 60:.0f}分钟"
        else:
            return f"{duration // 3600:.0f}小时"


class TaskManager:
    """任务管理器 - 单例模式"""
    _instance: Optional['TaskManager'] = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return
        self._initialized = True
        
        self.tasks: Dict[str, TaskInfo] = {}
        self.task_order: List[str] = []  # 保持任务顺序
        self.websocket_clients: List[asyncio.Queue] = []
        self.max_history = 100  # 最多保留 100 条历史记录
        self._cleanup_task: Optional[asyncio.Task] = None
    
    async def start(self):
        """启动后台任务"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
    
    async def stop(self):
        """停止后台任务"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
    
    async def _cleanup_loop(self):
        """定期清理已完成的任务"""
        while True:
            try:
                await asyncio.sleep(60)  # 每分钟清理一次
                await self._cleanup_completed()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"清理任务失败：{e}")
    
    async def _cleanup_completed(self):
        """清理已完成的任务，保留最近的记录"""
        completed = [
            tid for tid, t in self.tasks.items()
            if t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
        ]
        
        # 如果超过最大历史数，删除最旧的
        if len(completed) > self.max_history:
            to_remove = completed[:-self.max_history]
            for tid in to_remove:
                if tid in self.tasks:
                    del self.tasks[tid]
                    if tid in self.task_order:
                        self.task_order.remove(tid)
    
    def create_task(
        self,
        task_id: str,
        title: str,
        url: str,
        task_type: str = "single",
        source: str = "telegram",
        channel: str = "",
        message_id: Optional[int] = None,
    ) -> TaskInfo:
        """创建新任务"""
        task = TaskInfo(
            id=task_id,
            title=title,
            url=url,
            type=task_type,
            status=TaskStatus.QUEUED,
            source=source,
            channel=channel,
            message_id=message_id,
        )
        self.tasks[task_id] = task
        self.task_order.append(task_id)
        logger.info(f"创建任务：{task_id} - {title}")
        asyncio.create_task(self._broadcast_task_created(task.to_dict()))
        return task
    
    def update_task(
        self,
        task_id: str,
        status: Optional[TaskStatus] = None,
        progress: Optional[float] = None,
        downloaded_bytes: Optional[int] = None,
        total_bytes: Optional[int] = None,
        speed: Optional[float] = None,
        eta: Optional[int] = None,
        filename: Optional[str] = None,
        error: Optional[str] = None,
        extra: Optional[Dict] = None,
    ):
        """更新任务进度"""
        if task_id not in self.tasks:
            logger.warning(f"任务不存在：{task_id}")
            return
        
        task = self.tasks[task_id]
        updated = False
        
        if status is not None:
            task.status = status
            if status == TaskStatus.DOWNLOADING and task.started_at is None:
                task.started_at = time.time()
            elif status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                task.completed_at = time.time()
            updated = True
        
        if progress is not None:
            task.progress = progress
            updated = True
        
        if downloaded_bytes is not None:
            task.downloaded_bytes = downloaded_bytes
            updated = True
        
        if total_bytes is not None:
            task.total_bytes = total_bytes
            updated = True
        
        if speed is not None:
            task.speed = speed
            updated = True
        
        if eta is not None:
            task.eta = eta
            updated = True
        
        if filename is not None:
            task.filename = filename
            updated = True
        
        if error is not None:
            task.error = error
            updated = True
        
        if extra is not None:
            task.extra.update(extra)
            updated = True
        
        if updated:
            asyncio.create_task(self._broadcast_task_updated(task.to_dict()))
    
    def complete_task(self, task_id: str, success: bool = True, error: str = ""):
        """完成任务"""
        task = self.tasks.get(task_id)
        failed_progress = task.progress if task else 0.0
        self.update_task(
            task_id,
            status=TaskStatus.COMPLETED if success else TaskStatus.FAILED,
            progress=100.0 if success else failed_progress,
            error=error,
        )
        logger.info(f"任务完成：{task_id} - {'成功' if success else '失败'}")
    
    def cancel_task(self, task_id: str):
        """取消任务"""
        self.update_task(task_id, status=TaskStatus.CANCELLED)
        logger.info(f"任务取消：{task_id}")
    
    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        """获取任务信息"""
        return self.tasks.get(task_id)
    
    def get_all_tasks(self, limit: int = 50) -> List[Dict]:
        """获取所有任务（最近的优先）"""
        result = []
        for tid in reversed(self.task_order[-limit:]):
            if tid in self.tasks:
                result.append(self.tasks[tid].to_dict())
        return result
    
    def get_active_tasks(self) -> List[Dict]:
        """获取活跃任务"""
        return [
            t.to_dict() for t in self.tasks.values()
            if t.status in (TaskStatus.QUEUED, TaskStatus.DOWNLOADING, TaskStatus.PROCESSING)
        ]
    
    def get_completed_tasks(self, limit: int = 20) -> List[Dict]:
        """获取已完成任务"""
        completed = [
            t for t in self.tasks.values()
            if t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
        ]
        completed.sort(key=lambda x: x.completed_at or 0, reverse=True)
        return [t.to_dict() for t in completed[:limit]]
    
    def get_statistics(self) -> Dict:
        """获取统计信息"""
        now = time.time()
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        
        today_count = sum(
            1 for t in self.tasks.values()
            if t.created_at >= today_start and t.status == TaskStatus.COMPLETED
        )
        
        active_count = sum(
            1 for t in self.tasks.values()
            if t.status in (TaskStatus.QUEUED, TaskStatus.DOWNLOADING, TaskStatus.PROCESSING)
        )
        
        return {
            "total_tasks": len(self.tasks),
            "active_tasks": active_count,
            "today_downloads": today_count,
            "completed_today": today_count,
        }
    
    async def register_websocket(self, queue: asyncio.Queue):
        """注册 WebSocket 客户端"""
        async with self._lock:
            self.websocket_clients.append(queue)
        logger.debug(f"WebSocket 客户端已连接，当前连接数：{len(self.websocket_clients)}")
    
    async def unregister_websocket(self, queue: asyncio.Queue):
        """注销 WebSocket 客户端"""
        async with self._lock:
            if queue in self.websocket_clients:
                self.websocket_clients.remove(queue)
        logger.debug(f"WebSocket 客户端已断开，当前连接数：{len(self.websocket_clients)}")
    
    async def _broadcast(self, event_type: str, data: Dict):
        """广播事件到所有 WebSocket 客户端"""
        message = {
            "type": event_type,
            "data": data,
            "timestamp": time.time(),
        }
        
        async with self._lock:
            dead_clients = []
            for client in self.websocket_clients:
                try:
                    await client.put(message)
                except Exception:
                    dead_clients.append(client)
            
            # 移除失效的客户端
            for client in dead_clients:
                if client in self.websocket_clients:
                    self.websocket_clients.remove(client)
    
    async def _broadcast_task_created(self, task_data: Dict):
        """广播任务创建事件"""
        await self._broadcast("task_created", task_data)
    
    async def _broadcast_task_updated(self, task_data: Dict):
        """广播任务更新事件"""
        await self._broadcast("task_updated", task_data)
    
    async def broadcast_task_progress(self, task_id: str, progress_data: dict):
        """从 yt-dlp 进度数据广播任务更新"""
        if task_id not in self.tasks:
            return
        
        task = self.tasks[task_id]
        
        status = progress_data.get('status', '')
        
        if status == 'downloading':
            downloaded = progress_data.get('downloaded_bytes', 0) or 0
            total = progress_data.get('total_bytes') or progress_data.get('total_bytes_estimate', 0) or 0
            speed = progress_data.get('speed', 0) or 0
            eta = progress_data.get('eta', 0) or 0
            
            progress = (downloaded / total * 100) if total > 0 else 0
            
            self.update_task(
                task_id,
                status=TaskStatus.DOWNLOADING,
                progress=progress,
                downloaded_bytes=downloaded,
                total_bytes=total,
                speed=speed,
                eta=eta,
                filename=progress_data.get('filename', ''),
            )
        
        elif status == 'finished':
            self.update_task(
                task_id,
                status=TaskStatus.PROCESSING,
                progress=100.0,
                filename=progress_data.get('filename', ''),
            )
        
        elif status == 'error':
            self.complete_task(
                task_id,
                success=False,
                error=progress_data.get('error', '未知错误'),
            )


# 全局任务管理器实例
task_manager = TaskManager()


def get_task_manager() -> TaskManager:
    """获取任务管理器实例"""
    return task_manager
