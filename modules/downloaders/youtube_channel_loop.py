# -*- coding: utf-8 -*-
"""YouTube频道播放列表循环下载逻辑。"""

import asyncio
import os
from pathlib import Path


async def run_youtube_channel_playlists_loop(
    downloader,
    *,
    playlist_entries,
    channel_path,
    message_updater,
    status_message,
    loop,
    global_progress,
    logger,
):
    """循环下载频道内播放列表并产出统计结果。"""
    downloaded_playlists = []
    playlist_stats = []

    for i, entry in enumerate(playlist_entries, 1):
        playlist_id = entry.get("id")
        playlist_title = entry.get("title", f"Playlist_{playlist_id}")
        logger.info(f"🎬 开始下载第 {i}/{len(playlist_entries)} 个播放列表: {playlist_title}")
        logger.info(f"    📋 播放列表ID: {playlist_id}")

        check_result = downloader._check_playlist_already_downloaded(playlist_id, channel_path)

        if message_updater:
            try:
                if asyncio.iscoroutinefunction(message_updater):
                    if check_result.get("already_downloaded", False):
                        await message_updater(
                            f"✅ 检查第 {i}/{len(playlist_entries)} 个播放列表：{playlist_title} (已完整下载)"
                        )
                    else:
                        await message_updater(
                            f"📥 正在下载第 {i}/{len(playlist_entries)} 个播放列表：{playlist_title}"
                        )
                else:
                    if check_result.get("already_downloaded", False):
                        message_updater(
                            f"✅ 检查第 {i}/{len(playlist_entries)} 个播放列表：{playlist_title} (已完整下载)"
                        )
                    else:
                        message_updater(
                            f"📥 正在下载第 {i}/{len(playlist_entries)} 个播放列表：{playlist_title}"
                        )
            except Exception as e:
                logger.warning(f"更新状态消息失败: {e}")

        playlist_progress_data = {
            "playlist_index": i,
            "total_playlists": len(playlist_entries),
            "playlist_title": playlist_title,
            "current_video": 0,
            "total_videos": 0,
            "downloaded_videos": 0,
        }

        def create_playlist_progress_callback(progress_data):
            last_update = {"percent": -1, "time": 0, "text": ""}
            import time as _time

            def escape_num(text):
                if not isinstance(text, str):
                    text = str(text)
                escape_chars = [
                    "_",
                    "*",
                    "[",
                    "]",
                    "(",
                    ")",
                    "~",
                    "`",
                    ">",
                    "#",
                    "+",
                    "-",
                    "=",
                    "|",
                    "{",
                    "}",
                    ".",
                    "!",
                ]
                for char in escape_chars:
                    text = text.replace(char, "\\" + char)
                return text

            def progress_callback(d):
                logger.info(
                    f"🔍 [PROGRESS_CALLBACK] 被调用: status={d.get('status')}, filename={d.get('filename', 'N/A')}"
                )

                if d.get("status") == "downloading":
                    logger.info(
                        f"🔍 YouTube播放列表进度回调: status={d.get('status')}, filename={d.get('filename', 'N/A')}"
                    )
                    cur_idx = (
                        d.get("playlist_index")
                        or d.get("info_dict", {}).get("playlist_index")
                        or 1
                    )
                    total_idx = (
                        d.get("playlist_count")
                        or d.get("info_dict", {}).get("n_entries")
                        or (
                            progress_data.get("total_videos")
                            if progress_data and isinstance(progress_data, dict)
                            else 0
                        )
                        or 1
                    )
                    if progress_data and isinstance(progress_data, dict):
                        progress_text = (
                            f"📥 正在下载第{escape_num(progress_data['playlist_index'])}/{escape_num(progress_data['total_playlists'])}个播放列表：{escape_num(progress_data['playlist_title'])}\n\n"
                            f"📺 当前视频: {escape_num(cur_idx)}/{escape_num(total_idx)}\n"
                        )
                    else:
                        progress_text = f"📺 当前视频: {escape_num(cur_idx)}/{escape_num(total_idx)}\n"
                    percent = 0
                    if d.get("filename"):
                        filename = os.path.basename(d.get("filename", ""))
                        total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                        downloaded_bytes = d.get("downloaded_bytes", 0)
                        speed_bytes_s = d.get("speed", 0)
                        eta_seconds = d.get("eta", 0)
                        if total_bytes and total_bytes > 0:
                            downloaded_mb = downloaded_bytes / (1024 * 1024)
                            total_mb = total_bytes / (1024 * 1024)
                            speed_mb_s = speed_bytes_s / (1024 * 1024) if speed_bytes_s else 0
                            percent = int(downloaded_bytes * 100 / total_bytes)
                            bar = downloader._make_progress_bar(percent)
                            try:
                                minutes, seconds = divmod(int(eta_seconds), 60)
                                eta_str = f"{minutes:02d}:{seconds:02d}"
                            except (ValueError, TypeError):
                                eta_str = "未知"
                            downloaded_mb_str = f"{downloaded_mb:.2f}"
                            total_mb_str = f"{total_mb:.2f}"
                            speed_mb_s_str = f"{speed_mb_s:.2f}"
                            percent_str = f"{percent:.1f}"
                            progress_text += (
                                f"📝 文件: {escape_num(filename)}\n"
                                f"💾 大小: {escape_num(downloaded_mb_str)}MB / {escape_num(total_mb_str)}MB\n"
                                f"⚡ 速度: {escape_num(speed_mb_s_str)}MB/s\n"
                                f"⏳ 预计剩余: {escape_num(eta_str)}\n"
                                f"📊 进度: {bar} {escape_num(percent_str)}%"
                            )
                        else:
                            downloaded_mb = downloaded_bytes / (1024 * 1024) if downloaded_bytes > 0 else 0
                            speed_mb_s = speed_bytes_s / (1024 * 1024) if speed_bytes_s else 0
                            downloaded_mb_str = f"{downloaded_mb:.2f}"
                            speed_mb_s_str = f"{speed_mb_s:.2f}"
                            progress_text += (
                                f"📝 文件: {escape_num(filename)}\n"
                                f"💾 大小: {escape_num(downloaded_mb_str)}MB\n"
                                f"⚡ 速度: {escape_num(speed_mb_s_str)}MB/s\n"
                                f"📊 进度: 下载中..."
                            )
                    now = _time.time()
                    if (abs(percent - last_update["percent"]) >= 5) or (now - last_update["time"] > 1):
                        if progress_text != last_update["text"]:
                            logger.info(f"🔄 更新进度消息: percent={percent}%")
                        last_update["percent"] = percent
                        last_update["time"] = now
                        last_update["text"] = progress_text
                        import asyncio

                        tg_updated = False

                        if status_message and loop:
                            try:
                                def fix_markdown_v2(text):
                                    text = text.replace("\\", "")
                                    special_chars = [
                                        "_",
                                        "*",
                                        "[",
                                        "]",
                                        "(",
                                        ")",
                                        "~",
                                        "`",
                                        ">",
                                        "#",
                                        "+",
                                        "-",
                                        "=",
                                        "|",
                                        "{",
                                        "}",
                                        ".",
                                        "!",
                                    ]
                                    for char in special_chars:
                                        text = text.replace(char, f"\\{char}")
                                    return text

                                fixed_text = fix_markdown_v2(progress_text)
                                future = asyncio.run_coroutine_threadsafe(
                                    status_message.edit_text(fixed_text, parse_mode=None),
                                    loop,
                                )
                                future.result(timeout=3.0)
                                tg_updated = True
                            except Exception:
                                try:
                                    clean_text = progress_text.replace("\\", "")
                                    future = asyncio.run_coroutine_threadsafe(
                                        status_message.edit_text(clean_text),
                                        loop,
                                    )
                                    future.result(timeout=3.0)
                                    tg_updated = True
                                except Exception:
                                    tg_updated = False
                        else:
                            tg_updated = False

                        if not tg_updated and message_updater:
                            try:
                                def fixed_message_updater(text):
                                    if hasattr(message_updater, "__closure__") and message_updater.__closure__:
                                        for cell in message_updater.__closure__:
                                            try:
                                                value = cell.cell_contents
                                                if hasattr(value, "edit_text") and hasattr(value, "chat_id"):
                                                    status_msg = value
                                                    for cell2 in message_updater.__closure__:
                                                        try:
                                                            value2 = cell2.cell_contents
                                                            if hasattr(value2, "run_until_complete"):
                                                                event_loop = value2

                                                                def fix_markdown_v2(text):
                                                                    text = text.replace("\\", "")
                                                                    special_chars = [
                                                                        "_",
                                                                        "*",
                                                                        "[",
                                                                        "]",
                                                                        "(",
                                                                        ")",
                                                                        "~",
                                                                        "`",
                                                                        ">",
                                                                        "#",
                                                                        "+",
                                                                        "-",
                                                                        "=",
                                                                        "|",
                                                                        "{",
                                                                        "}",
                                                                        ".",
                                                                        "!",
                                                                    ]
                                                                    for char in special_chars:
                                                                        text = text.replace(char, f"\\{char}")
                                                                    return text

                                                                try:
                                                                    fixed_text = fix_markdown_v2(text)
                                                                    future = asyncio.run_coroutine_threadsafe(
                                                                        status_msg.edit_text(fixed_text, parse_mode=None),
                                                                        event_loop,
                                                                    )
                                                                    future.result(timeout=3.0)
                                                                    return True
                                                                except Exception:
                                                                    clean_text = text.replace("\\", "")
                                                                    future = asyncio.run_coroutine_threadsafe(
                                                                        status_msg.edit_text(clean_text),
                                                                        event_loop,
                                                                    )
                                                                    future.result(timeout=3.0)
                                                                    return True
                                                        except Exception:
                                                            continue
                                            except Exception:
                                                continue

                                    logger.warning("⚠️ 无法从 message_updater 提取 TG 对象，尝试原调用")
                                    return False

                                if not fixed_message_updater(progress_text):
                                    logger.warning("⚠️ 修复的 message_updater 失败")

                            except Exception as e:
                                logger.error(f"❌ 调用修复的 message_updater 失败: {e}")

                        if not tg_updated and not message_updater:
                            logger.warning("⚠️ 没有可用的消息更新方法")
                elif d.get("status") == "finished":
                    if progress_data and isinstance(progress_data, dict):
                        progress_data["downloaded_videos"] += 1
                        logger.info(
                            f"✅ 播放列表 {progress_data['playlist_title']} 第 {progress_data['downloaded_videos']} 个视频下载完成"
                        )

                    if "filename" in d:
                        filename = d["filename"]
                        if filename.endswith(".part"):
                            logger.warning(f"⚠️ 文件合并可能失败: {filename}")
                        else:
                            logger.info(f"✅ 文件下载并合并成功: {filename}")

            return progress_callback

        logger.info(f"🎬 开始下载播放列表 {i}/{len(playlist_entries)}: {playlist_title}")
        progress_callback = create_playlist_progress_callback(playlist_progress_data)
        logger.info(f"🔧 创建进度回调函数: {type(progress_callback)}")
        logger.info(f"🔧 进度回调函数是否为None: {progress_callback is None}")
        logger.info(f"🔧 message_updater是否为None: {message_updater is None}")
        result = await downloader._download_youtube_playlist_with_progress(
            playlist_id,
            channel_path,
            progress_callback,
        )

        if result.get("success"):
            downloaded_playlists.append(result.get("playlist_title", playlist_title))

            if message_updater:
                try:
                    if asyncio.iscoroutinefunction(message_updater):
                        if result.get("already_downloaded", False):
                            await message_updater(
                                f"✅ 第 {i}/{len(playlist_entries)} 个播放列表：{playlist_title} (已存在)"
                            )
                        else:
                            await message_updater(
                                f"✅ 第 {i}/{len(playlist_entries)} 个播放列表：{playlist_title} (下载完成)"
                            )
                    else:
                        if result.get("already_downloaded", False):
                            message_updater(
                                f"✅ 第 {i}/{len(playlist_entries)} 个播放列表：{playlist_title} (已存在)"
                            )
                        else:
                            message_updater(
                                f"✅ 第 {i}/{len(playlist_entries)} 个播放列表：{playlist_title} (下载完成)"
                            )
                except Exception as e:
                    logger.warning(f"更新完成状态消息失败: {e}")

            video_count = result.get("video_count", 0)
            if video_count == 0:
                playlist_path = Path(result.get("download_path", ""))
                if playlist_path.exists():
                    video_files = (
                        list(playlist_path.glob("*.mp4"))
                        + list(playlist_path.glob("*.mkv"))
                        + list(playlist_path.glob("*.webm"))
                    )
                    video_count = len(video_files)
                    logger.info(f"📊 通过扫描目录计算播放列表 '{playlist_title}' 的集数: {video_count}")

            playlist_stats.append(
                {
                    "title": result.get("playlist_title", playlist_title),
                    "video_count": video_count,
                    "download_path": result.get("download_path", ""),
                    "total_size_mb": result.get("total_size_mb", 0),
                    "resolution": result.get("resolution", "未知"),
                    "success_count": result.get("success_count", video_count),
                    "part_count": result.get("part_count", 0),
                }
            )
            global_progress["completed_playlists"] += 1
            logger.info(f"    ✅ 播放列表 '{playlist_title}' 下载成功，集数: {video_count}")
        else:
            error_msg = result.get("error", "未知错误")
            logger.error(f"    ❌ 播放列表 '{playlist_title}' 下载失败: {error_msg}")

    return {
        "downloaded_playlists": downloaded_playlists,
        "playlist_stats": playlist_stats,
    }
