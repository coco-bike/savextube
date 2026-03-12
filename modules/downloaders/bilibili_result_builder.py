# -*- coding: utf-8 -*-
"""B站下载结果构建工具。"""

import os


def _build_playlist_summary(downloader, video_files):
    """构建多文件结果共用统计信息。"""
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
        "total_size_mb": total_size_mb,
        "file_info_list": file_info_list,
        "filename_display": filename_display,
        "resolution_display": resolution_display,
    }


def build_bilibili_download_result(
    downloader,
    *,
    video_files,
    download_path,
    is_list: bool,
    part_files,
):
    """根据文件列表构建B站下载返回结构。"""
    if is_list:
        if not video_files:
            return {"success": False, "error": "B站合集下载完成但未找到本次下载的文件"}

        summary = _build_playlist_summary(downloader, video_files)
        return {
            "success": True,
            "is_playlist": True,
            "file_count": len(video_files),
            "total_size_mb": summary["total_size_mb"],
            "files": summary["file_info_list"],
            "platform": "bilibili",
            "download_path": str(download_path),
            "filename": summary["filename_display"],
            "size_mb": summary["total_size_mb"],
            "resolution": summary["resolution_display"],
            "episode_count": len(video_files),
            "success_count": len(video_files),
            "part_count": len(part_files),
            "part_files": [str(pf) for pf in part_files] if part_files else [],
        }

    if not video_files:
        return {"success": False, "error": "B站多P下载完成但未找到本次下载的文件"}

    if len(video_files) > 1:
        summary = _build_playlist_summary(downloader, video_files)
        return {
            "success": True,
            "is_playlist": True,
            "video_type": "playlist",
            "file_count": len(video_files),
            "total_size_mb": summary["total_size_mb"],
            "files": summary["file_info_list"],
            "platform": "bilibili",
            "download_path": str(download_path),
            "filename": summary["filename_display"],
            "size_mb": summary["total_size_mb"],
            "resolution": summary["resolution_display"],
            "episode_count": len(video_files),
        }

    video_files.sort(key=lambda x: x[1], reverse=True)
    final_file_path = str(video_files[0][0])
    media_info = downloader.get_media_info(final_file_path)
    size_mb = os.path.getsize(final_file_path) / (1024 * 1024)
    return {
        "success": True,
        "filename": os.path.basename(final_file_path),
        "full_path": final_file_path,
        "size_mb": size_mb,
        "platform": "bilibili",
        "download_path": str(download_path),
        "resolution": media_info.get("resolution", "未知"),
        "abr": media_info.get("bit_rate"),
    }
