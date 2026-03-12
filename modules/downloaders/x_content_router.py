# -*- coding: utf-8 -*-
"""X 内容下载路由器。"""

from modules.downloaders.message_updater_factory import build_reply_message_updater


async def route_x_content_download(downloader, *, url, message, logger):
    """按内容类型路由 X 下载逻辑。"""
    logger.info(f"🚀 开始下载 X 内容: {url}")

    content_type = downloader._detect_x_content_type(url)
    logger.info(f"📊 检测到内容类型: {content_type}")

    if content_type == "video":
        logger.info("🎬 使用 yt-dlp 下载 X 视频")
        message_updater = build_reply_message_updater(message, logger)
        return await downloader._download_x_video_with_ytdlp(url, message_updater)

    logger.info("📸 使用 gallery-dl 下载 X 图片")
    return await downloader._download_x_image_with_gallerydl(url, message)
