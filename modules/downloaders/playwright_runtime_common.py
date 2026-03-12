# -*- coding: utf-8 -*-
"""Playwright 下载运行时通用辅助。"""


def build_playwright_unavailable_result(platform_name_cn: str, platform_name_en: str):
    """构建 Playwright 未安装错误返回。"""
    return {
        "success": False,
        "error": f"Playwright 未安装，无法下载{platform_name_cn}视频",
        "platform": platform_name_en,
        "content_type": "video",
    }


def build_playwright_download_error_result(platform_name_en: str, error_message: str):
    """构建 Playwright 下载失败返回。"""
    return {
        "success": False,
        "error": error_message,
        "platform": platform_name_en,
        "content_type": "video",
    }


async def safe_delete_start_message(downloader, *, message, start_message, logger):
    """安全删除启动消息。"""
    if not start_message:
        return

    if hasattr(start_message, "delete"):
        try:
            await start_message.delete()
            return
        except Exception as e:
            logger.warning(f"⚠️ 删除开始消息失败: {e}")

    if (
        hasattr(downloader, "bot")
        and downloader.bot
        and message
        and hasattr(message, "chat")
        and hasattr(message.chat, "id")
        and hasattr(start_message, "message_id")
    ):
        try:
            await downloader.bot.delete_message(message.chat.id, start_message.message_id)
        except Exception as e:
            logger.warning(f"⚠️ 删除开始消息失败: {e}")
