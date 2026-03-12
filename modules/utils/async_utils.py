# -*- coding: utf-8 -*-
"""异步工具函数。"""

import asyncio
from typing import Optional


def get_preferred_event_loop() -> asyncio.AbstractEventLoop:
    """获取可用事件循环，不可用时创建新循环。"""
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        try:
            return asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop


def run_coroutine_threadsafe(coro, loop: Optional[asyncio.AbstractEventLoop] = None):
    """在线程安全模式下调度协程。"""
    target_loop = loop or get_preferred_event_loop()
    return asyncio.run_coroutine_threadsafe(coro, target_loop)


def edit_message_threadsafe(message, text: str, parse_mode=None, logger=None, warn_prefix: str = "更新消息失败"):
    """线程安全地更新 Telegram 消息文本。"""

    async def _do_update():
        try:
            await message.edit_text(text, parse_mode=parse_mode)
        except Exception as e:
            if logger and "Message is not modified" not in str(e):
                logger.warning(f"{warn_prefix}: {e}")

    return run_coroutine_threadsafe(_do_update())
