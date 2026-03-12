# -*- coding: utf-8 -*-
"""B站下载前置执行与早返回处理。"""

import asyncio
import threading


async def run_bilibili_preflight(
    downloader,
    *,
    url: str,
    download_path,
    message_updater=None,
    auto_playlist: bool = False,
    status_message=None,
    context=None,
    progress_hook_factory=None,
    logger,
):
    """执行 smart_download_bilibili 并处理可提前返回的场景。"""
    progress_data = {"final_filename": None, "lock": threading.Lock()}
    progress_callback = progress_hook_factory(
        message_updater=message_updater,
        progress_data=progress_data,
        status_message=status_message,
        context=context,
    )

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        downloader.smart_download_bilibili,
        url,
        str(download_path),
        progress_callback,
        auto_playlist,
    )

    if isinstance(result, dict) and result.get("status") == "single_video":
        logger.info("🔄 smart_download_bilibili 检测到单视频，回退到通用下载器")
        fallback_result = await downloader._download_single_video(
            url,
            download_path,
            message_updater,
            status_message=status_message,
            context=context,
        )
        return {
            "handled": True,
            "result": fallback_result,
            "progress_data": progress_data,
            "raw_result": result,
        }

    if not result:
        return {
            "handled": True,
            "result": {"success": False, "error": "B站下载失败"},
            "progress_data": progress_data,
            "raw_result": result,
        }

    if isinstance(result, dict) and result.get("status") == "success" and "files" in result:
        logger.info("✅ smart_download_bilibili 返回了完整的文件信息，直接使用")
        direct_result = {
            "success": True,
            "is_playlist": result.get("is_playlist", True),
            "file_count": result.get("file_count", 0),
            "total_size_mb": result.get("total_size_mb", 0),
            "files": result.get("files", []),
            "platform": result.get("platform", "bilibili"),
            "download_path": result.get("download_path", str(download_path)),
            "filename": result.get("filename", ""),
            "size_mb": result.get("size_mb", 0),
            "resolution": result.get("resolution", "未知"),
            "episode_count": result.get("episode_count", 0),
            "video_type": result.get("video_type", "playlist"),
        }
        return {
            "handled": True,
            "result": direct_result,
            "progress_data": progress_data,
            "raw_result": result,
        }

    return {
        "handled": False,
        "result": None,
        "progress_data": progress_data,
        "raw_result": result,
    }
