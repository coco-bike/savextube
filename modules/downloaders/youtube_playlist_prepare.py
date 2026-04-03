# -*- coding: utf-8 -*-
"""YouTube播放列表下载前置准备。"""

import asyncio
import os
import re


async def prepare_youtube_playlist_download_context(
    downloader,
    *,
    playlist_id: str,
    download_path,
    logger,
    yt_dlp_module,
):
    """准备播放列表下载上下文，包含已下载检查、信息提取与预期文件构建。"""
    logger.info("🔍 检查播放列表是否已完整下载...")
    check_result = downloader._check_playlist_already_downloaded(playlist_id, download_path)

    if check_result.get("already_downloaded", False):
        logger.info("✅ 播放列表已完整下载，直接返回结果")
        return {
            "handled": True,
            "result": {
                "success": True,
                "already_downloaded": True,
                "playlist_title": check_result.get("playlist_title", ""),
                "video_count": check_result.get("video_count", 0),
                "download_path": check_result.get("download_path", ""),
                "total_size_mb": check_result.get("total_size_mb", 0),
                "resolution": check_result.get("resolution", "未知"),
                "downloaded_files": check_result.get("downloaded_files", []),
                "completion_rate": check_result.get("completion_rate", 100),
            },
        }

    logger.info(f"📥 播放列表未完整下载，原因: {check_result.get('reason', '未知')}")
    if check_result.get("completion_rate", 0) > 0:
        logger.info(f"📊 当前完成度: {check_result.get('completion_rate', 0):.1f}%")

    info_opts = {
        "quiet": False,
        "ignoreerrors": True,
        "socket_timeout": 60,
        "retries": 3,
        "js_runtimes": {"node": {}},
        "age_limit": 99,
        "geo_bypass": True,
        "geo_bypass_country": "US",
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "ios", "web", "mweb"],
                "player_skip": ["configs", "webpage"],
                "include_dash_manifest": True,
            }
        },
    }
    if downloader.proxy_host:
        info_opts["proxy"] = downloader.proxy_host
        logger.info(f"🌐 使用代理: {downloader.proxy_host}")
    if downloader.youtube_cookies_path and os.path.exists(downloader.youtube_cookies_path):
        info_opts["cookiefile"] = downloader.youtube_cookies_path
        logger.info(f"🍪 使用YouTube cookies: {downloader.youtube_cookies_path}")

    def extract_playlist_info():
        logger.info("📡 正在从YouTube获取播放列表数据...")
        with yt_dlp_module.YoutubeDL(info_opts) as ydl:
            return ydl.extract_info(
                f"https://www.youtube.com/playlist?list={playlist_id}",
                download=False,
            )

    loop = asyncio.get_running_loop()
    info = await loop.run_in_executor(None, extract_playlist_info)

    if not info:
        logger.error("❌ 播放列表信息为空")
        return {"handled": True, "result": {"success": False, "error": "无法获取播放列表信息。"}}

    entries = info.get("entries", [])
    if not entries:
        logger.warning("❌ 播放列表为空")
        return {"handled": True, "result": {"success": False, "error": "播放列表为空。"}}

    logger.info(f"📊 播放列表包含 {len(entries)} 个视频")
    logger.info(f"🔍 播放列表原始标题: {info.get('title', 'N/A')}")
    logger.info(f"🔍 播放列表ID: {playlist_id}")
    logger.info(
        f"🔍 播放列表其他字段: uploader={info.get('uploader', 'N/A')}, uploader_id={info.get('uploader_id', 'N/A')}"
    )

    raw_title = info.get("title", f"Playlist_{playlist_id}")
    if raw_title == playlist_id or raw_title.startswith("Playlist_"):
        raw_title = info.get("uploader", info.get("channel", f"Playlist_{playlist_id}"))
        logger.info(f"🔧 使用备用标题: {raw_title}")

    playlist_title = re.sub(r'[\\/:*?"<>|]', "_", raw_title).strip()
    if (
        hasattr(downloader, "bot")
        and hasattr(downloader.bot, "youtube_id_tags")
        and downloader.bot.youtube_id_tags
    ):
        playlist_title_with_id = f"[{playlist_id}]"
    else:
        playlist_title_with_id = playlist_title

    playlist_path = download_path / playlist_title_with_id
    playlist_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"📁 播放列表目录: {playlist_path}")

    expected_files = []
    for i, entry in enumerate(entries, 1):
        title = entry.get("title", f"Video_{i}")
        safe_title = re.sub(r'[\\/:*?"<>|]', "_", title).strip()
        video_id = entry.get("id", "")

        if (
            hasattr(downloader, "bot")
            and hasattr(downloader.bot, "youtube_id_tags")
            and downloader.bot.youtube_id_tags
        ):
            expected_filename = f"{i:02d}. {safe_title}[{video_id}].mp4"
        else:
            expected_filename = f"{i:02d}. {safe_title}.mp4"

        expected_files.append(
            {
                "title": title,
                "filename": expected_filename,
                "index": i,
                "id": video_id,
            }
        )

    logger.info(f"📋 预期文件列表: {len(expected_files)} 个文件")
    return {
        "handled": False,
        "result": None,
        "playlist_path": playlist_path,
        "playlist_title_with_id": playlist_title_with_id,
        "expected_files": expected_files,
    }
