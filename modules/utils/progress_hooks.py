# -*- coding: utf-8 -*-
"""下载进度回调函数集合。"""

import asyncio
import os
import threading
import time
from typing import Any, Callable, Dict, Optional

from modules.utils.async_utils import get_preferred_event_loop


_netease_last_update_time = {"time": 0}


def create_unified_progress_hook(message_updater=None, progress_data=None, *, logger):
    """创建统一的 yt-dlp 进度回调函数。"""

    def progress_hook(d):
        try:
            if d.get("status") == "downloading":
                downloaded = d.get("downloaded_bytes", 0) or 0
                total = d.get("total_bytes") or d.get("total_bytes_estimate", 0) or 0

                if downloaded is None:
                    downloaded = 0
                if total is None or total <= 0:
                    total = 1

                percent = (downloaded / total) * 100 if total > 0 else 0

                speed = d.get("speed", 0) or 0
                speed_str = f"{speed / 1024 / 1024:.2f} MB/s" if speed and speed > 0 else "未知"

                eta = d.get("eta", 0) or 0
                eta_str = f"{eta}秒" if eta and eta > 0 else "未知"

                filename = os.path.basename(d.get("filename", "")) or "正在下载..."

                if progress_data:
                    progress_data.update(
                        {
                            "downloaded": downloaded,
                            "total": total,
                            "percent": percent,
                            "speed": speed_str,
                            "eta": eta_str,
                            "status": "downloading",
                            "filename": filename,
                        }
                    )

                logger.info(
                    f"下载进度: {percent:.1f}% ({downloaded}/{total} bytes) - {speed_str} - 剩余: {eta_str}"
                )

                if message_updater:
                    try:
                        if asyncio.iscoroutine(message_updater):
                            logger.error("❌ [progress_hook] message_updater 是协程对象，不是函数！")
                            return

                        if asyncio.iscoroutinefunction(message_updater):
                            loop = get_preferred_event_loop()
                            asyncio.run_coroutine_threadsafe(message_updater(d), loop)
                        else:
                            message_updater(d)
                    except Exception as e:
                        logger.warning(f"⚠️ 更新进度消息失败: {e}")

            if d.get("status") == "finished":
                logger.info("下载完成，开始后处理...")

                if progress_data and isinstance(progress_data, dict):
                    progress_data["status"] = "finished"

                filename = d.get("filename", "")
                if filename and progress_data and isinstance(progress_data, dict):
                    progress_data["final_filename"] = filename
                    logger.info(f"最终文件名: {filename}")

                    if filename.endswith(".part"):
                        logger.warning(f"⚠️ 文件合并可能失败: {filename}")
                    else:
                        logger.info(f"✅ 文件下载并合并成功: {filename}")
                else:
                    logger.warning("progress_hook 中未获取到文件名")

                if message_updater:
                    try:
                        logger.info(f"🔍 [progress_hook] finished状态 - message_updater 类型: {type(message_updater)}")

                        if asyncio.iscoroutine(message_updater):
                            logger.error("❌ [progress_hook] finished状态 - message_updater 是协程对象，不是函数！")
                            return

                        if asyncio.iscoroutinefunction(message_updater):
                            logger.info("🔍 [progress_hook] finished状态 - 检测到异步函数，使用 run_coroutine_threadsafe")
                            loop = get_preferred_event_loop()
                            asyncio.run_coroutine_threadsafe(message_updater(d), loop)
                        else:
                            logger.info("🔍 [progress_hook] finished状态 - 检测到同步函数，直接调用")
                            message_updater(d)
                    except Exception as e:
                        logger.warning(f"⚠️ 更新完成消息失败: {e}")

        except Exception as e:
            logger.error(f"progress_hook 处理错误: {e}")

    return progress_hook


