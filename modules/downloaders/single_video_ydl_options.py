# -*- coding: utf-8 -*-
"""单视频下载的 ydl 基础参数构建。"""

import os


def build_single_video_ydl_options(downloader, *, url: str, outtmpl: str, no_playlist: bool, logger):
    """构建单视频下载基础 ydl 配置（不含进度回调）。"""
    if "instagram.com" in url.lower():
        logger.info("🎯 Instagram检测：设置最高质量格式选择")

        if hasattr(downloader, "instagram_downloader") and downloader.instagram_downloader:
            logger.info("📱 使用专门的 Instagram 下载器")
            format_spec = (
                "bestvideo+bestaudio/bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
                "bestvideo+bestaudio[ext=m4a]/best[height>=1080]/best"
            )
            merge_format = "mp4"
        else:
            logger.info("📱 使用 yt-dlp 处理 Instagram")
            format_spec = (
                "bestvideo+bestaudio/bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
                "bestvideo+bestaudio[ext=m4a]/best[height>=1080]/best"
            )
            merge_format = "mp4"

        if (
            hasattr(downloader, "instagram_cookies_path")
            and downloader.instagram_cookies_path
            and os.path.exists(downloader.instagram_cookies_path)
        ):
            logger.info(f"🍪 Instagram将使用cookies: {downloader.instagram_cookies_path}")
        else:
            logger.warning("⚠️ 检测到Instagram链接但未设置cookies文件")
            logger.warning("💡 Instagram大部分内容需要登录才能访问")
            if hasattr(downloader, "instagram_cookies_path") and downloader.instagram_cookies_path:
                logger.warning(f"⚠️ Instagram cookies文件不存在: {downloader.instagram_cookies_path}")
            else:
                logger.warning("⚠️ 未设置INSTAGRAM_COOKIES环境变量")
            logger.warning("📝 请设置INSTAGRAM_COOKIES环境变量指向cookies文件")
    elif (
        downloader.is_youtube_url(url)
        and hasattr(downloader, "bot")
        and hasattr(downloader.bot, "youtube_audio_mode")
        and downloader.bot.youtube_audio_mode
    ):
        format_spec = "bestaudio[ext=mp3]/bestaudio[acodec=mp3]/bestaudio"
        merge_format = "mp3"
        logger.info("🎵 启用YouTube音频模式，优先下载最高码率MP3")
    else:
        if downloader.is_bilibili_url(url):
            format_spec = downloader._get_bilibili_best_format()
            logger.info("🎯 检测到B站URL，使用4K优先格式策略")
            logger.info(f"🔧 设置的格式字符串: {format_spec}")

            member_status = downloader.check_bilibili_member_status()
            logger.info(f"🔍 B站会员状态: {member_status['message']}")

            try:
                debug_result = downloader.debug_bilibili_formats(url)
                if debug_result["success"]:
                    max_height = debug_result["max_height"]
                    logger.info(f"🔍 B站视频最高分辨率: {max_height}p")
                    if max_height >= 2160:
                        logger.info("🎉 该视频支持4K下载（需要B站大会员）")
                        logger.info("💡 提示：要下载4K，需要B站大会员并正确设置cookies")
                    elif max_height >= 1440:
                        logger.info("✅ 该视频支持2K下载（需要B站大会员）")
                        logger.info("💡 提示：要下载2K，需要B站大会员并正确设置cookies")
                    elif max_height >= 1080:
                        logger.info("✅ 该视频支持1080p下载（需要B站会员）")
                        logger.info("💡 提示：要下载1080p，需要B站大会员并正确设置cookies")
                    elif max_height >= 720:
                        logger.info(f"✅ 该视频支持 {max_height}p 下载（非会员最高质量）")
                    else:
                        logger.warning(f"⚠️ 该视频最高分辨率仅 {max_height}p")
            except Exception as e:
                logger.warning(f"调试B站格式失败: {e}")
        elif downloader.is_youtube_url(url):
            format_spec = (
                "bestvideo[height>=2160]+bestaudio/"
                "bestvideo[height>=1440]+bestaudio/"
                "bestvideo[height>=1080]+bestaudio/"
                "bestvideo+bestaudio/best"
            )
            logger.info("🎬 检测到YouTube URL，使用4K优先格式策略 (2160p->1440p->1080p)")
        elif downloader.is_toutiao_url(url):
            format_spec = "bestvideo+bestaudio/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[height>=1080]/best"
            logger.info("📰 检测到头条视频 URL，使用高质量格式策略")
        else:
            format_spec = (
                "bestvideo+bestaudio/bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
                "bestvideo+bestaudio[ext=m4a]/best[height>=1080]/best"
            )
            logger.info("🌐 其他平台，使用通用1080p优先格式策略")
        merge_format = "mp4"

    if no_playlist:
        noplaylist_setting = True
        logger.info("🎵 Mix播放列表功能关闭，URL已清理，使用单个视频模式")
    elif (
        downloader.is_youtube_url(url)
        and hasattr(downloader, "bot")
        and hasattr(downloader.bot, "youtube_mix_playlist")
        and downloader.bot.youtube_mix_playlist
    ):
        noplaylist_setting = False
        logger.info("🎵 YouTube Mix播放列表下载已开启，允许下载播放列表内容")
    else:
        noplaylist_setting = True
        logger.info("🎬 使用单个视频模式，不下载播放列表内容")

    return {
        "outtmpl": outtmpl,
        "format": format_spec,
        "merge_output_format": merge_format,
        "noplaylist": noplaylist_setting,
        "nocheckcertificate": True,
        # 单视频必须显式暴露失败，避免误判成功后再进入“找不到文件”
        "ignoreerrors": False,
        "logtostderr": True,
        "quiet": False,
        "no_warnings": False,
        "default_search": "auto",
        "source_address": "0.0.0.0",
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        },
        "retries": 5,
        "fragment_retries": 5,
        "skip_unavailable_fragments": True,
        "keepvideo": False,
        "prefer_ffmpeg": True,
        "no_download_archive": True,
        "force_download": True,
        "socket_timeout": 30,
        "progress": True,
        "progress_hooks": [],
        "hls_use_mpegts": False,
        "hls_prefer_native": True,
        "concurrent_fragment_downloads": 3,
        "buffersize": 1024,
        "http_chunk_size": 10485760,
    }
