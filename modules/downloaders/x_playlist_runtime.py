# -*- coding: utf-8 -*-
"""X 播放列表下载执行逻辑。"""

import asyncio
import os


async def execute_x_playlist_download(
    downloader,
    *,
    url,
    download_path,
    progress_callback,
    logger,
    yt_dlp_module,
):
    """执行 X 播放列表下载并处理断点续传。"""

    if (
        hasattr(downloader, "bot")
        and hasattr(downloader.bot, "youtube_id_tags")
        and downloader.bot.youtube_id_tags
    ):
        outtmpl = str(download_path / "%(title)s[%(id)s].%(ext)s")
    else:
        outtmpl = str(download_path / "%(title)s.%(ext)s")

    base_opts = {
        "outtmpl": outtmpl,
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "progress_hooks": [progress_callback],
    }

    ydl_opts = downloader._get_enhanced_ydl_opts(base_opts)
    logger.info("🛡️ 使用增强配置，避免PART文件产生")

    if downloader.is_x_url(url) and downloader.x_cookies_path and os.path.exists(downloader.x_cookies_path):
        ydl_opts["cookiefile"] = downloader.x_cookies_path
        logger.info(f"🍪 为X播放列表添加cookies: {downloader.x_cookies_path}")
    elif downloader.is_x_url(url):
        logger.warning("⚠️ 检测到X播放列表但未设置cookies文件")
        logger.warning("⚠️ NSFW内容需要登录才能下载")
        if downloader.x_cookies_path:
            logger.warning(f"⚠️ X cookies文件不存在: {downloader.x_cookies_path}")
        else:
            logger.warning("⚠️ 未设置X_COOKIES环境变量")
        logger.warning("💡 请设置X_COOKIES环境变量指向cookies文件路径")

    run_loop = asyncio.get_running_loop()
    try:
        await run_loop.run_in_executor(
            None, lambda: yt_dlp_module.YoutubeDL(ydl_opts).download([url])
        )

        logger.info("🔍 检查下载完成状态...")
        resume_success = downloader._resume_failed_downloads(download_path, url, max_retries=5)

        if not resume_success:
            logger.warning("⚠️ 部分文件下载未完成，但已达到最大重试次数")
        else:
            logger.info("✅ 所有文件下载完成")

    except Exception as e:
        logger.error(f"❌ 下载过程中出现错误: {e}")
        logger.info("🔄 尝试断点续传未完成的文件...")
        downloader._resume_part_files(download_path, url)

    await asyncio.sleep(1)
