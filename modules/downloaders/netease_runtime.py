# -*- coding: utf-8 -*-
"""网易云音乐下载运行时逻辑。"""

import asyncio


async def download_netease_music_runtime(
    downloader,
    url: str,
    download_path: str,
    message_updater=None,
    status_message=None,
    context=None,
    *,
    logger,
    netease_music_progress_hook,
) -> dict:
    """下载网易云音乐"""
    return await download_netease_music_runtime(
        downloader,
        url,
        download_path,
        message_updater=message_updater,
        status_message=status_message,
        context=context,
        logger=logger,
        netease_music_progress_hook=netease_music_progress_hook,
    )
