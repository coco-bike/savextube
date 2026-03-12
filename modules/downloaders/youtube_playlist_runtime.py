# -*- coding: utf-8 -*-
"""YouTube播放列表下载执行与结果收集。"""

import asyncio


async def execute_youtube_playlist_download(
    downloader,
    *,
    playlist_id: str,
    playlist_path,
    download_path,
    progress_callback,
    original_url,
    logger,
    yt_dlp_module,
):
    """执行YouTube播放列表下载。"""

    def download_playlist():
        logger.info("🚀 开始下载播放列表...")

        if (
            hasattr(downloader, "bot")
            and hasattr(downloader.bot, "youtube_audio_mode")
            and downloader.bot.youtube_audio_mode
        ):
            music_playlist_path = playlist_path / "music"
            music_playlist_path.mkdir(exist_ok=True)
            actual_path = music_playlist_path
            logger.info("🎵 音频模式：播放列表将保存到music子目录")
        else:
            actual_path = playlist_path

        use_timestamp = (
            hasattr(downloader, "bot")
            and hasattr(downloader.bot, "youtube_timestamp_naming")
            and downloader.bot.youtube_timestamp_naming
        )
        use_id_tags = (
            hasattr(downloader, "bot")
            and hasattr(downloader.bot, "youtube_id_tags")
            and downloader.bot.youtube_id_tags
        )

        if use_timestamp:
            if use_id_tags:
                filename_template = "%(upload_date)s. %(title)s[%(id)s].%(ext)s"
            else:
                filename_template = "%(upload_date)s. %(title)s.%(ext)s"
        else:
            if use_id_tags:
                filename_template = "%(playlist_index)02d. %(title)s[%(id)s].%(ext)s"
            else:
                filename_template = "%(playlist_index)02d. %(title)s.%(ext)s"

        abs_outtmpl = str(actual_path.absolute() / filename_template)
        logger.info(f"🔧 [YT_PLAYLIST_WITH_PROGRESS] outtmpl 绝对路径: {abs_outtmpl}")

        if (
            hasattr(downloader, "bot")
            and hasattr(downloader.bot, "youtube_audio_mode")
            and downloader.bot.youtube_audio_mode
        ):
            format_spec = "bestaudio[ext=mp3]/bestaudio[acodec=mp3]/bestaudio"
            merge_format = "mp3"
            logger.info("🎵 启用YouTube音频模式，播放列表优先下载最高码率MP3")
        else:
            format_spec = None
            merge_format = "mp4"
            logger.info("🎬 YouTube频道下载使用yt-dlp原生最佳格式选择（恢复v0.4-dev3成功方式）")

        logger.info(f"🔧 [PROGRESS_HOOKS] progress_callback是否为None: {progress_callback is None}")
        logger.info(f"🔧 [PROGRESS_HOOKS] progress_callback类型: {type(progress_callback)}")
        base_opts = {
            "outtmpl": abs_outtmpl,
            "merge_output_format": merge_format,
            "ignoreerrors": True,
            "progress_hooks": [progress_callback] if progress_callback else [],
        }
        logger.info(
            f"🔧 [PROGRESS_HOOKS] base_opts中的progress_hooks: {len(base_opts['progress_hooks'])} 个回调"
        )

        if format_spec:
            base_opts["format"] = format_spec
            logger.info(f"🎯 [FORMAT_FIX] 已设置format到base_opts: {format_spec}")

        ydl_opts = downloader._get_enhanced_ydl_opts(base_opts)
        logger.info("🛡️ 使用增强配置，避免PART文件产生")

        if (
            hasattr(downloader, "bot")
            and hasattr(downloader.bot, "youtube_audio_mode")
            and downloader.bot.youtube_audio_mode
        ):
            ydl_opts["postprocessors"] = ydl_opts.get("postprocessors", []) + [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "320",
                }
            ]
            logger.info("🎵 播放列表添加音频转换后处理器：转换为320kbps MP3")

        if (
            hasattr(downloader, "bot")
            and hasattr(downloader.bot, "youtube_thumbnail_download")
            and downloader.bot.youtube_thumbnail_download
        ):
            ydl_opts["writethumbnail"] = True
            if "postprocessors" not in ydl_opts:
                ydl_opts["postprocessors"] = []
            ydl_opts["postprocessors"].append(
                {
                    "key": "FFmpegThumbnailsConvertor",
                    "format": "jpg",
                    "when": "before_dl",
                }
            )
            logger.info("🖼️ 播放列表开启YouTube封面下载（转换为JPG格式）")

        if (
            hasattr(downloader, "bot")
            and hasattr(downloader.bot, "youtube_subtitle_download")
            and downloader.bot.youtube_subtitle_download
        ):
            ydl_opts["writeautomaticsub"] = True
            ydl_opts["writesubtitles"] = True
            ydl_opts["subtitleslangs"] = ["zh", "en"]
            ydl_opts["convertsubtitles"] = "srt"
            ydl_opts["subtitlesformat"] = "best[ext=srt]/srt/best"
            logger.info("📝 播放列表开启YouTube字幕下载（中文、英文，SRT格式）")

        logger.info(f"🔧 [YT_PLAYLIST_WITH_PROGRESS] 最终ydl_opts关键配置: outtmpl={abs_outtmpl}")

        if original_url:
            playlist_url = original_url
            logger.info(f"🔗 使用原始URL: {playlist_url}")
        else:
            playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"
            logger.info(f"📋 使用构造的播放列表URL: {playlist_url}")

        try:
            with yt_dlp_module.YoutubeDL(ydl_opts) as ydl:
                ydl.download([playlist_url])

            logger.info("🔍 检查YouTube播放列表下载完成状态...")
            resume_success = downloader._resume_failed_downloads(
                download_path, playlist_url, max_retries=5
            )

            if not resume_success:
                logger.warning("⚠️ 部分文件下载未完成，但已达到最大重试次数")
            else:
                logger.info("✅ YouTube播放列表所有文件下载完成")

        except Exception as e:
            logger.error(f"❌ YouTube播放列表下载过程中出现错误: {e}")
            logger.info("🔄 尝试断点续传未完成的文件...")
            downloader._resume_part_files(download_path, playlist_url)
            raise

    run_loop = asyncio.get_running_loop()
    await run_loop.run_in_executor(None, download_playlist)
    logger.info("🎉 播放列表下载完成!")


