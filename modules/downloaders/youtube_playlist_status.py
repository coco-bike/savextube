# -*- coding: utf-8 -*-
"""YouTube 播放列表已下载状态检查。"""

import os
import re
import subprocess
from pathlib import Path


def _clean_filename_for_matching(filename, *, use_id_tags: bool):
    """清理文件名用于模糊匹配。"""
    if not filename:
        return ""

    cleaned = re.sub(r"\.[fm]\d+(\+\d+)*", "", filename)
    cleaned = re.sub(r"\.f\d+", "", cleaned)

    if use_id_tags:
        cleaned = re.sub(r"\[[a-zA-Z0-9_-]{10,12}\]", "", cleaned)

    cleaned = re.sub(r"\.(webm|m4a|mp3)$", ".mp4", cleaned)
    if not cleaned.endswith(".mp4"):
        cleaned = cleaned.rstrip(".") + ".mp4"

    return cleaned


def check_youtube_playlist_already_downloaded(
    downloader,
    *,
    playlist_id: str,
    download_path: Path,
    logger,
    yt_dlp_module,
):
    """检查 YouTube 播放列表是否已完整下载。"""
    logger.info(f"🔍 检查播放列表是否已下载: {playlist_id}")

    try:
        info_opts = {
            "quiet": True,
            "extract_flat": True,
            "ignoreerrors": True,
            "socket_timeout": 10,
            "retries": 2,
        }
        if downloader.proxy_host:
            info_opts["proxy"] = downloader.proxy_host
        if downloader.youtube_cookies_path and os.path.exists(downloader.youtube_cookies_path):
            info_opts["cookiefile"] = downloader.youtube_cookies_path

        with yt_dlp_module.YoutubeDL(info_opts) as ydl:
            info = ydl.extract_info(
                f"https://www.youtube.com/playlist?list={playlist_id}",
                download=False,
            )

        if not info:
            logger.warning("❌ 无法获取播放列表信息")
            return {"already_downloaded": False, "reason": "无法获取播放列表信息"}

        entries = info.get("entries", [])
        if not entries:
            logger.warning("❌ 播放列表为空")
            return {"already_downloaded": False, "reason": "播放列表为空"}

        use_id_tags = (
            hasattr(downloader, "bot")
            and hasattr(downloader.bot, "youtube_id_tags")
            and downloader.bot.youtube_id_tags
        )

        expected_files = []
        for i, entry in enumerate(entries, 1):
            title = entry.get("title", f"Video_{i}")
            safe_title = re.sub(r'[\\/:*?"<>|]', "_", title).strip()
            video_id = entry.get("id", "")

            if use_id_tags:
                expected_filename = f"{i:02d}. {safe_title}[{video_id}].mp4"
            else:
                expected_filename = f"{i:02d}. {safe_title}.mp4"

            expected_files.append(
                {
                    "title": title,
                    "filename": expected_filename,
                    "index": i,
                    "id": video_id,
                }
            )

        playlist_title = re.sub(
            r'[\\/:*?"<>|]', "_", info.get("title", f"Playlist_{playlist_id}")
        ).strip()
        playlist_title_with_id = f"[{playlist_id}]" if use_id_tags else playlist_title
        playlist_path = download_path / playlist_title_with_id

        if not playlist_path.exists():
            logger.info(f"📁 播放列表目录不存在: {playlist_path}")
            return {"already_downloaded": False, "reason": "目录不存在"}

        logger.info(f"📁 检查播放列表目录: {playlist_path}")

        missing_files = []
        existing_files = []
        total_size_mb = 0
        all_resolutions = set()

        for expected_file in expected_files:
            expected_filename = expected_file["filename"]
            expected_path = playlist_path / expected_filename
            title = expected_file["title"]

            if expected_path.exists():
                try:
                    file_size = expected_path.stat().st_size
                    if file_size > 0:
                        file_size_mb = file_size / (1024 * 1024)
                        total_size_mb += file_size_mb

                        media_info = downloader.get_media_info(str(expected_path))
                        resolution = media_info.get("resolution", "未知")
                        if resolution != "未知":
                            all_resolutions.add(resolution)

                        existing_files.append(
                            {
                                "filename": expected_filename,
                                "path": str(expected_path),
                                "size_mb": file_size_mb,
                                "video_title": title,
                            }
                        )
                        logger.info(f"✅ 找到文件: {expected_filename} ({file_size_mb:.2f}MB)")
                    else:
                        missing_files.append(f"{expected_file['index']}. {title}")
                        logger.warning(f"⚠️ 文件为空: {expected_filename}")
                except Exception as e:
                    missing_files.append(f"{expected_file['index']}. {title}")
                    logger.warning(f"⚠️ 无法检查文件: {expected_filename}, 错误: {e}")
            else:
                found = False
                for video_ext in ["*.mp4", "*.mkv", "*.webm", "*.avi", "*.mov", "*.flv"]:
                    matching_files = list(playlist_path.glob(video_ext))
                    for file_path in matching_files:
                        actual_filename = file_path.name
                        cleaned_actual = _clean_filename_for_matching(
                            actual_filename, use_id_tags=use_id_tags
                        )
                        cleaned_expected = _clean_filename_for_matching(
                            expected_filename, use_id_tags=use_id_tags
                        )

                        if cleaned_actual == cleaned_expected:
                            try:
                                file_size = file_path.stat().st_size
                                if file_size > 0:
                                    file_size_mb = file_size / (1024 * 1024)
                                    total_size_mb += file_size_mb

                                    media_info = downloader.get_media_info(str(file_path))
                                    resolution = media_info.get("resolution", "未知")
                                    if resolution != "未知":
                                        all_resolutions.add(resolution)

                                    existing_files.append(
                                        {
                                            "filename": actual_filename,
                                            "path": str(file_path),
                                            "size_mb": file_size_mb,
                                            "video_title": title,
                                        }
                                    )
                                    logger.info(
                                        f"✅ 通过模糊匹配找到文件: {actual_filename} ({file_size_mb:.2f}MB)"
                                    )
                                    found = True
                                    break
                            except Exception:
                                continue
                    if found:
                        break

                if not found:
                    missing_files.append(f"{expected_file['index']}. {title}")
                    logger.warning(f"⚠️ 未找到文件: {expected_filename}")

        total_videos = len(expected_files)
        downloaded_videos = len(existing_files)
        completion_rate = (downloaded_videos / total_videos) * 100 if total_videos > 0 else 0

        logger.info(f"📊 下载完成度: {downloaded_videos}/{total_videos} ({completion_rate:.1f}%)")

        if completion_rate >= 95:
            logger.info(f"✅ 播放列表已完整下载 ({completion_rate:.1f}%)")

            resolution = ", ".join(sorted(all_resolutions)) if all_resolutions else "未知"
            if existing_files:
                try:
                    first_file_path = existing_files[0]["path"]
                    result = subprocess.run(
                        [
                            "ffprobe",
                            "-v",
                            "quiet",
                            "-print_format",
                            "json",
                            "-show_streams",
                            first_file_path,
                        ],
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode == 0:
                        import json

                        data = json.loads(result.stdout)
                        for stream in data.get("streams", []):
                            if stream.get("codec_type") == "video":
                                width = stream.get("width", 0)
                                height = stream.get("height", 0)
                                if width and height:
                                    resolution = f"{width}x{height}"
                                    break
                except Exception as e:
                    logger.warning(f"无法获取视频分辨率: {e}")

            return {
                "already_downloaded": True,
                "playlist_title": playlist_title_with_id,
                "video_count": downloaded_videos,
                "total_videos": total_videos,
                "completion_rate": completion_rate,
                "download_path": str(playlist_path),
                "total_size_mb": total_size_mb,
                "resolution": resolution,
                "downloaded_files": existing_files,
                "missing_files": missing_files,
            }

        logger.info(f"📥 播放列表未完整下载 ({completion_rate:.1f}%)")
        return {
            "already_downloaded": False,
            "reason": f"完成度不足 ({completion_rate:.1f}%)",
            "downloaded_videos": downloaded_videos,
            "total_videos": total_videos,
            "completion_rate": completion_rate,
            "missing_files": missing_files,
        }

    except Exception as e:
        logger.error(f"❌ 检查播放列表下载状态时出错: {e}")
        return {"already_downloaded": False, "reason": f"检查失败: {str(e)}"}
