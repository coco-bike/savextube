# -*- coding: utf-8 -*-
"""单视频下载文件定位运行时逻辑。"""

import os
from pathlib import Path

import yt_dlp


def single_video_find_downloaded_file_runtime(
    downloader, download_path: Path, progress_data: dict = None, expected_title: str = None, url: str = None, *, logger
) -> str:
    """单视频下载的文件查找方法"""
    return single_video_find_downloaded_file_runtime(
        downloader,
        download_path,
        progress_data=progress_data,
        expected_title=expected_title,
        url=url,
        logger=logger,
    )