def collect_youtube_playlist_download_result(
    downloader,
    *,
    expected_files,
    playlist_path,
    playlist_title_with_id,
    logger,
):
    """根据预期文件列表收集下载结果。"""
    downloaded_files = []
    total_size_mb = 0
    all_resolutions = set()

    logger.info("🔍 使用预期文件名查找下载的文件")
    for expected_file in expected_files:
        expected_filename = expected_file["filename"]
        expected_path = playlist_path / expected_filename

        actual_path = expected_path
        if expected_path.exists():
            pass
        elif (
            hasattr(downloader, "bot")
            and hasattr(downloader.bot, "youtube_audio_mode")
            and downloader.bot.youtube_audio_mode
        ):
            mp3_path = expected_path.with_suffix(".mp3")
            if mp3_path.exists():
                actual_path = mp3_path
                logger.info(f"🎵 播放列表音频模式：找到转换后的MP3文件: {mp3_path.name}")
            else:
                logger.warning(
                    f"⚠️ 播放列表音频模式：未找到文件: {expected_filename} 或 {mp3_path.name}"
                )
                continue
        else:
            logger.warning(f"⚠️ 未找到预期文件: {expected_filename}")
            continue

        try:
            file_size = actual_path.stat().st_size
            if file_size > 0:
                file_size_mb = file_size / (1024 * 1024)
                total_size_mb += file_size_mb

                media_info = downloader.get_media_info(str(actual_path))
                resolution = media_info.get("resolution", "未知")
                if resolution != "未知":
                    all_resolutions.add(resolution)

                downloaded_files.append(
                    {
                        "filename": actual_path.name,
                        "path": str(actual_path),
                        "size_mb": file_size_mb,
                        "video_title": expected_file["title"],
                    }
                )
                logger.info(f"✅ 找到预期文件: {actual_path.name} ({file_size_mb:.2f}MB)")
            else:
                logger.warning(f"⚠️ 预期文件为空: {actual_path.name}")
        except Exception as e:
            logger.warning(f"⚠️ 无法检查预期文件: {actual_path.name}, 错误: {e}")

    resolution = ", ".join(sorted(all_resolutions)) if all_resolutions else "未知"

    logger.info(f"📊 播放列表找到文件数量: {len(downloaded_files)}/{len(expected_files)}")
    logger.info(f"📊 总大小: {total_size_mb:.2f}MB")

    return {
        "success": True,
        "playlist_title": playlist_title_with_id,
        "video_count": len(downloaded_files),
        "download_path": str(playlist_path),
        "total_size_mb": total_size_mb,
        "size_mb": total_size_mb,
        "resolution": resolution,
        "downloaded_files": downloaded_files,
    }
