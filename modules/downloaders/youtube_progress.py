# -*- coding: utf-8 -*-
"""YouTube 下载进度回调辅助。"""

import asyncio
import os
import time as _time


def _escape_num(text):
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


def create_single_playlist_progress_callback(
    progress_data,
    *,
    message_updater,
    loop,
    logger,
    make_progress_bar,
):
    """创建单个 YouTube 播放列表进度回调。"""
    last_update = {"percent": -1, "time": 0, "text": ""}

    def progress_callback(d):
        logger.info(
            f"🔍 [SINGLE_PLAYLIST_PROGRESS_CALLBACK] 被调用: status={d.get('status')}, filename={d.get('filename', 'N/A')}"
        )

        if d.get("status") != "downloading":
            return

        logger.info(
            f"🔍 单个YouTube播放列表进度回调: status={d.get('status')}, filename={d.get('filename', 'N/A')}"
        )

        cur_idx = d.get("playlist_index") or d.get("info_dict", {}).get("playlist_index") or 1
        total_idx = (
            d.get("playlist_count")
            or d.get("info_dict", {}).get("n_entries")
            or (progress_data.get("total_videos") if progress_data and isinstance(progress_data, dict) else 0)
            or 1
        )

        if progress_data and isinstance(progress_data, dict):
            progress_text = (
                f"📥 正在下载第{_escape_num(progress_data['playlist_index'])}/{_escape_num(progress_data['total_playlists'])}个播放列表：{_escape_num(progress_data['playlist_title'])}\n\n"
                f"📺 当前视频: {_escape_num(cur_idx)}/{_escape_num(total_idx)}\n"
            )
        else:
            progress_text = f"📺 当前视频: {_escape_num(cur_idx)}/{_escape_num(total_idx)}\n"

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
                speed_mb_s = (speed_bytes_s / (1024 * 1024)) if speed_bytes_s else 0
                percent = int(downloaded_bytes * 100 / total_bytes)
                bar = make_progress_bar(percent)
                try:
                    minutes, seconds = divmod(int(eta_seconds), 60)
                    eta_str = f"{minutes:02d}:{seconds:02d}"
                except (ValueError, TypeError):
                    eta_str = "未知"

                progress_text += (
                    f"📝 文件: {_escape_num(filename)}\n"
                    f"💾 大小: {_escape_num(f'{downloaded_mb:.2f}')}MB / {_escape_num(f'{total_mb:.2f}')}MB\n"
                    f"⚡ 速度: {_escape_num(f'{speed_mb_s:.2f}')}MB/s\n"
                    f"⏳ 预计剩余: {_escape_num(eta_str)}\n"
                    f"📊 进度: {bar} {_escape_num(f'{percent:.1f}')}%"
                )
            else:
                downloaded_mb = downloaded_bytes / (1024 * 1024) if downloaded_bytes > 0 else 0
                speed_mb_s = (speed_bytes_s / (1024 * 1024)) if speed_bytes_s else 0
                progress_text += (
                    f"📝 文件: {_escape_num(filename)}\n"
                    f"💾 大小: {_escape_num(f'{downloaded_mb:.2f}')}MB\n"
                    f"⚡ 速度: {_escape_num(f'{speed_mb_s:.2f}')}MB/s\n"
                    "📊 进度: 下载中..."
                )

        now = _time.time()
        if (abs(percent - last_update["percent"]) >= 5) or (now - last_update["time"] > 1):
            if progress_text != last_update["text"]:
                logger.info(f"🔄 单个播放列表更新进度消息: percent={percent}%")
            last_update["percent"] = percent
            last_update["time"] = now
            last_update["text"] = progress_text

            if message_updater:
                try:
                    if asyncio.iscoroutinefunction(message_updater):
                        if loop:
                            future = asyncio.run_coroutine_threadsafe(message_updater(progress_text), loop)
                            future.result(timeout=3.0)
                        else:
                            logger.warning("⚠️ 没有事件循环，无法调用异步函数")
                    else:
                        message_updater(progress_text)
                except Exception as e:
                    if "Message is not modified" not in str(e):
                        logger.warning(f"❌ 进度更新失败: {e}")
                    logger.debug(f"📊 进度更新: {progress_text}")

    return progress_callback
