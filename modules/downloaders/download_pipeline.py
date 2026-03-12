# -*- coding: utf-8 -*-
"""下载路由流水线执行。"""

from modules.downloaders.bilibili_router import route_bilibili_download
from modules.downloaders.final_fallback import handle_final_fallback
from modules.downloaders.music_router import route_music_download
from modules.downloaders.social_router import route_social_download
from modules.downloaders.youtube_router import route_youtube_download


async def run_download_pipeline(
    downloader,
    *,
    url: str,
    download_path,
    message_updater=None,
    auto_playlist: bool = False,
    status_message=None,
    loop=None,
    context=None,
    detection: dict,
    logger,
):
    """依次执行社媒、音乐、YouTube、B站及最终 fallback 路由。"""
    social_route_result = await route_social_download(
        downloader,
        url=url,
        download_path=download_path,
        message_updater=message_updater,
        status_message=status_message,
        context=context,
        detection={
            "is_x": detection["is_x"],
            "is_telegraph": detection["is_telegraph"],
            "is_douyin": detection["is_douyin"],
            "is_kuaishou": detection["is_kuaishou"],
            "is_facebook": detection["is_facebook"],
        },
        logger=logger,
    )
    if social_route_result.get("handled"):
        return social_route_result["result"]

    music_route_result = await route_music_download(
        downloader,
        url=url,
        download_path=download_path,
        message_updater=message_updater,
        status_message=status_message,
        context=context,
        detection={"is_netease": detection["is_netease"]},
        logger=logger,
    )
    if music_route_result.get("handled"):
        return music_route_result["result"]

    youtube_route_result = await route_youtube_download(
        downloader,
        url=url,
        download_path=download_path,
        message_updater=message_updater,
        status_message=status_message,
        loop=loop,
        is_youtube_channel=detection["is_youtube_channel"],
        channel_url=detection["channel_url"],
        is_youtube_playlist=detection["is_youtube_playlist"],
        playlist_id=detection["playlist_id"],
        logger=logger,
    )
    if youtube_route_result.get("handled"):
        return youtube_route_result["result"]

    bilibili_route_result = await route_bilibili_download(
        downloader,
        url=url,
        download_path=download_path,
        message_updater=message_updater,
        auto_playlist=auto_playlist,
        status_message=status_message,
        context=context,
        detection={
            "is_bilibili": detection["is_bilibili"],
            "is_list": detection["is_list"],
            "is_user_lists": detection["is_user_lists"],
            "user_uid": detection["user_uid"],
            "is_ugc_season": detection["is_ugc_season"],
            "ugc_bv_id": detection["ugc_bv_id"],
            "season_id": detection["season_id"],
            "is_multi_part": detection["is_multi_part"],
            "bv_id": detection["bv_id"],
        },
        logger=logger,
    )
    if bilibili_route_result.get("handled"):
        return bilibili_route_result["result"]

    return await handle_final_fallback(
        downloader,
        url=url,
        download_path=download_path,
        message_updater=message_updater,
        status_message=status_message,
        context=context,
        platform=detection["platform"],
        is_mix_playlist_disabled=detection["is_mix_playlist_disabled"],
        logger=logger,
    )
