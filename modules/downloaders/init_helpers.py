# -*- coding: utf-8 -*-
"""VideoDownloader 初始化辅助函数。"""

import os
from typing import Any


def init_multithread_components(
    downloader,
    *,
    enabled: bool,
    create_downloader,
    batch_processor_cls,
    logger,
) -> None:
    """初始化多线程下载器与批量处理器。"""
    if enabled:
        try:
            mt_threads = int(os.environ.get("MT_FILE_THREADS", "16"))
            mt_concurrent = int(os.environ.get("MT_CONCURRENT_FILES", "3"))
            mt_use_aria2c = os.environ.get("MT_USE_ARIA2C", "true").lower() == "true"

            downloader.multithread_downloader = create_downloader(
                file_threads=mt_threads,
                concurrent_files=mt_concurrent,
                use_aria2c=mt_use_aria2c,
            )
            logger.info(f"✅ 多线程下载器初始化成功（线程数：{mt_threads}, 并发数：{mt_concurrent}）")

            downloader.batch_processor = batch_processor_cls(
                downloader.multithread_downloader,
                max_concurrent=mt_concurrent,
            )
        except Exception as e:
            logger.error(f"❌ 多线程下载器初始化失败：{e}")
            downloader.multithread_downloader = None
            downloader.batch_processor = None
    else:
        downloader.multithread_downloader = None
        downloader.batch_processor = None


def init_modular_downloaders(
    downloader,
    *,
    enabled: bool,
    bilibili_cls,
    youtube_cls,
    music_cls,
    social_cls,
    logger,
) -> None:
    """初始化模块化下载器集合。"""
    if enabled:
        try:
            downloader.bilibili_downloader = bilibili_cls(downloader)
            downloader.youtube_downloader = youtube_cls(downloader)
            downloader.music_downloader = music_cls(downloader)
            downloader.social_downloader = social_cls(downloader)
            logger.info("✅ 模块化下载器初始化成功")
        except Exception as e:
            logger.error(f"❌ 模块化下载器初始化失败：{e}")
            downloader.bilibili_downloader = None
            downloader.youtube_downloader = None
            downloader.music_downloader = None
            downloader.social_downloader = None
    else:
        downloader.bilibili_downloader = None
        downloader.youtube_downloader = None
        downloader.music_downloader = None
        downloader.social_downloader = None


def init_instagram_downloader(downloader, *, logger) -> None:
    """初始化 Instagram 下载器。"""
    try:
        from modules.downloaders.instagram_downloader import InstagramPicDownloaderSimple

        downloader.instagram_downloader = InstagramPicDownloaderSimple(
            cookies_path=downloader.instagram_cookies_path or "/app/cookies/instagram_cookies.txt"
        )
        logger.info("✅ Instagram 下载器初始化成功")
    except ImportError as e:
        logger.warning(f"⚠️ Instagram 下载器导入失败: {e}")
        downloader.instagram_downloader = None
    except Exception as e:
        logger.error(f"❌ Instagram 下载器初始化失败: {e}")
        downloader.instagram_downloader = None


def init_apple_music_downloader(downloader, *, logger) -> None:
    """初始化 Apple Music 下载器。"""
    if not downloader.channel_switches.get("apple_music", True):
        logger.info("⏭️ Apple Music 渠道已禁用，跳过下载器初始化")
        downloader.apple_music_downloader = None
        return

    try:
        use_amd = os.environ.get("AMDP", "").lower() == "true"
        output_dir = str(downloader.apple_music_download_path)
        os.makedirs(output_dir, exist_ok=True)

        if use_amd:
            from modules.downloaders.applemusic_downloader_plus import AppleMusicDownloaderPlus

            downloader.apple_music_downloader = AppleMusicDownloaderPlus(
                output_dir=output_dir,
                cookies_path=downloader.apple_music_cookies_path,
            )
            logger.info("✅ Apple Music Plus 下载器(AMD)初始化成功")
        else:
            from modules.downloaders.applemusic_downloader import AppleMusicDownloader

            native_downloader = AppleMusicDownloader(
                output_dir=output_dir,
                cookies_path=downloader.apple_music_cookies_path,
            )
            downloader.apple_music_downloader = (
                native_downloader if native_downloader.gamdl_available else None
            )
            if downloader.apple_music_downloader:
                logger.info("✅ Apple Music 下载器 (GAMDL) 初始化成功")
            else:
                logger.warning("⚠️ Apple Music 下载器初始化失败：gamdl 不可用")
    except ImportError as e:
        logger.error(f"❌ Apple Music 下载器导入失败: {e}")
        downloader.apple_music_downloader = None
    except Exception as e:
        logger.error(f"❌ Apple Music 下载器初始化失败: {e}")
        downloader.apple_music_downloader = None


def init_music_downloaders(
    downloader,
    *,
    netease_cls,
    netease_adapter_cls,
    netease_module_path: str,
    qqmusic_cls,
    qqmusic_module_path: str,
    youtubemusic_cls,
    youtubemusic_module_path: str,
    logger,
) -> None:
    """初始化网易云、QQ 音乐和 YouTube Music 下载器。"""
    try:
        if netease_cls is None:
            raise ImportError("neteasecloud_music 模块不可用")
        base_downloader = netease_cls(bot=downloader)
        downloader.netease_downloader = netease_adapter_cls(base_downloader)
        logger.info(f"🎵 网易云音乐下载器初始化成功 (模块: {netease_module_path})")
    except Exception as e:
        logger.warning(f"网易云音乐下载器初始化失败: {e}")
        downloader.netease_downloader = None

    try:
        if qqmusic_cls is None:
            raise ImportError("qqmusic_downloader 模块不可用")
        downloader.qqmusic_downloader = qqmusic_cls(bot=downloader)
        logger.info(f"🎵 QQ音乐下载器初始化成功 (模块: {qqmusic_module_path})")
    except Exception as e:
        logger.warning(f"QQ音乐下载器初始化失败: {e}")
        downloader.qqmusic_downloader = None

    try:
        if youtubemusic_cls is None:
            raise ImportError("youtubemusic_downloader 模块不可用")
        downloader.youtubemusic_downloader = youtubemusic_cls(bot=downloader)
        logger.info(f"🎵 YouTube Music下载器初始化成功 (模块: {youtubemusic_module_path})")
    except Exception as e:
        logger.warning(f"YouTube Music下载器初始化失败: {e}")
        downloader.youtubemusic_downloader = None
