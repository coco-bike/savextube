# -*- coding: utf-8 -*-
"""X 播放列表下载结果收集与构建。"""

import os


def build_x_playlist_download_result(
    downloader,
    *,
    download_path,
    download_start_time,
    progress_data,
    logger,
):
    """收集本次下载到的文件并构建标准返回结果。"""
    video_files = []
    downloaded_files = (
        progress_data.get("downloaded_files", [])
        if progress_data and isinstance(progress_data, dict)
        else []
    )
    logger.info(f"📊 progress_data中记录的文件: {downloaded_files}")

    if downloaded_files:
        for filename in downloaded_files:
            file_path = download_path / filename
            if file_path.exists():
                video_files.append((file_path, os.path.getmtime(file_path)))
                logger.info(f"✅ 找到本次下载文件: {filename}")
            else:
                logger.warning(f"⚠️ 文件不存在: {filename}")

    if not video_files:
        logger.info("🔄 使用时间检测方法查找下载文件")
        for file in download_path.glob("*.mp4"):
            try:
                mtime = os.path.getmtime(file)
                if mtime >= download_start_time:
                    video_files.append((file, mtime))
                    logger.info(f"✅ 找到本次下载文件: {file.name}, 修改时间: {mtime}")
            except OSError:
                continue

    video_files.sort(key=lambda x: x[0].name)

    part_files = downloader._detect_part_files(download_path)
    success_count = len(video_files)
    part_count = len(part_files)

    logger.info("📊 下载完成统计：")
    logger.info(f"✅ 成功文件：{success_count} 个")
    if part_count > 0:
        logger.warning(f"⚠️ 未完成文件：{part_count} 个")
        downloader._log_part_files_details(part_files)
    else:
        logger.info("✅ 未发现PART文件，所有下载都已完成")

    if not video_files:
        return {"success": False, "error": "X播放列表下载完成但未找到本次下载的文件"}

    total_size_mb = 0
    file_info_list = []
    all_resolutions = set()

    for file_path, _mtime in video_files:
        size_mb = os.path.getsize(file_path) / (1024 * 1024)
        total_size_mb += size_mb
        media_info = downloader.get_media_info(str(file_path))
        resolution = media_info.get("resolution", "未知")
        if resolution != "未知":
            all_resolutions.add(resolution)
        file_info_list.append(
            {
                "filename": os.path.basename(file_path),
                "size_mb": size_mb,
                "resolution": resolution,
                "abr": media_info.get("bit_rate"),
            }
        )

    filename_list = [info["filename"] for info in file_info_list]
    filename_display = "\n".join([f"  {i + 1:02d}. {name}" for i, name in enumerate(filename_list)])
    resolution_display = ", ".join(sorted(all_resolutions)) if all_resolutions else "未知"

    return {
        "success": True,
        "is_playlist": True,
        "file_count": len(video_files),
        "total_size_mb": total_size_mb,
        "files": file_info_list,
        "platform": "X",
        "download_path": str(download_path),
        "filename": filename_display,
        "size_mb": total_size_mb,
        "resolution": resolution_display,
        "episode_count": len(video_files),
        "success_count": success_count,
        "part_count": part_count,
        "part_files": [str(pf) for pf in part_files] if part_files else [],
    }
