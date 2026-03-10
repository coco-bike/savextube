# SaveXTube 模块包
"""
模块化结构：
- modules/url_extractor.py - URL 提取工具
- modules/batch_downloader.py - 批量下载处理器
- modules/message_handler.py - Telegram 消息处理器
- modules/utils/ - 工具函数
- modules/downloaders/ - 平台下载器
"""

from .url_extractor import URLExtractor
from .batch_downloader import BatchDownloadProcessor
from .message_handler import TelegramMessageHandler

__all__ = [
    'URLExtractor',
    'BatchDownloadProcessor',
    'TelegramMessageHandler',
]
