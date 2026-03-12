# -*- coding: utf-8 -*-
"""单视频下载输出模板构建。"""


def build_single_video_outtmpl(downloader, *, url: str, download_path, title: str, logger):
    """根据平台与配置构建 outtmpl。"""
    if downloader.is_youtube_url(url):
        if (
            hasattr(downloader, "bot")
            and hasattr(downloader.bot, "youtube_audio_mode")
            and downloader.bot.youtube_audio_mode
        ):
            music_path = download_path / "music"
            music_path.mkdir(exist_ok=True)
            if (
                hasattr(downloader, "bot")
                and hasattr(downloader.bot, "youtube_id_tags")
                and downloader.bot.youtube_id_tags
            ):
                outtmpl = str(music_path.absolute() / f"{title}[%(id)s].%(ext)s")
            else:
                outtmpl = str(music_path.absolute() / f"{title}.%(ext)s")
            logger.info("🎵 音频模式：文件将保存到YouTube/music目录")
            return outtmpl

        if (
            hasattr(downloader, "bot")
            and hasattr(downloader.bot, "youtube_id_tags")
            and downloader.bot.youtube_id_tags
        ):
            return str(download_path.absolute() / f"{title}[%(id)s].%(ext)s")
        return str(download_path.absolute() / f"{title}.%(ext)s")

    if downloader.is_x_url(url):
        return str(download_path.absolute() / f"{title}.%(ext)s")

    if "instagram.com" in url.lower():
        optimized_title = downloader._optimize_instagram_filename(title)
        logger.info(f"🎨 Instagram优化文件名: {optimized_title}")
        return str(download_path.absolute() / f"{optimized_title}.%(ext)s")

    return str(download_path.absolute() / f"{title}.%(ext)s")
