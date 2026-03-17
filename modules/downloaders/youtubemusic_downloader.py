#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube Music Downloader
基于 yt-dlp 实现的 YouTube Music 音乐下载器
支持单曲、专辑和播放列表下载，输出高质量 M4A 音频文件
集成到 main.py 中使用，参考网易云下载器的实现模式
"""

import os
import re
import json
import time
import logging
import urllib.parse
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any, Union

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('youtube_music_downloader')

# 导入音乐元数据处理模块
try:
    from .music_metadata import MusicMetadataManager
    METADATA_AVAILABLE = True
    logger.info("✅ 成功导入音乐元数据模块（包内导入）")
except ImportError:
    try:
        from music_metadata import MusicMetadataManager
        METADATA_AVAILABLE = True
        logger.info("✅ 成功导入音乐元数据模块（兼容导入）")
    except ImportError as e:
        METADATA_AVAILABLE = False
        logger.warning(f"⚠️ 音乐元数据模块不可用，将跳过元数据处理: {e}")
    except Exception as e:
        METADATA_AVAILABLE = False
        logger.error(f"❌ 导入音乐元数据模块时出错: {e}")
except Exception as e:
    METADATA_AVAILABLE = False
    logger.error(f"❌ 导入音乐元数据模块时出错: {e}")

try:
    import yt_dlp
    YT_DLP_AVAILABLE = True
    logger.info(f"✅ 成功导入 yt-dlp 版本: {yt_dlp.version.__version__}")
except ImportError as e:
    YT_DLP_AVAILABLE = False
    logger.warning(f"⚠️ yt-dlp 不可用: {e}")
    logger.warning("📋 请安装 yt-dlp: pip install yt-dlp 或使用虚拟环境")

class YouTubeMusicDownloader:
    """YouTube Music 下载器 - 集成到 main.py 中使用"""
    
    def __init__(self, bot=None):
        """初始化 YouTube Music 下载器"""
        self.bot = bot  # 保存bot引用，用于访问配置
        
        # 初始化音乐元数据管理器
        if METADATA_AVAILABLE:
            try:
                self.metadata_manager = MusicMetadataManager()
                logger.info("✅ 音乐元数据管理器初始化成功")
            except Exception as e:
                logger.error(f"❌ 音乐元数据管理器初始化失败: {e}")
                self.metadata_manager = None
        else:
            self.metadata_manager = None
        
        # 设置cookies路径
        self.cookies_path = self._get_cookies_path()
        
        # 下载配置
        self.concurrent_downloads = int(os.getenv('YTM_CONCURRENT_DOWNLOADS', '3'))
        self.max_retries = int(os.getenv('YTM_MAX_RETRIES', '3'))
        self.timeout = int(os.getenv('YTM_TIMEOUT', '300'))
        
        # 文件命名配置
        self.enable_id_tags = os.getenv('YTM_ENABLE_ID_TAGS', 'false').lower() in ['true', '1', 'yes', 'on']
        self.audio_quality = os.getenv('YTM_AUDIO_QUALITY', 'best')  # best, 320k, 256k, 128k
        
        # 下载统计
        self.download_stats = {
            'total_files': 0,
            'downloaded_files': 0,
            'total_size': 0,
            'downloaded_songs': []
        }
        
        logger.info(f"🎵 YouTube Music 下载器初始化完成")
        logger.info(f"🔧 配置: 并发={self.concurrent_downloads}, 重试={self.max_retries}, 超时={self.timeout}s")
        logger.info(f"🎯 音质: {self.audio_quality}, ID标签: {self.enable_id_tags}")
    
    def _get_cookies_path(self) -> Optional[str]:
        """获取 YouTube cookies 文件路径"""
        possible_paths = [
            "YouTube/youtube_cookies.txt",
            "youtube_cookies.txt",
            "cookies/youtube_cookies.txt"
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                logger.info(f"✅ 找到 YouTube cookies 文件: {path}")
                return path
        
        logger.warning("⚠️ 未找到 YouTube cookies 文件，某些受限内容可能无法下载")
        return None
    
    def is_youtube_music_url(self, url: str) -> bool:
        """检查是否为 YouTube Music URL"""
        youtube_music_patterns = [
            r'music\.youtube\.com',
            r'youtube\.com.*[&?]list=',  # YouTube 播放列表
            r'youtu\.be',
            r'youtube\.com/watch'
        ]
        
        return any(re.search(pattern, url, re.IGNORECASE) for pattern in youtube_music_patterns)
    
    def is_playlist_url(self, url: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """检查是否为播放列表 URL 并提取播放列表信息"""
        try:
            # 检查 URL 中是否包含播放列表标识
            if 'list=' in url or 'playlist' in url.lower():
                # 使用 yt-dlp 提取播放列表信息
                ydl_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': True,  # 只提取基本信息，不下载
                }
                
                if self.cookies_path:
                    ydl_opts['cookiefile'] = self.cookies_path
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    
                    if info and '_type' in info and info['_type'] == 'playlist':
                        entries = info.get('entries', [])
                        playlist_info = {
                            'total_videos': len(entries),
                            'playlist_title': info.get('title', 'YouTube Music 播放列表'),
                            'playlist_id': info.get('id', ''),
                            'uploader': info.get('uploader', ''),
                            'entries': entries
                        }
                        logger.info(f"🎵 检测到播放列表: {playlist_info['playlist_title']}, 共 {len(entries)} 首歌曲")
                        return True, playlist_info
            
            return False, None
            
        except Exception as e:
            logger.warning(f"⚠️ 检查播放列表时出错: {e}")
            return False, None
    
    def _create_ydl_opts(self, output_dir: Path, filename_template: str = None) -> Dict[str, Any]:
        """创建 yt-dlp 配置选项"""
        if filename_template is None:
            if self.enable_id_tags:
                filename_template = '%(title).100s [%(id)s].%(ext)s'
            else:
                filename_template = '%(title).100s.%(ext)s'
        
        # 音频格式优先级：优先选择 M4A 格式，保留源音质
        format_selector = 'bestaudio[ext=m4a]/bestaudio'
        
        ydl_opts = {
            'format': format_selector,
            'outtmpl': str(output_dir / filename_template),
            'writeinfojson': False,  # 不下载 JSON 元数据
            'ignoreerrors': False,
            'no_warnings': False,
            'socket_timeout': self.timeout,
            'retries': self.max_retries,
            'fragment_retries': self.max_retries,
            'continuedl': True,  # 支持断点续传
            'noplaylist': True,  # 默认不下载播放列表（单独处理）
            'geo_bypass': True,
            'geo_bypass_country': 'US',
            # 关键：直接下载M4A格式，不重新编码
            'postprocessors': [
                {
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'm4a',
                    'preferredquality': '0',  # 保持原始质量
                    'nopostoverwrites': False,
                }
            ],
        }
        
        # 添加 cookies 文件
        if self.cookies_path:
            ydl_opts['cookiefile'] = self.cookies_path
        
        return ydl_opts
    
    def _playlist_progress_hook(self, d: Dict[str, Any], progress_callback=None, playlist_info=None):
        """播放列表专用进度回调函数 - 增强版本"""
        try:
            if d['status'] == 'downloading':
                filename = d.get('filename', 'Unknown')
                downloaded_bytes = d.get('downloaded_bytes', 0)
                total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                speed = d.get('speed', 0)
                
                if total_bytes > 0:
                    percentage = (downloaded_bytes / total_bytes) * 100
                    
                    def format_bytes(bytes_value):
                        if bytes_value < 1024:
                            return f"{bytes_value} B"
                        elif bytes_value < 1024 * 1024:
                            return f"{bytes_value / 1024:.2f}KB"
                        else:
                            return f"{bytes_value / (1024 * 1024):.2f}MB"
                    
                    # 计算预计剩余时间
                    remaining_bytes = total_bytes - downloaded_bytes
                    if speed > 0:
                        eta_seconds = remaining_bytes / speed
                        eta_minutes = int(eta_seconds // 60)
                        eta_seconds = int(eta_seconds % 60)
                        eta_str = f"{eta_minutes:02d}:{eta_seconds:02d}"
                    else:
                        eta_str = "--:--"
                    
                    # 创建进度条
                    bar_length = 20
                    filled_length = int(bar_length * percentage / 100)
                    bar = '█' * filled_length + '░' * (bar_length - filled_length)
                    
                    # 获取干净的文件名
                    clean_filename = Path(filename).name
                    if clean_filename.endswith('.part'):
                        clean_filename = clean_filename[:-5]
                    if clean_filename.endswith('.m4a.webm'):
                        clean_filename = clean_filename.replace('.m4a.webm', '.m4a')
                    
                    speed_str = format_bytes(speed) + "/s" if speed else "0.00MB/s"
                    
                    # 播放列表信息
                    playlist_title = playlist_info.get('playlist_title', '播放列表') if playlist_info else '播放列表'
                    
                    progress_msg = (
                        f"🎵 音乐: YouTube Music下载中...\n"
                        f"📋 播放列表: {playlist_title}\n"
                        f"📝 文件: {clean_filename}\n"
                        f"💾 大小: {format_bytes(downloaded_bytes)} / {format_bytes(total_bytes)}\n"
                        f"⚡️ 速度: {speed_str}\n"
                        f"⏳ 预计剩余: {eta_str}\n"
                        f"📊 进度: {bar} ({percentage:.1f}%)"
                    )
                    
                    logger.info(f"📥 {percentage:.1f}% - {clean_filename}")
                    
                    if progress_callback:
                        try:
                            progress_callback({'status': 'downloading', 'progress_text': progress_msg})
                        except Exception as e:
                            logger.warning(f"⚠️ 进度回调错误: {e}")
            
            elif d['status'] == 'finished':
                filename = d.get('filename', 'Unknown')
                clean_filename = Path(filename).name
                if clean_filename.endswith('.part'):
                    clean_filename = clean_filename[:-5]
                if clean_filename.endswith('.m4a.webm'):
                    clean_filename = clean_filename.replace('.m4a.webm', '.m4a')
                    
                logger.info(f"✅ 下载完成: {clean_filename}")
                
                if progress_callback:
                    try:
                        # 获取文件大小信息
                        file_size = 0
                        try:
                            if os.path.exists(filename):
                                file_size = os.path.getsize(filename)
                        except:
                            pass
                        
                        file_size_mb = round(file_size / (1024 * 1024), 2) if file_size > 0 else 0
                        
                        # 获取播放列表信息
                        playlist_title = playlist_info.get('playlist_title', '播放列表') if playlist_info else '播放列表'
                        
                        # 创建增强的完成消息
                        finished_msg = (
                            f"🎵 音乐: YouTube Music下载中...\n"
                            f"📋 播放列表: {playlist_title}\n"
                            f"📝 文件: {clean_filename}\n"
                            f"💾 大小: {file_size_mb} MB\n"
                            f"⚡️ 速度: 完成\n"
                            f"⏳ 预计剩余: 00:00\n"
                            f"📊 进度: {'█' * 20} (100.0%)"
                        )
                        
                        progress_callback(finished_msg)
                    except Exception as e:
                        logger.warning(f"⚠️ 进度回调错误: {e}")
                    
        except Exception as e:
            logger.warning(f"⚠️ 播放列表进度回调处理错误: {e}")
    
    def _progress_hook(self, d: Dict[str, Any], progress_callback=None):
        """单曲下载专用进度回调函数 - 增强版本"""
        try:
            if d['status'] == 'downloading':
                filename = d.get('filename', 'Unknown')
                downloaded_bytes = d.get('downloaded_bytes', 0)
                total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                speed = d.get('speed', 0)
                
                if total_bytes > 0:
                    percentage = (downloaded_bytes / total_bytes) * 100
                    
                    def format_bytes(bytes_value):
                        if bytes_value < 1024:
                            return f"{bytes_value} B"
                        elif bytes_value < 1024 * 1024:
                            return f"{bytes_value / 1024:.2f}KB"
                        else:
                            return f"{bytes_value / (1024 * 1024):.2f}MB"
                    
                    # 计算预计剩余时间
                    remaining_bytes = total_bytes - downloaded_bytes
                    if speed > 0:
                        eta_seconds = remaining_bytes / speed
                        eta_minutes = int(eta_seconds // 60)
                        eta_seconds = int(eta_seconds % 60)
                        eta_str = f"{eta_minutes:02d}:{eta_seconds:02d}"
                    else:
                        eta_str = "--:--"
                    
                    # 创建进度条
                    bar_length = 20
                    filled_length = int(bar_length * percentage / 100)
                    bar = '█' * filled_length + '░' * (bar_length - filled_length)
                    
                    # 获取干净的文件名
                    clean_filename = Path(filename).name
                    if clean_filename.endswith('.part'):
                        clean_filename = clean_filename[:-5]
                    if clean_filename.endswith('.m4a.webm'):
                        clean_filename = clean_filename.replace('.m4a.webm', '.m4a')
                    
                    speed_str = format_bytes(speed) + "/s" if speed else "0.00MB/s"
                    
                    progress_msg = (
                        f"🎵 音乐: YouTube Music下载中...\n"
                        f"📝 文件: {clean_filename}\n"
                        f"💾 大小: {format_bytes(downloaded_bytes)} / {format_bytes(total_bytes)}\n"
                        f"⚡️ 速度: {speed_str}\n"
                        f"⏳ 预计剩余: {eta_str}\n"
                        f"📊 进度: {bar} ({percentage:.1f}%)"
                    )
                    
                    logger.info(f"📥 {percentage:.1f}% - {clean_filename}")
                    
                    if progress_callback:
                        try:
                            progress_callback({'status': 'downloading', 'progress_text': progress_msg})
                        except Exception as e:
                            logger.warning(f"⚠️ 进度回调错误: {e}")
            
            elif d['status'] == 'finished':
                filename = d.get('filename', 'Unknown')
                clean_filename = Path(filename).name
                if clean_filename.endswith('.part'):
                    clean_filename = clean_filename[:-5]
                if clean_filename.endswith('.m4a.webm'):
                    clean_filename = clean_filename.replace('.m4a.webm', '.m4a')
                    
                logger.info(f"✅ 下载完成: {clean_filename}")
                
                if progress_callback:
                    try:
                        # 获取文件大小信息
                        file_size = 0
                        try:
                            if os.path.exists(filename):
                                file_size = os.path.getsize(filename)
                        except:
                            pass
                        
                        file_size_mb = round(file_size / (1024 * 1024), 2) if file_size > 0 else 0
                        
                        # 创建增强的完成消息
                        finished_msg = (
                            f"🎵 音乐: YouTube Music下载中...\n"
                            f"📝 文件: {clean_filename}\n"
                            f"💾 大小: {file_size_mb} MB\n"
                            f"⚡️ 速度: 完成\n"
                            f"⏳ 预计剩余: 00:00\n"
                            f"📊 进度: {'█' * 20} (100.0%)"
                        )
                        
                        progress_callback(finished_msg)
                    except Exception as e:
                        logger.warning(f"⚠️ 进度回调错误: {e}")
                    
        except Exception as e:
            logger.warning(f"⚠️ 单曲进度回调处理错误: {e}")

    def download_song_by_id(self, video_id: str, download_dir: str = "./downloads/youtube_music", quality: str = 'best', progress_callback=None) -> Dict[str, Any]:
        """通过视频ID下载单首歌曲 - 参考网易云下载器模式"""
        try:
            logger.info(f"🎵 开始下载单首歌曲: {video_id}")
            
            if progress_callback:
                progress_callback({'status': 'downloading', 'progress_text': '🎵 正在准备下载单首歌曲...'})
            
            # 构建YouTube URL
            url = f"https://www.youtube.com/watch?v={video_id}"
            
            # 确定下载路径
            output_dir = Path(download_dir) / "Singles"
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # 创建 yt-dlp 配置
            ydl_opts = self._create_ydl_opts(output_dir)
            ydl_opts['progress_hooks'] = [lambda d: self._progress_hook(d, progress_callback)]
            
            # 执行下载
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # 首先获取视频信息
                info = ydl.extract_info(url, download=False)
                
                if not info:
                    raise Exception("无法获取歌曲信息")
                
                # 下载音频
                ydl.download([url])
                
                # 查找下载的文件
                title = info.get('title', 'Unknown')
                uploader = info.get('uploader', 'Unknown')
                duration = info.get('duration', 0)
                
                # 查找实际下载的文件
                downloaded_files = []
                for file_path in output_dir.glob("*.m4a"):
                    if file_path.stat().st_mtime > (time.time() - 300):  # 5分钟内创建的文件
                        downloaded_files.append(file_path)
                
                if downloaded_files:
                    downloaded_file = downloaded_files[0]
                    file_size = downloaded_file.stat().st_size
                    
                    # 更新统计信息
                    self.download_stats['downloaded_files'] += 1
                    self.download_stats['total_size'] += file_size
                    
                    result = {
                        'success': True,
                        'message': f'YouTube Music 单曲下载完成: {title}',
                        'song_title': title,
                        'song_artist': uploader,
                        'filename': downloaded_file.name,
                        'file_path': str(downloaded_file),
                        'download_path': str(output_dir),
                        'file_size': file_size,
                        'size_mb': round(file_size / (1024 * 1024), 2),
                        'duration': duration,
                        'format': 'm4a',
                        'quality': quality,
                        'url': url
                    }
                    
                    logger.info(f"✅ 单首歌曲下载成功: {title}")
                    if progress_callback:
                        # 创建详细的单曲下载完成汇总
                        file_size_mb = round(file_size / (1024 * 1024), 2)
                        audio_quality = "M4A" if quality == 'best' else quality.upper()
                        bitrate_info = "AAC/256kbps" if quality == 'best' else "Variable"
                        
                        success_msg = (
                            f"🎵 YouTube Music 单曲下载完成\n\n"
                            f"📝 歌曲标题: {title}\n\n"
                            f"🎤 艺术家: {uploader}\n"
                            f"🎚️ 音频格式: {audio_quality}\n"
                            f"📊 码率: {bitrate_info}\n"
                            f"💾 文件大小: {file_size_mb} MB\n"
                            f"📂 保存位置: {downloaded_file}\n\n"
                            f"✅ 下载完成: {title}"
                        )
                        progress_callback(success_msg)
                    
                    return result
                
                else:
                    raise Exception("未找到下载的音频文件")
                
        except Exception as e:
            logger.error(f"❌ 单首歌曲下载失败: {e}")
            
            return {
                'success': False,
                'error': str(e),
                'message': f'YouTube Music 单曲下载失败: {str(e)}',
                'url': f"https://www.youtube.com/watch?v={video_id}"
            }
    
    def _album_progress_hook(self, d: Dict[str, Any], progress_callback=None, album_info=None):
        """专辑专用进度回调函数 - 增强版本"""
        try:
            if d['status'] == 'downloading':
                filename = d.get('filename', 'Unknown')
                downloaded_bytes = d.get('downloaded_bytes', 0)
                total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                speed = d.get('speed', 0)
                
                if total_bytes > 0:
                    percentage = (downloaded_bytes / total_bytes) * 100
                    
                    def format_bytes(bytes_value):
                        if bytes_value < 1024:
                            return f"{bytes_value} B"
                        elif bytes_value < 1024 * 1024:
                            return f"{bytes_value / 1024:.2f}KB"
                        else:
                            return f"{bytes_value / (1024 * 1024):.2f}MB"
                    
                    # 计算预计剩余时间
                    remaining_bytes = total_bytes - downloaded_bytes
                    if speed > 0:
                        eta_seconds = remaining_bytes / speed
                        eta_minutes = int(eta_seconds // 60)
                        eta_seconds = int(eta_seconds % 60)
                        eta_str = f"{eta_minutes:02d}:{eta_seconds:02d}"
                    else:
                        eta_str = "--:--"
                    
                    # 创建进度条
                    bar_length = 20
                    filled_length = int(bar_length * percentage / 100)
                    bar = '█' * filled_length + '░' * (bar_length - filled_length)
                    
                    # 获取干净的文件名
                    clean_filename = Path(filename).name
                    if clean_filename.endswith('.part'):
                        clean_filename = clean_filename[:-5]
                    if clean_filename.endswith('.m4a.webm'):
                        clean_filename = clean_filename.replace('.m4a.webm', '.m4a')
                    
                    speed_str = format_bytes(speed) + "/s" if speed else "0.00MB/s"
                    
                    # 专辑信息
                    album_title = album_info.get('playlist_title', '专辑') if album_info else '专辑'
                    
                    progress_msg = (
                        f"🎵 音乐: YouTube Music下载中...\n"
                        f"💿 专辑: {album_title}\n"
                        f"📝 文件: {clean_filename}\n"
                        f"💾 大小: {format_bytes(downloaded_bytes)} / {format_bytes(total_bytes)}\n"
                        f"⚡️ 速度: {speed_str}\n"
                        f"⏳ 预计剩余: {eta_str}\n"
                        f"📊 进度: {bar} ({percentage:.1f}%)"
                    )
                    
                    logger.info(f"📥 {percentage:.1f}% - {clean_filename}")
                    
                    if progress_callback:
                        try:
                            progress_callback({'status': 'downloading', 'progress_text': progress_msg})
                        except Exception as e:
                            logger.warning(f"⚠️ 进度回调错误: {e}")
            
            elif d['status'] == 'finished':
                filename = d.get('filename', 'Unknown')
                clean_filename = Path(filename).name
                if clean_filename.endswith('.part'):
                    clean_filename = clean_filename[:-5]
                if clean_filename.endswith('.m4a.webm'):
                    clean_filename = clean_filename.replace('.m4a.webm', '.m4a')
                    
                logger.info(f"✅ 下载完成: {clean_filename}")
                
                if progress_callback:
                    try:
                        # 获取文件大小信息
                        file_size = 0
                        try:
                            if os.path.exists(filename):
                                file_size = os.path.getsize(filename)
                        except:
                            pass
                        
                        file_size_mb = round(file_size / (1024 * 1024), 2) if file_size > 0 else 0
                        
                        # 获取专辑信息
                        album_title = album_info.get('playlist_title', '专辑') if album_info else '专辑'
                        
                        # 创建增强的完成消息
                        finished_msg = (
                            f"🎵 音乐: YouTube Music下载中...\n"
                            f"💿 专辑: {album_title}\n"
                            f"📝 文件: {clean_filename}\n"
                            f"💾 大小: {file_size_mb} MB\n"
                            f"⚡️ 速度: 完成\n"
                            f"⏳ 预计剩余: 00:00\n"
                            f"📊 进度: {'█' * 20} (100.0%)"
                        )
                        
                        progress_callback(finished_msg)
                    except Exception as e:
                        logger.warning(f"⚠️ 进度回调错误: {e}")
                    
        except Exception as e:
            logger.warning(f"⚠️ 专辑进度回调处理错误: {e}")

    def download_playlist_by_id(self, playlist_id: str, download_dir: str = "./downloads/youtube_music", quality: str = 'best', progress_callback=None) -> Dict[str, Any]:
        """通过播放列表ID下载播放列表 - 参考网易云下载器模式"""
        try:
            logger.info(f"📋 开始下载播放列表: {playlist_id}")
            
            if progress_callback:
                progress_callback({'status': 'downloading', 'progress_text': '📋 正在分析播放列表...'})
            
            # 构建YouTube播放列表URL
            url = f"https://www.youtube.com/playlist?list={playlist_id}"
            
            # 检查是否为播放列表
            is_playlist, playlist_info = self.is_playlist_url(url)
            if not is_playlist:
                raise Exception("URL 不是有效的播放列表")
            
            playlist_title = playlist_info['playlist_title']
            total_tracks = playlist_info['total_videos']
            
            logger.info(f"📋 播放列表: {playlist_title}, 共 {total_tracks} 首歌曲")
            
            # 确定下载路径
            safe_title = re.sub(r'[^\w\s-]', '', playlist_title).strip()
            output_dir = Path(download_dir) / "Playlists" / safe_title
            output_dir.mkdir(parents=True, exist_ok=True)
            
            if progress_callback:
                progress_callback({'status': 'downloading', 'progress_text': f'📋 开始下载播放列表: {playlist_title}\n共 {total_tracks} 首歌曲'})
            
            # 创建 yt-dlp 配置
            ydl_opts = self._create_ydl_opts(output_dir)
            ydl_opts['noplaylist'] = False  # 允许播放列表下载
            ydl_opts['progress_hooks'] = [lambda d: self._playlist_progress_hook(d, progress_callback, playlist_info)]
            
            # 执行下载
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    ydl.download([url])
                    success = True
                except Exception as e:
                    logger.error(f"❌ 播放列表下载过程中出错: {e}")
                    success = False
            
            # 统计下载结果
            downloaded_tracks = []
            total_size = 0
            for file_path in output_dir.glob("*.m4a"):
                file_size = file_path.stat().st_size
                total_size += file_size
                downloaded_tracks.append({
                    'file_path': str(file_path),
                    'file_size': file_size,
                    'title': file_path.stem
                })
            
            # 更新统计信息
            self.download_stats['downloaded_files'] += len(downloaded_tracks)
            self.download_stats['total_size'] += total_size
            
            result = {
                'success': True,
                'message': f'YouTube Music 播放列表下载完成: {playlist_title}',
                'playlist_name': playlist_title,
                'creator': playlist_info.get('uploader', ''),
                'total_songs': total_tracks,
                'downloaded_songs': len(downloaded_tracks),
                'failed_songs': total_tracks - len(downloaded_tracks),
                'download_path': str(output_dir),
                'total_size_mb': round(total_size / (1024 * 1024), 2),
                'songs': downloaded_tracks,
                'quality': quality,
                'url': url
            }
            
            logger.info(f"✅ 播放列表下载完成: {playlist_title}, 成功 {len(downloaded_tracks)}/{total_tracks}")
            
            if progress_callback:
                # 创建详细的播放列表下载完成汇总
                total_size_mb = round(total_size / (1024 * 1024), 2)
                
                # 统计音频信息
                audio_quality = "M4A" if quality == 'best' else quality.upper()
                bitrate_info = "AAC/256kbps" if quality == 'best' else "Variable"
                
                # 提取创建者信息
                creator_info = playlist_info.get('uploader', 'YouTube Music')
                
                # 构建歌曲列表
                song_list = []
                for i, track in enumerate(downloaded_tracks, 1):
                    file_size_mb = round(track['file_size'] / (1024 * 1024), 2)
                    # 使用与QQ音乐相同的格式：艺术家 - 歌名.m4a (xx.xMB)
                    track_title = track['title']
                    if ' - ' not in track_title:
                        # 如果没有艺术家信息，使用creator_info
                        track_title = f"{creator_info} - {track_title}"
                    song_list.append(f"{i:02d}. {track_title}.m4a ({file_size_mb}MB)")
                
                success_msg = (
                    f"🎵 YouTube Music专辑下载完成\n\n"
                    f"📀 专辑名称: {playlist_title}\n\n"
                    f"🎤 艺术家：{creator_info}\n"
                    f"🎼 曲目数量: {len(downloaded_tracks)} 首\n"
                    f"🎚️ 音频质量: {audio_quality}\无损\n"
                    f"💾 总大小: {total_size_mb:.2f} MB\n"
                    f"📊 码率: {bitrate_info}\n"
                    f"📂 保存位置: {output_dir}\n\n"
                    f"🎵 歌曲列表:\n\n"
                    + "\n".join(song_list)
                )
                
                # 直接发送字符串消息到Telegram
                progress_callback(success_msg)
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 播放列表下载失败: {e}")
            
            return {
                'success': False,
                'error': str(e),
                'message': f'YouTube Music 播放列表下载失败: {str(e)}',
                'url': f"https://www.youtube.com/playlist?list={playlist_id}"
            }
    
    def download_album_by_id(self, album_id: str, download_dir: str = "./downloads/youtube_music", quality: str = 'best', progress_callback=None) -> Dict[str, Any]:
        """通过专辑ID下载专辑 - 参考网易云下载器模式"""
        try:
            logger.info(f"💿 开始下载专辑: {album_id}")
            
            if progress_callback:
                progress_callback({'status': 'downloading', 'progress_text': '💿 正在分析专辑...'})
            
            # 构建YouTube播放列表URL（专辑通常也是播放列表形式）
            url = f"https://www.youtube.com/playlist?list={album_id}"
            
            # 检查是否为播放列表
            is_playlist, album_info = self.is_playlist_url(url)
            if not is_playlist:
                raise Exception("专辑URL 不是有效的播放列表")
            
            album_title = album_info['playlist_title']
            total_tracks = album_info['total_videos']
            
            logger.info(f"💿 专辑: {album_title}, 共 {total_tracks} 首歌曲")
            
            # 确定下载路径
            safe_title = re.sub(r'[^\w\s-]', '', album_title).strip()
            output_dir = Path(download_dir) / "Albums" / safe_title
            output_dir.mkdir(parents=True, exist_ok=True)
            
            if progress_callback:
                progress_callback({'status': 'downloading', 'progress_text': f'💿 开始下载专辑: {album_title}\n共 {total_tracks} 首歌曲'})
            
            # 创建 yt-dlp 配置
            ydl_opts = self._create_ydl_opts(output_dir)
            ydl_opts['noplaylist'] = False  # 允许播放列表下载
            ydl_opts['progress_hooks'] = [lambda d: self._album_progress_hook(d, progress_callback, album_info)]
            
            # 执行下载
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    ydl.download([url])
                    success = True
                except Exception as e:
                    logger.error(f"❌ 专辑下载过程中出错: {e}")
                    success = False
            
            # 统计下载结果
            downloaded_tracks = []
            total_size = 0
            for file_path in output_dir.glob("*.m4a"):
                file_size = file_path.stat().st_size
                total_size += file_size
                downloaded_tracks.append({
                    'file_path': str(file_path),
                    'file_size': file_size,
                    'title': file_path.stem
                })
            
            # 更新统计信息
            self.download_stats['downloaded_files'] += len(downloaded_tracks)
            self.download_stats['total_size'] += total_size
            
            result = {
                'success': True,
                'message': f'YouTube Music 专辑下载完成: {album_title}',
                'album_name': album_title,
                'creator': album_info.get('uploader', ''),
                'total_songs': total_tracks,
                'downloaded_songs': len(downloaded_tracks),
                'failed_songs': total_tracks - len(downloaded_tracks),
                'download_path': str(output_dir),
                'total_size_mb': round(total_size / (1024 * 1024), 2),
                'songs': downloaded_tracks,
                'quality': quality,
                'url': url
            }
            
            logger.info(f"✅ 专辑下载完成: {album_title}, 成功 {len(downloaded_tracks)}/{total_tracks}")
            
            if progress_callback:
                # 创建详细的专辑下载完成汇总
                total_size_mb = round(total_size / (1024 * 1024), 2)
                
                # 统计音频信息
                audio_quality = "M4A" if quality == 'best' else quality.upper()
                bitrate_info = "AAC/256kbps" if quality == 'best' else "Variable"
                
                # 提取艺术家信息（从专辑信息或第一首歌推断）
                artist_name = album_info.get('uploader', 'YouTube Music')
                if not artist_name or artist_name == 'YouTube Music':
                    if downloaded_tracks:
                        # 尝试从第一首歌的标题提取艺术家
                        first_title = downloaded_tracks[0]['title']
                        if ' - ' in first_title:
                            artist_name = first_title.split(' - ')[0]
                        else:
                            artist_name = 'YouTube Music'
                
                # 构建歌曲列表
                song_list = []
                for i, track in enumerate(downloaded_tracks, 1):
                    file_size_mb = round(track['file_size'] / (1024 * 1024), 2)
                    # 使用与QQ音乐相同的格式：艺术家 - 歌名.m4a (xx.xMB)
                    track_title = track['title']
                    if ' - ' not in track_title:
                        # 如果没有艺术家信息，使用artist_name
                        track_title = f"{artist_name} - {track_title}"
                    song_list.append(f"{i:02d}. {track_title}.m4a ({file_size_mb}MB)")
                
                # 提取创建者信息
                creator_info = album_info.get('uploader', artist_name)
                
                success_msg = (
                    f"🎵 YouTube Music专辑下载完成\n\n"
                    f"📀 专辑名称: {album_title}\n\n"
                    f"🎤 艺术家：{artist_name}\n"
                    f"🎼 曲目数量: {len(downloaded_tracks)} 首\n"
                    f"🎚️ 音频质量: {audio_quality}\无损\n"
                    f"💾 总大小: {total_size_mb:.2f} MB\n"
                    f"📊 码率: {bitrate_info}\n"
                    f"📂 保存位置: {output_dir}\n\n"
                    f"🎵 歌曲列表:\n\n"
                    + "\n".join(song_list)
                )
                
                # 直接发送字符串消息到Telegram
                progress_callback(success_msg)
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 专辑下载失败: {e}")
            
            return {
                'success': False,
                'error': str(e),
                'message': f'YouTube Music 专辑下载失败: {str(e)}',
                'url': f"https://www.youtube.com/playlist?list={album_id}"
            }
    
    def download_by_url(self, url: str, download_dir: str = "./downloads/youtube_music", quality: str = 'best', progress_callback=None) -> Dict[str, Any]:
        """通过URL下载音乐，自动识别链接类型 - 参考网易云下载器模式"""
        try:
            logger.info(f"🔗 开始通过URL下载: {url}")
            
            # 验证URL
            if not self.is_youtube_music_url(url):
                raise Exception("不是有效的 YouTube Music URL")
            
            # 自动检测下载类型
            is_playlist, playlist_info = self.is_playlist_url(url)
            
            if is_playlist:
                # 提取播放列表ID
                playlist_match = re.search(r'[&?]list=([^&]+)', url)
                if playlist_match:
                    playlist_id = playlist_match.group(1)
                    return self.download_playlist_by_id(playlist_id, download_dir, quality, progress_callback)
                else:
                    raise Exception("无法提取播放列表ID")
            else:
                # 单曲下载，提取视频ID
                video_match = re.search(r'(?:v=|youtu\.be/)([^&\?]+)', url)
                if video_match:
                    video_id = video_match.group(1)
                    return self.download_song_by_id(video_id, download_dir, quality, progress_callback)
                else:
                    raise Exception("无法提取视频ID")
                
        except Exception as e:
            logger.error(f"❌ URL下载失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': f'YouTube Music URL下载失败: {str(e)}',
                'url': url
            }
    
    def get_download_stats(self) -> Dict[str, Any]:
        """获取下载统计信息"""
        total_size_mb = self.download_stats['total_size'] / (1024 * 1024)
        
        return {
            'downloaded_files': self.download_stats['downloaded_files'],
            'total_size_mb': round(total_size_mb, 2),
            'downloaded_songs': self.download_stats['downloaded_songs']
        }

# 命令行接口（可选，用于独立测试）
def main():
    """主函数 - 命令行接口"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='YouTube Music Downloader - 基于 yt-dlp 的高质量音乐下载器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  %(prog)s "https://music.youtube.com/watch?v=example" --type single
  %(prog)s "https://music.youtube.com/playlist?list=example" --type playlist
  %(prog)s "https://youtu.be/example" --quality best --output ./downloads
        """
    )
    
    parser.add_argument('url', help='YouTube Music URL (单曲/专辑/播放列表)')
    parser.add_argument('--type', choices=['auto', 'single', 'playlist', 'album'], 
                       default='auto', help='下载类型 (默认: auto)')
    parser.add_argument('--output', '-o', help='输出目录 (默认: ./downloads/youtube_music)')
    parser.add_argument('--quality', choices=['best', '320k', '256k', '128k'], 
                       default='best', help='音频质量 (默认: best)')
    parser.add_argument('--cookies', help='YouTube cookies 文件路径')
    parser.add_argument('--enable-id', action='store_true', help='在文件名中包含视频ID')
    parser.add_argument('--verbose', '-v', action='store_true', help='详细输出')
    
    args = parser.parse_args()
    
    # 设置日志级别
    if args.verbose:
        logging.getLogger('youtube_music_downloader').setLevel(logging.DEBUG)
    
    # 设置环境变量
    if args.quality:
        os.environ['YTM_AUDIO_QUALITY'] = args.quality
    if args.enable_id:
        os.environ['YTM_ENABLE_ID_TAGS'] = 'true'
    
    try:
        # 创建下载器
        downloader = YouTubeMusicDownloader()
        
        # 如果指定了cookies文件，更新路径
        if args.cookies:
            downloader.cookies_path = args.cookies
        
        download_dir = args.output or "./downloads/youtube_music"
        
        print(f"🎵 YouTube Music 下载器")
        print(f"📁 下载路径: {download_dir}")
        print(f"🎯 音频质量: {args.quality}")
        print(f"🔗 URL: {args.url}")
        print("=" * 50)
        
        # 进度回调函数
        def simple_progress(data):
            print(f"📢 {data.get('progress_text', '')}")
        
        # 执行下载
        result = downloader.download_by_url(
            url=args.url,
            download_dir=download_dir,
            quality=args.quality,
            progress_callback=simple_progress
        )
        
        # 显示结果
        print("\n" + "=" * 50)
        if result['success']:
            print("✅ 下载完成!")
            
            if 'song_title' in result:  # 单曲
                print(f"🎵 歌曲: {result['song_title']}")
                print(f"👤 艺术家: {result.get('song_artist', 'Unknown')}")
                print(f"📁 文件: {result['file_path']}")
            elif 'playlist_name' in result:  # 播放列表
                print(f"📋 播放列表: {result['playlist_name']}")
                print(f"📊 下载: {result['downloaded_songs']}/{result['total_songs']} 首")
                print(f"📁 目录: {result['download_path']}")
            
            # 显示统计信息
            stats = downloader.get_download_stats()
            print(f"\n📊 统计信息:")
            print(f"   文件数: {stats['downloaded_files']}")
            print(f"   总大小: {stats['total_size_mb']} MB")
            
        else:
            print("❌ 下载失败!")
            print(f"错误: {result.get('error', 'Unknown error')}")
            return 1
        
        return 0
        
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断下载")
        return 1
    except Exception as e:
        print(f"❌ 程序错误: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    # 运行主函数
    exit_code = main()
    exit(exit_code)
