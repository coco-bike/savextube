# -*- coding: utf-8 -*-
"""社交媒体下载路由辅助。"""

from typing import Any, Dict

from modules.downloaders.xiaohongshu_router import route_xiaohongshu_download


class _MockMessage:
    def __init__(self, chat_id: int = 0):
        self.chat_id = chat_id
        self.message_id = 0


async def route_social_download(
    downloader,
    *,
    url: str,
    download_path,
    message_updater=None,
    status_message=None,
    context=None,
    detection: Dict[str, Any],
    logger,
) -> Dict[str, Any]:
    """路由处理社交媒体分支，未命中时返回 handled=False。"""
    if detection.get("is_x"):
        is_x_playlist, playlist_info = downloader.is_x_playlist_url(url)
        if is_x_playlist:
            logger.info(f"🎬 检测到X多集视频，共{playlist_info['total_videos']}个视频")
            return {
                "handled": True,
                "result": await downloader._download_x_playlist(
                    url,
                    download_path,
                    message_updater,
                    playlist_info,
                ),
            }

        logger.info("🔍 检测到X链接，开始检测内容类型...")
        content_type = downloader._detect_x_content_type(url)
        logger.info(f"📊 检测到内容类型: {content_type}")
        if content_type == "video":
            logger.info("🎬 X 视频使用统一的单视频下载函数")
            return {
                "handled": True,
                "result": await downloader._download_single_video(
                    url,
                    download_path,
                    message_updater,
                    status_message=status_message,
                    context=context,
                ),
            }

        logger.info("📸 X 图片使用 gallery-dl 下载")
        return {
            "handled": True,
            "result": await downloader.download_with_gallery_dl(url, download_path, message_updater),
        }

    if detection.get("is_telegraph"):
        logger.info("📸 检测到Telegraph链接，使用 gallery-dl 下载")
        return {
            "handled": True,
            "result": await downloader.download_with_gallery_dl(url, download_path, message_updater),
        }

    if detection.get("is_douyin"):
        logger.info("🎬 检测到抖音链接，使用Playwright方法下载")
        return {
            "handled": True,
            "result": await downloader._download_douyin_with_playwright(
                url,
                _MockMessage(),
                message_updater,
            ),
        }

    if detection.get("is_kuaishou"):
        logger.info("⚡ 检测到快手链接，使用Playwright方法下载")
        return {
            "handled": True,
            "result": await downloader._download_kuaishou_with_playwright(
                url,
                _MockMessage(),
                message_updater,
            ),
        }

    if detection.get("is_facebook"):
        logger.info("📘 检测到Facebook链接，使用yt-dlp方法下载")
        return {
            "handled": True,
            "result": await downloader._download_single_video(
                url,
                download_path,
                message_updater,
                status_message=status_message,
                context=context,
            ),
        }

    if downloader.is_xiaohongshu_url(url):
        return {
            "handled": True,
            "result": await route_xiaohongshu_download(
                downloader,
                url=url,
                message=_MockMessage(),
                message_updater=message_updater,
                logger=logger,
            ),
        }

    return {"handled": False}
