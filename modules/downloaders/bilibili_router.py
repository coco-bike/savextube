# -*- coding: utf-8 -*-
"""Bilibili 下载路由辅助。"""


async def route_bilibili_download(
    downloader,
    *,
    url: str,
    download_path,
    message_updater=None,
    auto_playlist: bool = False,
    status_message=None,
    context=None,
    detection,
    logger,
):
    """路由处理 B站分支，未命中时返回 handled=False。"""
    if not detection.get("is_bilibili"):
        return {"handled": False}

    is_list = detection.get("is_list", False)
    is_user_lists = detection.get("is_user_lists", False)
    user_uid = detection.get("user_uid")
    is_ugc_season = detection.get("is_ugc_season", False)
    ugc_bv_id = detection.get("ugc_bv_id")
    season_id = detection.get("season_id")
    is_multi_part = detection.get("is_multi_part", False)
    bv_id = detection.get("bv_id")

    logger.info(f"🔍 B站链接检测结果: is_user_lists={is_user_lists}, user_uid={user_uid}")
    logger.info(
        f"🔍 B站链接检测结果: is_ugc_season={is_ugc_season}, ugc_bv_id={ugc_bv_id}, season_id={season_id}"
    )
    logger.info(
        f"🔍 B站链接检测结果: is_multi_part={is_multi_part}, bv_id={bv_id if bv_id else 'N/A'}"
    )

    if is_user_lists:
        logger.info("✅ 检测到B站UP主合集列表页面，开始下载所有视频")
        logger.info(f"🎯 调用 _download_bilibili_user_all_videos(uid={user_uid})")
        result = await downloader._download_bilibili_user_all_videos(user_uid, download_path, message_updater)
        logger.info(f"🎯 UP主下载结果: {result.get('success', False)}")
        return {"handled": True, "result": result}

    if is_ugc_season:
        ugc_playlist_enabled = getattr(downloader.bot, "bilibili_ugc_playlist", True) if hasattr(downloader, "bot") else True
        if ugc_playlist_enabled:
            logger.info("✅ 检测到B站UGC合集，且UGC播放列表开启，下载整个合集")
            return {
                "handled": True,
                "result": await downloader._download_bilibili_ugc_season(
                    ugc_bv_id,
                    season_id,
                    download_path,
                    message_updater,
                ),
            }

        logger.info("✅ 检测到B站UGC合集，但UGC播放列表关闭，只下载当前单集")
        return {
            "handled": True,
            "result": await downloader._download_single_video(
                url,
                download_path,
                message_updater,
                status_message=status_message,
                context=context,
            ),
        }

    if not is_multi_part and not is_list:
        logger.info("✅ 检测到B站单集视频，直接使用通用下载器")
        return {
            "handled": True,
            "result": await downloader._download_single_video(
                url,
                download_path,
                message_updater,
                status_message=status_message,
                context=context,
            ),
        }

    if auto_playlist and (is_multi_part or is_list):
        logger.info("✅ 检测到B站多P视频或合集，且开启多P自动下载全集，使用专门的B站下载器")
        return {
            "handled": True,
            "result": await downloader._download_bilibili_video(
                url,
                download_path,
                message_updater,
                auto_playlist,
                status_message,
                context,
            ),
        }

    logger.info("✅ 检测到B站多P视频或合集，但未开启多P自动下载全集，使用通用下载器下载当前集")
    return {
        "handled": True,
        "result": await downloader._download_single_video(
            url,
            download_path,
            message_updater,
            status_message=status_message,
            context=context,
        ),
    }
