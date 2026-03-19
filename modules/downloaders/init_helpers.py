# -*- coding: utf-8 -*-
"""VideoDownloader 初始化辅助函数。"""

import os
from typing import Any


def _load_multithread_config_from_toml() -> dict:
    """Best-effort TOML reader for multithread settings."""
    try:
        from modules.config.toml_config import load_toml_config
    except ImportError:
        return {}

    config_candidates = [
        os.environ.get("SAVEXTUBE_CONFIG"),
        "/app/config/savextube.toml",
        "savextube.toml",
        "config/savextube.toml",
        "savextube_full.toml",
        "config.toml",
    ]

    for config_path in config_candidates:
        if not config_path:
            continue
        if not os.path.exists(config_path):
            continue
        try:
            config = load_toml_config(config_path)
        except Exception:
            continue
        if isinstance(config, dict) and config.get("multithread"):
            return config.get("multithread", {})
    return {}


def _get_bool_config(env_name: str, toml_section: dict, toml_key: str, default: bool) -> bool:
    env_value = os.environ.get(env_name)
    if env_value is not None:
        return env_value.strip().lower() in {"1", "true", "yes", "on"}

    toml_value = toml_section.get(toml_key)
    if toml_value is None:
        return default
    if isinstance(toml_value, bool):
        return toml_value
    return str(toml_value).strip().lower() in {"1", "true", "yes", "on"}


def _get_int_config(env_name: str, toml_section: dict, toml_key: str, default: int) -> int:
    env_value = os.environ.get(env_name)
    if env_value not in (None, ""):
        return int(env_value)

    toml_value = toml_section.get(toml_key)
    if toml_value in (None, ""):
        return default
    return int(toml_value)


def _get_str_config(env_name: str, toml_section: dict, toml_key: str, default: str) -> str:
    env_value = os.environ.get(env_name)
    if env_value not in (None, ""):
        return env_value

    toml_value = toml_section.get(toml_key)
    if toml_value in (None, ""):
        return default
    return str(toml_value)


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
            mt_config = _load_multithread_config_from_toml()
            mt_threads = _get_int_config("MT_FILE_THREADS", mt_config, "mt_file_threads", 16)
            mt_concurrent = _get_int_config("MT_CONCURRENT_FILES", mt_config, "mt_concurrent_files", 3)
            mt_use_aria2c = _get_bool_config("MT_USE_ARIA2C", mt_config, "mt_use_aria2c", True)
            mt_aria2c_connections = _get_int_config(
                "MT_ARIA2C_CONNECTIONS", mt_config, "mt_aria2c_connections", 16
            )
            mt_aria2c_splits = _get_int_config(
                "MT_ARIA2C_SPLITS", mt_config, "mt_aria2c_splits", 16
            )
            mt_aria2c_min_split_size = _get_str_config(
                "MT_ARIA2C_MIN_SPLIT_SIZE", mt_config, "mt_aria2c_min_split_size", "1M"
            )
            mt_speed_limit = _get_str_config("MT_SPEED_LIMIT", mt_config, "mt_speed_limit", "0")
            mt_retries = _get_int_config("MT_RETRIES", mt_config, "mt_retries", 5)
            mt_timeout = _get_int_config("MT_TIMEOUT", mt_config, "mt_timeout", 60)

            downloader.multithread_downloader = create_downloader(
                file_threads=mt_threads,
                concurrent_files=mt_concurrent,
                use_aria2c=mt_use_aria2c,
                aria2c_connections=mt_aria2c_connections,
                aria2c_splits=mt_aria2c_splits,
                aria2c_min_split_size=mt_aria2c_min_split_size,
                speed_limit=mt_speed_limit,
                retries=mt_retries,
                timeout=mt_timeout,
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
