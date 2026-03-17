# -*- coding: utf-8 -*-
"""
错误熔断和任务缓存模块
当连续失败超过阈值时，暂停所有任务，等待用户确认
"""

import json
import logging
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger('savextube.error_circuit')


class CircuitState(str, Enum):
    """熔断器状态"""
    CLOSED = "closed"  # 正常状态
    OPEN = "open"  # 熔断打开，暂停所有任务
    HALF_OPEN = "half_open"  # 半开状态，等待用户确认


@dataclass
class CachedTask:
    """缓存的任务数据"""
    task_id: str
    url: str
    title: str
    status: str
    progress: float
    error_message: str
    retry_count: int
    created_at: str
    cached_at: str
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'CachedTask':
        return cls(**data)


@dataclass
class CircuitBreakerState:
    """熔断器状态数据"""
    state: CircuitState = CircuitState.CLOSED
    triggered_at: Optional[str] = None
    triggered_by: Optional[str] = None  # 触发熔断的任务 ID
    total_failed: int = 0
    total_cached: int = 0
    user_notified: bool = False
    user_confirmed: bool = False
    confirmed_at: Optional[str] = None
    
    def to_dict(self) -> Dict:
        data = asdict(self)
        data['state'] = self.state.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'CircuitBreakerState':
        data = data.copy()
        if 'state' in data:
            data['state'] = CircuitState(data['state'])
        return cls(**data)


