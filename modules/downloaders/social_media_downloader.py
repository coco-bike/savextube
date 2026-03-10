# -*- coding: utf-8 -*-
"""
社交媒体下载器模块
负责 Twitter/X、Instagram、小红书、抖音、快手等平台的下载
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Callable

logger = logging.getLogger(__name__)


class SocialMediaDownloader:
    """社交媒体下载器"""
    
    def __init__(self, downloader_instance):
        """
        初始化社交媒体下载器
        
        Args:
            downloader_instance: VideoDownloader 实例
        """
        self.downloader = downloader_instance
    
    async def download_x(self, url: str, download_path: Path, message_updater: Optional[Callable] = None) -> Dict[str, Any]:
        """下载 Twitter/X 视频"""
        logger.info(f"🐦 开始下载 X 视频：{url}")
        
        try:
            result = await self.downloader._download_x_video_with_ytdlp(
                url=url,
                message_updater=message_updater
            )
            return result
        except Exception as e:
            logger.error(f"❌ X 视频下载失败：{e}")
            return {'success': False, 'error': str(e), 'platform': 'X'}
    
    async def download_instagram(self, url: str, download_path: Path, message_updater: Optional[Callable] = None) -> Dict[str, Any]:
        """下载 Instagram 内容"""
        logger.info(f"📸 开始下载 Instagram: {url}")
        
        try:
            if hasattr(self.downloader, 'instagram_downloader') and self.downloader.instagram_downloader:
                result = await self.downloader.instagram_downloader.download_post(
                    url=url,
                    download_dir=str(download_path),
                    progress_callback=message_updater
                )
                return result
            else:
                return await self.downloader._download_with_ytdlp_unified(
                    url=url,
                    download_path=download_path,
                    message_updater=message_updater,
                    platform_name="Instagram",
                    content_type="video"
                )
        except Exception as e:
            logger.error(f"❌ Instagram 下载失败：{e}")
            return {'success': False, 'error': str(e), 'platform': 'Instagram'}
    
    async def download_xiaohongshu(self, url: str, download_path: Path, message_updater: Optional[Callable] = None) -> Dict[str, Any]:
        """下载小红书内容"""
        logger.info(f"📕 开始下载小红书：{url}")
        
        try:
            result = await self.downloader._download_xiaohongshu_with_playwright(
                url=url,
                message=None,
                message_updater=message_updater
            )
            return result
        except Exception as e:
            logger.error(f"❌ 小红书下载失败：{e}")
            return {'success': False, 'error': str(e), 'platform': 'Xiaohongshu'}
    
    async def download_douyin(self, url: str, download_path: Path, message_updater: Optional[Callable] = None) -> Dict[str, Any]:
        """下载抖音内容"""
        logger.info(f"🎵 开始下载抖音：{url}")
        
        try:
            result = await self.downloader._download_douyin_with_playwright(
                url=url,
                message=None,
                message_updater=message_updater
            )
            return result
        except Exception as e:
            logger.error(f"❌ 抖音下载失败：{e}")
            return {'success': False, 'error': str(e), 'platform': 'Douyin'}
    
    async def download_kuaishou(self, url: str, download_path: Path, message_updater: Optional[Callable] = None) -> Dict[str, Any]:
        """下载快手内容"""
        logger.info(f"📹 开始下载快手：{url}")
        
        try:
            result = await self.downloader._download_kuaishou_with_playwright(
                url=url,
                message=None,
                message_updater=message_updater
            )
            return result
        except Exception as e:
            logger.error(f"❌ 快手下载失败：{e}")
            return {'success': False, 'error': str(e), 'platform': 'Kuaishou'}


def is_social_media_url(url: str) -> bool:
    """检查是否为社交媒体链接"""
    social_domains = [
        'twitter.com', 'x.com',
        'instagram.com',
        'xiaohongshu.com', 'rednote.com',
        'douyin.com',
        'kwai.com', 'kuaishou.com'
    ]
    return any(domain in url for domain in social_domains)
