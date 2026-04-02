# -*- coding: utf-8 -*-
"""单视频下载前置校验与元信息准备。"""

import asyncio
import os
import time


def validate_single_video_url(downloader, *, url: str, logger):
    """校验不应走单视频下载的音乐链接，命中时返回错误结果。"""
    if downloader.is_netease_url(url):
        logger.error(f"❌ 网易云音乐链接不应该调用_download_single_video函数: {url}")
        return {
            "success": False,
            "error": "网易云音乐链接不应该调用单视频下载函数",
            "platform": "Netease",
            "content_type": "music",
        }

    if downloader.is_qqmusic_url(url):
        logger.error(f"❌ QQ音乐链接不应该调用_download_single_video函数: {url}")
        return {
            "success": False,
            "error": "QQ音乐链接不应该调用单视频下载函数",
            "platform": "QQMusic",
            "content_type": "music",
        }

    if downloader.is_youtube_music_url(url):
        logger.error(f"❌ YouTube Music链接不应该调用_download_single_video函数: {url}")
        return {
            "success": False,
            "error": "YouTube Music链接不应该调用单视频下载函数",
            "platform": "YouTubeMusic",
            "content_type": "music",
        }

    return None


async def prepare_single_video_title(downloader, *, url: str, logger, yt_dlp_module):
    """预先提取单视频信息并生成安全标题。"""
    try:
        logger.info("🔍 步骤1: 预先获取视频信息...")
        info_opts = {
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 60,
            "retries": 5,
            "noplaylist": True,
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            },
        }

        if downloader.proxy_host:
            info_opts["proxy"] = downloader.proxy_host
            logger.info(f"🌪 使用代理: {downloader.proxy_host}")

        if (
            downloader.is_x_url(url)
            and downloader.x_cookies_path
            and os.path.exists(downloader.x_cookies_path)
        ):
            info_opts["cookiefile"] = downloader.x_cookies_path
            logger.info(f"🍪 使用X cookies: {downloader.x_cookies_path}")

        if downloader.is_youtube_url(url):
            info_opts["extractor_args"] = {
                "youtube": {
                    "player_client": ["android", "ios", "web", "mweb"],
                    "player_skip": ["configs", "webpage"],
                    "formats": ["missing_pot"],
                }
            }

        if (
            downloader.is_youtube_url(url)
            and downloader.youtube_cookies_path
            and os.path.exists(downloader.youtube_cookies_path)
        ):
            info_opts["cookiefile"] = downloader.youtube_cookies_path
            logger.info(f"🍪 使用YouTube cookies: {downloader.youtube_cookies_path}")
        elif downloader.is_youtube_url(url) and downloader.youtube_cookies_path:
            logger.warning(f"⚠️ YouTube cookies 文件未找到: {downloader.youtube_cookies_path}")
            logger.warning("⚠️ 需要登录的视频可能仍然无法下载，确认文件已挂载到容器或路径配置正确")

        if (
            downloader.is_douyin_url(url)
            and downloader.douyin_cookies_path
            and os.path.exists(downloader.douyin_cookies_path)
        ):
            info_opts["cookiefile"] = downloader.douyin_cookies_path
            logger.info(f"🍪 使用抖音 cookies: {downloader.douyin_cookies_path}")

        if "instagram.com" in url.lower():
            if (
                hasattr(downloader, "instagram_cookies_path")
                and downloader.instagram_cookies_path
                and os.path.exists(downloader.instagram_cookies_path)
            ):
                info_opts["cookiefile"] = downloader.instagram_cookies_path
                logger.info(
                    f"🍪 预先获取信息阶段使用Instagram cookies: {downloader.instagram_cookies_path}"
                )
            else:
                logger.warning("⚠️ Instagram预先获取信息：cookies未配置，可能导致获取失败")

        logger.info("🔍 步骤2: 开始提取视频信息...")
        loop = asyncio.get_running_loop()

        def extract_video_info():
            with yt_dlp_module.YoutubeDL(info_opts) as ydl:
                logger.info("🔗 正在从平台获取视频数据...")
                return ydl.extract_info(url, download=False)

        try:
            info = await asyncio.wait_for(
                loop.run_in_executor(None, extract_video_info), timeout=60.0
            )
            logger.info(f"✅ 视频信息获取完成，数据类型: {type(info)}")

            if info and isinstance(info, dict):
                video_id = info.get("id")
                title = info.get("title")
                if title:
                    title = downloader._sanitize_filename(title)
                else:
                    title = downloader._sanitize_filename(video_id)
                logger.info(f"📑 视频标题: {title}")
                logger.info(f"🆔 视频ID: {video_id}")
                return {"ok": True, "title": title}
            else:
                logger.warning(
                    "⚠️ yt-dlp 未返回有效的视频信息(info=None 或类型无效)，将使用 URL 片段或时间戳作为标题"
                )
                fallback_title = downloader._sanitize_filename(
                    url.split("/")[-1].split("?")[0] or str(int(time.time()))
                )
                fallback_title = fallback_title or downloader._sanitize_filename(str(int(time.time())))
                logger.info(f"📑 备用标题: {fallback_title}")
                return {"ok": True, "title": fallback_title}
        except asyncio.TimeoutError:
            logger.error("❌ 获取视频信息超时（60秒）")
            return {
                "ok": False,
                "result": {
                    "success": False,
                    "error": "获取视频信息超时（60秒），请检查网络连接或稍后重试。",
                },
            }
    except Exception as e:
        logger.error(f"❌ 无法预先获取视频信息: {e}")
        title = downloader._sanitize_filename(str(int(time.time())))
        logger.info(f"📑 使用时间戳作为标题: {title}")
        return {"ok": True, "title": title}
