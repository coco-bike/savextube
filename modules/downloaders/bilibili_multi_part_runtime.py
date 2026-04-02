# -*- coding: utf-8 -*-
"""B站多P检测运行时逻辑。"""

import re
from urllib.parse import urlparse, parse_qs


def is_bilibili_multi_part_video_runtime(downloader, url: str, *, logger) -> tuple:
    """检查是否为B站多P视频，并提取BV号"""
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if 'bilibili.com' not in host:
            return False, None

        match = re.search(r"/video/([bB][vV][A-Za-z0-9]+)", parsed.path)
        if not match:
            return False, None

        bv_id = match.group(1)
        query = parse_qs(parsed.query)
        if query.get('p'):
            logger.info(f"🔍 检测到B站多P视频: {url}, BV号: {bv_id}")
            return True, bv_id

        multipart_match = re.search(r"/p/(\d+)", parsed.path)
        if multipart_match:
            logger.info(f"🔍 检测到B站多P视频路径: {url}, BV号: {bv_id}")
            return True, bv_id

        return False, None
    except Exception as e:
        logger.warning(f"⚠️ 检测B站多P视频时出错: {e}")
        return False, None
