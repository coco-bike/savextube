# -*- coding: utf-8 -*-
"""YouTube频道播放列表下载结果汇总。"""

import asyncio
import os
from pathlib import Path
import re


async def build_youtube_channel_summary_result(
    downloader,
    *,
    channel_name: str,
    channel_path,
    downloaded_playlists,
    playlist_stats,
    message_updater,
    logger,
    yt_dlp_module,
):
    """构建频道下载汇总信息并返回最终结果。"""

    if not downloaded_playlists:
        logger.error("❌ 所有播放列表都下载失败了")
        if message_updater:
            try:
                if asyncio.iscoroutinefunction(message_updater):
                    await message_updater("❌ 频道中的所有播放列表都下载失败了。")
                else:
                    message_updater("❌ 频道中的所有播放列表都下载失败了。")
            except Exception as e:
                logger.warning(f"更新状态消息失败: {e}")
        return {"success": False, "error": "频道中的所有播放列表都下载失败了。"}

    logger.info("🎉 频道播放列表下载任务完成!")

    total_videos = sum(stat["video_count"] for stat in playlist_stats)
    total_size_mb = sum(stat["total_size_mb"] for stat in playlist_stats)

    downloaded_files = []
    for stat in playlist_stats:
        playlist_path = Path(stat["download_path"])
        if playlist_path.exists():
            try:
                info_opts = {
                    "quiet": True,
                    "extract_flat": True,
                    "ignoreerrors": True,
                }
                if downloader.proxy_host:
                    info_opts["proxy"] = downloader.proxy_host
                if downloader.youtube_cookies_path and os.path.exists(
                    downloader.youtube_cookies_path
                ):
                    info_opts["cookiefile"] = downloader.youtube_cookies_path

                playlist_id = ""
                path_name = playlist_path.name

                if path_name.startswith("[") and path_name.endswith("]"):
                    playlist_id = path_name[1:-1]
                    logger.info(f"🔍 从路径提取播放列表ID: {playlist_id}")
                else:
                    playlist_id = path_name.split("_")[-1] if "_" in path_name else ""
                    logger.info(f"🔍 从下划线分割提取播放列表ID: {playlist_id}")

                if not playlist_id:
                    playlist_id = stat.get("playlist_id", "")
                    logger.info(f"🔍 从stat获取播放列表ID: {playlist_id}")

                if playlist_id:
                    with yt_dlp_module.YoutubeDL(info_opts) as ydl:
                        playlist_info = ydl.extract_info(
                            f"https://www.youtube.com/playlist?list={playlist_id}",
                            download=False,
                        )
                        entries = playlist_info.get("entries", [])

                        for i, entry in enumerate(entries, 1):
                            if entry:
                                title = entry.get("title", f"Video_{i}")
                                clean_title = re.sub(r"#.*$", "", title)
                                safe_title = re.sub(r'[\\/:*?"<>]', "", clean_title)
                                safe_title = safe_title.strip()[:80]

                                expected_filename = f"{i:02d}. {safe_title}.mp4"
                                expected_file_path = playlist_path / expected_filename
                                if expected_file_path.exists():
                                    file_size = expected_file_path.stat().st_size / (1024 * 1024)
                                    downloaded_files.append(
                                        {
                                            "filename": expected_filename,
                                            "path": str(expected_file_path),
                                            "size_mb": file_size,
                                            "playlist": stat["title"],
                                            "video_title": title,
                                        }
                                    )
                                    logger.info(f"✅ 找到文件: {expected_filename} ({file_size:.2f}MB)")
                                else:
                                    logger.info(f"🔍 精确匹配失败，尝试智能模糊匹配: {expected_filename}")
                                    found_file = None

                                    matching_files = list(playlist_path.glob(f"{i:02d}.*"))
                                    if not matching_files:
                                        matching_files = list(playlist_path.glob(f"{i}.*"))

                                    if matching_files:
                                        found_file = matching_files[0]
                                        logger.info(f"✅ 通过编号匹配找到文件: {found_file.name}")
                                    else:
                                        title_words = re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z]+", title)
                                        if title_words and len(title_words) >= 2:
                                            keyword1 = title_words[0][:10]
                                            keyword2 = title_words[1][:10] if len(title_words) > 1 else ""

                                            for file_path in playlist_path.glob("*.mp4"):
                                                if keyword1 in file_path.name and (
                                                    not keyword2 or keyword2 in file_path.name
                                                ):
                                                    found_file = file_path
                                                    logger.info(
                                                        f"✅ 通过关键词匹配找到文件: {found_file.name}"
                                                    )
                                                    break

                                    if found_file:
                                        file_size = found_file.stat().st_size / (1024 * 1024)
                                        downloaded_files.append(
                                            {
                                                "filename": found_file.name,
                                                "path": str(found_file),
                                                "size_mb": file_size,
                                                "playlist": stat["title"],
                                                "video_title": title,
                                            }
                                        )
                                        logger.info(
                                            f"✅ 通过智能匹配找到文件: {found_file.name} ({file_size:.2f}MB)"
                                        )
                                    else:
                                        logger.warning(
                                            f"⚠️ 模糊匹配也未找到文件，编号: {i}, 标题: {safe_title}"
                                        )
            except Exception as e:
                logger.warning(f"⚠️ 获取播放列表信息失败 (ID: {playlist_id}): {e}")
                logger.info("💡 这通常是因为播放列表已被删除或设为私有，不影响已下载的文件")
                logger.info("🔄 回退到目录扫描模式来统计文件...")
                video_files = (
                    list(playlist_path.glob("*.mp4"))
                    + list(playlist_path.glob("*.mkv"))
                    + list(playlist_path.glob("*.webm"))
                )
                for video_file in video_files:
                    file_size = video_file.stat().st_size / (1024 * 1024)
                    downloaded_files.append(
                        {
                            "filename": video_file.name,
                            "path": str(video_file),
                            "size_mb": file_size,
                            "playlist": stat["title"],
                        }
                    )

    total_size_mb = sum(stat["total_size_mb"] for stat in playlist_stats)
    total_size_gb = total_size_mb / 1024

    total_success_count = sum(
        stat.get("success_count", stat.get("video_count", 0)) for stat in playlist_stats
    )
    total_part_count = sum(stat.get("part_count", 0) for stat in playlist_stats)

    total_video_count = sum(stat.get("video_count", 0) for stat in playlist_stats)
    total_failed_count = total_video_count - total_success_count

    total_size_str = f"{total_size_gb:.2f}GB" if total_size_gb >= 1.0 else f"{total_size_mb:.2f}MB"
    success_rate = (total_success_count / total_video_count) * 100 if total_video_count > 0 else 0.0

    completion_text = (
        f"📺 YouTube频道播放列表下载完成\n\n"
        f"📺 频道: {channel_name}\n"
        f"📊 播放列表数量: {len(downloaded_playlists)}\n\n"
        f"已下载的播放列表:\n\n"
    )

    for i, stat in enumerate(playlist_stats, 1):
        completion_text += f"    {i}. {stat['title']} ({stat['video_count']} 集)\n"

    stats_text = (
        f"总计: {total_video_count} 个\n"
        f"✅ 成功: {total_success_count} 个\n"
        f"❌ 失败: {total_failed_count} 个\n"
        f"📊成功率: {success_rate:.1f}%"
    )

    if total_part_count > 0:
        stats_text += f"\n⚠️ 未完成: {total_part_count} 个"
        stats_text += "\n💡 提示: 发现未完成文件，可能需要重新下载"

    completion_text += (
        f"\n📊 下载统计:\n{stats_text}\n\n"
        f"💾 文件总大小: {total_size_str}\n"
        f"📂 保存位置: {channel_path}"
    )

    if message_updater:
        try:
            if asyncio.iscoroutinefunction(message_updater):
                await message_updater(completion_text)
            else:
                message_updater(completion_text)
        except Exception as e:
            logger.warning(f"更新状态消息失败: {e}")

    return {
        "success": True,
        "is_channel": True,
        "channel_title": channel_name,
        "download_path": str(channel_path),
        "playlists_downloaded": downloaded_playlists,
        "playlist_stats": playlist_stats,
        "total_videos": total_videos,
        "total_size_mb": total_size_mb,
        "downloaded_files": downloaded_files,
    }
