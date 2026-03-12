# -*- coding: utf-8 -*-
"""QQ音乐下载器兼容实现。

说明：当前仓库缺少完整 QQMusicDownloader 实现时，提供一个最小可用占位，
避免 main.py 导入链中断，并返回明确错误信息。
"""

from typing import Any, Dict


class QQMusicDownloader:
    """QQ音乐下载器兼容占位类。"""

    def __init__(self, bot=None):
        self.bot = bot

    def download_by_url(
        self,
        url: str,
        download_dir: str = "./downloads/qqmusic",
        quality: str = "best",
        progress_callback=None,
    ) -> Dict[str, Any]:
        return {
            "success": False,
            "error": "当前环境未提供完整 qqmusic_downloader 实现，请补充对应模块后重试。",
            "platform": "QQMusic",
            "url": url,
            "download_path": download_dir,
            "quality": quality,
        }
