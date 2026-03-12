# -*- coding: utf-8 -*-
"""渠道路径初始化与目录创建工具。"""

from pathlib import Path
from typing import Dict


def build_channel_paths(base_download_path: Path) -> Dict[str, Path]:
    """基于下载根目录生成渠道路径映射。"""
    return {
        "x": base_download_path / "X",
        "youtube": base_download_path / "YouTube",
        "xvideos": base_download_path / "Xvideos",
        "pornhub": base_download_path / "Pornhub",
        "bilibili": base_download_path / "Bilibili",
        "music": base_download_path / "Music",
        "telegram": base_download_path / "Telegram",
        "telegraph": base_download_path / "Telegraph",
        "douyin": base_download_path / "Douyin",
        "kuaishou": base_download_path / "Kuaishou",
        "toutiao": base_download_path / "Toutiao",
        "facebook": base_download_path / "Facebook",
        "xiaohongshu": base_download_path / "Xiaohongshu",
        "weibo": base_download_path / "Weibo",
        "instagram": base_download_path / "Instagram",
        "tiktok": base_download_path / "TikTok",
        "netease": base_download_path / "NeteaseCloudMusic",
        "qqmusic": base_download_path / "QQMusic",
        "youtubemusic": Path("/downloads/YouTubeMusic"),
        "apple_music": base_download_path / "AppleMusic",
    }


def attach_channel_paths(downloader, channel_paths: Dict[str, Path]) -> None:
    """将渠道路径绑定到 VideoDownloader 实例属性。"""
    downloader.x_download_path = channel_paths["x"]
    downloader.youtube_download_path = channel_paths["youtube"]
    downloader.xvideos_download_path = channel_paths["xvideos"]
    downloader.pornhub_download_path = channel_paths["pornhub"]
    downloader.bilibili_download_path = channel_paths["bilibili"]
    downloader.music_download_path = channel_paths["music"]
    downloader.telegram_download_path = channel_paths["telegram"]
    downloader.telegraph_download_path = channel_paths["telegraph"]
    downloader.douyin_download_path = channel_paths["douyin"]
    downloader.kuaishou_download_path = channel_paths["kuaishou"]
    downloader.toutiao_download_path = channel_paths["toutiao"]
    downloader.facebook_download_path = channel_paths["facebook"]
    downloader.xiaohongshu_download_path = channel_paths["xiaohongshu"]
    downloader.weibo_download_path = channel_paths["weibo"]
    downloader.instagram_download_path = channel_paths["instagram"]
    downloader.tiktok_download_path = channel_paths["tiktok"]
    downloader.netease_download_path = channel_paths["netease"]
    downloader.qqmusic_download_path = channel_paths["qqmusic"]
    downloader.youtubemusic_download_path = channel_paths["youtubemusic"]
    downloader.apple_music_download_path = channel_paths["apple_music"]


def create_enabled_channel_dirs(channel_paths: Dict[str, Path], channel_switches: Dict[str, bool], logger) -> None:
    """仅为启用的渠道创建目录。"""
    for channel_key, path in channel_paths.items():
        enabled = channel_switches.get(channel_key, True)
        if enabled:
            path.mkdir(parents=True, exist_ok=True)
        else:
            logger.info(f"⏭️ 渠道已禁用，跳过创建目录: {channel_key} -> {path}")

    logger.info(f"X 下载路径: {channel_paths['x']}")
    logger.info(f"YouTube 下载路径: {channel_paths['youtube']}")
    logger.info(f"Xvideos 下载路径: {channel_paths['xvideos']}")
    logger.info(f"Pornhub 下载路径: {channel_paths['pornhub']}")
    logger.info(f"Bilibili 下载路径: {channel_paths['bilibili']}")
    logger.info(f"音乐下载路径: {channel_paths['music']}")
    logger.info(f"Telegram 文件下载路径: {channel_paths['telegram']}")
    logger.info(f"Telegraph 文件下载路径: {channel_paths['telegraph']}")
    logger.info(f"抖音下载路径: {channel_paths['douyin']}")
    logger.info(f"快手下载路径: {channel_paths['kuaishou']}")
    logger.info(f"Facebook下载路径: {channel_paths['facebook']}")
    logger.info(f"小红书下载路径: {channel_paths['xiaohongshu']}")
    logger.info(f"微博下载路径: {channel_paths['weibo']}")
    logger.info(f"Instagram下载路径: {channel_paths['instagram']}")
    logger.info(f"TikTok下载路径: {channel_paths['tiktok']}")
    logger.info(f"网易云音乐下载路径: {channel_paths['netease']}")
    logger.info(f"QQ音乐下载路径: {channel_paths['qqmusic']}")
    logger.info(f"YouTube Music下载路径: {channel_paths['youtubemusic']}")
    logger.info(f"Apple Music下载路径: {channel_paths['apple_music']}")