def create_single_video_progress_hook(
    message_updater=None,
    progress_data=None,
    status_message=None,
    context=None,
    *,
    logger,
    clean_filename_for_display: Callable[[str], str],
    create_progress_bar: Callable[[float, int], str],
    edit_message_threadsafe_func,
):
    """构建单视频下载进度回调。"""
    if progress_data is None:
        progress_data = {"final_filename": None, "lock": threading.Lock()}

    last_update_time = {"time": 0}

    def progress_hook(d):
        logger.info(f"🔍 [PROGRESS_HOOK] 被调用: {d.get('status', 'unknown')}")
        logger.info(f"🔍 [PROGRESS_DEBUG] status_message: {status_message is not None}, context: {context is not None}")
        if isinstance(d, dict) and d.get("status") == "downloading":
            progress = (d.get("downloaded_bytes", 0) / (d.get("total_bytes", 1))) * 100
            logger.info(f"📊 下载进度: {progress:.1f}%")
        elif isinstance(d, dict) and d.get("status") == "finished":
            logger.info("✅ 下载完成")

        if isinstance(d, str):
            if message_updater and status_message:
                edit_message_threadsafe_func(
                    status_message,
                    d,
                    parse_mode=None,
                    logger=logger,
                    warn_prefix="发送字符串进度到TG失败",
                )
            return

        if not isinstance(d, dict):
            logger.warning(f"progress_hook接收到非字典类型参数: {type(d)}, 内容: {d}")
            return

        try:
            if d["status"] == "downloading":
                raw_filename = d.get("filename", "")
                display_filename = os.path.basename(raw_filename) if raw_filename else "video.mp4"
                progress_data.update(
                    {
                        "filename": display_filename,
                        "total_bytes": d.get("total_bytes") or d.get("total_bytes_estimate", 0),
                        "downloaded_bytes": d.get("downloaded_bytes", 0),
                        "speed": d.get("speed", 0),
                        "status": "downloading",
                        "progress": (d.get("downloaded_bytes", 0) / (d.get("total_bytes") or d.get("total_bytes_estimate", 1))) * 100
                        if (d.get("total_bytes") or d.get("total_bytes_estimate", 0)) > 0
                        else 0.0,
                    }
                )
            elif d["status"] == "finished":
                final_filename = d.get("filename", "")
                display_filename = os.path.basename(final_filename) if final_filename else "video.mp4"
                progress_data.update(
                    {
                        "filename": display_filename,
                        "status": "finished",
                        "final_filename": final_filename,
                        "progress": 100.0,
                    }
                )
                logger.info(f"📝 记录最终文件名: {final_filename}")
        except Exception as e:
            logger.error(f"更新 progress_data 错误: {str(e)}")

        logger.info(f"🔍 [PROGRESS_DEBUG] status_message: {status_message is not None}, context: {context is not None}")
        if not status_message or not context:
            if message_updater:
                logger.info(
                    f"🔍 single_video_progress_hook 调用简单模式: status={d.get('status')}, async={asyncio.iscoroutinefunction(message_updater)}"
                )

                if asyncio.iscoroutinefunction(message_updater):
                    try:
                        logger.info("🔍 检测到异步进度更新器，创建新线程处理")

                        def run_async_in_thread():
                            try:
                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)
                                loop.run_until_complete(message_updater(d))
                                loop.close()
                                logger.info("✅ 线程中异步进度回调调用成功")
                            except Exception as e:
                                logger.warning(f"线程中异步进度回调调用失败: {e}")

                        thread = threading.Thread(target=run_async_in_thread, daemon=True)
                        thread.start()
                    except Exception as e:
                        logger.warning(f"创建异步进度回调线程失败: {e}")
                else:
                    try:
                        result = message_updater(d)
                        logger.info(f"✅ 同步进度回调调用成功: {result}")
                    except Exception as e:
                        logger.warning(f"进度回调调用失败: {e}")
            else:
                logger.warning("⚠️ message_updater 为空，跳过进度回调")
            return

        now = time.time()
        total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
        if total_bytes > 0 and total_bytes < 5 * 1024 * 1024:
            update_interval = 0.01
        else:
            update_interval = 0.1

        time_since_last = now - last_update_time["time"]
        current_progress = 0
        if total_bytes > 0:
            current_progress = (d.get("downloaded_bytes", 0) / total_bytes) * 100

        last_progress = progress_data.get("last_progress", 0) if isinstance(progress_data, dict) else 0

        force_update = (
            time_since_last > 1.0
            or abs(current_progress - last_progress) >= 1.0
            or d.get("status") == "finished"
        )

        if time_since_last < update_interval and not force_update:
            logger.info(f"⏰ 跳过更新，距离上次更新仅 {time_since_last:.2f}秒，需要等待 {update_interval}秒")
            return

        if force_update:
            if time_since_last > 1.0:
                logger.info(f"🔄 强制更新，距离上次更新已 {time_since_last:.2f}秒")
            elif abs(current_progress - last_progress) >= 1.0:
                logger.info(f"🔄 强制更新，进度变化 {last_progress:.1f}% -> {current_progress:.1f}%")
            elif d.get("status") == "finished":
                logger.info("🔄 强制更新，下载完成")

        if isinstance(progress_data, dict):
            progress_data["last_progress"] = current_progress

        if d.get("status") == "finished":
            logger.info("yt-dlp下载完成，显示完成信息")

            if isinstance(progress_data, dict):
                filename = progress_data.get("filename", "video.mp4")
                total_bytes = progress_data.get("total_bytes", 0)
                downloaded_bytes = progress_data.get("downloaded_bytes", 0)
            else:
                filename = "video.mp4"
                total_bytes = 0
                downloaded_bytes = 0

            actual_filename = d.get("filename", filename)
            if actual_filename.endswith(".part"):
                logger.warning(f"⚠️ 文件合并可能失败: {actual_filename}")
            else:
                logger.info(f"✅ 文件下载并合并成功: {actual_filename}")

            display_filename = clean_filename_for_display(filename)
            progress_bar = create_progress_bar(100.0)
            size_mb = total_bytes / (1024 * 1024) if total_bytes > 0 else downloaded_bytes / (1024 * 1024)

            completion_text = (
                f"📝 文件：{display_filename}\n"
                f"💾 大小：{size_mb:.2f}MB\n"
                f"⚡ 速度：完成\n"
                f"⏳ 预计剩余：0秒\n"
                f"📊 进度：{progress_bar} (100.0%)"
            )

            async def do_update():
                try:
                    await status_message.edit_text(completion_text, parse_mode=None)
                    logger.info("📱 显示下载完成进度信息")
                except Exception as e:
                    logger.warning(f"显示完成进度信息失败: {e}")

            loop = get_preferred_event_loop()
            asyncio.run_coroutine_threadsafe(do_update(), loop)
            return

        if d.get("status") == "downloading":
            logger.info("🔍 [DOWNLOADING_DEBUG] 进入下载中状态处理")
            logger.info(f"🔍 [DOWNLOADING_DEBUG] status_message: {status_message is not None}, context: {context is not None}")
            last_update_time["time"] = now

            total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            downloaded_bytes = d.get("downloaded_bytes", 0)
            speed_bytes_s = d.get("speed", 0)
            filename = d.get("filename", "") or "正在下载..."
            logger.info(
                f"🔍 [DOWNLOADING_DEBUG] 文件信息: {filename}, 总大小: {total_bytes}, 已下载: {downloaded_bytes}"
            )

            logger.info(f"🔍 [TOTAL_BYTES_DEBUG] total_bytes: {total_bytes}, 条件检查: {total_bytes > 0}")
            if total_bytes > 0:
                progress = (downloaded_bytes / total_bytes) * 100
                progress_bar = create_progress_bar(progress)
                size_mb = total_bytes / (1024 * 1024)
                speed_mb = (speed_bytes_s or 0) / (1024 * 1024)

                if speed_bytes_s and total_bytes and downloaded_bytes < total_bytes:
                    remaining = total_bytes - downloaded_bytes
                    eta = int(remaining / speed_bytes_s)
                    mins, secs = divmod(eta, 60)
                    if mins > 0:
                        eta_text = f"{mins}分{secs}秒"
                    else:
                        eta_text = f"{secs}秒"
                elif speed_bytes_s:
                    eta_text = "计算中"
                else:
                    eta_text = "未知"

                display_filename = clean_filename_for_display(filename)
                progress_text = (
                    f"📝 文件：{display_filename}\n"
                    f"💾 大小：{size_mb:.2f}MB\n"
                    f"⚡ 速度：{speed_mb:.2f}MB/s\n"
                    f"⏳ 预计剩余：{eta_text}\n"
                    f"📊 进度：{progress_bar} ({progress:.1f}%)"
                )

                async def do_update():
                    try:
                        logger.info("🔍 [DO_UPDATE_DEBUG] 开始更新Telegram消息")
                        logger.info(f"🔍 [DO_UPDATE_DEBUG] status_message: {status_message is not None}")
                        logger.info(f"🔍 [DO_UPDATE_DEBUG] progress_text: {progress_text[:100]}...")
                        await status_message.edit_text(progress_text, parse_mode=None)
                        logger.info(f"📱 更新Telegram进度: {progress:.1f}% - 文件: {display_filename}")
                    except Exception as e:
                        logger.error(f"🔍 [DO_UPDATE_ERROR] 更新Telegram失败: {e}")
                        if "Message is not modified" not in str(e):
                            logger.warning(f"更新Telegram进度失败: {e}")
                        else:
                            logger.info("📱 Telegram消息未修改，跳过更新")

                logger.info("🔍 [DO_UPDATE_DEFINED] do_update 协程已定义")
                loop = get_preferred_event_loop()

                logger.info("🔍 [ASYNC_DEBUG] 调用 asyncio.run_coroutine_threadsafe (下载中状态)")
                logger.info(f"🔍 [ASYNC_DEBUG] loop: {loop is not None}")
                logger.info(f"🔍 [ASYNC_DEBUG] do_update 函数: {do_update}")

                try:
                    if loop.is_running():
                        logger.info("🔍 [ASYNC_DEBUG] 事件循环正在运行，使用 run_coroutine_threadsafe")
                        future = asyncio.run_coroutine_threadsafe(do_update(), loop)
                        logger.info(f"🔍 [ASYNC_DEBUG] asyncio.run_coroutine_threadsafe 调用完成, future: {future}")
                        logger.info(f"🔍 [ASYNC_DEBUG] future.done(): {future.done()}")
                    else:
                        logger.info("🔍 [ASYNC_DEBUG] 事件循环未运行，直接运行协程")
                        asyncio.run(do_update())
                        logger.info("🔍 [ASYNC_DEBUG] 协程直接运行完成")
                except Exception as e:
                    logger.error(f"🔍 [ASYNC_ERROR] 异步调用失败: {e}")
                    import concurrent.futures

                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(asyncio.run, do_update())
                        logger.info(f"🔍 [ASYNC_DEBUG] 使用线程池运行协程: {future}")
            else:
                display_filename = clean_filename_for_display(filename)
                speed_mb = (speed_bytes_s or 0) / (1024 * 1024)
                progress_text = (
                    f"📝 文件：{display_filename}\n"
                    f"💾 大小：计算中...\n"
                    f"⚡ 速度：{speed_mb:.2f}MB/s\n"
                    f"⏳ 预计剩余：未知\n"
                    f"📊 进度：下载中..."
                )

                async def do_update():
                    try:
                        await status_message.edit_text(progress_text, parse_mode=None)
                        logger.info(f"📱 更新Telegram进度（无大小信息）- 文件: {display_filename}")
                    except Exception as e:
                        if "Message is not modified" not in str(e):
                            logger.warning(f"更新Telegram进度失败: {e}")
                        else:
                            logger.info("📱 Telegram消息未修改，跳过更新")

                loop = get_preferred_event_loop()
                asyncio.run_coroutine_threadsafe(do_update(), loop)

    return progress_hook


