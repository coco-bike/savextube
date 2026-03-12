# -*- coding: utf-8 -*-
"""YouTube 频道播放列表下载初始化逻辑。"""

import asyncio
import os
import re
import time


async def init_youtube_channel_playlists_context(
    downloader,
    *,
    channel_url: str,
    download_path,
    message_updater,
    logger,
    yt_dlp_module,
):
    """初始化频道播放列表下载上下文，失败时返回可直接返回的结果。"""

    async def _safe_update(text: str):
        if not message_updater:
            return
        try:
            if asyncio.iscoroutinefunction(message_updater):
                await message_updater(text)
            else:
                message_updater(text)
        except Exception as e:
            logger.warning(f"更新状态消息失败: {e}")

    try:
        downloader._main_loop = asyncio.get_running_loop()
        logger.info(f"✅ 成功设置事件循环: {downloader._main_loop}")
    except Exception as e:
        logger.warning(f"⚠️ 无法获取事件循环: {e}")
        downloader._main_loop = None

    global_progress = {
        "total_playlists": 0,
        "completed_playlists": 0,
        "total_videos": 0,
        "completed_videos": 0,
        "total_size_mb": 0,
        "downloaded_size_mb": 0,
        "channel_name": "",
        "start_time": time.time(),
    }

    await _safe_update("🔍 正在获取频道信息...")
    logger.info("🔍 步骤1: 准备获取频道信息...")

    info_opts = {
        "quiet": True,
        "extract_flat": True,
        "ignoreerrors": True,
        "socket_timeout": 30,
        "retries": 8,
        "fragment_retries": 8,
        "playlistend": None,
        "playliststart": 1,
    }
    if downloader.proxy_host:
        info_opts["proxy"] = downloader.proxy_host
        logger.info(f"🌐 使用代理: {downloader.proxy_host}")
    if downloader.youtube_cookies_path and os.path.exists(downloader.youtube_cookies_path):
        info_opts["cookiefile"] = downloader.youtube_cookies_path
        logger.info(f"🍪 使用YouTube cookies: {downloader.youtube_cookies_path}")

    logger.info("🔍 步骤2: 开始提取频道信息（设置30秒超时）...")
    loop = asyncio.get_running_loop()

    def extract_channel_info():
        logger.info("📡 正在从YouTube获取频道数据...")
        with yt_dlp_module.YoutubeDL(info_opts) as ydl:
            logger.info("🔗 开始网络请求...")
            result = ydl.extract_info(channel_url, download=False)
            logger.info(f"📊 网络请求完成，结果类型: {type(result)}")
            return result

    try:
        await _safe_update("⏳ 正在连接YouTube服务器...")
        info = await asyncio.wait_for(
            loop.run_in_executor(None, extract_channel_info), timeout=60.0
        )
        logger.info(f"✅ 频道信息获取完成，数据类型: {type(info)}")
        await _safe_update("✅ 频道信息获取成功，正在分析...")
    except asyncio.TimeoutError:
        logger.error("❌ 获取频道信息超时（30秒）")
        await _safe_update("❌ 获取频道信息超时，请检查网络连接或稍后重试。")
        return {
            "ok": False,
            "result": {
                "success": False,
                "error": "获取频道信息超时，请检查网络连接或稍后重试。",
            },
        }

    logger.info("🔍 步骤3: 检查频道信息结构...")
    if not info:
        logger.error("❌ 频道信息为空")
        await _safe_update("❌ 无法获取频道信息。")
        return {"ok": False, "result": {"success": False, "error": "无法获取频道信息。"}}

    if "entries" not in info:
        logger.warning("❌ 频道信息中没有找到 'entries' 字段")
        logger.info(
            f"📊 频道信息包含的字段: {list(info.keys()) if isinstance(info, dict) else '非字典类型'}"
        )
        await _safe_update("❌ 此频道主页未找到任何播放列表。")
        return {
            "ok": False,
            "result": {"success": False, "error": "此频道主页未找到任何播放列表。"},
        }

    entries = info.get("entries", [])
    logger.info(f"📊 找到 {len(entries)} 个条目")
    if not entries:
        logger.warning("❌ 频道条目列表为空")
        await _safe_update("❌ 此频道主页未找到任何播放列表。")
        return {
            "ok": False,
            "result": {"success": False, "error": "此频道主页未找到任何播放列表。"},
        }

    logger.info("🔍 步骤4: 分析频道条目...")
    await _safe_update(f"🔍 正在分析 {len(entries)} 个频道条目...")

    type_counts = {}
    playlist_entries = []
    for i, entry in enumerate(entries):
        if entry:
            entry_type = entry.get("_type", "unknown")
            entry_id = entry.get("id", "no_id")
            entry_title = entry.get("title", "no_title")
            entry_url = entry.get("url", "")

            type_counts[entry_type] = type_counts.get(entry_type, 0) + 1
            logger.info(
                f"  📋 条目 {i + 1}: 类型={entry_type}, ID={entry_id}, 标题={entry_title[:50]}..."
            )

            if entry_type == "playlist":
                playlist_entries.append(entry)
                logger.info("    ✅ 识别为播放列表")
            elif entry_type == "url" and "playlist?list=" in entry_url:
                playlist_entries.append(entry)
                logger.info("    ✅ 识别为播放列表URL")
            elif entry_type == "video":
                logger.info("    ⏭️ 跳过单个视频（只下载播放列表）")
            else:
                logger.info(f"    ⏭️ 跳过非播放列表条目（类型: {entry_type}）")
        else:
            logger.warning(f"  ⚠️ 条目 {i + 1} 为空")

    logger.info(f"📊 条目类型统计: {type_counts}")
    logger.info(f"📊 过滤结果: 总条目 {len(entries)} 个，播放列表 {len(playlist_entries)} 个")
    logger.info(f"📊 总共找到 {len(playlist_entries)} 个播放列表")

    if not playlist_entries:
        logger.warning("❌ 没有找到任何播放列表")
        await _safe_update("❌ 频道中没有找到任何播放列表。")
        return {
            "ok": False,
            "result": {"success": False, "error": "频道中没有找到任何播放列表。"},
        }

    logger.info("🔍 步骤5: 创建频道目录...")
    channel_name = re.sub(r'[\\/:*?"<>|]', "_", info.get("uploader", "Unknown Channel")).strip()
    channel_path = download_path / channel_name
    channel_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"📁 频道目录: {channel_path}")

    logger.info("🔍 步骤6: 开始下载播放列表...")
    await _safe_update(f"🎬 开始下载 {len(playlist_entries)} 个播放列表...")

    global_progress["total_playlists"] = len(playlist_entries)
    global_progress["channel_name"] = channel_name

    total_video_count = 0
    for entry in playlist_entries:
        if entry and "video_count" in entry:
            total_video_count += entry.get("video_count", 0)

    if total_video_count == 0:
        logger.info("📊 无法从API获取视频数量，将在下载过程中动态计算")
        global_progress["total_videos"] = -1
    else:
        global_progress["total_videos"] = total_video_count

    logger.info(
        f"📊 全局进度初始化: {global_progress['total_playlists']} 个播放列表, {global_progress['total_videos']} 个视频"
    )

    return {
        "ok": True,
        "global_progress": global_progress,
        "playlist_entries": playlist_entries,
        "channel_name": channel_name,
        "channel_path": channel_path,
    }
