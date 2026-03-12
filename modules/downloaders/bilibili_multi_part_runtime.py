# -*- coding: utf-8 -*-
"""B站多P检测运行时逻辑。"""

import re

import yt_dlp


def is_bilibili_multi_part_video_runtime(downloader, url: str, *, logger) -> tuple:
    """检查是否为B站多P视频，并提取BV号"""
    return is_bilibili_multi_part_video_runtime(downloader, url, logger=logger)
