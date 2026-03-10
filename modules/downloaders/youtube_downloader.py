# -*- coding: utf-8 -*-
"""
YouTube 下载器模块
负责 YouTube 视频和播放列表的下载
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Callable

logger = logging.getLogger(__name__)


class YouTubeDownloader:
    """YouTube 视频下载器"""
    
    def __init__(self, downloader_instance):
        """
        初始化 YouTube 下载器
        
        Args:
            downloader_instance: VideoDownloader 实例
        """
        self.downloader = downloader_instance
    
    async def download_video(
        self,
        url: str,
        download_path: Path,
        message_updater: Optional[Callable] = None,
        status_message=None,
        context=None
    ) -> Dict[str, Any]:
        """
        下载 YouTube 视频
        
        Args:
            url: YouTube 视频链接
            download_path: 下载目录
            message_updater: 消息更新回调
            status_message: 状态消息
            context: 上下文
            
        Returns:
            下载结果字典
        """
        logger.info(f"🎬 开始下载 YouTube 视频：{url}")
        
        try:
            # 检查是否为音频模式
            if hasattr(self.downloader, 'bot') and hasattr(self.downloader.bot, 'youtube_audio_mode'):
                if self.downloader.bot.youtube_audio_mode:
                    return await self.download_audio(
                        url=url,
                        download_path=download_path,
                        message_updater=message_updater
                    )
            
            # 使用统一的 yt-dlp 下载方法
            result = await self.downloader._download_with_ytdlp_unified(
                url=url,
                download_path=download_path,
                message_updater=message_updater,
                platform_name="YouTube",
                content_type="video",
                format_spec=self._get_video_format(),
                cookies_path=self.downloader.youtube_cookies_path
            )
            
            return result
            
        except Exception as e:
            logger.error(f"❌ YouTube 视频下载失败：{e}")
            return {
                'success': False,
                'error': str(e),
                'platform': 'YouTube',
                'url': url
            }
    
    async def download_audio(
        self,
        url: str,
        download_path: Path,
        message_updater: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        下载 YouTube 音频（MP3）
        
        Args:
            url: YouTube 视频链接
            download_path: 下载目录
            message_updater: 消息更新回调
            
        Returns:
            下载结果字典
        """
        logger.info(f"🎵 开始下载 YouTube 音频：{url}")
        
        try:
            result = await self.downloader._download_with_ytdlp_unified(
                url=url,
                download_path=download_path / "music",
                message_updater=message_updater,
                platform_name="YouTube",
                content_type="audio",
                format_spec=self._get_audio_format()
            )
            
            return result
            
        except Exception as e:
            logger.error(f"❌ YouTube 音频下载失败：{e}")
            return {
                'success': False,
                'error': str(e),
                'platform': 'YouTube',
                'url': url
            }
    
    async def download_playlist(
        self,
        playlist_url: str,
        download_path: Path,
        message_updater: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        下载 YouTube 播放列表
        
        Args:
            playlist_url: 播放列表链接
            download_path: 下载目录
            message_updater: 消息更新回调
            
        Returns:
            下载结果字典
        """
        logger.info(f"📚 开始下载 YouTube 播放列表：{playlist_url}")
        
        try:
            # 使用播放列表下载方法
            result = await self.downloader._download_youtube_playlist_with_progress(
                url=playlist_url,
                download_path=download_path,
                message_updater=message_updater
            )
            
            return result
            
        except Exception as e:
            logger.error(f"❌ YouTube 播放列表下载失败：{e}")
            return {
                'success': False,
                'error': str(e),
                'platform': 'YouTube',
                'url': playlist_url
            }
    
    async def download_channel(
        self,
        channel_url: str,
        download_path: Path,
        message_updater: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        下载 YouTube 频道视频
        
        Args:
            channel_url: 频道链接
            download_path: 下载目录
            message_updater: 消息更新回调
            
        Returns:
            下载结果字典
        """
        logger.info(f"📺 开始下载 YouTube 频道：{channel_url}")
        
        try:
            result = await self.downloader._download_youtube_channel_playlists(
                url=channel_url,
                download_path=download_path,
                message_updater=message_updater
            )
            
            return result
            
        except Exception as e:
            logger.error(f"❌ YouTube 频道下载失败：{e}")
            return {
                'success': False,
                'error': str(e),
                'platform': 'YouTube',
                'url': channel_url
            }
    
    def _get_video_format(self) -> str:
        """获取 YouTube 视频最佳格式"""
        # 4K 优先，支持 HDR 和 VP9
        return "bestvideo[height<=2160]+bestaudio/bestvideo+bestaudio/best"
    
    def _get_audio_format(self) -> str:
        """获取 YouTube 音频最佳格式"""
        # 最高质量 MP3
        return "bestaudio[ext=mp3]/bestaudio[acodec=mp3]/bestaudio"


def is_youtube_url(url: str) -> bool:
    """检查是否为 YouTube 链接"""
    return 'youtube.com' in url or 'youtu.be' in url
