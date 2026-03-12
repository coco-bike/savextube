# -*- coding: utf-8 -*-
"""音乐平台下载路由辅助。"""

import os


async def route_music_download(
    downloader,
    *,
    url: str,
    download_path,
    message_updater=None,
    status_message=None,
    context=None,
    detection,
    logger,
):
    """路由处理音乐平台分支，未命中时返回 handled=False。"""
    is_netease = detection.get("is_netease", False)

    if is_netease:
        logger.info("🎵 检测到网易云音乐链接，使用网易云音乐下载器")
        return {
            "handled": True,
            "result": await downloader._download_netease_music(
                url,
                download_path,
                message_updater,
                status_message,
                context,
            ),
        }

    if downloader.is_qqmusic_url(url):
        logger.info("🎵 检测到QQ音乐链接，使用QQ音乐下载器")
        return {
            "handled": True,
            "result": await downloader._download_qqmusic_music(
                url,
                download_path,
                message_updater,
                status_message,
                context,
            ),
        }

    if downloader.is_youtube_music_url(url):
        logger.info("🎵 检测到YouTube Music链接，使用YouTube Music下载器")
        return {
            "handled": True,
            "result": await downloader._download_youtubemusic_music(
                url,
                download_path,
                message_updater,
                status_message,
                context,
            ),
        }

    if downloader.is_apple_music_url(url):
        use_amd = os.environ.get("AMDP", "false").lower() == "true"
        if use_amd:
            logger.info("🍎 检测到 Apple Music 链接，使用 Apple Music Plus 下载器 (AMD)")
        else:
            logger.info("🍎 检测到 Apple Music 链接，使用 Apple Music 下载器 (GAMDL)")
        return {
            "handled": True,
            "result": await downloader._download_apple_music(
                url,
                download_path,
                message_updater,
                status_message,
                context,
            ),
        }

    return {"handled": False}
