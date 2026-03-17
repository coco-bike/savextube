# -*- coding: utf-8 -*-
"""
下载任务持久化模块
支持任务状态保存、恢复、断点续传
"""

import json
import logging
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger('savextube.task_persistence')


class TaskPersistStatus(str, Enum):
    """任务持久化状态"""
    PENDING = "pending"  # 等待中
    DOWNLOADING = "downloading"  # 下载中
    PAUSED = "paused"  # 已暂停
    ERROR = "error"  # 错误（可恢复）
    FAILED = "failed"  # 失败（不可恢复）
    COMPLETED = "completed"  # 已完成
    CANCELLED = "cancelled"  # 已取消


@dataclass
class PersistedTask:
    """持久化任务数据"""
    task_id: str
    url: str
    title: str = ""
    status: TaskPersistStatus = TaskPersistStatus.PENDING
    progress: float = 0.0
    downloaded_bytes: int = 0
    total_bytes: int = 0
    error_message: str = ""
    retry_count: int = 0
    max_retries: int = 5
    created_at: str = ""
    updated_at: str = ""
    paused_at: Optional[str] = None
    completed_at: Optional[str] = None
    
    # 下载上下文（用于恢复）
    context: Dict[str, Any] = None
    
    # 来源信息
    source: str = "telegram"  # telegram, web, api
    chat_id: Optional[int] = None
    message_id: Optional[int] = None
    user_id: Optional[int] = None
    
    def __post_init__(self):
        if self.context is None:
            self.context = {}
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        data = asdict(self)
        data['status'] = self.status.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'PersistedTask':
        """从字典创建"""
        data = data.copy()
        if 'status' in data:
            data['status'] = TaskPersistStatus(data['status'])
        if data.get('context') is None:
            data['context'] = {}
        return cls(**data)
    
    def update_timestamp(self):
        """更新时间戳"""
        self.updated_at = datetime.now().isoformat()


