# -*- coding: utf-8 -*-
"""图片下载通用工具：目录快照、差集检测、结果标准化。"""

import time
from pathlib import Path


MEDIA_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
}


def collect_relative_files(root_path: Path):
    """收集目录下文件相对路径集合。"""
    result = set()
    if root_path.exists():
        for file_path in root_path.rglob("*"):
            if file_path.is_file():
                result.add(str(file_path.relative_to(root_path)))
    return result


def discover_new_media_files(root_path: Path, before_files, logger, recent_seconds: int = 300):
    """根据快照差集发现新下载文件，失败时回退到最近修改策略。"""
    downloaded_files = []
    total_size_bytes = 0
    file_formats = set()

    logger.info(f"🔍 开始查找新下载的文件...")
    logger.info(f"🔍 查找目录: {root_path}")
    logger.info(f"🔍 下载前文件数量: {len(before_files)}")

    if not root_path.exists():
        logger.warning(f"⚠️ 下载目录不存在: {root_path}")
        return downloaded_files, total_size_bytes, file_formats

    current_files = collect_relative_files(root_path)
    logger.info(f"🔍 当前文件数量: {len(current_files)}")

    new_files = current_files - before_files
    logger.info(f"🔍 新文件数量: {len(new_files)}")

    if new_files:
        logger.info(f"🔍 新文件示例: {list(new_files)[:5]}")
        for relative_path in new_files:
            file_path = root_path / relative_path
            if file_path.is_file() and file_path.suffix.lower() in MEDIA_EXTENSIONS:
                downloaded_files.append(file_path)
                try:
                    file_size = file_path.stat().st_size
                    total_size_bytes += file_size
                    file_formats.add(file_path.suffix.lower())
                    logger.info(f"✅ 找到下载文件: {relative_path} ({file_size} bytes)")
                except OSError as e:
                    logger.warning(f"无法获取文件大小: {file_path} - {e}")
    else:
        logger.warning("⚠️ 没有找到新文件，尝试查找最近修改的文件...")
        try:
            recent_files = []
            now = time.time()
            for file_path in root_path.rglob("*"):
                if file_path.is_file():
                    file_mtime = file_path.stat().st_mtime
                    if now - file_mtime < recent_seconds:
                        recent_files.append(file_path)

            logger.info(f"🔍 最近{recent_seconds}秒内修改的文件数量: {len(recent_files)}")
            if recent_files:
                logger.info(f"🔍 最近修改文件示例: {[f.name for f in recent_files[:3]]}")

            for file_path in recent_files:
                if file_path.suffix.lower() in MEDIA_EXTENSIONS:
                    downloaded_files.append(file_path)
                    try:
                        file_size = file_path.stat().st_size
                        total_size_bytes += file_size
                        file_formats.add(file_path.suffix.lower())
                        logger.info(f"✅ 找到最近修改的文件: {file_path.name} ({file_size} bytes)")
                    except OSError as e:
                        logger.warning(f"无法获取文件大小: {file_path} - {e}")
        except Exception as e:
            logger.error(f"❌ 查找最近修改文件时出错: {e}")

    return downloaded_files, total_size_bytes, file_formats


def build_gallery_download_success_result(downloaded_files, total_size_bytes, file_formats, download_dir: str):
    """构建 gallery-dl 下载成功结果。"""
    size_mb = total_size_bytes / (1024 * 1024)
    format_str = ", ".join(sorted(file_formats)) if file_formats else "未知格式"

    return {
        "success": True,
        "message": (
            f"✅ 图片下载完成！\n\n"
            f"🖼️ 图片数量：{len(downloaded_files)} 张\n"
            f"📝 保存位置：{download_dir}\n"
            f"💾 总大小：{size_mb:.1f} MB\n"
            f"📄 文件格式：{format_str}"
        ),
        "files_count": len(downloaded_files),
        "failed_count": 0,
        "files": [str(f) for f in downloaded_files],
        "size_mb": size_mb,
        "filename": downloaded_files[0].name if downloaded_files else "未知文件",
        "download_path": download_dir,
        "full_path": str(downloaded_files[0]) if downloaded_files else "",
        "resolution": "图片",
        "abr": None,
        "file_formats": list(file_formats),
    }


def normalize_image_download_result(
    *,
    platform: str,
    title: str,
    download_path: str,
    files_count: int,
    size_mb: float,
    file_formats,
    full_path: str = "",
    filename: str = "",
    extra: dict | None = None,
):
    """统一图片下载成功返回结构。"""
    result = {
        "success": True,
        "platform": platform,
        "content_type": "image",
        "title": title,
        "download_path": download_path,
        "full_path": full_path,
        "filename": filename,
        "size_mb": size_mb,
        "total_size_mb": size_mb,
        "resolution": "图片",
        "files_count": files_count,
        "file_formats": file_formats or [],
    }
    if extra:
        result.update(extra)
    return result


def normalize_image_error_result(platform: str, error: str):
    """统一图片下载失败返回结构。"""
    return {
        "success": False,
        "error": error,
        "platform": platform,
        "content_type": "image",
    }