def create_netease_music_progress_hook(
    message_updater=None,
    progress_data=None,
    status_message=None,
    context=None,
    *,
    logger,
    clean_filename_for_display: Callable[[str], str],
    create_progress_bar: Callable[[float, int], str],
    edit_message_threadsafe_func,
):
    """构建网易云音乐下载进度回调。"""
    if progress_data is None:
        progress_data = {"final_filename": None, "lock": threading.Lock()}

    global _netease_last_update_time
    last_update_time = _netease_last_update_time

    def progress_hook(d):
        logger.info(f"🔍 [NETEASE_PROGRESS] 收到进度回调: {d}")
        logger.info(
            f"🔍 [NETEASE_PROGRESS] status_message: {status_message is not None}, context: {context is not None}, message_updater: {message_updater is not None}"
        )

        if isinstance(d, str):
            if message_updater and status_message:
                edit_message_threadsafe_func(
                    status_message,
                    d,
                    parse_mode=None,
                    logger=logger,
                    warn_prefix="发送字符串进度到TG失败",
                )
            return

        if not isinstance(d, dict):
            logger.warning(f"netease_progress_hook接收到非字典类型参数: {type(d)}, 内容: {d}")
            return

        try:
            if d["status"] == "downloading":
                raw_filename = d.get("filename", "")
                display_filename = os.path.basename(raw_filename) if raw_filename else "music.mp3"
                progress_data.update(
                    {
                        "filename": display_filename,
                        "total_bytes": d.get("total_bytes", 0),
                        "downloaded_bytes": d.get("downloaded_bytes", 0),
                        "speed": d.get("speed", 0),
                        "status": "downloading",
                        "progress": (d.get("downloaded_bytes", 0) / d.get("total_bytes", 1)) * 100
                        if d.get("total_bytes", 0) > 0
                        else 0.0,
                    }
                )
            elif d["status"] == "finished":
                final_filename = d.get("filename", "")
                display_filename = os.path.basename(final_filename) if final_filename else "music.mp3"
                progress_data.update(
                    {
                        "filename": display_filename,
                        "status": "finished",
                        "final_filename": final_filename,
                        "progress": 100.0,
                    }
                )
                logger.info(f"📝 网易云音乐下载完成: {final_filename}")
        except Exception as e:
            logger.error(f"更新网易云音乐进度数据错误: {str(e)}")

        simple_mode = not status_message or not context
        logger.info(f"🔍 [NETEASE_PROGRESS] simple_mode: {simple_mode}")

        if simple_mode and message_updater:
            logger.info(f"🔍 netease_progress_hook 简单模式: status={d.get('status')}")
            try:
                if d.get("status") == "downloading":
                    downloaded_bytes = d.get("downloaded_bytes", 0)
                    speed = d.get("speed", 0)
                    filename = d.get("filename", "music.mp3")
                    total_bytes = d.get("total_bytes", 0)

                    if total_bytes > 0:
                        progress = (downloaded_bytes / total_bytes) * 100
                        speed_mb = speed / (1024 * 1024) if speed > 0 else 0
                        total_mb = total_bytes / (1024 * 1024)
                        downloaded_mb = downloaded_bytes / (1024 * 1024)

                        if speed > 0 and total_bytes > downloaded_bytes:
                            remaining = total_bytes - downloaded_bytes
                            eta_seconds = int(remaining / speed)
                            mins, secs = divmod(eta_seconds, 60)
                            if mins > 0:
                                eta_str = f"{mins:02d}:{secs:02d}"
                            else:
                                eta_str = f"00:{secs:02d}"
                        else:
                            eta_str = "未知"

                        progress_bar = create_progress_bar(progress)
                        display_filename = clean_filename_for_display(filename)
                        progress_text = (
                            f"📝 文件: `{display_filename}`\n"
                            f"💾 大小: `{downloaded_mb:.2f}MB / {total_mb:.2f}MB`\n"
                            f"⚡ 速度: `{speed_mb:.2f}MB/s`\n"
                            f"⏳ 预计剩余: `{eta_str}`\n"
                            f"📊 进度: {progress_bar} `{progress:.1f}%`"
                        )
                    else:
                        display_filename = clean_filename_for_display(filename)
                        progress_text = (
                            f"📝 文件: `{display_filename}`\n"
                            "💾 大小: 未知\n"
                            "⚡ 速度: 未知\n"
                            "⏳ 预计剩余: 未知\n"
                            "📊 进度: 下载中..."
                        )

                    edit_message_threadsafe_func(
                        status_message,
                        progress_text,
                        parse_mode=None,
                        logger=logger,
                        warn_prefix="发送简单模式进度到TG失败",
                    )
                elif d.get("status") == "finished":
                    filename = d.get("filename", "music.mp3")
                    total_bytes = d.get("total_bytes", 0)
                    total_mb = total_bytes / (1024 * 1024) if total_bytes > 0 else 0

                    display_filename = clean_filename_for_display(filename)
                    progress_bar = create_progress_bar(100.0)
                    finish_text = (
                        f"📝 文件: `{display_filename}`\n"
                        f"💾 大小: `{total_mb:.2f}MB`\n"
                        "⚡ 速度: 完成\n"
                        "⏳ 预计剩余: 0秒\n"
                        f"📊 进度: {progress_bar} `100.0%`"
                    )
                    edit_message_threadsafe_func(
                        status_message,
                        finish_text,
                        parse_mode=None,
                        logger=logger,
                        warn_prefix="发送简单模式完成消息到TG失败",
                    )
            except Exception as e:
                logger.warning(f"网易云音乐简单模式回调失败: {e}")
        elif simple_mode:
            logger.warning("⚠️ 网易云音乐简单模式但无message_updater")

        logger.info(f"🔍 [NETEASE_PROGRESS] 进入完整进度显示逻辑: status={d.get('status')}")

        if d.get("status") == "downloading":
            logger.info("🔍 [NETEASE_PROGRESS] 处理下载中状态")
            now = time.time()
            total_bytes = d.get("total_bytes", 0)
            downloaded_bytes = d.get("downloaded_bytes", 0)
            speed_bytes_s = d.get("speed", 0)
            filename = d.get("filename", "") or "正在下载..."

            if total_bytes > 0:
                progress = (downloaded_bytes / total_bytes) * 100
                progress_bar = create_progress_bar(progress)
                size_mb = total_bytes / (1024 * 1024)
                speed_mb = (speed_bytes_s or 0) / (1024 * 1024)

                if speed_bytes_s and total_bytes and downloaded_bytes < total_bytes:
                    remaining = total_bytes - downloaded_bytes
                    eta = int(remaining / speed_bytes_s)
                    mins, secs = divmod(eta, 60)
                    if mins > 0:
                        eta_text = f"{mins}分{secs}秒"
                    else:
                        eta_text = f"{secs}秒"
                elif speed_bytes_s:
                    eta_text = "计算中"
                else:
                    eta_text = "未知"

                display_filename = clean_filename_for_display(filename)
                progress_text = (
                    f"🎵 音乐：{display_filename}\n"
                    f"💾 大小：{downloaded_bytes / (1024 * 1024):.2f}MB / {size_mb:.2f}MB\n"
                    f"⚡ 速度：{speed_mb:.2f}MB/s\n"
                    f"⏳ 预计剩余：{eta_text}\n"
                    f"📊 进度：{progress_bar} ({progress:.1f}%)"
                )

                async def do_update():
                    try:
                        await status_message.edit_text(progress_text)
                        logger.info(f"📱 更新Telegram进度: {progress:.1f}% - 文件: {display_filename}")
                        last_update_time["time"] = now
                    except Exception as e:
                        logger.warning(f"🔍 [NETEASE_PROGRESS] 更新网易云音乐进度失败: {e}")
                        if "Message is not modified" not in str(e) and message_updater:
                            try:
                                logger.info("🔍 [NETEASE_PROGRESS] 尝试使用备用message_updater")
                                if asyncio.iscoroutinefunction(message_updater):
                                    await message_updater(progress_text)
                                else:
                                    message_updater(progress_text)
                                logger.info("✅ 使用备用message_updater更新成功")
                                last_update_time["time"] = now
                            except Exception as backup_e:
                                logger.warning(f"备用message_updater也失败: {backup_e}")

                loop = get_preferred_event_loop()
                if loop.is_running():
                    try:
                        future = asyncio.run_coroutine_threadsafe(do_update(), loop)
                        try:
                            future.result(timeout=0.1)
                        except asyncio.TimeoutError:
                            pass
                        except Exception as e:
                            logger.error(f"🔍 [NETEASE_PROGRESS] 进度更新任务执行失败: {e}")
                    except Exception as e:
                        logger.error(f"🔍 [NETEASE_PROGRESS] 提交进度更新任务失败: {e}")
                else:
                    try:
                        asyncio.run(do_update())
                    except Exception as e:
                        logger.error(f"🔍 [NETEASE_PROGRESS] 直接运行协程失败: {e}")
            return

        if d.get("status") == "finished":
            logger.info("🎵 网易云音乐下载完成，显示完成信息")

            filename = progress_data.get("filename", "music.mp3")
            total_bytes = progress_data.get("total_bytes", 0)
            downloaded_bytes = progress_data.get("downloaded_bytes", 0)
            now = time.time()

            display_filename = clean_filename_for_display(filename)
            progress_bar = create_progress_bar(100.0)
            size_mb = total_bytes / (1024 * 1024) if total_bytes > 0 else downloaded_bytes / (1024 * 1024)

            completion_text = (
                f"🎵 音乐：{display_filename}\n"
                f"💾 大小：{size_mb:.2f}MB\n"
                "⚡ 速度：完成\n"
                "⏳ 预计剩余：0秒\n"
                f"📊 进度：{progress_bar} (100.0%)"
            )

            async def do_update():
                try:
                    await status_message.edit_text(completion_text)
                    logger.info("🎵 显示网易云音乐下载完成进度信息")
                    last_update_time["time"] = now
                except Exception as e:
                    logger.warning(f"显示网易云音乐完成进度信息失败: {e}")
                    if message_updater:
                        try:
                            if asyncio.iscoroutinefunction(message_updater):
                                await message_updater(completion_text)
                            else:
                                message_updater(completion_text)
                            logger.info("✅ 使用备用message_updater显示完成信息成功")
                            last_update_time["time"] = now
                        except Exception as backup_e:
                            logger.warning(f"备用message_updater显示完成信息也失败: {backup_e}")

            loop = get_preferred_event_loop()
            if loop.is_running():
                try:
                    future = asyncio.run_coroutine_threadsafe(do_update(), loop)
                    try:
                        future.result(timeout=0.1)
                    except asyncio.TimeoutError:
                        pass
                    except Exception as e:
                        logger.error(f"🔍 [NETEASE_PROGRESS] 完成状态更新任务执行失败: {e}")
                except Exception as e:
                    logger.error(f"🔍 [NETEASE_PROGRESS] 提交完成状态更新任务失败: {e}")
            else:
                try:
                    asyncio.run(do_update())
                except Exception as e:
                    logger.error(f"🔍 [NETEASE_PROGRESS] 直接运行完成状态协程失败: {e}")
            return

    return progress_hook
