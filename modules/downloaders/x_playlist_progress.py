# -*- coding: utf-8 -*-
"""X 播放列表下载进度回调构建器。"""

import asyncio
import time


def create_x_playlist_progress_callback(
    *,
    progress_data,
    message_updater,
    make_progress_bar,
    logger,
):
    """创建 X 播放列表下载进度回调。"""

    def escape_num(text):
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

    def calculate_overall_progress():
        if not progress_data or not isinstance(progress_data, dict) or progress_data["total"] == 0:
            return 0
        return (progress_data["current"] / progress_data["total"]) * 100

    def progress_callback(d):
        try:
            if not progress_data or not isinstance(progress_data, dict):
                return
            current = progress_data["current"]
            total = progress_data["total"]
            overall_percent = calculate_overall_progress()

            if d.get("status") == "finished":
                progress_data["current"] += 1
                current = progress_data["current"]
                overall_percent = calculate_overall_progress()

                if "filename" in d:
                    filename = d["filename"]
                    if "downloaded_files" not in progress_data:
                        progress_data["downloaded_files"] = []
                    progress_data["downloaded_files"].append(filename)

                    if filename.endswith(".part"):
                        logger.warning(f"⚠️ 文件合并可能失败: {filename}")
                    else:
                        logger.info(f"✅ 文件下载并合并成功: {filename}")

            progress_bar = make_progress_bar(overall_percent)
            elapsed_time = time.time() - (
                progress_data["start_time"]
                if progress_data and isinstance(progress_data, dict)
                else time.time()
            )

            status_text = "🎬 X播放列表下载进度\n"
            status_text += f"📊 总体进度: {progress_bar} {overall_percent:.1f}%\n"
            status_text += f"📹 当前: {current}/{total} 个视频\n"
            status_text += f"⏱️ 已用时: {elapsed_time:.0f}秒\n"

            if d.get("status") == "downloading":
                if "_percent_str" in d:
                    status_text += f"📥 当前视频: {d.get('_percent_str', '0%')}\n"
                if "_speed_str" in d:
                    status_text += f"🚀 速度: {d.get('_speed_str', 'N/A')}\n"

            escaped_text = escape_num(status_text)

            try:
                if message_updater:
                    if asyncio.iscoroutinefunction(message_updater):
                        try:
                            loop = asyncio.get_running_loop()
                        except RuntimeError:
                            try:
                                loop = asyncio.get_event_loop()
                            except RuntimeError:
                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)

                        coro = message_updater(escaped_text)
                        asyncio.run_coroutine_threadsafe(coro, loop)
                    else:
                        message_updater(escaped_text)
            except Exception as e:
                if "Message is not modified" not in str(e):
                    logger.warning(f"⚠️ 更新播放列表进度失败: {e}")
                logger.info(f"进度更新: {escaped_text}")

        except Exception as e:
            logger.warning(f"⚠️ 更新播放列表进度失败: {e}")

    return progress_callback
