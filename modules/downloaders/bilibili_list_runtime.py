# -*- coding: utf-8 -*-
"""B站播放列表下载运行时逻辑。"""

import asyncio
from pathlib import Path
from typing import Any, Dict

import yt_dlp


async def download_bilibili_list_runtime(
    downloader, uid: str, list_id: str, download_path: Path, message_updater=None, *, logger
) -> Dict[str, Any]:
    """下载Bilibili播放列表"""
    return await download_bilibili_list_runtime(
        downloader, uid, list_id, download_path, message_updater=message_updater, logger=logger
    )
