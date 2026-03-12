# -*- coding: utf-8 -*-
"""单视频下载选项增强与 Instagram 专用处理。"""

import asyncio
import os
from pathlib import Path


def enrich_single_video_ydl_options(downloader, *, url: str, ydl_opts: dict, logger):
    """在基础 ydl 配置上叠加平台相关的增强选项。"""
    if (
        downloader.is_youtube_url(url)
        and hasattr(downloader, "bot")
        and hasattr(downloader.bot, "youtube_audio_mode")
        and downloader.bot.youtube_audio_mode
    ):
        ydl_opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "320",
            }
        ]
        logger.info("🎵 添加音频转换后处理器：转换为320kbps MP3")

    if (
        downloader.is_youtube_url(url)
        and hasattr(downloader, "bot")
        and hasattr(downloader.bot, "youtube_thumbnail_download")
        and downloader.bot.youtube_thumbnail_download
    ):
        ydl_opts["writethumbnail"] = True
        if "postprocessors" not in ydl_opts:
            ydl_opts["postprocessors"] = []
        ydl_opts["postprocessors"].append(
            {
                "key": "FFmpegThumbnailsConvertor",
                "format": "jpg",
                "when": "before_dl",
            }
        )
        logger.info("🖼️ 开启YouTube封面下载（转换为JPG格式）")

    if (
        downloader.is_youtube_url(url)
        and hasattr(downloader, "bot")
        and hasattr(downloader.bot, "youtube_subtitle_download")
        and downloader.bot.youtube_subtitle_download
    ):
        ydl_opts["writeautomaticsub"] = True
        ydl_opts["writesubtitles"] = True
        ydl_opts["subtitleslangs"] = ["zh", "en"]
        ydl_opts["convertsubtitles"] = "srt"
        ydl_opts["subtitlesformat"] = "best[ext=srt]/srt/best"
        logger.info("📝 开启YouTube字幕下载（中文、英文，SRT格式）")

    if (
        downloader.is_bilibili_url(url)
        and hasattr(downloader, "bot")
        and hasattr(downloader.bot, "bilibili_thumbnail_download")
        and downloader.bot.bilibili_thumbnail_download
    ):
        ydl_opts["writethumbnail"] = True
        if "postprocessors" not in ydl_opts:
            ydl_opts["postprocessors"] = []
        ydl_opts["postprocessors"].append(
            {
                "key": "FFmpegThumbnailsConvertor",
                "format": "jpg",
                "when": "before_dl",
            }
        )
        logger.info("🖼️ 通用下载器开启B站封面下载（转换为JPG格式）")

    if downloader.is_x_url(url) and downloader.x_cookies_path and os.path.exists(downloader.x_cookies_path):
        ydl_opts["cookiefile"] = downloader.x_cookies_path
        logger.info(f"🍪 为X链接添加cookies: {downloader.x_cookies_path}")
    elif downloader.is_x_url(url):
        logger.warning("⚠️ 检测到X链接但未设置cookies文件")
        logger.warning("⚠️ NSFW内容需要登录才能下载")
        if downloader.x_cookies_path:
            logger.warning(f"⚠️ X cookies文件不存在: {downloader.x_cookies_path}")
        else:
            logger.warning("⚠️ 未设置X_COOKIES环境变量")
        logger.warning("💡 请设置X_COOKIES环境变量指向cookies文件路径")

    if (
        downloader.is_youtube_url(url)
        and downloader.youtube_cookies_path
        and os.path.exists(downloader.youtube_cookies_path)
    ):
        ydl_opts["cookiefile"] = downloader.youtube_cookies_path
        logger.info(f"🍪 为YouTube链接添加cookies: {downloader.youtube_cookies_path}")

    if (
        downloader.is_bilibili_url(url)
        and downloader.b_cookies_path
        and os.path.exists(downloader.b_cookies_path)
    ):
        ydl_opts["cookiefile"] = downloader.b_cookies_path
        logger.info(f"🍪 为B站链接添加cookies: {downloader.b_cookies_path}")

    if (
        downloader.is_douyin_url(url)
        and downloader.douyin_cookies_path
        and os.path.exists(downloader.douyin_cookies_path)
    ):
        ydl_opts["cookiefile"] = downloader.douyin_cookies_path
        logger.info(f"🍪 为抖音链接添加cookies: {downloader.douyin_cookies_path}")
    elif downloader.is_douyin_url(url):
        logger.warning("⚠️ 检测到抖音链接但未设置cookies文件")
        if downloader.douyin_cookies_path:
            logger.warning(f"⚠️ 抖音cookies文件不存在: {downloader.douyin_cookies_path}")
        else:
            logger.warning("⚠️ 未设置DOUYIN_COOKIES环境变量")

    if "instagram.com" in url.lower():
        if (
            hasattr(downloader, "instagram_cookies_path")
            and downloader.instagram_cookies_path
            and os.path.exists(downloader.instagram_cookies_path)
        ):
            ydl_opts["cookiefile"] = downloader.instagram_cookies_path
            logger.info(f"🍪 为Instagram链接应用cookies: {downloader.instagram_cookies_path}")
        else:
            logger.warning("⚠️ Instagram链接：cookies未配置或文件不存在")

    if downloader.proxy_host:
        ydl_opts["proxy"] = downloader.proxy_host

    return downloader._add_danmaku_options(ydl_opts, url)


async def try_instagram_special_download(
    downloader,
    *,
    url: str,
    download_path,
    title: str,
    message_updater=None,
    logger,
):
    """尝试使用专门的 Instagram 下载器，成功则直接返回。"""
    if "instagram.com" not in url.lower():
        return {"handled": False, "result": None}

    if not (hasattr(downloader, "instagram_downloader") and downloader.instagram_downloader):
        return {"handled": False, "result": None}

    logger.info("📱 使用专门的 Instagram 下载器处理")
    try:
        async def instagram_progress_callback(text):
            if not message_updater:
                return
            try:
                if asyncio.iscoroutinefunction(message_updater):
                    await message_updater(text)
                else:
                    message_updater(text)
            except Exception as e:
                logger.warning(f"Instagram 进度回调失败: {e}")

        result = await downloader.instagram_downloader.download_post(
            url,
            str(download_path),
            instagram_progress_callback,
        )

        if result.get("success"):
            logger.info(f"✅ Instagram 下载成功: {result}")
            files = result.get("files", [])
            if files:
                main_file = files[0]
                file_path = Path(main_file.get("path", ""))
                if file_path.exists():
                    return {
                        "handled": True,
                        "result": {
                            "success": True,
                            "file_path": str(file_path),
                            "title": title,
                            "platform": "instagram",
                            "files": files,
                            "total_size": result.get("total_size", 0),
                            "files_count": result.get("files_count", 0),
                        },
                    }

            return {
                "handled": True,
                "result": {
                    "success": True,
                    "platform": "instagram",
                    "message": "Instagram 内容下载完成",
                    "result": result,
                },
            }

        logger.warning(f"⚠️ Instagram 下载器失败，回退到 yt-dlp: {result.get('error')}")
        return {"handled": False, "result": None}
    except Exception as e:
        logger.error(f"❌ Instagram 下载器异常，回退到 yt-dlp: {e}")
        return {"handled": False, "result": None}
