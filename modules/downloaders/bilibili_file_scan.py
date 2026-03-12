# -*- coding: utf-8 -*-
"""B站下载后的文件扫描工具。"""

import os
from pathlib import Path


def scan_bilibili_video_files(download_path, logger):
    """扫描下载目录并返回视频文件列表（文件路径, 修改时间）。"""
    video_files = []
    logger.info("🎯 B站多P下载：没有预期文件列表，智能查找子目录中的文件")
    logger.info(f"🔍 搜索路径: {download_path}")

    base_path = Path(download_path)
    if not base_path.exists():
        logger.error(f"❌ 下载路径不存在: {download_path}")
        return {"ok": False, "error": "下载路径不存在", "video_files": []}

    try:
        all_items = list(base_path.iterdir())
        subdirs = [item for item in all_items if item.is_dir()]

        if subdirs:
            latest_subdir = max(subdirs, key=lambda x: x.stat().st_mtime)
            logger.info(f"📁 找到最新子目录: {latest_subdir.name}")

            video_extensions = ["*.mp4", "*.mkv", "*.webm", "*.avi", "*.mov", "*.flv"]
            for ext in video_extensions:
                matching_files = list(latest_subdir.glob(ext))
                if matching_files:
                    logger.info(f"✅ 在子目录中找到 {len(matching_files)} 个 {ext} 文件")
                    for file_path in matching_files:
                        try:
                            mtime = os.path.getmtime(file_path)
                            video_files.append((file_path, mtime))
                            logger.info(f"✅ 找到文件: {file_path.name}")
                        except OSError:
                            continue
        else:
            logger.warning("⚠️ 未找到子目录，在根目录查找")
            video_extensions = ["*.mp4", "*.mkv", "*.webm", "*.avi", "*.mov", "*.flv"]
            for ext in video_extensions:
                matching_files = list(base_path.glob(ext))
                for file_path in matching_files:
                    try:
                        mtime = os.path.getmtime(file_path)
                        video_files.append((file_path, mtime))
                        logger.info(f"✅ 找到文件: {file_path.name}")
                    except OSError:
                        continue

        return {"ok": True, "error": "", "video_files": video_files}
    except Exception as e:
        logger.error(f"❌ 智能查找失败: {e}")
        return {"ok": False, "error": f"文件查找失败: {e}", "video_files": []}