class ErrorCircuitBreaker:
    """错误熔断器"""
    
    def __init__(self, cache_path: str = "/app/db/circuit_cache.json"):
        """
        初始化熔断器
        
        Args:
            cache_path: 缓存文件路径
        """
        self.cache_path = Path(cache_path)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.state = CircuitBreakerState()
        self.cached_tasks: Dict[str, CachedTask] = {}
        self.paused_tasks: List[str] = []  # 暂停的任务 ID 列表
        
        # 配置
        self.max_retries = 5  # 最大重试次数
        self.continuous_error_threshold = 3  # 连续错误阈值（触发熔断）
        self.continuous_errors = 0  # 当前连续错误计数
        
        # 加载缓存
        self._load_cache()
        
        logger.info(f"✅ 错误熔断器已初始化 | 缓存：{self.cache_path}")
    
    def _load_cache(self):
        """加载缓存"""
        if not self.cache_path.exists():
            logger.info("📝 熔断缓存不存在，将创建新文件")
            self._save_cache()
            return
        
        try:
            with open(self.cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.state = CircuitBreakerState.from_dict(data.get('state', {}))
            self.cached_tasks = {
                tid: CachedTask.from_dict(t)
                for tid, t in data.get('cached_tasks', {}).items()
            }
            self.paused_tasks = data.get('paused_tasks', [])
            
            logger.info(f"📥 加载了 {len(self.cached_tasks)} 个缓存任务")
        except Exception as e:
            logger.error(f"❌ 加载缓存失败：{e}")
            self.state = CircuitBreakerState()
            self.cached_tasks = {}
            self.paused_tasks = []
    
    def _save_cache(self):
        """保存缓存"""
        try:
            data = {
                'version': 1,
                'updated_at': datetime.now().isoformat(),
                'state': self.state.to_dict(),
                'cached_tasks': {tid: t.to_dict() for tid, t in self.cached_tasks.items()},
                'paused_tasks': self.paused_tasks,
            }
            
            # 原子写入
            temp_path = self.cache_path.with_suffix('.tmp')
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            temp_path.replace(self.cache_path)
            
            logger.debug(f"💾 已保存熔断缓存")
        except Exception as e:
            logger.error(f"❌ 保存缓存失败：{e}")
    
    def record_error(self, task_id: str, url: str, title: str, error_message: str, retry_count: int) -> bool:
        """
        记录错误，检查是否需要触发熔断
        
        Args:
            task_id: 任务 ID
            url: 任务 URL
            title: 任务标题
            error_message: 错误信息
            retry_count: 当前重试次数
            
        Returns:
            是否触发了熔断
        """
        # 更新连续错误计数
        self.continuous_errors += 1
        
        # 检查是否超过最大重试次数
        if retry_count >= self.max_retries:
            logger.warning(f"⚠️ 任务 {task_id} 超过最大重试次数")
            
            # 缓存任务
            self._cache_task(task_id, url, title, error_message, retry_count)
            
            # 检查是否需要触发熔断
            if self.continuous_errors >= self.continuous_error_threshold:
                logger.error(f"🚨 连续错误 {self.continuous_errors} 次，触发熔断！")
                self._trigger_circuit(task_id)
                return True
        
        self._save_cache()
        return False
    
    def record_success(self):
        """记录成功，重置连续错误计数"""
        self.continuous_errors = 0
        logger.debug("✅ 下载成功，重置连续错误计数")
    
    def _cache_task(self, task_id: str, url: str, title: str, error_message: str, retry_count: int):
        """缓存失败的任务"""
        cached = CachedTask(
            task_id=task_id,
            url=url,
            title=title,
            status="cached",
            progress=0,
            error_message=error_message,
            retry_count=retry_count,
            created_at=datetime.now().isoformat(),
            cached_at=datetime.now().isoformat(),
        )
        self.cached_tasks[task_id] = cached
        logger.info(f"📦 缓存任务：{task_id}")
    
    def _trigger_circuit(self, triggered_by: str):
        """触发熔断"""
        self.state.state = CircuitState.OPEN
        self.state.triggered_at = datetime.now().isoformat()
        self.state.triggered_by = triggered_by
        self.state.total_failed = len(self.cached_tasks)
        self.state.total_cached = len(self.cached_tasks)
        
        # 标记需要通知用户
        self.state.user_notified = False
        self.state.user_confirmed = False
        
        logger.error(f"🚨 熔断器已打开！触发任务：{triggered_by}")
        self._save_cache()
    
    def pause_all_tasks(self, task_ids: List[str]):
        """暂停所有任务"""
        self.paused_tasks = task_ids
        logger.info(f"⏸️ 已暂停 {len(task_ids)} 个任务")
        self._save_cache()
    
    def get_circuit_state(self) -> Dict:
        """获取熔断器状态"""
        return {
            'state': self.state.state.value,
            'triggered_at': self.state.triggered_at,
            'triggered_by': self.state.triggered_by,
            'total_failed': self.state.total_failed,
            'total_cached': self.state.total_cached,
            'user_notified': self.state.user_notified,
            'user_confirmed': self.state.user_confirmed,
            'continuous_errors': self.continuous_errors,
            'cached_tasks': [t.to_dict() for t in self.cached_tasks.values()],
        }
    
    def mark_user_notified(self):
        """标记用户已通知"""
        self.state.user_notified = True
        self._save_cache()
    
    def confirm_recovery(self) -> bool:
        """
        用户确认恢复
        
        Returns:
            是否成功确认
        """
        if self.state.state != CircuitState.OPEN:
            return False
        
        self.state.state = CircuitState.HALF_OPEN
        self.state.user_confirmed = True
        self.state.confirmed_at = datetime.now().isoformat()
        
        logger.info("✅ 用户确认恢复，熔断器进入半开状态")
        self._save_cache()
        return True
    
    def reset_circuit(self):
        """重置熔断器"""
        self.state = CircuitBreakerState()
        self.cached_tasks = {}
        self.paused_tasks = []
        self.continuous_errors = 0
        
        logger.info("🔄 熔断器已重置")
        self._save_cache()
    
    def get_cached_tasks(self) -> List[CachedTask]:
        """获取缓存的任务列表"""
        return list(self.cached_tasks.values())
    
    def get_paused_tasks(self) -> List[str]:
        """获取暂停的任务 ID 列表"""
        return self.paused_tasks.copy()
    
    def clear_cache(self):
        """清除缓存"""
        self.cached_tasks = {}
        self.paused_tasks = []
        self._save_cache()
        logger.info("🧹 缓存已清除")
    
    def is_circuit_open(self) -> bool:
        """检查熔断器是否打开"""
        return self.state.state == CircuitState.OPEN
    
    def is_user_confirmed(self) -> bool:
        """检查用户是否已确认"""
        return self.state.user_confirmed


# 全局实例
_circuit_breaker: Optional[ErrorCircuitBreaker] = None


def get_circuit_breaker(cache_path: str = "/app/db/circuit_cache.json") -> ErrorCircuitBreaker:
    """获取熔断器实例"""
    global _circuit_breaker
    if _circuit_breaker is None:
        _circuit_breaker = ErrorCircuitBreaker(cache_path)
    return _circuit_breaker


def init_circuit_breaker(cache_path: str = "/app/db/circuit_cache.json") -> ErrorCircuitBreaker:
    """初始化熔断器"""
    global _circuit_breaker
    _circuit_breaker = ErrorCircuitBreaker(cache_path)
    return _circuit_breaker
