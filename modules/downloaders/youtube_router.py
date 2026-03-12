# -*- coding: utf-8 -*-
"""YouTube 相关下载路由辅助。"""

from modules.downloaders.youtube_progress import create_single_playlist_progress_callback


async def route_youtube_download(
    downloader,
    *,
    url: str,
    download_path,
    message_updater=None,
    status_message=None,
    loop=None,
    is_youtube_channel: bool,
    channel_url: str,
    is_youtube_playlist: bool,
    playlist_id: str,
    logger,
):
    """路由处理 YouTube 频道/播放列表分支，未命中时返回 handled=False。"""
    if is_youtube_channel:
        logger.info("✅ 检测到YouTube频道播放列表，开始下载所有播放列表")
        return {
            "handled": True,
            "result": await downloader._download_youtube_channel_playlists(
                channel_url,
                download_path,
                message_updater,
                status_message,
                loop,
            ),
        }

    logger.info(f"🔍 检查YouTube播放列表分支: is_youtube_playlist={is_youtube_playlist}")
    if not is_youtube_playlist:
        logger.info("❌ 不是YouTube播放列表，继续其他处理逻辑")
        return {"handled": False}

    logger.info(f"✅ 检测到YouTube播放列表，播放列表ID: {playlist_id}")

    if message_updater:
        playlist_progress_data = {
            "playlist_index": 1,
            "total_playlists": 1,
            "playlist_title": "播放列表",
            "current_video": 0,
            "total_videos": 0,
            "downloaded_videos": 0,
        }

        progress_callback = create_single_playlist_progress_callback(
            playlist_progress_data,
            message_updater=message_updater,
            loop=loop,
            logger=logger,
            make_progress_bar=downloader._make_progress_bar,
        )
        logger.info(f"🔧 为单个播放列表创建进度回调函数: {type(progress_callback)}")
    else:
        progress_callback = None
        logger.info("⚠️ 没有message_updater，跳过进度回调创建")

    return {
        "handled": True,
        "result": await downloader._download_youtube_playlist_with_progress(
            playlist_id,
            download_path,
            progress_callback,
            original_url=url,
        ),
    }
