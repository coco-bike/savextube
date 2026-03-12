# -*- coding: utf-8 -*-
"""下载平台识别与上下文构建。"""

import re


def build_download_context(downloader, *, url: str, auto_playlist: bool, logger):
    """识别 URL 平台并构建下载上下文。"""
    logger.info(f"🔍 download_video 开始处理URL: {url}")
    logger.info(f"🔍 自动下载全集模式: {'开启' if auto_playlist else '关闭'}")

    is_bilibili = downloader.is_bilibili_url(url)
    is_list, uid, list_id = downloader.is_bilibili_list_url(url)
    is_user_lists, user_uid = downloader.is_bilibili_user_lists_url(url)
    is_ugc_season, ugc_bv_id, season_id = downloader.is_bilibili_ugc_season(url)
    is_multi_part, bv_id = downloader.is_bilibili_multi_part_video(url)

    logger.info(f"🔍 即将调用is_youtube_playlist_url检查: {url}")
    is_youtube_playlist, playlist_id = downloader.is_youtube_playlist_url(url)
    logger.info(
        f"🎯 is_youtube_playlist_url返回结果: is_playlist={is_youtube_playlist}, playlist_id={playlist_id}"
    )

    is_mix_playlist_disabled = False
    if not is_youtube_playlist and "list=RDMM" in url:
        logger.info("🎵 检测到Mix播放列表但功能关闭，清理URL中的播放列表参数")
        original_url = url
        url = re.sub(r"[&?]list=[^&]*", "", url)
        url = re.sub(r"[&?]index=[^&]*", "", url)
        url = re.sub(r"[&]{2,}", "&", url)
        url = re.sub(r"[?&]$", "", url)
        logger.info(f"🔗 原始URL: {original_url}")
        logger.info(f"🔗 清理后URL: {url}")
        is_mix_playlist_disabled = True

    is_youtube_channel, channel_url = downloader.is_youtube_channel_playlists_url(url)
    logger.info(
        f"🔍 YouTube频道识别结果: is_youtube_channel={is_youtube_channel}, channel_url={channel_url}"
    )

    is_x = downloader.is_x_url(url)
    is_telegraph = downloader.is_telegraph_url(url)
    is_douyin = downloader.is_douyin_url(url)
    is_kuaishou = downloader.is_kuaishou_url(url)
    is_facebook = downloader.is_facebook_url(url)
    is_netease = downloader.is_netease_url(url)
    platform = downloader.get_platform_name(url)

    logger.info("🔍 URL识别结果:")
    logger.info(f"  - is_bilibili_url: {is_bilibili}")
    logger.info(f"  - is_bilibili_list_url: {is_list}, uid: {uid}, list_id: {list_id}")
    logger.info(f"  - is_bilibili_user_lists_url: {is_user_lists}, uid: {user_uid}")
    logger.info(
        f"  - is_bilibili_ugc_season: {is_ugc_season}, bv_id: {ugc_bv_id}, season_id: {season_id}"
    )
    logger.info(f"  - is_bilibili_multi_part: {is_multi_part}, bv_id: {bv_id}")
    logger.info(f"  - is_youtube_playlist: {is_youtube_playlist}, playlist_id: {playlist_id}")
    logger.info(
        f"  - is_youtube_channel: {is_youtube_channel}, channel_url: {channel_url if is_youtube_channel else 'None'}"
    )
    logger.info(f"  - is_x_url: {is_x}")
    logger.info(f"  - is_telegraph_url: {is_telegraph}")
    logger.info(f"  - is_netease_url: {is_netease}")
    logger.info(f"  - platform: {platform}")

    download_path = downloader.get_download_path(url)
    logger.info(f"📁 获取到的下载路径: {download_path}")

    return {
        "url": url,
        "download_path": download_path,
        "platform": platform,
        "is_mix_playlist_disabled": is_mix_playlist_disabled,
        "is_bilibili": is_bilibili,
        "is_list": is_list,
        "uid": uid,
        "list_id": list_id,
        "is_user_lists": is_user_lists,
        "user_uid": user_uid,
        "is_ugc_season": is_ugc_season,
        "ugc_bv_id": ugc_bv_id,
        "season_id": season_id,
        "is_multi_part": is_multi_part,
        "bv_id": bv_id,
        "is_youtube_playlist": is_youtube_playlist,
        "playlist_id": playlist_id,
        "is_youtube_channel": is_youtube_channel,
        "channel_url": channel_url,
        "is_x": is_x,
        "is_telegraph": is_telegraph,
        "is_douyin": is_douyin,
        "is_kuaishou": is_kuaishou,
        "is_facebook": is_facebook,
        "is_netease": is_netease,
    }
