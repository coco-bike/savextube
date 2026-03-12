'''
Author: coco-bike 444503829@qq.com
Date: 2026-03-12 14:25:35
LastEditors: coco-bike 444503829@qq.com
LastEditTime: 2026-03-12 14:44:59
FilePath: \savextube\modules\downloaders\final_fallback.py
Description: 
'''
# -*- coding: utf-8 -*-
"""下载路由的末端校验与兜底处理。"""


async def handle_final_fallback(
    downloader,
    *,
    url: str,
    download_path,
    message_updater=None,
    status_message=None,
    context=None,
    platform: str,
    is_mix_playlist_disabled: bool,
    logger,
):
    """处理末端平台校验与单视频兜底下载。"""
    if downloader.is_weibo_url(url) or downloader.is_instagram_url(url) or downloader.is_tiktok_url(url):
        logger.info(f"✅ 检测到{platform}视频，使用通用下载器")
        return await downloader._download_single_video(
            url,
            download_path,
            message_updater,
            status_message=status_message,
            context=context,
        )

    if downloader.is_bilibili_url(url) and "space.bilibili.com" in url:
        logger.error(f"❌ B站UP主空间URL不应该fallback到单个视频下载: {url}")
        return {"success": False, "error": "B站UP主空间URL处理失败，请检查URL格式或重试"}

    if downloader.is_netease_url(url):
        logger.error(f"❌ 网易云音乐链接不应该fallback到单个视频下载: {url}")
        return {"success": False, "error": "网易云音乐链接处理失败，请检查URL格式或重试"}

    if downloader.is_qqmusic_url(url):
        logger.error(f"❌ QQ音乐链接不应该fallback到单个视频下载: {url}")
        return {"success": False, "error": "QQ音乐链接处理失败，请检查URL格式或重试"}

    logger.info(f"✅ 使用通用下载器处理单个视频，平台: {platform}")
    logger.info(f"🔍 最终fallback: URL={url}")
    return await downloader._download_single_video(
        url,
        download_path,
        message_updater,
        no_playlist=is_mix_playlist_disabled,
        status_message=status_message,
        context=context,
    )
