# -*- coding: utf-8 -*-
"""
Bilibili 下载器模块
负责 B 站视频的下载处理
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Callable

logger = logging.getLogger(__name__)


class BilibiliDownloader:
    """B 站视频下载器"""
    
    def __init__(self, downloader_instance):
        """
        初始化 B 站下载器
        
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
        下载 B 站视频
        
        Args:
            url: B 站视频链接
            download_path: 下载目录
            message_updater: 消息更新回调
            status_message: 状态消息
            context: 上下文
            
        Returns:
            下载结果字典
        """
        logger.info(f"🎬 开始下载 B 站视频：{url}")
        
        try:
            # 使用统一的 yt-dlp 下载方法
            result = await self.downloader._download_with_ytdlp_unified(
                url=url,
                download_path=download_path,
                message_updater=message_updater,
                platform_name="Bilibili",
                content_type="video",
                format_spec=self._get_best_format(),
                cookies_path=self.downloader.b_cookies_path
            )
            
            return result
            
        except Exception as e:
            logger.error(f"❌ B 站视频下载失败：{e}")
            return {
                'success': False,
                'error': str(e),
                'platform': 'Bilibili',
                'url': url
            }
    
    async def download_favorites(
        self,
        fav_url: str,
        download_path: Path,
        message_updater: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        下载 B 站收藏夹视频
        
        Args:
            fav_url: 收藏夹链接
            download_path: 下载目录
            message_updater: 消息更新回调
            
        Returns:
            下载结果字典
        """
        logger.info(f"📚 开始下载 B 站收藏夹：{fav_url}")
        
        try:
            # 使用 B 站收藏夹订阅管理器
            if hasattr(self.downloader, 'bilibili_favsub'):
                result = await self.downloader.bilibili_favsub.manual_download(
                    fav_url=fav_url,
                    download_path=str(download_path)
                )
                return result
            else:
                # 使用 yt-dlp 下载播放列表
                return await self._download_playlist_with_ytdlp(
                    url=fav_url,
                    download_path=download_path,
                    message_updater=message_updater
                )
                
        except Exception as e:
            logger.error(f"❌ B 站收藏夹下载失败：{e}")
            return {
                'success': False,
                'error': str(e),
                'platform': 'Bilibili',
                'url': fav_url
            }
    
    async def download_season(
        self,
        season_url: str,
        download_path: Path,
        message_updater: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        下载 B 站番剧/季度
        
        Args:
            season_url: 季度链接
            download_path: 下载目录
            message_updater: 消息更新回调
            
        Returns:
            下载结果字典
        """
        logger.info(f"📺 开始下载 B 站季度：{season_url}")
        
        try:
            # 使用 yt-dlp 下载季度
            return await self._download_playlist_with_ytdlp(
                url=season_url,
                download_path=download_path,
                message_updater=message_updater,
                is_season=True
            )
            
        except Exception as e:
            logger.error(f"❌ B 站季度下载失败：{e}")
            return {
                'success': False,
                'error': str(e),
                'platform': 'Bilibili',
                'url': season_url
            }
    
    async def download_user_videos(
        self,
        user_url: str,
        download_path: Path,
        message_updater: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        下载 B 站用户所有视频
        
        Args:
            user_url: 用户主页链接
            download_path: 下载目录
            message_updater: 消息更新回调
            
        Returns:
            下载结果字典
        """
        logger.info(f"👤 开始下载 B 站用户视频：{user_url}")
        
        try:
            # 使用 yt-dlp 下载用户视频
            return await self._download_playlist_with_ytdlp(
                url=user_url,
                download_path=download_path,
                message_updater=message_updater,
                is_user_page=True
            )
            
        except Exception as e:
            logger.error(f"❌ B 站用户视频下载失败：{e}")
            return {
                'success': False,
                'error': str(e),
                'platform': 'Bilibili',
                'url': user_url
            }
    
    def _get_best_format(self) -> str:
        """获取 B 站最佳格式选择"""
        # 4K 优先，支持 HDR 和杜比视界
        return "bestvideo[height<=2160]+bestaudio/bestvideo+bestaudio/best"
    
    async def _download_playlist_with_ytdlp(
        self,
        url: str,
        download_path: Path,
        message_updater: Optional[Callable] = None,
        is_season: bool = False,
        is_user_page: bool = False
    ) -> Dict[str, Any]:
        """使用 yt-dlp 下载播放列表"""
        import yt_dlp
        
        try:
            # 配置 yt-dlp 选项
            ydl_opts = {
                'format': self._get_best_format(),
                'outtmpl': str(download_path / '%(title)s.%(ext)s'),
                'quiet': True,
                'no_warnings': True,
                'noplaylist': False,  # 下载播放列表
                'extract_flat': False,
                'cookiefile': self.downloader.b_cookies_path if hasattr(self.downloader, 'b_cookies_path') else None,
            }
            
            if self.downloader.proxy_host:
                ydl_opts['proxy'] = self.downloader.proxy_host
            
            # 执行下载
            loop = asyncio.get_running_loop()
            
            def download_task():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.download([url])
            
            await loop.run_in_executor(None, download_task)
            
            return {
                'success': True,
                'platform': 'Bilibili',
                'url': url,
                'download_path': str(download_path)
            }
            
        except Exception as e:
            logger.error(f"❌ B 站播放列表下载失败：{e}")
            return {
                'success': False,
                'error': str(e),
                'platform': 'Bilibili',
                'url': url
            }


def is_bilibili_url(url: str) -> bool:
    """检查是否为 B 站链接"""
    return 'bilibili.com' in url or 'b23.tv' in url