class TaskPersistenceManager:
    """任务持久化管理器"""
    
    def __init__(self, db_path: str = "/app/db/tasks.json"):
        """
        初始化持久化管理器
        
        Args:
            db_path: 任务数据库路径（JSON 文件）
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.tasks: Dict[str, PersistedTask] = {}
        self.lock = asyncio.Lock()
        
        # 加载现有任务
        self._load_tasks()
        
        logger.info(f"✅ 任务持久化管理器已初始化 | 数据库：{self.db_path}")
    
    def _load_tasks(self):
        """从文件加载任务"""
        if not self.db_path.exists():
            logger.info("📝 任务数据库不存在，将创建新文件")
            self._save_tasks_unlocked()
            return
        
        try:
            with open(self.db_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.tasks = {}
            for task_id, task_data in data.get('tasks', {}).items():
                try:
                    self.tasks[task_id] = PersistedTask.from_dict(task_data)
                except Exception as e:
                    logger.warning(f"⚠️ 加载任务 {task_id} 失败：{e}")
            
            # 恢复未完成的任务状态
            self._recover_active_tasks()
            
            logger.info(f"📥 加载了 {len(self.tasks)} 个任务")
        except Exception as e:
            logger.error(f"❌ 加载任务数据库失败：{e}")
            self.tasks = {}
    
    def _save_tasks_unlocked(self):
        """保存任务到文件（不获取锁）"""
        try:
            data = {
                'version': 1,
                'updated_at': datetime.now().isoformat(),
                'tasks': {tid: t.to_dict() for tid, t in self.tasks.items()}
            }
            
            # 原子写入（先写临时文件，再重命名）
            temp_path = self.db_path.with_suffix('.tmp')
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            temp_path.replace(self.db_path)
            logger.debug(f"💾 已保存 {len(self.tasks)} 个任务")
        except Exception as e:
            logger.error(f"❌ 保存任务数据库失败：{e}")
    
    async def save_task(self, task: PersistedTask):
        """保存单个任务"""
        async with self.lock:
            task.update_timestamp()
            self.tasks[task.task_id] = task
            self._save_tasks_unlocked()
    
    async def get_task(self, task_id: str) -> Optional[PersistedTask]:
        """获取任务"""
        async with self.lock:
            return self.tasks.get(task_id)
    
    async def create_task(
        self,
        task_id: str,
        url: str,
        title: str = "",
        source: str = "telegram",
        chat_id: Optional[int] = None,
        message_id: Optional[int] = None,
        user_id: Optional[int] = None,
        context: Optional[Dict] = None,
    ) -> PersistedTask:
        """创建新任务"""
        async with self.lock:
            task = PersistedTask(
                task_id=task_id,
                url=url,
                title=title,
                source=source,
                chat_id=chat_id,
                message_id=message_id,
                user_id=user_id,
                context=context or {},
            )
            self.tasks[task_id] = task
            self._save_tasks_unlocked()
            logger.info(f"📝 创建任务：{task_id}")
            return task
    
    async def update_status(
        self,
        task_id: str,
        status: TaskPersistStatus,
        error_message: str = "",
    ):
        """更新任务状态"""
        async with self.lock:
            if task_id not in self.tasks:
                logger.warning(f"⚠️ 任务不存在：{task_id}")
                return
            
            task = self.tasks[task_id]
            task.status = status
            task.error_message = error_message
            
            if status == TaskPersistStatus.COMPLETED:
                task.completed_at = datetime.now().isoformat()
                task.progress = 100.0
            elif status == TaskPersistStatus.PAUSED:
                task.paused_at = datetime.now().isoformat()
            elif status == TaskPersistStatus.ERROR:
                task.retry_count += 1
            
            task.update_timestamp()
            self._save_tasks_unlocked()
    
    async def update_progress(
        self,
        task_id: str,
        progress: float,
        downloaded_bytes: int = 0,
        total_bytes: int = 0,
    ):
        """更新任务进度"""
        async with self.lock:
            if task_id not in self.tasks:
                return
            
            task = self.tasks[task_id]
            task.progress = progress
            task.downloaded_bytes = downloaded_bytes
            task.total_bytes = total_bytes
            task.update_timestamp()
            self._save_tasks_unlocked()
    
    async def pause_task(self, task_id: str) -> bool:
        """暂停任务"""
        async with self.lock:
            if task_id not in self.tasks:
                return False
            
            task = self.tasks[task_id]
            if task.status not in (TaskPersistStatus.DOWNLOADING, TaskPersistStatus.PENDING):
                return False
            
            task.status = TaskPersistStatus.PAUSED
            task.paused_at = datetime.now().isoformat()
            task.update_timestamp()
            self._save_tasks_unlocked()
            logger.info(f"⏸️ 任务已暂停：{task_id}")
            return True
    
    async def resume_task(self, task_id: str) -> bool:
        """恢复任务"""
        async with self.lock:
            if task_id not in self.tasks:
                return False
            
            task = self.tasks[task_id]
            if task.status != TaskPersistStatus.PAUSED:
                return False
            
            task.status = TaskPersistStatus.PENDING
            task.paused_at = None
            task.update_timestamp()
            self._save_tasks_unlocked()
            logger.info(f"▶️ 任务已恢复：{task_id}")
            return True
    
    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        async with self.lock:
            if task_id not in self.tasks:
                return False
            
            task = self.tasks[task_id]
            task.status = TaskPersistStatus.CANCELLED
            task.completed_at = datetime.now().isoformat()
            task.update_timestamp()
            self._save_tasks_unlocked()
            logger.info(f"⏹️ 任务已取消：{task_id}")
            return True
    
    async def get_active_tasks(self) -> List[PersistedTask]:
        """获取活跃任务（未完成、未取消）"""
        async with self.lock:
            return [
                t for t in self.tasks.values()
                if t.status not in (
                    TaskPersistStatus.COMPLETED,
                    TaskPersistStatus.CANCELLED,
                    TaskPersistStatus.FAILED,
                )
            ]
    
    async def get_paused_tasks(self) -> List[PersistedTask]:
        """获取已暂停任务"""
        async with self.lock:
            return [
                t for t in self.tasks.values()
                if t.status == TaskPersistStatus.PAUSED
            ]
    
    async def get_error_tasks(self) -> List[PersistedTask]:
        """获取错误任务（可重试）"""
        async with self.lock:
            return [
                t for t in self.tasks.values()
                if t.status == TaskPersistStatus.ERROR
                and t.retry_count < t.max_retries
            ]
    
    def _recover_active_tasks(self):
        """恢复活跃任务状态"""
        recovered = 0
        for task in self.tasks.values():
            if task.status == TaskPersistStatus.DOWNLOADING:
                # 下载中的任务改为错误状态（因为程序重启了）
                task.status = TaskPersistStatus.ERROR
                task.error_message = "程序重启，任务中断"
                recovered += 1
                logger.info(f"🔄 恢复任务：{task.task_id} (状态：{task.status.value})")
        
        if recovered > 0:
            logger.info(f"✅ 恢复了 {recovered} 个中断的任务")
            self._save_tasks_unlocked()
    
    async def cleanup_completed(self, days: int = 7) -> int:
        """清理完成的旧任务"""
        async with self.lock:
            cutoff = datetime.now().timestamp() - (days * 24 * 3600)
            to_remove = []
            
            for task_id, task in self.tasks.items():
                if task.status in (TaskPersistStatus.COMPLETED, TaskPersistStatus.CANCELLED, TaskPersistStatus.FAILED):
                    if task.completed_at:
                        try:
                            completed_time = datetime.fromisoformat(task.completed_at).timestamp()
                            if completed_time < cutoff:
                                to_remove.append(task_id)
                        except Exception:
                            pass
            
            for task_id in to_remove:
                del self.tasks[task_id]
            
            if to_remove:
                self._save_tasks_unlocked()
                logger.info(f"🧹 清理了 {len(to_remove)} 个旧任务")
            
            return len(to_remove)


# 全局实例
_persistence_manager: Optional[TaskPersistenceManager] = None


def get_persistence_manager(db_path: str = "/app/db/tasks.json") -> TaskPersistenceManager:
    """获取持久化管理器实例"""
    global _persistence_manager
    if _persistence_manager is None:
        _persistence_manager = TaskPersistenceManager(db_path)
    return _persistence_manager


def init_persistence(db_path: str = "/app/db/tasks.json") -> TaskPersistenceManager:
    """初始化持久化管理器"""
    global _persistence_manager
    _persistence_manager = TaskPersistenceManager(db_path)
    return _persistence_manager
