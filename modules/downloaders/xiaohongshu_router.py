# -*- coding: utf-8 -*-
"""小红书内容下载路由。"""


async def route_xiaohongshu_download(
    downloader,
    *,
    url,
    message,
    message_updater,
    logger,
):
    """按内容类型路由小红书下载。"""
    logger.info("📖 检测到小红书链接")
    content_type = await downloader._detect_xiaohongshu_content_type(url)
    logger.info(f"📊 小红书内容类型: {content_type}")

    if content_type == "image":
        logger.info("🖼️ 检测到小红书图片，使用xiaohongshu_downloader方法下载")
        return await downloader._download_xiaohongshu_image_with_downloader(url, message_updater)

    logger.info("🎬 检测到小红书视频，使用Playwright方法下载")
    return await downloader._download_xiaohongshu_with_playwright(url, message, message_updater)
