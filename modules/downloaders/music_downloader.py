# -*- coding: utf-8 -*-
"""
音乐下载器模块
负责网易云、QQ 音乐、Apple Music、YouTube Music 的下载
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Callable

logger = logging.getLogger(__name__)


class MusicDownloader:
    """音乐下载器"""
    
    def __init__(self, downloader_instance):
        """
        初始化音乐下载器
        
        Args:
            downloader_instance: VideoDownloader 实例
        """
        self.downloader = downloader_instance
    
    async def download_netease(
        self,
        url: str,
        download_path: Path,
        message_updater: Optional[Callable] = None,
        status_message=None,
        context=None
    ) -> Dict[str, Any]:
        """
        下载网易云音乐
        
        Args:
            url: 网易云音乐链接
            download_path: 下载目录
            message_updater: 消息更新回调
            status_message: 状态消息
            context: 上下文
            
        Returns:
            下载结果字典
        """
        logger.info(f"🎵 开始下载网易云音乐：{url}")
        
        try:
            if hasattr(self.downloader, 'netease_downloader') and self.downloader.netease_downloader:
                result = await self.downloader._download_netease_music(
                    url=url,
                    download_path=str(download_path),
                    message_updater=message_updater,
                    status_message=status_message,
                    context=context
                )
                return result
            else:
                return {
                    'success': False,
                    'error': '网易云音乐下载器未初始化',
                    'platform': 'Netease'
                }
                
        except Exception as e:
            logger.error(f"❌ 网易云音乐下载失败：{e}")
            return {
                'success': False,
                'error': str(e),
                'platform': 'Netease',
                'url': url
            }
    
    async def download_qqmusic(
        self,
        url: str,
        download_path: Path,
        message_updater: Optional[Callable] = None,
        status_message=None,
        context=None
    ) -> Dict[str, Any]:
        """下载 QQ 音乐"""
        logger.info(f"🎵 开始下载 QQ 音乐：{url}")
        
        try:
            if hasattr(self.downloader, 'qqmusic_downloader') and self.downloader.qqmusic_downloader:
                result = await self.downloader._download_qqmusic_music(
                    url=url,
                    download_path=str(download_path),
                    message_updater=message_updater,
                    status_message=status_message,
                    context=context
                )
                return result
            else:
                return {
                    'success': False,
                    'error': 'QQ 音乐下载器未初始化',
                    'platform': 'QQMusic'
                }
                
        except Exception as e:
            logger.error(f"❌ QQ 音乐下载失败：{e}")
            return {
                'success': False,
                'error': str(e),
                'platform': 'QQMusic',
                'url': url
            }
    
    async def download_applemusic(
        self,
        url: str,
        download_path: Path,
        message_updater: Optional[Callable] = None,
        status_message=None,
        context=None
    ) -> Dict[str, Any]:
        """下载 Apple Music"""
        logger.info(f"🎵 开始下载 Apple Music: {url}")
        
        try:
            if hasattr(self.downloader, 'apple_music_downloader') and self.downloader.apple_music_downloader:
                result = await self.downloader._download_apple_music(
                    url=url,
                    download_path=str(download_path),
                    message_updater=message_updater,
                    status_message=status_message,
                    context=context
                )
                return result
            else:
                return {
                    'success': False,
                    'error': 'Apple Music 下载器未初始化',
                    'platform': 'AppleMusic'
                }
                
        except Exception as e:
            logger.error(f"❌ Apple Music 下载失败：{e}")
            return {
                'success': False,
                'error': str(e),
                'platform': 'AppleMusic',
                'url': url
            }
    
    async def download_youtubemusic(
        self,
        url: str,
        download_path: Path,
        message_updater: Optional[Callable] = None,
        status_message=None,
        context=None
    ) -> Dict[str, Any]:
        """下载 YouTube Music"""
        logger.info(f"🎵 开始下载 YouTube Music: {url}")
        
        try:
            if hasattr(self.downloader, 'youtube_music_downloader') and self.downloader.youtube_music_downloader:
                result = await self.downloader._download_youtubemusic_music(
                    url=url,
                    download_path=str(download_path),
                    message_updater=message_updater,
                    status_message=status_message,
                    context=context
                )
                return result
            else:
                return {
                    'success': False,
                    'error': 'YouTube Music 下载器未初始化',
                    'platform': 'YouTubeMusic'
                }
                
        except Exception as e:
            logger.error(f"❌ YouTube Music 下载失败：{e}")
            return {
                'success': False,
                'error': str(e),
                'platform': 'YouTubeMusic',
                'url': url
            }


def is_music_platform(url: str) -> bool:
    """检查是否为音乐平台链接"""
    music_domains = [
        'music.163.com',      # 网易云
        'y.qq.com',           # QQ 音乐
        'music.apple.com',    # Apple Music
        'music.youtube.com',  # YouTube Music
    ]
    return any(domain in url for domain in music_domains)
