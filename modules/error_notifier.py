# -*- coding: utf-8 -*-
"""
下载错误通知模块
通过 Telegram 机器人发送错误通知给用户
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger('savextube.error_notify')


class ErrorNotifier:
    """错误通知器"""
    
    def __init__(self, bot_instance):
        """
        初始化通知器
        
        Args:
            bot_instance: TelegramBot 实例
        """
        self.bot = bot_instance
        self.notified_users: set = set()  # 已通知的用户 ID
        self.last_notify_time: Dict[int, float] = {}  # 每个用户最后通知时间
    
    async def notify_circuit_break(
        self,
        user_id: int,
        cached_tasks: List[Dict],
        continuous_errors: int,
    ):
        """
        通知用户熔断器已触发
        
        Args:
            user_id: 用户 ID
            cached_tasks: 缓存的任务列表
            continuous_errors: 连续错误次数
        """
        try:
            # 构建通知消息
            message = self._build_circuit_break_message(cached_tasks, continuous_errors)
            
            # 发送消息
            if self.bot and hasattr(self.bot, 'application') and self.bot.application:
                await self.bot.application.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode="HTML",
                )
                self.notified_users.add(user_id)
                self.last_notify_time[user_id] = datetime.now().timestamp()
                
                logger.info(f"📬 已发送熔断通知给用户 {user_id}")
            else:
                logger.warning("⚠️ Bot 未初始化，无法发送通知")
                
        except Exception as e:
            logger.error(f"❌ 发送通知失败：{e}")
    
    def _build_circuit_break_message(
        self,
        cached_tasks: List[Dict],
        continuous_errors: int,
    ) -> str:
        """构建熔断通知消息"""
        
        # 任务列表摘要（最多显示 5 个）
        tasks_summary = ""
        for i, task in enumerate(cached_tasks[:5], 1):
            title = task.get('title', '未知任务')[:30]
            error = task.get('error_message', '未知错误')[:40]
            tasks_summary += f"\n  {i}. <code>{title}</code>"
            tasks_summary += f"\n     ❌ {error}"
        
        if len(cached_tasks) > 5:
            tasks_summary += f"\n  ... 还有 {len(cached_tasks) - 5} 个任务"
        
        message = f"""
🚨 <b>下载错误通知</b>

检测到连续 <b>{continuous_errors}</b> 次下载失败，系统已自动暂停所有下载任务。

<b>📦 缓存的任务 ({len(cached_tasks)} 个):</b>{tasks_summary}

<b>⚠️ 可能原因:</b>
  • 网络连接问题
  • 目标网站限制
  • 代理配置错误
  • 资源已失效

<b>🔧 请检查:</b>
  1. 网络连接是否正常
  2. 代理配置是否正确
  3. Cookies 是否过期

<b>✅ 确认后请发送命令:</b>
  <code>/resume</code> - 恢复所有缓存任务
  <code>/clear_cache</code> - 清除缓存并重置

<b>📊 查看缓存状态:</b>
  <code>/cache_status</code> - 查看缓存任务详情
"""
        return message.strip()
    
    async def send_recovery_confirmation(self, user_id: int):
        """发送恢复确认消息"""
        message = """
✅ <b>恢复确认</b>

系统已准备恢复缓存的下载任务。

请发送 <code>/resume</code> 开始恢复下载。
"""
        try:
            if self.bot and hasattr(self.bot, 'application') and self.bot.application:
                await self.bot.application.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode="HTML",
                )
        except Exception as e:
            logger.error(f"❌ 发送恢复确认失败：{e}")
    
    async def send_cache_status(self, user_id: int, cached_tasks: List[Dict], circuit_state: str):
        """发送缓存状态"""
        # 构建状态消息
        tasks_list = ""
        for i, task in enumerate(cached_tasks[:10], 1):
            title = task.get('title', '未知任务')[:25]
            error = task.get('error_message', '未知错误')[:30]
            tasks_list += f"\n  {i}. {title}"
            tasks_list += f"\n     ❌ {error}"
        
        if len(cached_tasks) > 10:
            tasks_list += f"\n  ... 还有 {len(cached_tasks) - 10} 个任务"
        
        message = f"""
📊 <b>缓存状态</b>

<b>熔断器状态:</b> {circuit_state}
<b>缓存任务数:</b> {len(cached_tasks)}

<b>📦 缓存任务列表:</b>{tasks_list}

<b>操作命令:</b>
  <code>/resume</code> - 恢复所有任务
  <code>/clear_cache</code> - 清除缓存
"""
        try:
            if self.bot and hasattr(self.bot, 'application') and self.bot.application:
                await self.bot.application.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode="HTML",
                )
        except Exception as e:
            logger.error(f"❌ 发送状态失败：{e}")
    
    async def send_resume_result(self, user_id: int, success_count: int, fail_count: int = 0):
        """发送恢复结果"""
        message = f"""
✅ <b>任务恢复完成</b>

成功恢复：<b>{success_count}</b> 个任务
恢复失败：<b>{fail_count}</b> 个任务

下载将继续进行，请留意后续进度通知。
"""
        try:
            if self.bot and hasattr(self.bot, 'application') and self.bot.application:
                await self.bot.application.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode="HTML",
                )
        except Exception as e:
            logger.error(f"❌ 发送恢复结果失败：{e}")
    
    async def send_clear_cache_result(self, user_id: int, cleared_count: int):
        """发送清除缓存结果"""
        message = f"""
🧹 <b>缓存已清除</b>

已清除 <b>{cleared_count}</b> 个缓存任务。

系统已重置，可以正常下载新任务。
"""
        try:
            if self.bot and hasattr(self.bot, 'application') and self.bot.application:
                await self.bot.application.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode="HTML",
                )
        except Exception as e:
            logger.error(f"❌ 发送清除结果失败：{e}")
    
    def is_notified(self, user_id: int) -> bool:
        """检查用户是否已通知"""
        return user_id in self.notified_users
    
    def reset_notifications(self):
        """重置通知状态"""
        self.notified_users.clear()
        self.last_notify_time.clear()


# 全局实例
_notifier: Optional[ErrorNotifier] = None


def get_error_notifier(bot_instance=None) -> ErrorNotifier:
    """获取通知器实例"""
    global _notifier
    if _notifier is None:
        if bot_instance is None:
            raise ValueError("首次调用需要提供 bot_instance")
        _notifier = ErrorNotifier(bot_instance)
    return _notifier


def init_error_notifier(bot_instance) -> ErrorNotifier:
    """初始化通知器"""
    global _notifier
    _notifier = ErrorNotifier(bot_instance)
    return _notifier
