# -*- coding: utf-8 -*-
# 在最开始就禁用SSL警告
import os
# 设置环境变量禁用SSL警告
os.environ['PYTHONWARNINGS'] = 'ignore:Unverified HTTPS request'
os.environ['URLLIB3_DISABLE_WARNINGS'] = '1'

import warnings
warnings.filterwarnings('ignore', message='Unverified HTTPS request')
warnings.filterwarnings('ignore', message='.*certificate verification.*')
warnings.filterwarnings('ignore', message='.*SSL.*')
warnings.filterwarnings('ignore', category=UserWarning, module='urllib3')

import logging.handlers
import os
import sys
import asyncio
import logging
import logging
logging.getLogger("telethon").setLevel(logging.WARNING)
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional, Dict, Any
from enum import Enum
from dataclasses import dataclass
import time
import threading
import requests
import urllib3
# 立即禁用urllib3的SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 尝试禁用其他可能存在的SSL警告
try:
    urllib3.disable_warnings(urllib3.exceptions.SubjectAltNameWarning)
except AttributeError:
    pass  # 该警告类型不存在，忽略

try:
    urllib3.disable_warnings(urllib3.exceptions.InsecurePlatformWarning)
except AttributeError:
    pass  # 该警告类型不存在，忽略

try:
    urllib3.disable_warnings(urllib3.exceptions.SNIMissingWarning)
except AttributeError:
    pass  # 该警告类型不存在，忽略

import re
import uuid
import mimetypes
import json
import subprocess
from telethon import TelegramClient, types
from telethon.sessions import StringSession
from telegram import (
    Update,
    Bot,
    InputFile,
    Audio,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
try:
    from .bilibili_favsub import BilibiliFavSubscriptionManager
except ImportError:
    from bilibili_favsub import BilibiliFavSubscriptionManager
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackContext,
    CallbackQueryHandler,
)
import yt_dlp
import qbittorrentapi
import signal
import gc
from concurrent.futures import ThreadPoolExecutor

# 导入多线程下载增强模块
try:
    from multithread_downloader import MultiThreadDownloader, DownloadConfig, create_downloader
    MULTITHREAD_ENABLED = True
except ImportError:
    MultiThreadDownloader = None
    DownloadConfig = None
    create_downloader = None
    MULTITHREAD_ENABLED = False
    logger.warning("⚠️ 多线程下载模块未加载")

# 导入模块化下载器
try:
    from modules.downloaders.bilibili_downloader import BilibiliDownloader, is_bilibili_url
    from modules.downloaders.youtube_downloader import YouTubeDownloader, is_youtube_url
    from modules.downloaders.music_downloader import MusicDownloader, is_music_platform
    from modules.downloaders.social_media_downloader import SocialMediaDownloader, is_social_media_url
    MODULES_ENABLED = True
except ImportError as e:
    logger.warning(f"⚠️ 模块化下载器导入失败：{e}")
    BilibiliDownloader = None
    YouTubeDownloader = None
    MusicDownloader = None
    SocialMediaDownloader = None
    MODULES_ENABLED = False

# 网络错误处理相关导入
import httpx
from telegram.error import NetworkError, TimedOut, RetryAfter

# 健康检查功能已删除，但保留 Telegram 会话生成功能
from flask import Flask, jsonify, request
import threading

# 配置读取器
try:
    from config_reader import load_toml_config, get_qbittorrent_config
except ImportError:
    load_toml_config = None
    get_qbittorrent_config = None

# 网易云音乐下载器
try:
    # 强制重新加载模块以避免缓存问题
    import sys
    import importlib
    if 'neteasecloud_music' in sys.modules:
        importlib.reload(sys.modules['neteasecloud_music'])

    import neteasecloud_music as _ncm
    from neteasecloud_music import NeteaseDownloader
    NETEASE_MODULE_PATH = getattr(_ncm, '__file__', 'unknown')
except ImportError:
    # 导入失败则置空，由初始化逻辑决定禁用该功能
    NeteaseDownloader = None
    NETEASE_MODULE_PATH = 'unavailable'

# 导入QQ音乐下载器
try:
    from qqmusic_downloader import QQMusicDownloader
    QQMUSIC_MODULE_PATH = 'qqmusic_downloader.py'
except ImportError:
    # 导入失败则置空，由初始化逻辑决定禁用该功能
    QQMusicDownloader = None
    QQMUSIC_MODULE_PATH = 'unavailable'

# 导入YouTube Music下载器
try:
    from youtubemusic_downloader import YouTubeMusicDownloader
    YOUTUBEMUSIC_MODULE_PATH = 'youtubemusic_downloader.py'
except ImportError:
    # 导入失败则置空，由初始化逻辑决定禁用该功能
    YouTubeMusicDownloader = None
    YOUTUBEMUSIC_MODULE_PATH = 'unavailable'

# 导入配置管理器
try:
    from config_manager import ConfigManager
    CONFIG_MANAGER_AVAILABLE = True
except ImportError:
    logger.error("❌ 无法导入配置管理器，程序无法继续运行")
    ConfigManager = None
    CONFIG_MANAGER_AVAILABLE = False
    sys.exit(1)  # 直接退出，因为没有配置管理器程序无法运行

# 导入配置读取器
try:
    from config_reader import (
        load_toml_config,
        get_telegram_config,
        get_proxy_config,
        print_config_summary
    )
    CONFIG_READER_AVAILABLE = True
except ImportError:
    logger.warning("⚠️ 无法导入配置读取器，将禁用 TOML 配置文件支持")
    load_toml_config = None
    get_telegram_config = None
    get_proxy_config = None
    print_config_summary = None
    CONFIG_READER_AVAILABLE = False

# 适配器：为缺少 download_album_by_id 的旧版 NeteaseDownloader 提供兼容实现
class _NeteaseDownloaderAdapter:
    def __init__(self, base):
        self._base = base

    def __getattr__(self, name):
        # 其他属性与方法直接透传
        return getattr(self._base, name)

    def download_album_by_id(self, album_id: str, download_dir: str = "./downloads/netease", quality: str = '128k', progress_callback=None) -> dict:
        # 如果原始实例已经实现了该方法，直接调用
        try:
            method = getattr(self._base, 'download_album_by_id')
        except AttributeError:
            method = None
        if callable(method):
            return method(album_id, download_dir, quality, progress_callback)

        # 兼容实现：基于 get_album_songs + download_song_by_id
        import os
        try:
            songs = self._base.get_album_songs(album_id)
            if not songs:
                return {
                    'success': False,
                    'error': f'无法获取专辑ID {album_id} 的歌曲信息',
                    'album_name': '',
                    'total_songs': 0,
                    'downloaded_songs': 0,
                    'total_size_mb': 0,
                    'download_path': download_dir,
                    'songs': [],
                    'quality': quality
                }

            album_title = songs[0].get('album', f'专辑_{album_id}')
            
            # 使用neteasecloud_music.py中的配置
            dir_format = self._base.dir_format
            album_folder_format = self._base.album_folder_format
            
            # 获取艺术家信息
            artist_name = songs[0].get('artist', '未知艺术家')
            
            # 构建专辑文件夹名称（使用NCM_ALBUM_FOLDER_FORMAT）
            if '{AlbumName}' in album_folder_format:
                # 替换专辑名称占位符
                album_folder_name = album_folder_format.replace('{AlbumName}', album_title)
                
                # 如果有发布日期占位符，尝试获取发布日期
                if '{ReleaseDate}' in album_folder_name:
                    try:
                        # 尝试从歌曲信息中获取发布日期
                        release_date = songs[0].get('publishTime', '')
                        if release_date:
                            # 转换时间戳为年份
                            import time
                            try:
                                year = time.strftime('%Y', time.localtime(int(release_date) / 1000))
                                album_folder_name = album_folder_name.replace('{ReleaseDate}', year)
                            except:
                                album_folder_name = album_folder_name.replace('{ReleaseDate}', '')
                        else:
                            album_folder_name = album_folder_name.replace('{ReleaseDate}', '')
                    except:
                        album_folder_name = album_folder_name.replace('{ReleaseDate}', '')
                
                # 清理文件名中的非法字符
                safe_album_folder_name = self._base.clean_filename(album_folder_name)
            else:
                # 如果没有占位符，直接使用专辑名称
                safe_album_folder_name = self._base.clean_filename(album_title)
            
            # 构建完整的目录路径（使用NCM_DIR_FORMAT）
            if '{ArtistName}' in dir_format and '{AlbumName}' in dir_format:
                # 格式：{ArtistName}/{AlbumName} - 艺术家/专辑
                safe_artist_name = self._base.clean_filename(artist_name)
                album_dir = os.path.join(download_dir, safe_artist_name, safe_album_folder_name)
                logger.info(f"🔍 使用艺术家/专辑目录结构: {safe_artist_name}/{safe_album_folder_name}")
            elif '{AlbumName}' in dir_format:
                # 格式：{AlbumName} - 直接以专辑命名
                album_dir = os.path.join(download_dir, safe_album_folder_name)
                logger.info(f"🔍 使用专辑目录结构: {safe_album_folder_name}")
            else:
                # 默认格式：直接以专辑命名
                album_dir = os.path.join(download_dir, safe_album_folder_name)
                logger.info(f"🔍 使用默认专辑目录结构: {safe_album_folder_name}")
            os.makedirs(album_dir, exist_ok=True)

            songs_info = []
            total_size = 0
            downloaded = 0

            # 使用neteasecloud_music.py中的配置
            song_file_format = self._base.song_file_format
            
            for i, song in enumerate(songs, 1):
                sid = str(song.get('id'))
                res = self._base.download_song_by_id(sid, album_dir, quality, progress_callback)
                if res and res.get('success'):
                    downloaded += 1
                    size_mb = res.get('size_mb', 0) or 0
                    try:
                        size_bytes = int(float(size_mb) * 1024 * 1024)
                    except Exception:
                        size_bytes = 0
                    total_size += size_bytes
                    
                    # 获取歌曲信息
                    song_title = res.get('song_title', song.get('name', 'Unknown'))
                    song_artist = res.get('song_artist', song.get('artist', 'Unknown'))
                    original_filename = res.get('filename', '')
                    
                    # 构建自定义文件名
                    if '{SongNumber}' in song_file_format or '{SongName}' in song_file_format or '{ArtistName}' in song_file_format:
                        # 替换占位符
                        custom_filename = song_file_format
                        
                        # 替换歌曲编号
                        if '{SongNumber}' in custom_filename:
                            custom_filename = custom_filename.replace('{SongNumber}', f"{i:02d}")
                        
                        # 替换歌曲名称
                        if '{SongName}' in custom_filename:
                            custom_filename = custom_filename.replace('{SongName}', song_title)
                        
                        # 替换艺术家名称
                        if '{ArtistName}' in custom_filename:
                            custom_filename = custom_filename.replace('{ArtistName}', song_artist)
                        
                        # 添加文件扩展名
                        if original_filename and '.' in original_filename:
                            file_ext = original_filename.split('.')[-1]
                            custom_filename = f"{custom_filename}.{file_ext}"
                        
                        # 清理文件名中的非法字符
                        safe_custom_filename = self._base.clean_filename(custom_filename)
                        
                        # 重命名文件
                        try:
                            original_filepath = os.path.join(album_dir, original_filename)
                            new_filepath = os.path.join(album_dir, safe_custom_filename)
                            
                            if os.path.exists(original_filepath) and original_filepath != new_filepath:
                                os.rename(original_filepath, new_filepath)
                                logger.info(f"✅ 重命名歌曲文件: {original_filename} -> {safe_custom_filename}")
                                final_filename = safe_custom_filename
                            else:
                                final_filename = original_filename
                        except Exception as e:
                            logger.warning(f"⚠️ 重命名文件失败: {e}")
                            final_filename = original_filename
                    else:
                        final_filename = original_filename
                    
                    songs_info.append({
                        'name': f"{song_title} - {song_artist}",
                        'size': size_bytes,
                        'filepath': os.path.join(album_dir, final_filename)
                    })
                else:
                    songs_info.append({
                        'name': f"{song.get('name', 'Unknown')} - {song.get('artist', 'Unknown')}",
                        'size': 0,
                        'filepath': ''
                    })

            return {
                'success': True,
                'album_name': album_title,
                'total_songs': len(songs),
                'downloaded_songs': downloaded,
                'total_size_mb': (total_size / (1024 * 1024)) if total_size else 0,
                'download_path': album_dir,
                'songs': songs_info,
                'quality': quality
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'专辑下载失败: {e}',
                'album_name': '',
                'total_songs': 0,
                'downloaded_songs': 0,
                'total_size_mb': 0,
                'download_path': download_dir,
                'songs': [],
                'quality': quality
            }

def extract_xiaohongshu_url(text):
    import re
    # 先尝试提取标准http/https链接
    urls = re.findall(r'http[s]?://[^\s]+', text)
    for url in urls:
        if 'xhslink.com' in url or 'xiaohongshu.com' in url:
            return url

    # 如果没有找到标准链接，尝试提取其他格式的小红书链接
    # 匹配 p://、tp://、ttp:// 等协议，并转换为https://
    non_http_urls = re.findall(r'(p|tp|ttp)://([^\s]+)', text)
    for protocol, url in non_http_urls:
        if 'xhslink.com' in url or 'xiaohongshu.com' in url:
            return f"https://{url}"

    # 匹配没有协议的小红书域名
    domain_urls = re.findall(r'(xhslink\.com/[^\s]+|xiaohongshu\.com/[^\s]+)', text)
    for url in domain_urls:
        return f"https://{url}"

    return None
# 抖音和小红书下载相关导入
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("警告: playwright 未安装，抖音和小红书下载功能将不可用")


# 程序版本信息
BOT_VERSION = "v0.4"

# 创建 Flask 应用（仅用于 Telegram 会话生成）
app = Flask(__name__, static_folder="web", static_url_path="/web")

# 注册 Telethon Web 蓝图（用于生成 Session String）——按你的要求，固定使用 web/tg_setup.py
try:
    import os as _os
    _static_dir_abs = _os.path.join(_os.path.dirname(__file__), "web")
    from web.tg_setup import create_blueprint as _tg_create_bp
    app.register_blueprint(_tg_create_bp(static_dir=_static_dir_abs))
    logging.getLogger(__name__).info("✅ /setup 已由主进程Flask托管（使用 web/tg_setup.py）")
except Exception as _e:
    logging.getLogger(__name__).warning(f"⚠️ 注册 /setup 失败: {_e}")

# 尝试导入 gallery-dl
try:
    import gallery_dl
    GALLERY_DL_AVAILABLE = True
except ImportError:
    GALLERY_DL_AVAILABLE = False
    print("警告: gallery-dl 未安装，X图片下载功能将不可用")


# 心跳更新功能已删除


# 健康检查功能已删除


# 健康检查功能已删除，避免事件循环冲突


try:
    from telegram import Update
    from telegram.ext import (
        Application,
        CommandHandler,
        MessageHandler,
        filters,
        ContextTypes,
    )
    import yt_dlp
except ImportError as e:
    print(f"Error importing required packages: {e}")
    print("Please install: pip install python-telegram-bot yt-dlp requests")
    sys.exit(1)

# 工具函数定义
def _clean_filename_for_display_local(filename: str) -> str:
    try:
        import re, os
        # 移除时间戳前缀(10位数字+下划线)
        if filename and re.match(r"^\d{10}_", filename):
            display_name = filename[11:]
        else:
            display_name = filename or ""
        # 智能截断过长文件名
        if len(display_name) > 35:
            name, ext = os.path.splitext(display_name)
            display_name = name[:30] + "..." + ext
        return display_name
    except Exception:
        filename = filename or ""
        return filename if len(filename) <= 35 else filename[:32] + "..."

# 顶层提供进度条工具，避免嵌套函数名解析问题
def _create_progress_bar_local(percent: float, length: int = 20) -> str:
    filled_length = int(length * percent / 100)
    return "█" * filled_length + "░" * (length - filled_length)

# 全局工具函数，供网易云音乐进度回调使用
def _clean_filename_for_display(filename: str) -> str:
    try:
        import re, os
        # 移除时间戳前缀(10位数字+下划线)
        if filename and re.match(r"^\d{10}_", filename):
            display_name = filename[11:]
        else:
            display_name = filename or ""
        # 智能截断过长文件名
        if len(display_name) > 35:
            name, ext = os.path.splitext(display_name)
            display_name = name[:30] + "..." + ext
        return display_name
    except Exception:
        filename = filename or ""
        return filename if len(filename) <= 35 else filename[:32] + "..."

def _create_progress_bar(percent: float, length: int = 20) -> str:
    filled_length = int(length * percent / 100)
    return "█" * filled_length + "░" * (length - filled_length)

def _escape_markdown_v2(text: str) -> str:
    """独立的MarkdownV2转义函数，用于网易云进度消息"""
    if not text:
        return text
    
    # 先转义反斜杠，避免重复转义
    escaped_text = text.replace("\\", "\\\\")
    
    # 转义MarkdownV2特殊字符
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        escaped_text = escaped_text.replace(char, f"\\{char}")
    
    return escaped_text

# 配置增强的日志系统
# 导入模块化工具
from modules.url_extractor import URLExtractor
from modules.batch_downloader import BatchDownloadProcessor
from modules.message_handler import TelegramMessageHandler


def setup_logging():
    """配置增强的日志系统，支持远程NAS目录"""
    # 从环境变量获取日志配置
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_dir = os.getenv("LOG_DIR", "./logs")  # 改为当前目录下的logs
    log_max_size = int(os.getenv("LOG_MAX_SIZE", "10")) * 1024 * 1024  # 默认10MB
    log_backup_count = int(os.getenv("LOG_BACKUP_COUNT", "5"))
    log_to_console = os.getenv("LOG_TO_CONSOLE", "true").lower() == "true"
    log_to_file = os.getenv("LOG_TO_FILE", "true").lower() == "true"
    # 创建日志目录（支持远程NAS路径）
    log_path = Path(log_dir)
    try:
        log_path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"警告：无法创建日志目录 {log_path}: {e}")
        # 如果无法创建远程目录，回退到本地目录
        log_path = Path("./logs")  # 改为当前目录下的logs
        log_path.mkdir(parents=True, exist_ok=True)
        print(f"已回退到本地日志目录: {log_path}")
    # 配置日志格式
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    # 创建格式化器
    formatter = logging.Formatter(log_format, date_format)
    # 获取根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level))
    # 清除现有的处理器
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    # 文件日志处理器（带轮转）
    if log_to_file:
        try:
            file_handler = logging.handlers.RotatingFileHandler(
                log_path / "savextube.log",
                maxBytes=log_max_size,
                backupCount=log_backup_count,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            file_handler.setLevel(getattr(logging, log_level))
            root_logger.addHandler(file_handler)
        except Exception as e:
            print(f"警告：无法创建文件日志处理器: {e}")
            log_to_file = False
    # 控制台日志处理器
    if log_to_console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(getattr(logging, log_level))
        root_logger.addHandler(console_handler)

    # 设置第三方库的日志级别，减少冗余输出
    # httpx - Telegram API 请求日志
    logging.getLogger("httpx").setLevel(logging.WARNING)
    # urllib3 - HTTP 请求日志
    logging.getLogger("urllib3").setLevel(logging.ERROR)
    logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)
    logging.getLogger("urllib3.util.retry").setLevel(logging.ERROR)
    # 禁用urllib3的所有警告
    logging.getLogger("urllib3").disabled = True

# 设置日志
setup_logging()
logger = logging.getLogger("savextube")

# 统一的进度管理函数
def create_unified_progress_hook(message_updater=None, progress_data=None):
    """
    创建统一的进度回调函数，适用于所有基于 yt-dlp 的下载

    Args:
        message_updater: 同步或异步消息更新函数
        progress_data: 进度数据字典，用于存储最终文件名等信息

    Returns:
        progress_hook: 统一的进度回调函数
    """
    def progress_hook(d):
        try:
            if d.get('status') == 'downloading':
                # 安全地获取下载进度信息
                downloaded = d.get('downloaded_bytes', 0) or 0
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0) or 0

                # 确保数值有效
                if downloaded is None:
                    downloaded = 0
                if total is None or total <= 0:
                    total = 1  # 避免除零错误

                # 计算进度百分比
                if total > 0:
                    percent = (downloaded / total) * 100
                else:
                    percent = 0

                # 格式化速度
                speed = d.get('speed', 0) or 0
                if speed and speed > 0:
                    speed_str = f"{speed / 1024 / 1024:.2f} MB/s"
                else:
                    speed_str = "未知"

                # 格式化剩余时间
                eta = d.get('eta', 0) or 0
                if eta and eta > 0:
                    eta_str = f"{eta}秒"
                else:
                    eta_str = "未知"

                # 获取文件名
                filename = os.path.basename(d.get('filename', '')) or "正在下载..."

                # 更新进度数据
                if progress_data:
                    progress_data.update({
                        'downloaded': downloaded,
                        'total': total,
                        'percent': percent,
                        'speed': speed_str,
                        'eta': eta_str,
                        'status': 'downloading',
                        'filename': filename
                    })

                # 记录进度信息
                logger.info(f"下载进度: {percent:.1f}% ({downloaded}/{total} bytes) - {speed_str} - 剩余: {eta_str}")

                # 如果有消息更新器，调用它
                if message_updater:
                    try:
                        # 检查是否为协程对象（错误情况）
                        if asyncio.iscoroutine(message_updater):
                            logger.error(f"❌ [progress_hook] message_updater 是协程对象，不是函数！")
                            return

                        # 检查是否为异步函数
                        if asyncio.iscoroutinefunction(message_updater):
                            # 异步函数，使用 run_coroutine_threadsafe
                            try:
                                loop = asyncio.get_running_loop()
                            except RuntimeError:
                                try:
                                    loop = asyncio.get_event_loop()
                                except RuntimeError:
                                    loop = asyncio.new_event_loop()
                                    asyncio.set_event_loop(loop)

                            # 直接传递原始进度数据字典
                            asyncio.run_coroutine_threadsafe(
                                message_updater(d), loop)
                        else:
                            # 同步函数，直接调用
                            message_updater(d)
                    except Exception as e:
                        logger.warning(f"⚠️ 更新进度消息失败: {e}")
                        logger.warning(f"⚠️ 异常类型: {type(e)}")
                        import traceback
                        logger.warning(f"⚠️ 异常堆栈: {traceback.format_exc()}")

            if d.get('status') == 'finished':
                logger.info("下载完成，开始后处理...")

                # 更新进度数据
                if progress_data and isinstance(progress_data, dict):
                    progress_data['status'] = 'finished'

                # 安全地获取文件名
                filename = d.get('filename', '')
                if filename and progress_data and isinstance(progress_data, dict):
                    progress_data['final_filename'] = filename
                    logger.info(f"最终文件名: {filename}")

                    # 监控文件合并状态
                    if filename.endswith('.part'):
                        logger.warning(f"⚠️ 文件合并可能失败: {filename}")
                    else:
                        logger.info(f"✅ 文件下载并合并成功: {filename}")
                else:
                    logger.warning("progress_hook 中未获取到文件名")

                # 如果有消息更新器，发送完成消息
                if message_updater:
                    try:
                        # 添加详细的调试日志
                        logger.info(f"🔍 [progress_hook] finished状态 - message_updater 类型: {type(message_updater)}")

                        # 检查是否为协程对象（错误情况）
                        if asyncio.iscoroutine(message_updater):
                            logger.error(f"❌ [progress_hook] finished状态 - message_updater 是协程对象，不是函数！")
                            return

                        # 检查是否为异步函数
                        if asyncio.iscoroutinefunction(message_updater):
                            logger.info(f"🔍 [progress_hook] finished状态 - 检测到异步函数，使用 run_coroutine_threadsafe")
                            # 异步函数，使用 run_coroutine_threadsafe
                            try:
                                loop = asyncio.get_running_loop()
                            except RuntimeError:
                                try:
                                    loop = asyncio.get_event_loop()
                                except RuntimeError:
                                    loop = asyncio.new_event_loop()
                                    asyncio.set_event_loop(loop)

                            # 直接传递原始进度数据字典
                            asyncio.run_coroutine_threadsafe(
                                message_updater(d), loop)
                        else:
                            logger.info(f"🔍 [progress_hook] finished状态 - 检测到同步函数，直接调用")
                            # 同步函数，直接调用
                            message_updater(d)
                    except Exception as e:
                        logger.warning(f"⚠️ 更新完成消息失败: {e}")
                        logger.warning(f"⚠️ 异常类型: {type(e)}")
                        import traceback
                        logger.warning(f"⚠️ 异常堆栈: {traceback.format_exc()}")

        except Exception as e:
            logger.error(f"progress_hook 处理错误: {e}")
            import traceback
            logger.error(f"progress_hook 异常堆栈: {traceback.format_exc()}")
            # 不中断下载，只记录错误

    return progress_hook
def create_bilibili_message_updater(status_message, context, progress_data):
    """
    专门为B站多P下载创建的消息更新器
    完全复制YouTube的成功逻辑
    """
    import time
    import asyncio

    # 缓存上次发送的内容，避免重复发送
    last_progress_text = {"text": None}

    # --- 进度回调 ---
    last_update_time = {"time": time.time()}
    last_progress_percent = {"value": 0}
    progress_state = {"last_stage": None, "last_percent": 0, "finished_shown": False}
    last_progress_text = {"text": ""}

    # 创建B站专用的消息更新器函数
    async def bilibili_message_updater(text_or_dict):
        try:
            logger.info(f"🔍 bilibili_message_updater 被调用，参数类型: {type(text_or_dict)}")
            logger.info(f"🔍 bilibili_message_updater 参数内容: {text_or_dict}")

            # 如果已经显示完成状态，忽略所有后续调用
            if progress_state["finished_shown"]:
                logger.info("B站下载已完成，忽略bilibili_message_updater后续调用")
                return

            # 处理字符串类型，避免重复发送相同内容
            if isinstance(text_or_dict, str):
                if text_or_dict == last_progress_text["text"]:
                    logger.info("🔍 跳过重复内容")
                    return  # 跳过重复内容
                last_progress_text["text"] = text_or_dict
                await status_message.edit_text(text_or_dict, parse_mode=None)
                return

            # 检查是否为字典类型（来自progress_hook的进度数据）
            if isinstance(text_or_dict, dict):
                logger.info(f"🔍 检测到字典类型，状态: {text_or_dict.get('status')}")

                # 记录文件名（用于文件查找）
                if text_or_dict.get("status") == "finished":
                    filename = text_or_dict.get('filename', '')
                    if filename:
                        # 记录到progress_data中
                        if progress_data and isinstance(progress_data, dict):
                            if 'downloaded_files' not in progress_data:
                                progress_data['downloaded_files'] = []
                            progress_data['downloaded_files'].append(filename)
                        logger.info(f"📝 B站下载器记录完成文件: {filename}")

                if text_or_dict.get("status") == "finished":
                    # 对于finished状态，不调用update_progress，避免显示错误的进度信息
                    logger.info("🔍 检测到finished状态，跳过update_progress调用")
                    return
                elif text_or_dict.get("status") == "downloading":
                    # 这是来自progress_hook的下载进度数据
                    logger.info("🔍 检测到下载进度数据，准备调用 update_progress...")
                    # 这里需要实现update_progress逻辑，暂时先记录
                    logger.info(f"📊 B站下载进度: {text_or_dict}")
                else:
                    # 其他字典状态，转换为文本
                    logger.info(f"🔍 其他字典状态: {text_or_dict}")
                    dict_text = str(text_or_dict)
                    if dict_text == last_progress_text["text"]:
                        logger.info("🔍 跳过重复字典内容")
                        return  # 跳过重复内容
                    last_progress_text["text"] = dict_text
                    await status_message.edit_text(dict_text, parse_mode=None)
            else:
                # 普通文本消息
                logger.info(f"🔍 普通文本消息: {text_or_dict}")
                text_str = str(text_or_dict)
                if text_str == last_progress_text["text"]:
                    logger.info("🔍 跳过重复文本内容")
                    return  # 跳过重复内容
                last_progress_text["text"] = text_str
                await status_message.edit_text(text_str, parse_mode=None)
        except Exception as e:
            logger.error(f"❌ bilibili_message_updater 处理错误: {e}")
            logger.error(f"❌ 异常类型: {type(e)}")
            import traceback
            logger.error(f"❌ 异常堆栈: {traceback.format_exc()}")
            if "Message is not modified" not in str(e):
                logger.warning(f"更新B站状态消息失败: {e}")

    return bilibili_message_updater

def single_video_progress_hook(message_updater=None, progress_data=None, status_message=None, context=None):
    """
    适用于所有单集下载的 yt-dlp 进度回调，下载过程中显示进度，下载完成后显示文件信息。
    整合了完整的进度显示逻辑，包括进度条、速度、剩余时间等。
    """
    import os  # 导入os模块以解决作用域问题
    import time
    import threading
    
    # 定义工具函数，避免作用域问题
    def _clean_filename_for_display_local(filename: str) -> str:
        try:
            import re
            # 只保留文件名，移除路径
            display_name = os.path.basename(filename) if filename else ""
            # 移除时间戳前缀(10位数字+下划线)
            if display_name and re.match(r"^\d{10}_", display_name):
                display_name = display_name[11:]
            # 智能截断过长文件名
            if len(display_name) > 35:
                name, ext = os.path.splitext(display_name)
                display_name = name[:30] + "..." + ext
            return display_name
        except Exception:
            filename = filename or ""
            # 确保只返回文件名
            display_name = os.path.basename(filename)
            return display_name if len(display_name) <= 35 else display_name[:32] + "..."

    def _create_progress_bar_local(percent: float, length: int = 20) -> str:
        filled_length = int(length * percent / 100)
        return "█" * filled_length + "░" * (length - filled_length)

    # 初始化进度数据
    if progress_data is None:
        progress_data = {"final_filename": None, "lock": threading.Lock()}

    # 初始化更新频率控制
    last_update_time = {"time": 0}

    def progress_hook(d):
        # 显示进度日志
        logger.info(f"🔍 [PROGRESS_HOOK] 被调用: {d.get('status', 'unknown')}")
        logger.info(f"🔍 [PROGRESS_DEBUG] status_message: {status_message is not None}, context: {context is not None}")
        if isinstance(d, dict) and d.get('status') == 'downloading':
            progress = (d.get('downloaded_bytes', 0) / (d.get('total_bytes', 1))) * 100
            logger.info(f"📊 下载进度: {progress:.1f}%")
        elif isinstance(d, dict) and d.get('status') == 'finished':
            logger.info("✅ 下载完成")
        
        # 支持字符串类型，直接发到Telegram
        if isinstance(d, str):
            if message_updater and status_message:
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)

                async def do_update():
                    try:
                        await status_message.edit_text(d, parse_mode=None)
                    except Exception as e:
                        logger.warning(f"发送字符串进度到TG失败: {e}")

                asyncio.run_coroutine_threadsafe(do_update(), loop)
            return

        # 添加类型检查，确保d是字典类型
        if not isinstance(d, dict):
            logger.warning(f"progress_hook接收到非字典类型参数: {type(d)}, 内容: {d}")
            return

        # 更新 progress_data
        try:
            if d['status'] == 'downloading':
                raw_filename = d.get('filename', '')
                display_filename = os.path.basename(raw_filename) if raw_filename else 'video.mp4'
                progress_data.update({
                    'filename': display_filename,
                    'total_bytes': d.get('total_bytes') or d.get('total_bytes_estimate', 0),
                    'downloaded_bytes': d.get('downloaded_bytes', 0),
                    'speed': d.get('speed', 0),
                    'status': 'downloading',
                    'progress': (d.get('downloaded_bytes', 0) / (d.get('total_bytes') or d.get('total_bytes_estimate', 1))) * 100 if (d.get('total_bytes') or d.get('total_bytes_estimate', 0)) > 0 else 0.0
                })
            elif d['status'] == 'finished':
                final_filename = d.get('filename', '')
                display_filename = os.path.basename(final_filename) if final_filename else 'video.mp4'
                progress_data.update({
                    'filename': display_filename,
                    'status': 'finished',
                    'final_filename': final_filename,
                    'progress': 100.0
                })
                logger.info(f"📝 记录最终文件名: {final_filename}")
        except Exception as e:
            logger.error(f"更新 progress_data 错误: {str(e)}")

        # 如果没有status_message和context，使用简单的message_updater
        logger.info(f"🔍 [PROGRESS_DEBUG] status_message: {status_message is not None}, context: {context is not None}")
        if not status_message or not context:
            if message_updater:
                logger.info(f"🔍 single_video_progress_hook 调用简单模式: status={d.get('status')}, async={asyncio.iscoroutinefunction(message_updater)}")

                if asyncio.iscoroutinefunction(message_updater):
                    # 异步函数，在独立线程中创建新的事件循环来运行
                    try:
                        logger.info(f"🔍 检测到异步进度更新器，创建新线程处理")

                        def run_async_in_thread():
                            try:
                                # 在新线程中创建事件循环
                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)

                                # 运行异步函数
                                loop.run_until_complete(message_updater(d))
                                loop.close()

                                logger.info(f"✅ 线程中异步进度回调调用成功")
                            except Exception as e:
                                logger.warning(f"线程中异步进度回调调用失败: {e}")

                        # 启动线程（不等待完成）
                        import threading
                        thread = threading.Thread(target=run_async_in_thread, daemon=True)
                        thread.start()

                    except Exception as e:
                        logger.warning(f"创建异步进度回调线程失败: {e}")
                else:
                    try:
                        result = message_updater(d)
                        logger.info(f"✅ 同步进度回调调用成功: {result}")
                    except Exception as e:
                        logger.warning(f"进度回调调用失败: {e}")
            else:
                logger.warning("⚠️ message_updater 为空，跳过进度回调")
            return

        # 完整的进度显示逻辑
        now = time.time()

        # 动态更新频率控制：更宽松的频率控制
        total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
        if total_bytes > 0 and total_bytes < 5 * 1024 * 1024:  # 小于5MB的文件
            update_interval = 0.01  # 10ms更新一次，确保小文件也能看到进度
        else:
            update_interval = 0.1  # 大文件0.1秒更新一次

        time_since_last = now - last_update_time['time']
        
        # 计算当前进度
        current_progress = 0
        if total_bytes > 0:
            current_progress = (d.get('downloaded_bytes', 0) / total_bytes) * 100
        
        # 获取上次的进度
        if progress_data and isinstance(progress_data, dict):
            last_progress = progress_data.get('last_progress', 0)
        else:
            last_progress = 0
        
        # 强制更新条件：
        # 1. 超过1秒没有更新
        # 2. 进度变化超过1%
        # 3. 下载完成
        force_update = (time_since_last > 1.0 or 
                       abs(current_progress - last_progress) >= 1.0 or
                       d.get('status') == 'finished')
        
        if time_since_last < update_interval and not force_update:
            logger.info(f"⏰ 跳过更新，距离上次更新仅 {time_since_last:.2f}秒，需要等待 {update_interval}秒")
            return
        
        if force_update:
            if time_since_last > 1.0:
                logger.info(f"🔄 强制更新，距离上次更新已 {time_since_last:.2f}秒")
            elif abs(current_progress - last_progress) >= 1.0:
                logger.info(f"🔄 强制更新，进度变化 {last_progress:.1f}% -> {current_progress:.1f}%")
            elif d.get('status') == 'finished':
                logger.info(f"🔄 强制更新，下载完成")
        
        # 更新进度记录
        if progress_data and isinstance(progress_data, dict):
            progress_data['last_progress'] = current_progress

        # 处理下载完成状态 - 直接显示完成信息并返回
        if d.get('status') == 'finished':
            logger.info("yt-dlp下载完成，显示完成信息")

            # 获取进度信息
            if progress_data and isinstance(progress_data, dict):
                filename = progress_data.get('filename', 'video.mp4')
                total_bytes = progress_data.get('total_bytes', 0)
                downloaded_bytes = progress_data.get('downloaded_bytes', 0)
            else:
                filename = 'video.mp4'
                total_bytes = 0
                downloaded_bytes = 0

            # 监控文件合并状态
            actual_filename = d.get('filename', filename)
            if actual_filename.endswith('.part'):
                logger.warning(f"⚠️ 文件合并可能失败: {actual_filename}")
            else:
                logger.info(f"✅ 文件下载并合并成功: {actual_filename}")

            # 显示完成信息
            display_filename = _clean_filename_for_display_local(filename)
            progress_bar = _create_progress_bar_local(100.0)
            size_mb = total_bytes / (1024 * 1024) if total_bytes > 0 else downloaded_bytes / (1024 * 1024)

            completion_text = (
                f"📝 文件：{display_filename}\n"
                f"💾 大小：{size_mb:.2f}MB\n"
                f"⚡ 速度：完成\n"
                f"⏳ 预计剩余：0秒\n"
                f"📊 进度：{progress_bar} (100.0%)"
            )

            async def do_update():
                try:
                    await status_message.edit_text(completion_text, parse_mode=None)
                    logger.info("📱 显示下载完成进度信息")
                except Exception as e:
                    logger.warning(f"显示完成进度信息失败: {e}")

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

            asyncio.run_coroutine_threadsafe(do_update(), loop)
            return

        # 处理下载中状态 - 这是关键部分，需要发送到Telegram
        if d.get('status') == 'downloading':
            logger.info(f"🔍 [DOWNLOADING_DEBUG] 进入下载中状态处理")
            logger.info(f"🔍 [DOWNLOADING_DEBUG] status_message: {status_message is not None}, context: {context is not None}")
            last_update_time['time'] = now

            total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            downloaded_bytes = d.get('downloaded_bytes', 0)
            speed_bytes_s = d.get('speed', 0)
            eta_seconds = d.get('eta', 0)
            filename = d.get('filename', '') or "正在下载..."
            logger.info(f"🔍 [DOWNLOADING_DEBUG] 文件信息: {filename}, 总大小: {total_bytes}, 已下载: {downloaded_bytes}")

            # 计算进度
            logger.info(f"🔍 [TOTAL_BYTES_DEBUG] total_bytes: {total_bytes}, 条件检查: {total_bytes > 0}")
            if total_bytes > 0:
                progress = (downloaded_bytes / total_bytes) * 100
                progress_bar = _create_progress_bar_local(progress)
                size_mb = total_bytes / (1024 * 1024)
                speed_mb = (speed_bytes_s or 0) / (1024 * 1024)

                # 计算预计剩余时间
                eta_text = ""
                if speed_bytes_s and total_bytes and downloaded_bytes < total_bytes:
                    remaining = total_bytes - downloaded_bytes
                    eta = int(remaining / speed_bytes_s)
                    mins, secs = divmod(eta, 60)
                    if mins > 0:
                        eta_text = f"{mins}分{secs}秒"
                    else:
                        eta_text = f"{secs}秒"
                elif speed_bytes_s:
                    eta_text = "计算中"
                else:
                    eta_text = "未知"

                display_filename = _clean_filename_for_display_local(filename)
                progress_text = (
                    f"📝 文件：{display_filename}\n"
                    f"💾 大小：{size_mb:.2f}MB\n"
                    f"⚡ 速度：{speed_mb:.2f}MB/s\n"
                    f"⏳ 预计剩余：{eta_text}\n"
                    f"📊 进度：{progress_bar} ({progress:.1f}%)"
                )

                async def do_update():
                    try:
                        logger.info(f"🔍 [DO_UPDATE_DEBUG] 开始更新Telegram消息")
                        logger.info(f"🔍 [DO_UPDATE_DEBUG] status_message: {status_message is not None}")
                        logger.info(f"🔍 [DO_UPDATE_DEBUG] progress_text: {progress_text[:100]}...")
                        await status_message.edit_text(progress_text, parse_mode=None)
                        logger.info(f"📱 更新Telegram进度: {progress:.1f}% - 文件: {display_filename}")
                    except Exception as e:
                        logger.error(f"🔍 [DO_UPDATE_ERROR] 更新Telegram失败: {e}")
                        if "Message is not modified" not in str(e):
                            logger.warning(f"更新Telegram进度失败: {e}")
                        else:
                            logger.info(f"📱 Telegram消息未修改，跳过更新")
                
                logger.info(f"🔍 [DO_UPDATE_DEFINED] do_update 协程已定义")

                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)

                logger.info(f"🔍 [ASYNC_DEBUG] 调用 asyncio.run_coroutine_threadsafe (下载中状态)")
                logger.info(f"🔍 [ASYNC_DEBUG] loop: {loop is not None}")
                logger.info(f"🔍 [ASYNC_DEBUG] do_update 函数: {do_update}")
                
                # 检查事件循环是否正在运行
                try:
                    if loop.is_running():
                        logger.info(f"🔍 [ASYNC_DEBUG] 事件循环正在运行，使用 run_coroutine_threadsafe")
                        future = asyncio.run_coroutine_threadsafe(do_update(), loop)
                        logger.info(f"🔍 [ASYNC_DEBUG] asyncio.run_coroutine_threadsafe 调用完成, future: {future}")
                        logger.info(f"🔍 [ASYNC_DEBUG] future.done(): {future.done()}")
                    else:
                        logger.info(f"🔍 [ASYNC_DEBUG] 事件循环未运行，直接运行协程")
                        # 如果事件循环没有运行，直接运行协程
                        asyncio.run(do_update())
                        logger.info(f"🔍 [ASYNC_DEBUG] 协程直接运行完成")
                except Exception as e:
                    logger.error(f"🔍 [ASYNC_ERROR] 异步调用失败: {e}")
                    # 备用方案：使用线程池
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(asyncio.run, do_update())
                        logger.info(f"🔍 [ASYNC_DEBUG] 使用线程池运行协程: {future}")
            else:
                # 没有总大小信息时的处理
                display_filename = _clean_filename_for_display_local(filename)
                speed_mb = (speed_bytes_s or 0) / (1024 * 1024)
                progress_text = (
                    f"📝 文件：{display_filename}\n"
                    f"💾 大小：计算中...\n"
                    f"⚡ 速度：{speed_mb:.2f}MB/s\n"
                    f"⏳ 预计剩余：未知\n"
                    f"📊 进度：下载中..."
                )

                async def do_update():
                    try:
                        await status_message.edit_text(progress_text, parse_mode=None)
                        logger.info(f"📱 更新Telegram进度（无大小信息）- 文件: {display_filename}")
                    except Exception as e:
                        if "Message is not modified" not in str(e):
                            logger.warning(f"更新Telegram进度失败: {e}")
                        else:
                            logger.info(f"📱 Telegram消息未修改，跳过更新")

                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)

                asyncio.run_coroutine_threadsafe(do_update(), loop)

    return progress_hook


def apple_music_progress_hook(message_updater=None, progress_data=None, status_message=None, context=None):
    """
    Apple Music 下载进度回调，支持下载和解密两个阶段的进度显示
    """
    import os
    import time
    import threading

    # 初始化进度数据
    if progress_data is None:
        progress_data = {"final_filename": None, "lock": threading.Lock()}

    # 初始化更新频率控制
    last_update_time = {"time": 0}
    last_message_content = {"text": ""}

    def progress_hook(progress_info):
        # 处理新的进度信息格式
        if isinstance(progress_info, dict):
            try:
                phase = progress_info.get('phase', 'unknown')
                
                if phase == 'downloading':
                    # 下载阶段
                    percentage = progress_info.get('percentage', 0)
                    downloaded = progress_info.get('downloaded', 0)
                    total = progress_info.get('total', 0)
                    unit = progress_info.get('unit', 'MB')
                    speed = progress_info.get('speed', '0 MB/s')
                    
                    # 计算预计剩余时间
                    if speed and 'MB/s' in speed:
                        try:
                            speed_value = float(speed.replace(' MB/s', ''))
                            if speed_value > 0:
                                remaining_mb = total - downloaded
                                remaining_seconds = remaining_mb / speed_value
                                if remaining_seconds < 60:
                                    remaining_time = f"00:{int(remaining_seconds):02d}"
                                else:
                                    minutes = int(remaining_seconds // 60)
                                    seconds = int(remaining_seconds % 60)
                                    remaining_time = f"{minutes:02d}:{seconds:02d}"
                            else:
                                remaining_time = "00:00"
                        except:
                            remaining_time = "00:00"
                    else:
                        remaining_time = "00:00"
                    
                    # 创建进度条
                    progress_bar_length = 20
                    filled_length = int(progress_bar_length * percentage / 100)
                    progress_bar = "█" * filled_length + "░" * (progress_bar_length - filled_length)
                    
                    # 获取文件名（如果可用）
                    filename = progress_info.get('filename', '未知文件')
                    
                    # 判断是专辑还是单曲（通过检查文件名是否包含扩展名）
                    if '.' in filename and filename.endswith(('.flac', '.m4a', '.aac')):
                        # 单曲：显示文件信息
                        file_display = f"📝 文件: {filename}"
                        progress_text = (
                            f"🍎 Apple Music 下载中\n\n"
                            f"{file_display}\n"
                            f"💾 大小: {downloaded:.2f}{unit} / {total:.2f}{unit}\n"
                            f"⚡️ 下载速度: {speed}\n"
                            f"⏳ 预计剩余: {remaining_time}\n"
                            f"📊 进度: {progress_bar} {percentage}%"
                        )
                    else:
                        # 专辑：显示专辑信息和文件信息
                        # 专辑下载时，需要显示当前正在下载的单曲名称
                        album_name = filename
                        current_track = progress_info.get('current_track', None)
                        
                        if current_track:
                            # 如果有当前单曲名称，显示为 "专辑名 + 当前单曲 + .m4a格式"
                            file_display = f"📀 专辑: {album_name}\n📝 文件: {current_track}.m4a"
                        else:
                            # 如果没有当前单曲名称，显示专辑名
                            file_display = f"📀 专辑: {album_name}\n📝 文件: 正在获取单曲信息..."
                        
                        progress_text = (
                            f"🍎 Apple Music 下载中\n\n"
                            f"{file_display}\n"
                            f"💾 大小: {downloaded:.2f}{unit} / {total:.2f}{unit}\n"
                            f"⚡️ 下载速度: {speed}\n"
                            f"⏳ 预计剩余: {remaining_time}\n"
                            f"📊 进度: {progress_bar} {percentage}%"
                        )
                    
                    # 发送进度信息到Telegram
                    if message_updater and status_message:
                        try:
                            loop = asyncio.get_running_loop()
                        except RuntimeError:
                            try:
                                loop = asyncio.get_event_loop()
                            except RuntimeError:
                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)

                        async def do_update():
                            try:
                                await status_message.edit_text(progress_text, parse_mode='Markdown')
                            except Exception as e:
                                logger.warning(f"发送Apple Music进度到TG失败: {e}")

                        asyncio.run_coroutine_threadsafe(do_update(), loop)
                    return
                    
                else:
                    # 其他阶段，简化处理，避免循环
                    logger.debug(f"🍎 Apple Music 阶段: {phase}")
                    return
                
            except Exception as e:
                logger.error(f"处理Apple Music进度信息时出错: {e}")
                return
        
        # 兼容旧的字符串类型，直接发到Telegram
        if isinstance(progress_info, str):
            text = progress_info
            if message_updater and status_message:
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)

                async def do_update():
                    try:
                        await status_message.edit_text(progress_info)
                    except Exception as e:
                        logger.warning(f"发送字符串进度到TG失败: {e}")

                asyncio.run_coroutine_threadsafe(do_update(), loop)
            return

    return progress_hook

# 全局变量，在函数外部定义，确保状态持久化
_netease_last_update_time = {"time": 0}

def netease_music_progress_hook(message_updater=None, progress_data=None, status_message=None, context=None):
    """
    网易云音乐下载进度回调，参考YouTube单集下载的进度显示样式
    """
    import os
    import time
    import threading
    
    # 定义工具函数，避免作用域问题
    def _clean_filename_for_display_local(filename: str) -> str:
        try:
            import re
            # 只保留文件名，移除路径
            display_name = os.path.basename(filename) if filename else ""
            # 移除时间戳前缀(10位数字+下划线)
            if display_name and re.match(r"^\d{10}_", display_name):
                display_name = display_name[11:]
            # 智能截断过长文件名
            if len(display_name) > 35:
                name, ext = os.path.splitext(display_name)
                display_name = name[:30] + "..." + ext
            return display_name
        except Exception:
            filename = filename or ""
            # 确保只返回文件名
            display_name = os.path.basename(filename)
            return display_name if len(display_name) <= 35 else display_name[:32] + "..."
    
    def _create_progress_bar_local(percent: float, length: int = 20) -> str:
        filled_length = int(length * percent / 100)
        return "█" * filled_length + "░" * (length - filled_length)
    


    # 初始化进度数据
    if progress_data is None:
        progress_data = {"final_filename": None, "lock": threading.Lock()}

    # 使用全局变量，确保状态在多次调用间持久化
    global _netease_last_update_time
    last_update_time = _netease_last_update_time

    def progress_hook(d):
        # 添加调试日志
        logger.info(f"🔍 [NETEASE_PROGRESS] 收到进度回调: {d}")
        logger.info(f"🔍 [NETEASE_PROGRESS] status_message: {status_message is not None}, context: {context is not None}, message_updater: {message_updater is not None}")
        
        # 支持字符串类型，直接发到Telegram
        if isinstance(d, str):
            if message_updater and status_message:
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)

                async def do_update():
                    try:
                        await status_message.edit_text(d, parse_mode=None)
                    except Exception as e:
                        logger.warning(f"发送字符串进度到TG失败: {e}")

                asyncio.run_coroutine_threadsafe(do_update(), loop)
            return

        # 添加类型检查，确保d是字典类型
        if not isinstance(d, dict):
            logger.warning(f"netease_progress_hook接收到非字典类型参数: {type(d)}, 内容: {d}")
            return

        # 更新 progress_data
        try:
            if d['status'] == 'downloading':
                raw_filename = d.get('filename', '')
                display_filename = os.path.basename(raw_filename) if raw_filename else 'music.mp3'
                progress_data.update({
                    'filename': display_filename,
                    'total_bytes': d.get('total_bytes', 0),
                    'downloaded_bytes': d.get('downloaded_bytes', 0),
                    'speed': d.get('speed', 0),
                    'status': 'downloading',
                    'progress': (d.get('downloaded_bytes', 0) / d.get('total_bytes', 1)) * 100 if d.get('total_bytes', 0) > 0 else 0.0
                })
            elif d['status'] == 'finished':
                final_filename = d.get('filename', '')
                display_filename = os.path.basename(final_filename) if final_filename else 'music.mp3'
                progress_data.update({
                    'filename': display_filename,
                    'status': 'finished',
                    'final_filename': final_filename,
                    'progress': 100.0
                })
                logger.info(f"📝 网易云音乐下载完成: {final_filename}")
        except Exception as e:
            logger.error(f"更新网易云音乐进度数据错误: {str(e)}")

        # 如果没有status_message和context，使用简单的message_updater（但仍要执行完整的进度显示逻辑）
        simple_mode = not status_message or not context
        logger.info(f"🔍 [NETEASE_PROGRESS] simple_mode: {simple_mode}")
        
        if simple_mode and message_updater:
            logger.info(f"🔍 netease_progress_hook 简单模式: status={d.get('status')}")

            # 简单模式（参考Apple Music实现，移除频率控制）
            # 为简单模式创建格式化的进度文本
            try:
                if isinstance(d, dict) and d.get('status') == 'downloading':
                    downloaded_bytes = d.get('downloaded_bytes', 0)
                    speed = d.get('speed', 0)
                    filename = d.get('filename', 'music.mp3')
                    total_bytes = d.get('total_bytes', 0)
                    
                    if total_bytes > 0:
                        progress = (downloaded_bytes / total_bytes) * 100
                        speed_mb = speed / (1024 * 1024) if speed > 0 else 0
                        total_mb = total_bytes / (1024 * 1024)
                        downloaded_mb = downloaded_bytes / (1024 * 1024)
                        
                        # 计算预计剩余时间
                        if speed > 0 and total_bytes > downloaded_bytes:
                            remaining = total_bytes - downloaded_bytes
                            eta_seconds = int(remaining / speed)
                            mins, secs = divmod(eta_seconds, 60)
                            if mins > 0:
                                eta_str = f"{mins:02d}:{secs:02d}"
                            else:
                                eta_str = f"00:{secs:02d}"
                        else:
                            eta_str = "未知"
                        
                        # 创建进度条（和单集下载一样的样式）
                        progress_bar = _create_progress_bar(progress)
                        
                        # 使用和单集下载相同的格式
                        display_filename = _clean_filename_for_display(filename)
                        progress_text = (
                            f"📝 文件: `{display_filename}`\n"
                            f"💾 大小: `{downloaded_mb:.2f}MB / {total_mb:.2f}MB`\n"
                            f"⚡ 速度: `{speed_mb:.2f}MB/s`\n"
                            f"⏳ 预计剩余: `{eta_str}`\n"
                            f"📊 进度: {progress_bar} `{progress:.1f}%`"
                        )
                    else:
                        display_filename = _clean_filename_for_display(filename)
                        progress_text = (
                            f"📝 文件: `{display_filename}`\n"
                            f"💾 大小: 未知\n"
                            f"⚡ 速度: 未知\n"
                            f"⏳ 预计剩余: 未知\n"
                            f"📊 进度: 下载中..."
                        )
                        
                    # 使用普通文本
                    simple_message = progress_text
                    
                    # 发送消息到Telegram
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        try:
                            loop = asyncio.get_event_loop()
                        except RuntimeError:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)

                    async def do_update():
                        try:
                            await status_message.edit_text(simple_message, parse_mode=None)
                        except Exception as e:
                            logger.warning(f"发送简单模式进度到TG失败: {e}")

                    asyncio.run_coroutine_threadsafe(do_update(), loop)
                    
                elif isinstance(d, dict) and d.get('status') == 'finished':
                    filename = d.get('filename', 'music.mp3')
                    total_bytes = d.get('total_bytes', 0)
                    total_mb = total_bytes / (1024 * 1024) if total_bytes > 0 else 0
                    
                    # 使用和单集下载相同的完成格式
                    display_filename = _clean_filename_for_display(filename)
                    progress_bar = _create_progress_bar(100.0)
                    finish_text = (
                        f"📝 文件: `{display_filename}`\n"
                        f"💾 大小: `{total_mb:.2f}MB`\n"
                        f"⚡ 速度: 完成\n"
                        f"⏳ 预计剩余: 0秒\n"
                        f"📊 进度: {progress_bar} `100.0%`"
                    )
                    # 使用普通文本
                    simple_message = finish_text
                    
                    # 发送消息到Telegram
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        try:
                            loop = asyncio.get_event_loop()
                        except RuntimeError:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)

                    async def do_update():
                        try:
                            await status_message.edit_text(simple_message, parse_mode=None)
                        except Exception as e:
                            logger.warning(f"发送简单模式完成消息到TG失败: {e}")

                    asyncio.run_coroutine_threadsafe(do_update(), loop)
                
            except Exception as e:
                logger.warning(f"网易云音乐简单模式回调失败: {e}")
        elif simple_mode:
            logger.warning("⚠️ 网易云音乐简单模式但无message_updater")
        
        # 继续执行完整的进度显示逻辑（无论是否为简单模式）

        # 完整的进度显示逻辑（参考Apple Music实现，移除频率控制）
        logger.info(f"🔍 [NETEASE_PROGRESS] 进入完整进度显示逻辑: status={d.get('status')}")

        # 处理下载中状态
        if d.get('status') == 'downloading':
            logger.info(f"🔍 [NETEASE_PROGRESS] 处理下载中状态")

            total_bytes = d.get('total_bytes', 0)
            downloaded_bytes = d.get('downloaded_bytes', 0)
            speed_bytes_s = d.get('speed', 0)
            eta_seconds = d.get('eta', 0)
            filename = d.get('filename', '') or "正在下载..."
            now = time.time()

            # 计算进度
            if total_bytes > 0:
                progress = (downloaded_bytes / total_bytes) * 100
                progress_bar = _create_progress_bar(progress)
                size_mb = total_bytes / (1024 * 1024)
                speed_mb = (speed_bytes_s or 0) / (1024 * 1024)

                # 计算预计剩余时间
                eta_text = ""
                if speed_bytes_s and total_bytes and downloaded_bytes < total_bytes:
                    remaining = total_bytes - downloaded_bytes
                    eta = int(remaining / speed_bytes_s)
                    mins, secs = divmod(eta, 60)
                    if mins > 0:
                        eta_text = f"{mins}分{secs}秒"
                    else:
                        eta_text = f"{secs}秒"
                elif speed_bytes_s:
                    eta_text = "计算中"
                else:
                    eta_text = "未知"

                display_filename = _clean_filename_for_display(filename)
                progress_text = (
                    f"🎵 音乐：{display_filename}\n"
                    f"💾 大小：{downloaded_bytes/(1024*1024):.2f}MB / {size_mb:.2f}MB\n"
                    f"⚡ 速度：{speed_mb:.2f}MB/s\n"
                    f"⏳ 预计剩余：{eta_text}\n"
                    f"📊 进度：{progress_bar} ({progress:.1f}%)"
                )

                async def do_update():
                    try:
                        await status_message.edit_text(progress_text)
                        logger.info(f"📱 更新Telegram进度: {progress:.1f}% - 文件: {display_filename}")
                        # 更新成功后才更新时间戳
                        last_update_time['time'] = now
                    except Exception as e:
                        logger.warning(f"🔍 [NETEASE_PROGRESS] 更新网易云音乐进度失败: {e}")
                        if "Message is not modified" not in str(e):
                            # 备用：如果status_message更新失败，尝试使用message_updater
                            if message_updater:
                                try:
                                    logger.info(f"🔍 [NETEASE_PROGRESS] 尝试使用备用message_updater")
                                    if asyncio.iscoroutinefunction(message_updater):
                                        await message_updater(progress_text)
                                    else:
                                        message_updater(progress_text)
                                    logger.info("✅ 使用备用message_updater更新成功")
                                    # 备用方案成功也更新时间戳
                                    last_update_time['time'] = now
                                except Exception as backup_e:
                                    logger.warning(f"备用message_updater也失败: {backup_e}")

                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)

                if loop.is_running():
                    # 事件循环正在运行，使用 run_coroutine_threadsafe
                    try:
                        future = asyncio.run_coroutine_threadsafe(do_update(), loop)
                        # 尝试获取结果，设置短超时
                        try:
                            result = future.result(timeout=0.1)
                        except asyncio.TimeoutError:
                            pass  # 超时是正常的，任务在后台执行
                        except Exception as e:
                            logger.error(f"🔍 [NETEASE_PROGRESS] 进度更新任务执行失败: {e}")
                    except Exception as e:
                        logger.error(f"🔍 [NETEASE_PROGRESS] 提交进度更新任务失败: {e}")
                else:
                    # 事件循环没有运行，直接运行协程
                    try:
                        asyncio.run(do_update())
                    except Exception as e:
                        logger.error(f"🔍 [NETEASE_PROGRESS] 直接运行协程失败: {e}")
            return

        # 处理下载完成状态 - 直接显示完成信息并返回
        if d.get('status') == 'finished':
            logger.info("🎵 网易云音乐下载完成，显示完成信息")

            # 获取进度信息
            filename = progress_data.get('filename', 'music.mp3')
            total_bytes = progress_data.get('total_bytes', 0)
            downloaded_bytes = progress_data.get('downloaded_bytes', 0)

            # 显示完成信息
            display_filename = _clean_filename_for_display(filename)
            progress_bar = _create_progress_bar(100.0)
            size_mb = total_bytes / (1024 * 1024) if total_bytes > 0 else downloaded_bytes / (1024 * 1024)

            completion_text = (
                f"🎵 音乐：{display_filename}\n"
                f"💾 大小：{size_mb:.2f}MB\n"
                f"⚡ 速度：完成\n"
                f"⏳ 预计剩余：0秒\n"
                f"📊 进度：{progress_bar} (100.0%)"
            )

            async def do_update():
                try:
                    await status_message.edit_text(completion_text)
                    logger.info("🎵 显示网易云音乐下载完成进度信息")
                    # 更新成功后才更新时间戳
                    last_update_time['time'] = now
                except Exception as e:
                    logger.warning(f"显示网易云音乐完成进度信息失败: {e}")
                    # 备用：如果status_message更新失败，尝试使用message_updater
                    if message_updater:
                        try:
                            if asyncio.iscoroutinefunction(message_updater):
                                await message_updater(completion_text)
                            else:
                                message_updater(completion_text)
                            logger.info("✅ 使用备用message_updater显示完成信息成功")
                            # 备用方案成功也更新时间戳
                            last_update_time['time'] = now
                        except Exception as backup_e:
                            logger.warning(f"备用message_updater显示完成信息也失败: {backup_e}")

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

            if loop.is_running():
                # 事件循环正在运行，使用 run_coroutine_threadsafe
                try:
                    future = asyncio.run_coroutine_threadsafe(do_update(), loop)
                    # 尝试获取结果，设置短超时
                    try:
                        result = future.result(timeout=0.1)
                    except asyncio.TimeoutError:
                        pass  # 超时是正常的，任务在后台执行
                    except Exception as e:
                        logger.error(f"🔍 [NETEASE_PROGRESS] 完成状态更新任务执行失败: {e}")
                except Exception as e:
                    logger.error(f"🔍 [NETEASE_PROGRESS] 提交完成状态更新任务失败: {e}")
            else:
                # 事件循环没有运行，直接运行协程
                try:
                    asyncio.run(do_update())
                except Exception as e:
                    logger.error(f"🔍 [NETEASE_PROGRESS] 直接运行完成状态协程失败: {e}")
            return

        # 处理下载中状态
        if d.get('status') == 'downloading':
            last_update_time['time'] = now

            total_bytes = d.get('total_bytes', 0)
            downloaded_bytes = d.get('downloaded_bytes', 0)
            speed_bytes_s = d.get('speed', 0)
            eta_seconds = d.get('eta', 0)
            filename = d.get('filename', '') or "正在下载..."

            # 计算进度
            if total_bytes > 0:
                progress = (downloaded_bytes / total_bytes) * 100
                progress_bar = _create_progress_bar(progress)
                size_mb = total_bytes / (1024 * 1024)
                speed_mb = (speed_bytes_s or 0) / (1024 * 1024)

                # 计算预计剩余时间
                eta_text = ""
                if speed_bytes_s and total_bytes and downloaded_bytes < total_bytes:
                    remaining = total_bytes - downloaded_bytes
                    eta = int(remaining / speed_bytes_s)
                    mins, secs = divmod(eta, 60)
                    if mins > 0:
                        eta_text = f"{mins}分{secs}秒"
                    else:
                        eta_text = f"{secs}秒"
                elif speed_bytes_s:
                    eta_text = "计算中"
                else:
                    eta_text = "未知"

                display_filename = _clean_filename_for_display(filename)
                progress_text = (
                    f"🎵 音乐：{display_filename}\n"
                    f"💾 大小：{downloaded_bytes/(1024*1024):.2f}MB / {size_mb:.2f}MB\n"
                    f"⚡ 速度：{speed_mb:.2f}MB/s\n"
                    f"⏳ 预计剩余：{eta_text}\n"
                    f"📊 进度：{progress_bar} ({progress:.1f}%)"
                )

                async def do_update():
                    try:
                        await status_message.edit_text(progress_text)
                    except Exception as e:
                        if "Message is not modified" not in str(e):
                            logger.warning(f"更新网易云音乐进度失败: {e}")
                            # 备用：如果status_message更新失败，尝试使用message_updater
                            if message_updater:
                                try:
                                    if asyncio.iscoroutinefunction(message_updater):
                                        await message_updater(progress_text)
                                    else:
                                        message_updater(progress_text)
                                    logger.info("✅ 使用备用message_updater更新成功")
                                except Exception as backup_e:
                                    logger.warning(f"备用message_updater也失败: {backup_e}")

                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)

                asyncio.run_coroutine_threadsafe(do_update(), loop)

        # 处理下载完成状态 - 直接显示完成信息并返回
        if d.get('status') == 'finished':
            logger.info("🎵 网易云音乐下载完成，显示完成信息")

            # 获取进度信息
            if progress_data and isinstance(progress_data, dict):
                filename = progress_data.get('filename', 'music.mp3')
                total_bytes = progress_data.get('total_bytes', 0)
                downloaded_bytes = progress_data.get('downloaded_bytes', 0)
            else:
                filename = 'music.mp3'
                total_bytes = 0
                downloaded_bytes = 0

            # 显示完成信息
            display_filename = _clean_filename_for_display_local(filename)
            progress_bar = _create_progress_bar_local(100.0)
            size_mb = total_bytes / (1024 * 1024) if total_bytes > 0 else downloaded_bytes / (1024 * 1024)

            completion_text = (
                f"🎵 音乐：{display_filename}\n"
                f"💾 大小：{size_mb:.2f}MB\n"
                f"⚡ 速度：完成\n"
                f"⏳ 预计剩余：0秒\n"
                f"📊 进度：{progress_bar} (100.0%)"
            )

            async def do_update():
                try:
                    await status_message.edit_text(completion_text, parse_mode=None)
                    logger.info("🎵 显示网易云音乐下载完成进度信息")
                except Exception as e:
                    logger.warning(f"显示网易云音乐完成进度信息失败: {e}")
                    # 备用：如果status_message更新失败，尝试使用message_updater
                    if message_updater:
                        try:
                            if asyncio.iscoroutinefunction(message_updater):
                                await message_updater(completion_text)
                            else:
                                message_updater(completion_text)
                            logger.info("✅ 使用备用message_updater显示完成信息成功")
                        except Exception as backup_e:
                            logger.warning(f"备用message_updater显示完成信息也失败: {backup_e}")

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

            asyncio.run_coroutine_threadsafe(do_update(), loop)
            return

        # 处理下载中状态
        if d.get('status') == 'downloading':
            last_update_time['time'] = now

            total_bytes = d.get('total_bytes', 0)
            downloaded_bytes = d.get('downloaded_bytes', 0)
            speed_bytes_s = d.get('speed', 0)
            eta_seconds = d.get('eta', 0)
            filename = d.get('filename', '') or "正在下载..."

            # 计算进度
            if total_bytes > 0:
                progress = (downloaded_bytes / total_bytes) * 100
                progress_bar = _create_progress_bar_local(progress)
                size_mb = total_bytes / (1024 * 1024)
                speed_mb = (speed_bytes_s or 0) / (1024 * 1024)

                # 计算预计剩余时间
                eta_text = ""
                if speed_bytes_s and total_bytes and downloaded_bytes < total_bytes:
                    remaining = total_bytes - downloaded_bytes
                    eta = int(remaining / speed_bytes_s)
                    mins, secs = divmod(eta, 60)
                    if mins > 0:
                        eta_text = f"{mins}分{secs}秒"
                    else:
                        eta_text = f"{secs}秒"
                elif speed_bytes_s:
                    eta_text = "计算中"
                else:
                    eta_text = "未知"

                display_filename = _clean_filename_for_display_local(filename)
                progress_text = (
                    f"🎵 音乐：{display_filename}\n"
                    f"💾 大小：{size_mb:.2f}MB\n"
                    f"⚡ 速度：{speed_mb:.2f}MB/s\n"
                    f"⏳ 预计剩余：{eta_text}\n"
                    f"📊 进度：{progress_bar} ({progress:.1f}%)"
                )

                async def do_update():
                    try:
                        await status_message.edit_text(progress_text, parse_mode=None)
                    except Exception as e:
                        if "Message is not modified" not in str(e):
                            logger.warning(f"更新网易云音乐进度失败: {e}")
                            # 备用：如果status_message更新失败，尝试使用message_updater
                            if message_updater:
                                try:
                                    if asyncio.iscoroutinefunction(message_updater):
                                        await message_updater(progress_text)
                                    else:
                                        message_updater(progress_text)
                                    logger.info("✅ 使用备用message_updater更新成功")
                                except Exception as backup_e:
                                    logger.warning(f"备用message_updater也失败: {backup_e}")

                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)

                asyncio.run_coroutine_threadsafe(do_update(), loop)

    return progress_hook
class VideoDownloader:
    # 平台枚举定义
    class Platform(str, Enum):
        DOUYIN = "douyin"
        KUAISHOU = "kuaishou"
        XIAOHONGSHU = "xiaohongshu"
        UNKNOWN = "unknown"

    def __init__(
        self,
        base_download_path: str,
        x_cookies_path: str = None,
        b_cookies_path: str = None,
        youtube_cookies_path: str = None,
        douyin_cookies_path: str = None,
        kuaishou_cookies_path: str = None,
        facebook_cookies_path: str = None,
        instagram_cookies_path: str = None,
    ):
        self.download_path = Path(base_download_path).resolve()
        self.x_download_path = self.download_path / "X"
        self.bilibili_download_path = self.download_path / "Bilibili"
        self.youtube_download_path = self.download_path / "YouTube"
        self.music_download_path = self.download_path / "Music"
        self.pornhub_download_path = self.download_path / "Pornhub"
        self.telegram_download_path = self.download_path / "Telegram"
        self.telegraph_download_path = self.download_path / "Telegraph"
        self.douyin_download_path = self.download_path / "Douyin"
        self.kuaishou_download_path = self.download_path / "Kuaishou"
        self.toutiao_download_path = self.download_path / "Toutiao"
        self.facebook_download_path = self.download_path / "Facebook"
        self.weibo_download_path = self.download_path / "Weibo"
        self.instagram_download_path = self.download_path / "Instagram"
        self.tiktok_download_path = self.download_path / "TikTok"
        self.netease_download_path = self.download_path / "NeteaseCloudMusic"
        self.qqmusic_download_path = self.download_path / "QQMusic"
        self.youtubemusic_download_path = Path("/downloads/YouTubeMusic")
        self.apple_music_download_path = self.download_path / "AppleMusic"
        self.x_cookies_path = x_cookies_path
        self.b_cookies_path = b_cookies_path
        self.youtube_cookies_path = youtube_cookies_path
        self.douyin_cookies_path = douyin_cookies_path
        self.kuaishou_cookies_path = kuaishou_cookies_path
        self.facebook_cookies_path = facebook_cookies_path
        self.instagram_cookies_path = instagram_cookies_path
        self.apple_music_cookies_path = os.environ.get("APPLEMUSIC_COOKIES") or os.environ.get("APPLEMUSIC_COOKIE_FILE") or "/app/cookies/apple_music_cookies.txt"
        self.proxy_host = os.environ.get("PROXY_HOST")
        
        # 初始化多线程下载器
        if MULTITHREAD_ENABLED:
            try:
                mt_threads = int(os.environ.get("MT_FILE_THREADS", "16"))
                mt_concurrent = int(os.environ.get("MT_CONCURRENT_FILES", "3"))
                mt_use_aria2c = os.environ.get("MT_USE_ARIA2C", "true").lower() == "true"
                
                self.multithread_downloader = create_downloader(
                    file_threads=mt_threads,
                    concurrent_files=mt_concurrent,
                    use_aria2c=mt_use_aria2c
                )
                logger.info(f"✅ 多线程下载器初始化成功（线程数：{mt_threads}, 并发数：{mt_concurrent}）")
                
                # 初始化批量下载处理器
                self.batch_processor = BatchDownloadProcessor(
                    self.multithread_downloader,
                    max_concurrent=mt_concurrent
                )
            except Exception as e:
                logger.error(f"❌ 多线程下载器初始化失败：{e}")
                self.multithread_downloader = None
                self.batch_processor = None
        else:
            self.multithread_downloader = None
            self.batch_processor = None
        
        # 初始化模块化下载器（如果可用）
        if MODULES_ENABLED:
            try:
                self.bilibili_downloader = BilibiliDownloader(self)
                self.youtube_downloader = YouTubeDownloader(self)
                self.music_downloader = MusicDownloader(self)
                self.social_downloader = SocialMediaDownloader(self)
                logger.info("✅ 模块化下载器初始化成功")
            except Exception as e:
                logger.error(f"❌ 模块化下载器初始化失败：{e}")
                self.bilibili_downloader = None
                self.youtube_downloader = None
                self.music_downloader = None
                self.social_downloader = None
        else:
            self.bilibili_downloader = None
            self.youtube_downloader = None
            self.music_downloader = None
            self.social_downloader = None
        
        # 初始化 Instagram 下载器
        try:
            from Instagram_downloader import InstagramPicDownloaderSimple
            self.instagram_downloader = InstagramPicDownloaderSimple(
                cookies_path=self.instagram_cookies_path or "/app/cookies/instagram_cookies.txt"
            )
            logger.info("✅ Instagram 下载器初始化成功")
        except ImportError as e:
            logger.warning(f"⚠️ Instagram 下载器导入失败: {e}")
            self.instagram_downloader = None
        except Exception as e:
            logger.error(f"❌ Instagram 下载器初始化失败: {e}")
            self.instagram_downloader = None

        # 初始化 Apple Music 下载器
        try:
            # 检查环境变量，决定使用哪个下载器
            # 如果没有设置AMDP环境变量，尝试自动检测AMD下载器是否可用
            amdp_env = os.environ.get("AMDP", "")
            if not amdp_env:
                # 自动检测：检查AMD工具是否可用
                amd_tool_path = "/app/amdp/amd"
                if os.path.exists(amd_tool_path) and os.access(amd_tool_path, os.X_OK):
                    logger.info("🔍 检测到AMD工具可用，自动启用AMD下载器")
                    os.environ["AMDP"] = "true"
                    use_amd = True
                else:
                    logger.info("🔍 未检测到AMD工具，使用GAMDL下载器")
                    use_amd = False
            else:
                use_amd = amdp_env.lower() == "true"
            
            logger.info(f"🔧 Apple Music 下载器环境变量 AMDP: {os.environ.get('AMDP', '未设置')} -> 使用AMD: {use_amd}")
            
            # 导入 asyncio 模块
            import asyncio
            
            # 检查当前事件循环状态
            try:
                current_loop = asyncio.get_running_loop()
                logger.info(f"🔍 检测到运行中的事件循环: {current_loop}")
                has_running_loop = True
            except RuntimeError:
                logger.info("✅ 没有运行中的事件循环")
                has_running_loop = False
            
            if use_amd:
                # 使用新的 apple-music-downloader 后端
                logger.info("🚀 尝试初始化 Apple Music Plus 下载器 (AMD)")
                
                # 在独立线程中初始化下载器，避免事件循环冲突
                def init_apple_music_downloader():
                    """在独立线程中初始化Apple Music下载器"""
                    try:
                        from applemusic_downloader_plus import AppleMusicDownloaderPlus
                        
                        # 检查输出目录
                        output_dir = str(self.apple_music_download_path)
                        if not os.path.exists(output_dir):
                            os.makedirs(output_dir, exist_ok=True)
                        
                        # 确保AMD工具目录存在
                        amd_dir = "/app/amdp"
                        if not os.path.exists(amd_dir):
                            os.makedirs(amd_dir, exist_ok=True)
                            logger.info(f"✅ 创建AMD工具目录: {amd_dir}")
                        
                        # 检查AMD工具是否可用
                        amd_tool_path = os.path.join(amd_dir, "amd")
                        if not os.path.exists(amd_tool_path):
                            logger.warning(f"⚠️ AMD工具不存在: {amd_tool_path}")
                        elif not os.access(amd_tool_path, os.X_OK):
                            logger.warning(f"⚠️ AMD工具不可执行: {amd_tool_path}")
                            try:
                                os.chmod(amd_tool_path, 0o755)
                                logger.info("✅ 修复AMD工具权限成功")
                            except Exception as e:
                                logger.error(f"❌ 修复AMD工具权限失败: {e}")
                        
                        downloader = AppleMusicDownloaderPlus(
                            output_dir=output_dir,
                            cookies_path=self.apple_music_cookies_path
                        )
                        
                        # 检查下载器是否真正可用
                        if hasattr(downloader, 'is_available'):
                            is_available = downloader.is_available()
                            if not is_available:
                                logger.error("❌ Apple Music Plus 下载器初始化失败：工具不可用")
                                return None
                        
                        # 额外检查：确保有可用的后端
                        if hasattr(downloader, 'backends'):
                            available_backends = [b for b in downloader.backends if b.is_available()]
                            if not available_backends:
                                logger.error("❌ Apple Music Plus 下载器初始化失败：没有可用的后端")
                                return None
                            logger.info(f"✅ Apple Music Plus 下载器后端检查通过: {[b.name for b in available_backends]}")
                        
                        # 验证配置文件是否正确创建
                        config_path = os.path.join(amd_dir, "config.yaml")
                        if os.path.exists(config_path):
                            try:
                                with open(config_path, 'r', encoding='utf-8') as f:
                                    config_content = f.read()
                                if "alac-save-folder:" in config_content:
                                    logger.info("✅ AMD配置文件验证成功")
                                else:
                                    logger.warning("⚠️ AMD配置文件内容可能不正确")
                            except Exception as e:
                                logger.warning(f"⚠️ 无法读取AMD配置文件: {e}")
                        else:
                            logger.warning(f"⚠️ AMD配置文件不存在: {config_path}")
                        
                        return downloader
                        
                    except Exception as e:
                        logger.error(f"❌ Apple Music Plus 下载器初始化失败: {e}")
                        import traceback
                        logger.error(f"📋 错误堆栈: {traceback.format_exc()}")
                        return None
                
                # 如果有运行的事件循环，使用线程池初始化
                if has_running_loop:
                    logger.info("🔄 在运行的事件循环中，使用线程池初始化下载器...")
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(init_apple_music_downloader)
                        self.apple_music_downloader = future.result()
                else:
                    # 没有运行的事件循环，直接初始化
                    logger.info("✅ 直接初始化下载器...")
                    self.apple_music_downloader = init_apple_music_downloader()
                
                if self.apple_music_downloader:
                    logger.info("✅ Apple Music Plus 下载器(AMD)初始化成功")
                else:
                    logger.error("❌ Apple Music Plus 下载器初始化失败")
                    
            else:
                # 使用原有的 gamdl 后端
                logger.info("🚀 尝试初始化 Apple Music 下载器 (GAMDL)")
                
                def init_gamdl_downloader():
                    """在独立线程中初始化GAMDL下载器"""
                    try:
                        from applemusic_downloader import AppleMusicDownloader
                        downloader = AppleMusicDownloader(
                            output_dir=str(self.apple_music_download_path),
                            cookies_path=self.apple_music_cookies_path
                        )
                        return downloader if downloader.gamdl_available else None
                    except Exception as e:
                        logger.error(f"❌ GAMDL下载器初始化失败: {e}")
                        return None
                
                # 如果有运行的事件循环，使用线程池初始化
                if has_running_loop:
                    logger.info("🔄 在运行的事件循环中，使用线程池初始化GAMDL下载器...")
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(init_gamdl_downloader)
                        self.apple_music_downloader = future.result()
                else:
                    # 没有运行的事件循环，直接初始化
                    logger.info("✅ 直接初始化GAMDL下载器...")
                    self.apple_music_downloader = init_gamdl_downloader()
                
                if self.apple_music_downloader:
                    logger.info("✅ Apple Music 下载器 (GAMDL) 初始化成功")
                else:
                    logger.warning("⚠️ Apple Music 下载器初始化失败：gamdl 不可用")
                    
        except ImportError as e:
            logger.error(f"❌ Apple Music 下载器导入失败: {e}")
            logger.error(f"🔍 详细错误信息: {type(e).__name__}: {str(e)}")
            self.apple_music_downloader = None
        except Exception as e:
            logger.error(f"❌ Apple Music 下载器初始化失败: {e}")
            logger.error(f"🔍 详细错误信息: {type(e).__name__}: {str(e)}")
            import traceback
            logger.error(f"📋 错误堆栈: {traceback.format_exc()}")
            self.apple_music_downloader = None
        self._main_loop = None
        try:
            import asyncio

            self._main_loop = asyncio.get_running_loop()
        except Exception:
            self._main_loop = None
        # 从环境变量获取是否转换格式的配置
        self.convert_to_mp4 = (
            os.getenv("YOUTUBE_CONVERT_TO_MP4", "true").lower() == "true"
        )
        logger.info(f"视频格式转换: {'开启' if self.convert_to_mp4 else '关闭'}")
        # 设置各平台下载路径（使用默认结构）
        self.x_download_path = self.download_path / "X"
        self.youtube_download_path = self.download_path / "YouTube"
        self.xvideos_download_path = self.download_path / "Xvideos"
        self.pornhub_download_path = self.download_path / "Pornhub"
        self.bilibili_download_path = self.download_path / "Bilibili"
        self.music_download_path = self.download_path / "Music"
        self.telegram_download_path = self.download_path / "Telegram"
        self.telegraph_download_path = self.download_path / "Telegraph"
        self.douyin_download_path = self.download_path / "Douyin"
        self.kuaishou_download_path = self.download_path / "Kuaishou"
        self.facebook_download_path = self.download_path / "Facebook"
        self.xiaohongshu_download_path = self.download_path / "Xiaohongshu"
        self.weibo_download_path = self.download_path / "Weibo"
        self.instagram_download_path = self.download_path / "Instagram"
        self.tiktok_download_path = self.download_path / "TikTok"
        self.netease_download_path = self.download_path / "NeteaseCloudMusic"
        self.qqmusic_download_path = self.download_path / "QQMusic"
        self.youtubemusic_download_path = Path("/downloads/YouTubeMusic")
        self.apple_music_download_path = self.download_path / "AppleMusic"
        # 创建所有下载目录
        for path in [
            self.x_download_path,
            self.youtube_download_path,
            self.xvideos_download_path,
            self.pornhub_download_path,
            self.bilibili_download_path,
            self.music_download_path,
            self.telegram_download_path,
            self.telegraph_download_path,
            self.douyin_download_path,
            self.kuaishou_download_path,
            self.facebook_download_path,
            self.xiaohongshu_download_path,
            self.weibo_download_path,
            self.instagram_download_path,
            self.tiktok_download_path,
            self.netease_download_path,
            self.qqmusic_download_path,
            self.youtubemusic_download_path,
            self.apple_music_download_path,
        ]:
            path.mkdir(parents=True, exist_ok=True)
        logger.info(f"X 下载路径: {self.x_download_path}")
        logger.info(f"YouTube 下载路径: {self.youtube_download_path}")
        logger.info(f"Xvideos 下载路径: {self.xvideos_download_path}")
        logger.info(f"Pornhub 下载路径: {self.pornhub_download_path}")
        logger.info(f"Bilibili 下载路径: {self.bilibili_download_path}")
        logger.info(f"音乐下载路径: {self.music_download_path}")
        logger.info(f"Telegram 文件下载路径: {self.telegram_download_path}")
        logger.info(f"Telegraph 文件下载路径: {self.telegraph_download_path}")
        logger.info(f"抖音下载路径: {self.douyin_download_path}")
        logger.info(f"快手下载路径: {self.kuaishou_download_path}")
        logger.info(f"Facebook下载路径: {self.facebook_download_path}")
        logger.info(f"小红书下载路径: {self.xiaohongshu_download_path}")
        logger.info(f"微博下载路径: {self.weibo_download_path}")
        logger.info(f"Instagram下载路径: {self.instagram_download_path}")
        logger.info(f"TikTok下载路径: {self.tiktok_download_path}")
        logger.info(f"网易云音乐下载路径: {self.netease_download_path}")
        logger.info(f"QQ音乐下载路径: {self.qqmusic_download_path}")
        logger.info(f"YouTube Music下载路径: {self.youtubemusic_download_path}")
        logger.info(f"Apple Music下载路径: {self.apple_music_download_path}")
        # 如果设置了 Bilibili cookies，记录日志
        if self.b_cookies_path:
            logger.info(f"Bilibili Cookies 路径: {self.b_cookies_path}")
        # 如果设置了 YouTube cookies，记录日志
        if self.youtube_cookies_path:
            logger.info(f"🍪 使用YouTube cookies: {self.youtube_cookies_path}")

        # 如果设置了抖音 cookies，记录日志
        if self.douyin_cookies_path:
            logger.info(f"🍪 使用抖音 cookies: {self.douyin_cookies_path}")

        # 如果设置了快手 cookies，记录日志
        if self.kuaishou_cookies_path:
            logger.info(f"🍪 使用快手 cookies: {self.kuaishou_cookies_path}")

        # 如果设置了Instagram cookies，记录日志
        if self.instagram_cookies_path:
            logger.info(f"🍪 使用Instagram cookies: {self.instagram_cookies_path}")

        # 测试代理连接
        if self.proxy_host:
            if self._test_proxy_connection():
                logger.info(f"代理服务器已配置并连接成功: {self.proxy_host}")
                logger.info(f"yt-dlp 使用代理: {self.proxy_host}")
                # 设置系统代理环境变量
                os.environ['HTTP_PROXY'] = self.proxy_host
                os.environ['HTTPS_PROXY'] = self.proxy_host
                os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
            else:
                logger.warning(f"代理服务器已配置但连接失败: {self.proxy_host}")
                logger.info("yt-dlp 直接连接")
                self.proxy_host = None  # 连接失败时禁用代理
                # 清除系统代理环境变量
                os.environ.pop('HTTP_PROXY', None)
                os.environ.pop('HTTPS_PROXY', None)
                os.environ.pop('NO_PROXY', None)
        else:
            logger.info("代理服务器未配置，将直接连接")
            logger.info("yt-dlp 直接连接")

        # 创建 gallery-dl.conf 配置文件
        try:
            self._create_gallery_dl_config()
        except Exception as e:
            logger.warning(f"创建 gallery-dl 配置文件失败: {e}")

        # 初始化网易云音乐下载器
        try:
            if NeteaseDownloader is None:
                raise ImportError("neteasecloud_music 模块不可用")
            base_downloader = NeteaseDownloader(bot=self)
            # 使用适配器包装，兼容旧版本缺少的方法
            self.netease_downloader = _NeteaseDownloaderAdapter(base_downloader)
            logger.info(f"🎵 网易云音乐下载器初始化成功 (模块: {NETEASE_MODULE_PATH})")
        except Exception as e:
            logger.warning(f"网易云音乐下载器初始化失败: {e}")
            self.netease_downloader = None

        # 初始化QQ音乐下载器
        try:
            if QQMusicDownloader is None:
                raise ImportError("qqmusic_downloader 模块不可用")
            self.qqmusic_downloader = QQMusicDownloader(bot=self)
            logger.info(f"🎵 QQ音乐下载器初始化成功 (模块: {QQMUSIC_MODULE_PATH})")
        except Exception as e:
            logger.warning(f"QQ音乐下载器初始化失败: {e}")
            self.qqmusic_downloader = None

        # 初始化YouTube Music下载器
        try:
            if YouTubeMusicDownloader is None:
                raise ImportError("youtubemusic_downloader 模块不可用")
            self.youtubemusic_downloader = YouTubeMusicDownloader(bot=self)
            logger.info(f"🎵 YouTube Music下载器初始化成功 (模块: {YOUTUBEMUSIC_MODULE_PATH})")
        except Exception as e:
            logger.warning(f"YouTube Music下载器初始化失败: {e}")
            self.youtubemusic_downloader = None

    def _parse_cookies_file(self, cookies_path: str) -> dict:
        """解析 Netscape 格式的 X cookies 文件并转换为 JSON 格式"""
        try:
            cookies_dict = {}

            with open(cookies_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # 跳过注释行和空行
                    if line.startswith('#') or not line:
                        continue

                    # Netscape 格式: domain, domain_specified, path, secure, expiry, name, value
                    parts = line.split('\t')
                    if len(parts) >= 7:
                        domain = parts[0]
                        secure = parts[3] == 'TRUE'
                        expiry = parts[4]
                        name = parts[5]
                        value = parts[6]

                        # 只处理 twitter.com 和 x.com 的 cookies
                        if domain in ['.twitter.com', '.x.com', 'twitter.com', 'x.com']:
                            cookies_dict[name] = value
                            logger.debug(f"解析 X cookie: {name} = {value[:10]}...")

            logger.info(f"成功解析 {len(cookies_dict)} 个 X cookies")
            return cookies_dict

        except Exception as e:
            logger.error(f"解析 X cookies 文件失败: {e}")
            return {}

    def _parse_douyin_cookies_file(self, cookies_path: str) -> dict:
        """解析 Netscape 格式的抖音 cookies 文件并转换为 JSON 格式"""
        try:
            cookies_dict = {}

            with open(cookies_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # 跳过注释行和空行
                    if line.startswith('#') or not line:
                        continue

                    # Netscape 格式: domain, domain_specified, path, secure, expiry, name, value
                    parts = line.split('\t')
                    if len(parts) >= 7:
                        domain = parts[0]
                        secure = parts[3] == 'TRUE'
                        expiry = parts[4]
                        name = parts[5]
                        value = parts[6]

                        # 只处理抖音相关的 cookies
                        if domain in ['.douyin.com', 'douyin.com', 'www.douyin.com', 'v.douyin.com', 'www.iesdouyin.com', 'iesdouyin.com']:
                            cookies_dict[name] = value
                            logger.debug(f"解析抖音 cookie: {name} = {value[:10]}...")

            logger.info(f"成功解析 {len(cookies_dict)} 个抖音 cookies")
            return cookies_dict

        except Exception as e:
            logger.error(f"解析抖音 cookies 文件失败: {e}")
            return {}

    def _parse_kuaishou_cookies_file(self, cookies_path: str) -> dict:
        """解析 Netscape 格式的快手 cookies 文件并转换为 JSON 格式"""
        try:
            cookies_dict = {}

            with open(cookies_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        parts = line.split('\t')
                        if len(parts) >= 7:
                            domain = parts[0]
                            flag = parts[1] == 'TRUE'
                            path = parts[2]
                            secure = parts[3] == 'TRUE'
                            expiry = parts[4]
                            name = parts[5]
                            value = parts[6]

                            # 只处理快手相关的 cookies
                            if domain in ['.kuaishou.com', 'kuaishou.com', 'www.kuaishou.com', 'v.kuaishou.com']:
                                cookies_dict[name] = value
                                logger.debug(f"解析快手 cookie: {name} = {value[:10]}...")

            logger.info(f"成功解析 {len(cookies_dict)} 个快手 cookies")
            return cookies_dict

        except Exception as e:
            logger.error(f"解析快手 cookies 文件失败: {e}")
            return {}

    def _test_proxy_connection(self) -> bool:
        """测试代理服务器连接"""
        if not self.proxy_host:
            return False
        try:
            # 解析代理地址
            proxy_url = urlparse(self.proxy_host)
            proxies = {"http": self.proxy_host, "https": self.proxy_host}
            # 设置超时时间为5秒
            response = requests.get(
                "http://www.google.com", proxies=proxies, timeout=5, verify=False
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"代理连接测试失败: {str(e)}")
            return False

    def is_x_url(self, url: str) -> bool:
        """检查是否为 X (Twitter) URL"""
        parsed = urlparse(url)
        return parsed.netloc.lower() in [
            "twitter.com",
            "x.com",
            "www.twitter.com",
            "www.x.com",
        ]

    def is_youtube_url(self, url: str) -> bool:
        """检查是否为 YouTube URL"""
        parsed = urlparse(url)
        return parsed.netloc.lower() in [
            "youtube.com",
            "www.youtube.com",
            "youtu.be",
            "m.youtube.com",
        ]

    def is_facebook_url(self, url: str) -> bool:
        """检查是否为 Facebook URL"""
        parsed = urlparse(url)
        return parsed.netloc.lower() in [
            "facebook.com",
            "www.facebook.com",
            "m.facebook.com",
            "fb.watch",
            "fb.com",
        ]

    def is_xvideos_url(self, url: str) -> bool:
        """检查是否为 xvideos URL"""
        parsed = urlparse(url)
        return any(
            domain in parsed.netloc for domain in ["xvideos.com", "www.xvideos.com"]
        )

    def is_pornhub_url(self, url: str) -> bool:
        """检查是否为 pornhub URL"""
        parsed = urlparse(url)
        return any(
            domain in parsed.netloc
            for domain in ["pornhub.com", "www.pornhub.com", "cn.pornhub.com"]
        )

    def _get_bilibili_best_format(self) -> str:
        """
        获取B站最佳格式选择策略，智能根据会员状态选择最高画质
        - 有会员：优先4K，回退到2K、1080p高码率
        - 无会员：优先1080p，回退到720p
        """
        # 智能B站格式策略：根据会员状态自动选择最高可用画质
        bilibili_format = (
            # 策略1: 4K (需要大会员)
            "bestvideo[height>=2160]+bestaudio/"
            # 策略2: 2K (需要大会员)
            "bestvideo[height>=1440]+bestaudio/"
            # 策略3: 1080p高码率 (需要大会员)
            "bestvideo[height>=1080][tbr>2000]+bestaudio/"
            # 策略4: 1080p普通 (免费)
            "bestvideo[height>=1080]+bestaudio/"
            # 策略5: 720p (免费)
            "bestvideo[height>=720]+bestaudio/"
            # 策略6: 最终回退
            "bestvideo+bestaudio/best"
        )
        logger.info("🎯 使用智能B站格式策略：有会员优先4K，无会员优先1080p")
        logger.info(f"🔧 格式选择字符串: {bilibili_format}")
        return bilibili_format

    def check_bilibili_member_status(self) -> Dict[str, Any]:
        """检查B站会员状态"""
        try:
            if not self.b_cookies_path or not os.path.exists(self.b_cookies_path):
                return {
                    "success": False,
                    "is_member": False,
                    "message": "未设置B站cookies，无法检测会员状态"
                }
            
            # 这里可以添加实际的B站API调用来检测会员状态
            # 目前返回默认状态
            return {
                "success": True,
                "is_member": False,
                "message": "非会员用户，最高可下载480p-720p"
            }
        except Exception as e:
            return {
                "success": False,
                "is_member": False,
                "message": f"检测会员状态失败: {e}"
            }

    def debug_bilibili_formats(self, url: str) -> Dict[str, Any]:
        """调试B站视频格式，显示可用分辨率"""
        try:
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "listformats": True,
            }
            
            # 添加B站cookies
            if self.b_cookies_path and os.path.exists(self.b_cookies_path):
                ydl_opts["cookiefile"] = self.b_cookies_path
                
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                formats = info.get("formats", [])
                
                video_formats = []
                for fmt in formats:
                    if fmt.get("vcodec", "none") != "none":  # 视频格式
                        format_info = {
                            "id": fmt.get("format_id", "unknown"),
                            "height": fmt.get("height", 0),
                            "width": fmt.get("width", 0),
                            "tbr": fmt.get("tbr", 0),
                            "ext": fmt.get("ext", "unknown"),
                            "format_note": fmt.get("format_note", "unknown"),
                            "filesize": fmt.get("filesize", 0),
                        }
                        video_formats.append(format_info)
                
                # 按分辨率排序
                video_formats.sort(key=lambda x: x["height"], reverse=True)
                
                logger.info("🔍 B站可用视频格式:")
                for fmt in video_formats:
                    logger.info(f"  ID: {fmt['id']}, 分辨率: {fmt['width']}x{fmt['height']}, 码率: {fmt['tbr']}kbps, 格式: {fmt['ext']}, 说明: {fmt['format_note']}")
                
                return {
                    "success": True,
                    "formats": video_formats,
                    "max_height": max([f["height"] for f in video_formats]) if video_formats else 0
                }
                
        except Exception as e:
            logger.error(f"调试B站格式失败: {e}")
            return {"success": False, "error": str(e)}

    def is_bilibili_url(self, url: str) -> bool:
        """检查是否为 Bilibili URL"""
        parsed = urlparse(url)
        return parsed.netloc.lower() in [
            "bilibili.com",
            "www.bilibili.com",
            "space.bilibili.com",
            "b23.tv",
        ]

    def is_telegraph_url(self, url: str) -> bool:
        """检查是否为 Telegraph URL"""
        parsed = urlparse(url)
        return parsed.netloc.lower() in ["telegra.ph", "telegraph.co"]

    def is_douyin_url(self, url: str) -> bool:
        """检查是否为抖音 URL"""
        parsed = urlparse(url)
        return parsed.netloc.lower() in [
            "douyin.com",
            "www.douyin.com",
            "v.douyin.com",
            "www.iesdouyin.com",
            "iesdouyin.com"
        ]

    def is_kuaishou_url(self, url: str) -> bool:
        """检查是否为快手 URL"""
        parsed = urlparse(url)
        # 支持多种快手URL格式
        if parsed.netloc.lower() in [
            "kuaishou.com",
            "www.kuaishou.com",
            "v.kuaishou.com",
            "m.kuaishou.com",
            "f.kuaishou.com"
        ]:
            return True

        # 检查URL路径是否包含快手特征
        if 'kuaishou.com' in url.lower():
            return True

        return False

    def is_toutiao_url(self, url: str) -> bool:
        """检查是否为头条视频 URL"""
        parsed = urlparse(url)
        return parsed.netloc.lower() in [
            "toutiao.com",
            "www.toutiao.com",
            "m.toutiao.com",
        ]

    def extract_urls_from_text(self, text: str) -> list:
        """从文本中提取所有URL - 改进版本支持更多格式"""
        urls = []

        # 基础URL正则模式 - 支持中文文本中的URL
        url_patterns = [
            # 标准HTTP/HTTPS URL
            r'https?://[^\s\u4e00-\u9fff]+',
            # 快手短链接特殊处理
            r'v\.kuaishou\.com/[A-Za-z0-9]+',
            # 抖音短链接
            r'v\.douyin\.com/[A-Za-z0-9]+',
            # Facebook链接
            r'facebook\.com/[A-Za-z0-9/._-]+',
            r'fb\.watch/[A-Za-z0-9]+',
            # 其他短链接格式
            r'[a-zA-Z0-9.-]+\.com/[A-Za-z0-9/]+',
        ]

        for pattern in url_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                # 清理URL末尾的标点符号
                clean_url = match.rstrip('.,;!?。，；！？')
                # 确保URL有协议前缀
                if not clean_url.startswith(('http://', 'https://')):
                    clean_url = 'https://' + clean_url
                urls.append(clean_url)

        # 去重并保持顺序
        seen = set()
        unique_urls = []
        for url in urls:
            if url not in seen:
                seen.add(url)
                unique_urls.append(url)

        return unique_urls

    def _extract_clean_url_from_text(self, text: str) -> str:
        """从包含描述文本的字符串中提取纯净的URL"""
        try:
            # 使用已有的URL提取方法
            urls = self.extract_urls_from_text(text)
            if urls:
                return urls[0]  # 返回第一个找到的URL

            # 如果没有找到，可能文本本身就是一个URL
            text = text.strip()
            if text.startswith(('http://', 'https://')):
                # 提取URL部分（到第一个空格为止）
                url_part = text.split()[0] if ' ' in text else text
                return url_part

            return None
        except Exception as e:
            logger.warning(f"提取纯净URL失败: {e}")
            return None

    def _clean_netease_url_special(self, text: str) -> str:
        """
        专门为网易云音乐清理URL，从包含中文描述的文本中提取纯净的网易云音乐链接
        
        Args:
            text: 包含中文描述的文本，如"分享G.E.M.邓紫棋的专辑《T.I.M.E.》https://163cn.tv/jKbaG97 (@网易云音乐)"
            
        Returns:
            str: 清理后的纯净URL，如果没找到则返回None
        """
        try:
            # 网易云音乐URL的正则模式
            netease_patterns = [
                # 短链接格式
                r'https?://163cn\.tv/[A-Za-z0-9]+',
                r'https?://music\.163\.cn/[A-Za-z0-9/]+',
                # 官方链接格式
                r'https?://music\.163\.com/#/[^\\s\u4e00-\u9fff]+',
                r'https?://y\.music\.163\.com/[^\\s\u4e00-\u9fff]+',
                r'https?://m\.music\.163\.com/[^\\s\u4e00-\u9fff]+',
            ]
            
            for pattern in netease_patterns:
                matches = re.findall(pattern, text)
                if matches:
                    # 取第一个匹配的URL
                    clean_url = matches[0]
                    # 清理URL末尾的标点符号
                    clean_url = clean_url.rstrip('.,;!?。，；！？')
                    logger.info(f"🎵 网易云音乐URL清理成功: {text[:50]}... -> {clean_url}")
                    return clean_url
            
            # 如果没有找到，尝试从文本中提取任何看起来像URL的内容
            url_pattern = r'https?://[^\s\u4e00-\u9fff]+'
            matches = re.findall(url_pattern, text)
            for match in matches:
                if '163cn.tv' in match or 'music.163.com' in match:
                    clean_url = match.rstrip('.,;!?。，；！？')
                    logger.info(f"🎵 网易云音乐URL清理成功(备用): {text[:50]}... -> {clean_url}")
                    return clean_url
            
            logger.warning(f"⚠️ 未在文本中找到网易云音乐链接: {text[:50]}...")
            return None
            
        except Exception as e:
            logger.error(f"❌ 网易云音乐URL清理失败: {e}")
            return None

    def is_xiaohongshu_url(self, url: str) -> bool:
        """检查是否为小红书 URL"""
        parsed = urlparse(url)
        return parsed.netloc.lower() in [
            "xiaohongshu.com",
            "www.xiaohongshu.com",
            "xhslink.com",
        ]

    async def _detect_xiaohongshu_content_type(self, url: str) -> str:
        """检测小红书内容类型（图片或视频）"""
        try:
            # 对于短链接，先展开再检测
            if 'xhslink.com' in url:
                logger.info(f"🔗 检测到小红书短链接，先展开: {url}")
                # 使用 xiaohongshu_downloader 展开短链接
                try:
                    from xiaohongshu_downloader import XiaohongshuDownloader
                    downloader = XiaohongshuDownloader()
                    # 先展开短链接获取完整URL
                    expanded_url = downloader._expand_short_url(url)
                    if expanded_url and expanded_url != url:
                        logger.info(f"✅ 短链接展开成功: {expanded_url}")
                        url = expanded_url
                    else:
                        logger.warning(f"⚠️ 短链接展开失败，使用原URL")
                except Exception as e:
                    logger.warning(f"⚠️ 短链接展开异常: {e}")
            
            # 使用简单的启发式方法检测
            # 如果URL包含特定关键词，可能是图片
            if any(keyword in url.lower() for keyword in ['/explore/', '/discovery/item/']):
                # 进一步检测页面内容
                import httpx
                async with httpx.AsyncClient() as client:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                        'Referer': 'https://www.xiaohongshu.com/'
                    }
                    
                    response = await client.get(url, headers=headers, follow_redirects=True, timeout=10)
                    html_content = response.text.lower()
                    
                    # 检查HTML内容中的关键词
                    if any(keyword in html_content for keyword in ['图片', 'image', 'photo', '壁纸', '头像']):
                        return "image"
                    elif any(keyword in html_content for keyword in ['视频', 'video', '播放']):
                        return "video"
                    
                    # 默认返回图片类型，因为小红书大部分内容是图片
                    return "image"
            else:
                # 对于其他URL（包括短链接），默认返回图片类型
                logger.info(f"🔍 URL不包含特定关键词，默认返回图片类型: {url}")
                return "image"
                    
        except Exception as e:
            logger.warning(f"⚠️ 检测小红书内容类型失败: {e}")
            # 默认返回图片类型
            return "image"

    def is_weibo_url(self, url: str) -> bool:
        """检查是否为微博 URL"""
        parsed = urlparse(url)
        return parsed.netloc.lower() in [
            "weibo.com",
            "www.weibo.com",
            "m.weibo.com",
            "video.weibo.com",
            "t.cn",  # 微博短链接
            "weibo.cn",  # 微博短链接
            "sinaurl.cn",  # 新浪短链接
        ]

    def _expand_weibo_short_url(self, url: str) -> str:
        """展开微博短链接为长链接"""
        import requests
        import re

        try:
            # 检查是否为微博短链接
            parsed = urlparse(url)
            short_domains = ["t.cn", "weibo.cn", "sinaurl.cn"]

            if parsed.netloc.lower() in short_domains:
                logger.info(f"🔄 检测到微博短链接，开始展开: {url}")

                # 优先使用移动端User-Agent，避免重定向到登录页面
                mobile_headers = {
                    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_7_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Mobile/15E148 Safari/604.1',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1'
                }

                # 桌面端User-Agent作为备用
                desktop_headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1'
                }

                # 先尝试移动端User-Agent的GET请求
                expanded_url = None
                try:
                    logger.info(f"🔄 使用移动端User-Agent请求...")
                    response = requests.get(url, headers=mobile_headers, allow_redirects=True, timeout=10)
                    expanded_url = response.url
                    logger.info(f"🔄 移动端请求重定向到: {expanded_url}")

                    # 检查是否得到了有效的微博视频URL
                    if "weibo.com" in expanded_url and ("tv/show" in expanded_url or "video" in expanded_url):
                        logger.info(f"✅ 移动端请求成功获取微博视频URL")
                        # 如果是h5.video.weibo.com，转换为标准的weibo.com格式
                        if "h5.video.weibo.com" in expanded_url:
                            expanded_url = expanded_url.replace("h5.video.weibo.com", "weibo.com/tv")
                            logger.info(f"🔄 转换为标准格式: {expanded_url}")
                    else:
                        logger.info(f"⚠️ 移动端请求未获取到标准微博视频URL，尝试桌面端...")
                        raise Exception("移动端未获取到标准URL")

                except Exception as e:
                    logger.warning(f"⚠️ 移动端请求失败: {e}")
                    # 如果移动端请求失败，尝试桌面端请求
                    try:
                        logger.info(f"🔄 使用桌面端User-Agent请求...")
                        response = requests.get(url, headers=desktop_headers, allow_redirects=True, timeout=10)
                        expanded_url = response.url
                        logger.info(f"🔄 桌面端请求重定向到: {expanded_url}")
                    except Exception as e2:
                        logger.warning(f"⚠️ 桌面端请求也失败: {e2}")
                        return url

                # 检查展开后的URL是否有效
                if expanded_url and expanded_url != url:
                    # 进一步处理可能的中间跳转页面
                    if "passport.weibo.com" in expanded_url and "url=" in expanded_url:
                        # 从跳转页面URL中提取真实的目标URL
                        import urllib.parse
                        try:
                            # 尝试多种URL参数提取方式
                            match = re.search(r'url=([^&]+)', expanded_url)
                            if match:
                                encoded_url = match.group(1)
                                # 多次URL解码，因为可能被多次编码
                                real_url = urllib.parse.unquote(encoded_url)
                                real_url = urllib.parse.unquote(real_url)  # 再次解码

                                # 清理URL参数，移除不必要的参数
                                if '?' in real_url:
                                    base_url, params = real_url.split('?', 1)
                                    # 保留重要参数，移除跟踪参数
                                    important_params = []
                                    for param in params.split('&'):
                                        if '=' in param:
                                            key, value = param.split('=', 1)
                                            if key in ['fid', 'id', 'video_id']:  # 保留重要的视频ID参数
                                                important_params.append(param)

                                    if important_params:
                                        real_url = base_url + '?' + '&'.join(important_params)
                                    else:
                                        real_url = base_url

                                logger.info(f"🔄 从跳转页面提取真实URL: {real_url}")
                                expanded_url = real_url
                        except Exception as e:
                            logger.warning(f"⚠️ 提取真实URL失败: {e}")
                            # 如果提取失败，尝试直接使用原始短链接
                            logger.info(f"🔄 回退到原始短链接: {url}")
                            expanded_url = url

                    logger.info(f"✅ 微博短链接展开成功: {url} -> {expanded_url}")
                    return expanded_url
                else:
                    logger.warning(f"⚠️ 短链接展开后URL无变化，使用原URL: {url}")
                    return url
            else:
                # 不是短链接，直接返回原URL
                return url

        except Exception as e:
            logger.warning(f"⚠️ 展开微博短链接失败: {e}")
            logger.warning(f"⚠️ 将使用原始URL: {url}")
            return url

    def is_instagram_url(self, url: str) -> bool:
        """检查是否为Instagram URL"""
        parsed = urlparse(url)
        return parsed.netloc.lower() in [
            "instagram.com",
            "www.instagram.com",
            "m.instagram.com",
        ]

    def is_tiktok_url(self, url: str) -> bool:
        """检查是否为TikTok URL"""
        parsed = urlparse(url)
        return parsed.netloc.lower() in [
            "tiktok.com",
            "www.tiktok.com",
            "m.tiktok.com",
            "vm.tiktok.com",
        ]

    def is_netease_url(self, url: str) -> bool:
        """检查是否为网易云音乐 URL"""
        parsed = urlparse(url)
        # 检查官方域名
        if parsed.netloc.lower() in [
            "music.163.com",
            "y.music.163.com",
            "m.music.163.com",
        ]:
            return True
        
        # 检查短链接域名
        if parsed.netloc.lower() in [
            "163cn.tv",
            "music.163.cn",
        ]:
            return True
        
        return False

    def is_qqmusic_url(self, url: str) -> bool:
        """检查是否为QQ音乐 URL"""
        parsed = urlparse(url)
        # 检查官方域名
        if parsed.netloc.lower() in [
            "y.qq.com",
            "music.qq.com",
            "c.y.qq.com",
            "c6.y.qq.com",
            "i.y.qq.com",
        ]:
            return True
        
        # 检查短链接域名
        if parsed.netloc.lower() in [
            "qq.cn",
            "qq.com",
        ]:
            return True
        
        return False

    def is_apple_music_url(self, url: str) -> bool:
        """检查是否为 Apple Music URL"""
        parsed = urlparse(url)
        return parsed.netloc.lower() in [
            "music.apple.com",
        ]

    def is_youtube_music_url(self, url: str) -> bool:
        """检查是否为 YouTube Music URL"""
        parsed = urlparse(url)
        # 检查YouTube Music专用域名
        if parsed.netloc.lower() in [
            "music.youtube.com",
        ]:
            return True
        
        # 检查普通YouTube链接但包含播放列表标识（可能是YouTube Music播放列表）
        if parsed.netloc.lower() in [
            "youtube.com",
            "www.youtube.com",
            "youtu.be",
            "m.youtube.com",
        ]:
            # 检查URL中是否包含播放列表参数
            if 'list=' in url:
                return True
        
        return False

    def is_x_playlist_url(self, url: str) -> tuple:
        """
        检查是否为X播放列表URL，并提取播放列表信息
        Returns:
            tuple: (is_playlist, playlist_info) 或 (False, None)
        """
        import yt_dlp

        try:
            # 首先检查是否为X URL
            if not self.is_x_url(url):
                return False, None

            # 使用yt-dlp检查是否为播放列表
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
            }

            if self.proxy_host:
                ydl_opts['proxy'] = self.proxy_host

            if self.x_cookies_path:
                ydl_opts['cookiefile'] = self.x_cookies_path

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

                # 检查是否为播放列表
                if info and '_type' in info and info['_type'] == 'playlist':
                    entries = info.get('entries', [])
                    if len(entries) > 1:
                        playlist_info = {
                            'total_videos': len(entries),
                            'playlist_title': info.get('title', 'X播放列表'),
                            'playlist_url': url,
                            'entries': entries
                        }
                        logger.info(f"检测到X播放列表: {playlist_info['playlist_title']}, 共{len(entries)}个视频")
                        return True, playlist_info

                # 检查是否有多个条目
                if info and 'entries' in info and len(info['entries']) > 1:
                    playlist_info = {
                        'total_videos': len(info['entries']),
                        'playlist_title': info.get('title', 'X播放列表'),
                        'playlist_url': url,
                        'entries': info['entries']
                    }
                    logger.info(f"检测到X播放列表: {playlist_info['playlist_title']}, 共{len(info['entries'])}个视频")
                    return True, playlist_info

            return False, None
        except Exception as e:
            logger.warning(f"检查X播放列表时出错: {e}")
            return False, None

    def is_bilibili_list_url(self, url: str) -> tuple:
        """
        检查是否为B站用户列表URL，并提取用户ID和列表ID
        Returns:
            tuple: (is_list, uid, list_id) 或 (False, None, None)
        """
        import re

        # 匹配B站用户列表URL:
        # https://space.bilibili.com/477348669/lists/2111173?type=season
        pattern = r"space\.bilibili\.com/(\d+)/lists/(\d+)"
        match = re.search(pattern, url)
        if match:
            uid = match.group(1)
            list_id = match.group(2)
            return True, uid, list_id
        return False, None, None

    def is_bilibili_user_lists_url(self, url: str) -> tuple:
        """
        检查是否为B站用户合集列表页面URL，并提取用户ID
        Returns:
            tuple: (is_user_lists, uid) 或 (False, None)
        """
        import re

        # 匹配B站用户合集列表页面URL:
        # https://space.bilibili.com/3546380987533935/lists
        pattern = r"space\.bilibili\.com/(\d+)/lists/?$"
        match = re.search(pattern, url)
        if match:
            uid = match.group(1)
            return True, uid
        return False, None



    def is_bilibili_ugc_season(self, url: str) -> tuple:
        """
        检查是否为B站UGC合集，并提取BV号和合集ID
        Returns:
            tuple: (is_ugc_season, bv_id, season_id) 或 (False, None, None)
        """
        import re
        import requests

        try:
            # 首先尝试从URL中提取BV号和season_id
            bv_pattern = r'BV[a-zA-Z0-9]+'
            season_pattern = r'season_id=(\d+)'

            bv_match = re.search(bv_pattern, url)
            season_match = re.search(season_pattern, url)

            # 如果URL中没有BV号，可能是短链接，需要先解析
            if not bv_match and ("b23.tv" in url or "b23.wtf" in url):
                logger.info(f"🔄 检测UGC合集：解析短链接 {url}")
                try:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                    }
                    response = requests.get(url, headers=headers, allow_redirects=True, timeout=10)
                    real_url = response.url
                    logger.info(f"🔄 短链接解析结果: {real_url}")

                    # 重新提取BV号和season_id
                    bv_match = re.search(bv_pattern, real_url)
                    season_match = re.search(season_pattern, real_url)
                    url = real_url  # 更新URL为真实URL
                except Exception as e:
                    logger.warning(f"⚠️ 解析短链接失败: {e}")
                    return False, None, None

            if not bv_match:
                return False, None, None

            bv_id = bv_match.group(0)

            # 如果URL中有season_id，直接使用
            if season_match:
                season_id = season_match.group(1)
                logger.info(f"🔍 从URL中检测到UGC合集: BV={bv_id}, Season={season_id}")
                return True, bv_id, season_id

            # 如果URL中没有season_id，尝试通过API获取
            logger.info(f"🔍 检查BV号是否属于UGC合集: {bv_id}")
            api_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bv_id}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://www.bilibili.com/',
            }

            response = requests.get(api_url, headers=headers, timeout=10)
            data = response.json()

            if data.get('code') == 0:
                ugc_season = data.get('data', {}).get('ugc_season')
                if ugc_season:
                    season_id = str(ugc_season.get('id'))
                    season_title = ugc_season.get('title', '未知合集')
                    logger.info(f"✅ 检测到UGC合集: {season_title} (Season ID: {season_id})")
                    return True, bv_id, season_id

            return False, None, None

        except Exception as e:
            logger.warning(f"⚠️ 检测UGC合集时出错: {e}")
            return False, None, None

    def is_bilibili_multi_part_video(self, url: str) -> tuple:
        """
        检查是否为B站多P视频，并提取BV号
        Returns:
            tuple: (is_multi_part, bv_id) 或 (False, None)
        """
        import re
        import yt_dlp
        try:
            # 首先尝试从URL中提取BV号
            bv_pattern = r'BV[a-zA-Z0-9]+'
            bv_match = re.search(bv_pattern, url)

            # 如果URL中没有BV号，可能是短链接，需要先解析
            if not bv_match and ("b23.tv" in url or "b23.wtf" in url):
                logger.info(f"🔄 检测到B站短链接，先解析获取真实URL: {url}")
                try:
                    # 使用yt-dlp解析短链接
                    temp_opts = {
                        'quiet': True,
                        'no_warnings': True,
                    }
                    with yt_dlp.YoutubeDL(temp_opts) as ydl:
                        temp_info = ydl.extract_info(url, download=False)

                    if temp_info.get('webpage_url'):
                        real_url = temp_info['webpage_url']
                        logger.info(f"🔄 短链接解析结果: {real_url}")
                        # 从真实URL中提取BV号
                        bv_match = re.search(bv_pattern, real_url)
                        if bv_match:
                            logger.info(f"✅ 从短链接中提取到BV号: {bv_match.group(0)}")
                except Exception as e:
                    logger.warning(f"⚠️ 解析短链接失败: {e}")

            if not bv_match:
                return False, None

            bv_id = bv_match.group(0)

            # 使用yt-dlp检查是否为多P视频或合集
            # 先尝试快速检测（extract_flat=True）
            ydl_opts_flat = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'flat_playlist': True,
            }

            try:
                with yt_dlp.YoutubeDL(ydl_opts_flat) as ydl:
                    info = ydl.extract_info(url, download=False)

                    # 检查是否有多个条目
                    if info and '_type' in info and info['_type'] == 'playlist':
                        entries = info.get('entries', [])
                        if len(entries) > 1:
                            logger.info(f"✅ 检测到B站多内容视频: {bv_id}, 共{len(entries)}个条目")
                            return True, bv_id

                    # 检查是否有分P信息
                    if info and 'entries' in info and len(info['entries']) > 1:
                        logger.info(f"✅ 检测到B站多内容视频: {bv_id}, 共{len(info['entries'])}个条目")
                        return True, bv_id
            except Exception as e:
                logger.warning(f"快速检测失败: {e}")

            # 如果快速检测失败，尝试完整检测（extract_flat=False）
            logger.info(f"🔄 快速检测未发现多内容，尝试完整检测: {bv_id}")

            # 使用输出捕获来检测anthology
            import io
            from contextlib import redirect_stdout, redirect_stderr

            stdout_capture = io.StringIO()
            stderr_capture = io.StringIO()

            ydl_opts_full = {
                'quiet': False,  # 改为False以便看到更多信息
                'no_warnings': False,  # 改为False以便看到警告信息
                'extract_flat': False,
                'noplaylist': False,
                'simulate': True,  # 添加模拟模式
            }

            try:
                with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                    with yt_dlp.YoutubeDL(ydl_opts_full) as ydl:
                        info = ydl.extract_info(url, download=False)

                # 检查捕获的输出中是否包含anthology
                stdout_output = stdout_capture.getvalue()
                stderr_output = stderr_capture.getvalue()
                all_output = (stdout_output + stderr_output).lower()

                if 'anthology' in all_output or 'extracting videos in anthology' in all_output:
                    logger.info(f"✅ 从yt-dlp输出中检测到anthology: {bv_id}")
                    return True, bv_id

                # 检查是否有多个条目
                    if info and '_type' in info and info['_type'] == 'playlist':
                        entries = info.get('entries', [])
                        if len(entries) > 1:
                            logger.info(f"✅ 完整检测发现B站多内容视频: {bv_id}, 共{len(entries)}个条目")
                            return True, bv_id

                    # 检查是否有分P信息
                    if info and 'entries' in info and len(info['entries']) > 1:
                        logger.info(f"✅ 完整检测发现B站多内容视频: {bv_id}, 共{len(info['entries'])}个条目")
                        return True, bv_id

                    # 检查是否包含anthology信息（B站合集的特征）
                    info_str = str(info).lower()
                    if info and any(key in info_str for key in ['anthology', 'collection', 'series']):
                        logger.info(f"✅ 检测到B站合集特征: {bv_id}")
                        return True, bv_id

                    # 额外检查：使用模拟下载来检测anthology
                    try:
                        logger.info(f"🔍 使用模拟下载检测anthology: {bv_id}")

                        # 使用更详细的日志捕获anthology信息
                        import io
                        import sys
                        from contextlib import redirect_stdout, redirect_stderr

                        # 捕获yt-dlp的输出
                        stdout_capture = io.StringIO()
                        stderr_capture = io.StringIO()

                        simulate_opts = {
                            'quiet': False,  # 改为False以捕获anthology信息
                            'no_warnings': False,  # 改为False以捕获更多信息
                            'simulate': True,
                            'extract_flat': False,
                        }

                        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                            with yt_dlp.YoutubeDL(simulate_opts) as sim_ydl:
                                sim_info = sim_ydl.extract_info(url, download=False)

                        # 检查捕获的输出中是否包含anthology
                        stdout_output = stdout_capture.getvalue().lower()
                        stderr_output = stderr_capture.getvalue().lower()
                        all_output = stdout_output + stderr_output

                        if 'anthology' in all_output or 'extracting videos in anthology' in all_output:
                            logger.info(f"✅ 从输出中检测到anthology关键词: {bv_id}")
                            return True, bv_id

                        # 检查模拟下载的信息中是否包含anthology
                        sim_str = str(sim_info).lower()
                        if 'anthology' in sim_str:
                            logger.info(f"✅ 模拟下载检测到anthology关键词: {bv_id}")
                            return True, bv_id

                        # 检查是否有多个entries
                        if sim_info and 'entries' in sim_info and len(sim_info['entries']) > 1:
                            logger.info(f"✅ 模拟下载检测到多个条目: {bv_id}, 共{len(sim_info['entries'])}个")
                            return True, bv_id

                    except Exception as sim_e:
                        logger.warning(f"模拟下载检测失败: {sim_e}")

                    # 尝试从重定向URL中提取用户ID，检查用户空间是否有多个视频
                    webpage_url = info.get('webpage_url', '')
                    if webpage_url and 'up_id=' in webpage_url:
                        import re
                        up_id_match = re.search(r'up_id=(\d+)', webpage_url)
                        if up_id_match:
                            up_id = up_id_match.group(1)
                            logger.info(f"🔍 尝试检查用户空间: {up_id}")

                            # 检查用户空间是否有多个视频
                            user_space_url = f"https://space.bilibili.com/{up_id}"
                            try:
                                user_opts = {
                                    'quiet': True,
                                    'no_warnings': True,
                                    'extract_flat': True,
                                    'flat_playlist': True,
                                }
                                with yt_dlp.YoutubeDL(user_opts) as user_ydl:
                                    user_info = user_ydl.extract_info(user_space_url, download=False)

                                if user_info and 'entries' in user_info:
                                    user_entries = user_info['entries']
                                    if len(user_entries) > 1:
                                        logger.info(f"✅ 用户空间检测到多个视频: {len(user_entries)}个，可能是合集分享")
                                        return True, bv_id
                            except Exception as user_e:
                                logger.warning(f"用户空间检测失败: {user_e}")

            except Exception as e:
                logger.warning(f"完整检测失败: {e}")

            return False, bv_id
        except Exception as e:
            logger.warning(f"检查B站多P视频时出错: {e}")
            return False, None

    def is_youtube_playlist_url(self, url: str) -> tuple:
        """检查是否为 YouTube 播放列表 URL"""
        import re

        logger.info(f"🔍 检查是否为YouTube播放列表URL: {url}")

        # 匹配 YouTube 播放列表 URL（支持移动版和桌面版）
        patterns = [
            r"(?:(?:m\.)?youtube\.com/playlist\?list=|(?:m\.)?youtube\.com/watch\?.*&list=)([a-zA-Z0-9_-]+)",
            r"(?:m\.)?youtube\.com/playlist\?list=([a-zA-Z0-9_-]+)",
        ]
        for i, pattern in enumerate(patterns, 1):
            match = re.search(pattern, url)
            if match:
                playlist_id = match.group(1)
                logger.info(f"🎯 模式{i}匹配成功，捕获播放列表ID: {playlist_id}")
                logger.info(f"📋 检测到播放列表: {playlist_id}")
                return True, playlist_id

        logger.info("❌ 未检测到播放列表参数")
        return False, None



    def is_youtube_channel_playlists_url(self, url: str) -> tuple:
        """检查是否为 YouTube 频道播放列表页面 URL 或频道主页 URL"""
        import re

        # 首先匹配已经包含 /playlists 的URL（支持移动版和桌面版）
        playlists_patterns = [
            r"(?:m\.)?youtube\.com/@([^/\?]+)/playlists",
            r"(?:m\.)?youtube\.com/c/([^/\?]+)/playlists",
            r"(?:m\.)?youtube\.com/channel/([^/\?]+)/playlists",
            r"(?:m\.)?youtube\.com/user/([^/\?]+)/playlists",
        ]
        for pattern in playlists_patterns:
            match = re.search(pattern, url)
            if match:
                channel_identifier = match.group(1)
                return True, url

        # 然后匹配频道主页URL，自动转换为播放列表URL（支持移动版和桌面版）
        channel_patterns = [
            r"(?:m\.)?youtube\.com/@([^/\?]+)(?:\?.*)?$",  # @username 格式
            r"(?:m\.)?youtube\.com/c/([^/\?]+)(?:\?.*)?$",  # /c/channel 格式
            r"(?:m\.)?youtube\.com/channel/([^/\?]+)(?:\?.*)?$",  # /channel/ID 格式
            r"(?:m\.)?youtube\.com/user/([^/\?]+)(?:\?.*)?$",  # /user/username 格式
        ]
        for pattern in channel_patterns:
            match = re.search(pattern, url)
            if match:
                channel_identifier = match.group(1)
                # 构建播放列表URL
                if "@" in url:
                    playlists_url = f"https://www.youtube.com/@{channel_identifier}/playlists"
                elif "/c/" in url:
                    playlists_url = f"https://www.youtube.com/c/{channel_identifier}/playlists"
                elif "/channel/" in url:
                    playlists_url = f"https://www.youtube.com/channel/{channel_identifier}/playlists"
                elif "/user/" in url:
                    playlists_url = f"https://www.youtube.com/user/{channel_identifier}/playlists"
                else:
                    playlists_url = url

                logger.info(f"🔍 检测到YouTube频道主页，转换为播放列表URL: {playlists_url}")
                return True, playlists_url
        return False, None

    def get_download_path(self, url: str) -> Path:
        """根据 URL 确定下载路径"""
        if self.is_x_url(url):
            return self.x_download_path.resolve()
        elif self.is_youtube_url(url):
            return self.youtube_download_path.resolve()
        elif self.is_xvideos_url(url):
            return self.xvideos_download_path.resolve()
        elif self.is_pornhub_url(url):
            return self.pornhub_download_path.resolve()
        elif self.is_bilibili_url(url):
            return self.bilibili_download_path.resolve()
        elif self.is_telegraph_url(url):
            return self.telegraph_download_path.resolve()
        elif self.is_douyin_url(url):
            return self.douyin_download_path.resolve()
        elif self.is_kuaishou_url(url):
            return self.kuaishou_download_path.resolve()
        elif self.is_toutiao_url(url):
            return self.toutiao_download_path.resolve()
        elif self.is_facebook_url(url):
            return self.facebook_download_path.resolve()
        elif self.is_xiaohongshu_url(url):
            return self.xiaohongshu_download_path.resolve()  # 小红书使用自己的目录
        elif self.is_weibo_url(url):
            return self.weibo_download_path.resolve()
        elif self.is_instagram_url(url):
            return self.instagram_download_path.resolve()
        elif self.is_tiktok_url(url):
            return self.tiktok_download_path.resolve()
        elif self.is_netease_url(url):
            return self.netease_download_path.resolve()
        elif self.is_qqmusic_url(url):
            return self.qqmusic_download_path.resolve()
        elif self.is_youtube_music_url(url):
            return self.youtubemusic_download_path.resolve()
        elif self.is_apple_music_url(url):
            return self.apple_music_download_path.resolve()
        else:
            return self.youtube_download_path.resolve()

    def get_platform_name(self, url: str) -> str:
        """获取平台名称"""
        if self.is_x_url(url):
            return "x"
        elif self.is_youtube_url(url):
            return "youtube"
        elif self.is_xvideos_url(url):
            return "xvideos"
        elif self.is_pornhub_url(url):
            return "pornhub"
        elif self.is_bilibili_url(url):
            return "bilibili"
        elif self.is_telegraph_url(url):
            return "telegraph"
        elif self.is_douyin_url(url):
            return "douyin"
        elif self.is_kuaishou_url(url):
            return "kuaishou"
        elif self.is_toutiao_url(url):
            return "toutiao"
        elif self.is_facebook_url(url):
            return "facebook"
        elif self.is_xiaohongshu_url(url):
            return "xiaohongshu"
        elif self.is_weibo_url(url):
            return "weibo"
        elif self.is_instagram_url(url):
            return "instagram"
        elif self.is_tiktok_url(url):
            return "tiktok"
        elif self.is_netease_url(url):
            return "netease"
        elif self.is_qqmusic_url(url):
            return "qqmusic"
        elif self.is_youtube_music_url(url):
            return "youtubemusic"
        elif self.is_apple_music_url(url):
            return "applemusic"
        else:
            return "other"

    def check_ytdlp_version(self) -> Dict[str, Any]:
        """检查yt-dlp版本"""
        try:
            import yt_dlp

            version = yt_dlp.version.__version__
            return {
                "success": True,
                "version": version,
                "info": f"yt-dlp 版本: {version}",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def check_video_formats(self, url: str) -> Dict[str, Any]:
        """检查视频的可用格式"""
        try:
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "listformats": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                formats = info.get("formats", [])
                video_formats = []
                audio_formats = []
                for fmt in formats:
                    format_info = {
                        "id": fmt.get("format_id", "unknown"),
                        "ext": fmt.get("ext", "unknown"),
                        "quality": fmt.get("format_note", "unknown"),
                        "filesize": fmt.get("filesize", 0),
                        "height": fmt.get("height", 0),
                        "width": fmt.get("width", 0),
                        "fps": fmt.get("fps", 0),
                        "vcodec": fmt.get("vcodec", "none"),
                        "acodec": fmt.get("acodec", "none"),
                        "format_type": (
                            "video" if fmt.get("vcodec", "none") != "none" else "audio"
                        ),
                    }
                    if format_info["format_type"] == "video":
                        video_formats.append(format_info)
                    else:
                        audio_formats.append(format_info)
                # 按质量排序
                video_formats.sort(
                    key=lambda x: (x["height"], x["filesize"]), reverse=True
                )
                audio_formats.sort(key=lambda x: x["filesize"], reverse=True)
                # 检查是否有高分辨率格式
                has_high_res = any(f.get("height", 0) >= 2160 for f in video_formats)
                has_4k = any(f.get("height", 0) >= 2160 for f in video_formats)
                has_1080p = any(f.get("height", 0) >= 1080 for f in video_formats)
                has_720p = any(f.get("height", 0) >= 720 for f in video_formats)
                return {
                    "success": True,
                    "title": info.get("title", "Unknown"),
                    "duration": info.get("duration", 0),
                    "video_formats": video_formats[:10],  # 只显示前10个视频格式
                    "audio_formats": audio_formats[:5],  # 只显示前5个音频格式
                    "quality_info": {
                        "has_4k": has_4k,
                        "has_1080p": has_1080p,
                        "has_720p": has_720p,
                        "total_video_formats": len(video_formats),
                        "total_audio_formats": len(audio_formats),
                    },
                }
        except Exception as e:
            logger.error(f"格式检查失败: {str(e)}")
            return {"success": False, "error": str(e)}

    def get_media_info(self, file_path: str) -> Dict[str, Any]:
        """使用 ffprobe 获取媒体文件的详细信息"""
        try:
            # 首先检查文件是否存在
            if not os.path.exists(file_path):
                logger.warning(f"⚠️ 文件不存在: {file_path}")
                return {}

            # 检查文件大小
            file_size = os.path.getsize(file_path)
            if file_size == 0:
                logger.warning(f"⚠️ 文件大小为0: {file_path}")
                return {}

            logger.info(f"🔍 开始获取媒体信息: {file_path}")
            logger.info(f"📦 文件大小: {file_size / (1024 * 1024):.2f} MB")

            cmd = [
                "ffprobe",
                "-loglevel",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(file_path),
            ]

            logger.info(f"🔧 执行ffprobe命令: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)

            if result.returncode != 0:
                logger.warning(f"⚠️ ffprobe返回非零状态码: {result.returncode}")
                logger.warning(f"⚠️ stderr: {result.stderr}")

            info = json.loads(result.stdout)
            logger.info(f"✅ ffprobe解析成功，流数量: {len(info.get('streams', []))}")

            media_info = {}
            if "format" in info:
                duration = float(info["format"].get("duration", 0))
                if duration > 0:
                    media_info["duration"] = (
                        time.strftime("%H:%M:%S", time.gmtime(duration))
                        if duration >= 3600
                        else time.strftime("%M:%S", time.gmtime(duration))
                    )
                    logger.info(f"⏱️ 视频时长: {media_info['duration']}")
                size = int(info["format"].get("size", 0) or 0)
                if size > 0:
                    media_info["size"] = f"{size / (1024 * 1024):.2f} MB"

            # 查找视频流
            video_streams = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
            logger.info(f"🎬 找到 {len(video_streams)} 个视频流")

            video_stream = next(
                (s for s in info.get("streams", []) if s.get("codec_type") == "video"),
                None,
            )
            if video_stream:
                width, height = video_stream.get("width"), video_stream.get("height")
                logger.info(f"🔍 视频流信息: width={width}, height={height}")
                logger.info(f"🔍 视频编码: {video_stream.get('codec_name', '未知')}")

                if width and height:
                    resolution = f"{width}x{height}"
                    media_info["resolution"] = resolution
                    logger.info(f"✅ 获取到分辨率: {media_info['resolution']}")
                else:
                    logger.warning(f"⚠️ 视频流中没有宽高信息: width={width}, height={height}")
                    # 尝试从文件名推断分辨率
                    filename = os.path.basename(file_path)
                    resolution_from_filename = self._extract_resolution_from_filename(filename)
                    if resolution_from_filename:
                        # 检查是否已经包含质量标识，避免重复
                        if "(" in resolution_from_filename and ")" in resolution_from_filename:
                            media_info["resolution"] = resolution_from_filename
                            logger.info(f"📝 从文件名推断分辨率（已包含质量标识）: {resolution_from_filename}")
                        else:
                            # 如果没有质量标识，添加一个
                            if height >= 2160:
                                quality = "4K"
                            elif height >= 1440:
                                quality = "2K"
                            elif height >= 1080:
                                quality = "1080p"
                            elif height >= 720:
                                quality = "720p"
                            elif height >= 480:
                                quality = "480p"
                            else:
                                quality = f"{height}p"
                            # 检查resolution_from_filename是否已经包含质量标识
                            if "(" in resolution_from_filename and ")" in resolution_from_filename:
                                media_info["resolution"] = resolution_from_filename
                                logger.info(f"📝 从文件名推断分辨率（已包含质量标识）: {media_info['resolution']}")
                            else:
                                media_info["resolution"] = f"{resolution_from_filename} ({quality})"
                                logger.info(f"📝 从文件名推断分辨率（添加质量标识）: {media_info['resolution']}")
                    else:
                        logger.warning("⚠️ 没有找到视频流")
                        # 不尝试从文件名推断分辨率，避免与实际分辨率冲突
                        # 如果ffprobe无法获取分辨率，就标记为未知
                        media_info["resolution"] = "未知"
                        logger.info(f"📝 无法获取视频分辨率，标记为未知")

            audio_stream = next(
                (s for s in info.get("streams", []) if s.get("codec_type") == "audio"),
                None,
            )
            if audio_stream:
                bit_rate = int(audio_stream.get("bit_rate", 0))
                if bit_rate > 0:
                    media_info["bit_rate"] = f"{bit_rate // 1000} kbps"
                    logger.info(f"🔊 音频码率: {media_info['bit_rate']}")

            logger.info(f"📊 最终媒体信息: {media_info}")
            return media_info
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            json.JSONDecodeError,
        ) as e:
            logger.warning(f"⚠️ 无法使用 ffprobe 获取媒体信息: {e}")
            logger.warning(f"⚠️ 异常类型: {type(e)}")

            # 不尝试从文件名推断分辨率，避免与实际分辨率冲突
            logger.info(f"📝 跳过从文件名推断分辨率，避免与实际分辨率冲突")

            # 返回基本的文件信息
            try:
                if os.path.exists(file_path):
                    file_size = os.path.getsize(file_path)
                    if file_size > 0:
                        return {"size": f"{file_size / (1024 * 1024):.2f} MB"}
            except Exception as e2:
                logger.warning(f"⚠️ 获取文件大小失败: {e2}")
            return {}

    def _extract_resolution_from_filename(self, filename: str) -> str:
        """从文件名中提取分辨率信息"""
        try:
            import re

            # 常见的分辨率模式
            patterns = [
                # 标准分辨率格式：1920x1080, 1280x720等
                r'(\d{3,4})x(\d{3,4})',
                # 高度格式：1080p, 720p, 480p等
                r'(\d{3,4})[pP]',
                # 质量标识：4K, 2K, 1080P等
                r'(4K|2K|1080[Pp]|720[Pp]|480[Pp])',
                # B站特有格式
                r'(\d{3,4})[Pp](\d+)',
            ]

            for pattern in patterns:
                match = re.search(pattern, filename)
                if match:
                    if 'x' in pattern:
                        # 宽x高格式
                        width, height = int(match.group(1)), int(match.group(2))
                        resolution = f"{width}x{height}"
                        return resolution

                    elif match.group(1).isdigit():
                        # 纯数字高度格式
                        height = int(match.group(1))

                        # 推断常见的宽度
                        if height >= 2160:
                            width = 3840
                        elif height >= 1440:
                            width = 2560
                        elif height >= 1080:
                            width = 1920
                        elif height >= 720:
                            width = 1280
                        elif height >= 480:
                            width = 854
                        else:
                            width = 640

                        return f"{width}x{height}"

                    else:
                        # 质量标识格式
                        quality_str = match.group(1).upper()
                        if quality_str == "4K":
                            return "3840x2160"
                        elif quality_str == "2K":
                            return "2560x1440"
                        elif "1080" in quality_str:
                            return "1920x1080"
                        elif "720" in quality_str:
                            return "1280x720"
                        elif "480" in quality_str:
                            return "854x480"
                        else:
                            return f"未知分辨率"

            logger.debug(f"📝 无法从文件名提取分辨率: {filename}")
            return ""

        except Exception as e:
            logger.warning(f"⚠️ 从文件名提取分辨率时出错: {e}")
            return ""

    def single_video_find_downloaded_file(
        self, download_path: Path, progress_data: dict = None, expected_title: str = None, url: str = None
    ) -> str:
        """
        单视频下载的文件查找方法

        Args:
            download_path: 下载目录
            progress_data: 进度数据，包含final_filename
            expected_title: 预期的文件名（不包含扩展名）
            url: 原始URL，用于判断平台类型

        Returns:
            str: 找到的文件路径，如果没找到返回None
        """
        # 1. 优先使用progress_hook记录的文件路径
        if progress_data and isinstance(progress_data, dict) and progress_data.get("final_filename"):
            final_file_path = progress_data["final_filename"]

            # 检查是否是中间文件，如果是则直接查找合并后的文件
            original_path = Path(final_file_path)
            base_name = original_path.stem

            # 检查是否是中间文件（包含.f140, .f401等格式标识符）
            is_intermediate_file = False
            if "." in base_name:
                parts = base_name.split(".")
                # 如果最后一部分是数字（如f140, f401），则移除它
                if (
                    len(parts) > 1
                    and parts[-1].startswith("f")
                    and parts[-1][1:].isdigit()
                ):
                    base_name = ".".join(parts[:-1])
                    is_intermediate_file = True

            # 如果是中间文件，直接查找合并后的文件
            if is_intermediate_file:
                logger.info(f"🔍 检测到中间文件，直接查找合并后的文件: {final_file_path}")
                # 构造最终文件名（优先查找.mp4，然后是其他格式）
                possible_extensions = [".mp4", ".mkv", ".webm", ".avi", ".mov"]
                for ext in possible_extensions:
                    final_merged_file = original_path.parent / f"{base_name}{ext}"
                    logger.info(f"🔍 尝试查找合并后的文件: {final_merged_file}")

                    if os.path.exists(final_merged_file):
                        logger.info(f"✅ 找到合并后的文件: {final_merged_file}")
                        return str(final_merged_file)

                logger.warning(f"⚠️ 未找到合并后的文件，基础名称: {base_name}")
            else:
                # 不是中间文件，直接检查是否存在
                if os.path.exists(final_file_path):
                    logger.info(f"✅ 使用progress_hook记录的文件路径: {final_file_path}")
                    return final_file_path

                # 检查是否为YouTube音频模式，如果是则查找对应的MP3文件
                if (hasattr(self, 'bot') and hasattr(self.bot, 'youtube_audio_mode') and
                    self.bot.youtube_audio_mode and self.is_youtube_url(url)):
                    # 将原始文件扩展名替换为.mp3
                    original_path = Path(final_file_path)
                    mp3_path = original_path.with_suffix('.mp3')
                    if mp3_path.exists():
                        logger.info(f"✅ 音频模式：找到转换后的MP3文件: {mp3_path}")
                        return str(mp3_path)
                    else:
                        logger.warning(f"⚠️ 音频模式：未找到转换后的MP3文件: {mp3_path}")
                else:
                    # 检查是否为中间文件（包含格式代码的文件）
                    original_path = Path(final_file_path)
                    filename = original_path.name

                    # 检查是否为DASH中间文件
                    is_dash_intermediate = (
                        '.fdash-' in filename or
                        '.f' in filename and filename.count('.') >= 2 or
                        'dash-' in filename
                    )

                    if is_dash_intermediate:
                        logger.info(f"🔍 检测到DASH中间文件，尝试查找合并后的文件: {filename}")
                        # 尝试查找合并后的文件
                        base_name = filename.split('.f')[0] if '.f' in filename else filename.split('.')[0]
                        ext = '.mp4'  # 合并后通常是mp4格式
                        final_merged_file = original_path.parent / f"{base_name}{ext}"

                        if os.path.exists(final_merged_file):
                            logger.info(f"✅ 找到DASH合并后的文件: {final_merged_file}")
                            return str(final_merged_file)
                        else:
                            logger.info(f"🔍 DASH合并文件不存在，将使用其他方法查找: {final_merged_file}")
                    else:
                        logger.warning(f"⚠️ progress_hook记录的文件路径不存在: {final_file_path}")

        # 2. 基于预期文件名查找
        if expected_title:
            logger.info(f"🔍 基于预期文件名查找: {expected_title}")
            # 使用统一的文件名清理方法
            safe_title = self._sanitize_filename(expected_title)
            if safe_title:
                # 尝试不同的扩展名
                possible_extensions = [".mp4", ".mkv", ".webm", ".avi", ".mov"]
                for ext in possible_extensions:
                    expected_file = download_path / f"{safe_title}{ext}"
                    logger.info(f"🔍 尝试查找文件: {expected_file}")
                    if os.path.exists(expected_file):
                        logger.info(f"✅ 找到基于标题的文件: {expected_file}")
                        return str(expected_file)

                logger.warning(f"⚠️ 未找到基于标题的文件: {safe_title}")

        # 3. 基于平台特定逻辑查找
        if url:
            logger.info(f"🔍 基于平台特定逻辑查找: {url}")
            try:
                if self.is_x_url(url):
                    # X平台：基于视频标题查找
                    logger.info("🔍 X平台：尝试获取视频标题并查找")
                    info_opts = {
                        "quiet": True,
                        "no_warnings": True,
                        "socket_timeout": 15,
                        "retries": 2,
                    }
                    if self.x_cookies_path and os.path.exists(self.x_cookies_path):
                        info_opts["cookiefile"] = self.x_cookies_path

                    with yt_dlp.YoutubeDL(info_opts) as ydl:
                        info = ydl.extract_info(url, download=False)
                        if info and info.get('title'):
                            title = info.get('title')
                            safe_title = self._sanitize_filename(title)
                            if safe_title:
                                logger.info(f"🔍 X平台标题: {safe_title}")
                                # 尝试不同的扩展名
                                possible_extensions = [".mp4", ".mkv", ".webm", ".avi", ".mov"]
                                for ext in possible_extensions:
                                    expected_file = download_path / f"{safe_title}{ext}"
                                    logger.info(f"🔍 尝试查找X平台文件: {expected_file}")
                                    if os.path.exists(expected_file):
                                        logger.info(f"✅ 找到X平台文件: {expected_file}")
                                        return str(expected_file)

                                logger.warning(f"⚠️ 未找到X平台文件，标题: {safe_title}")
                            else:
                                logger.warning("⚠️ X平台标题为空或无效")
                        else:
                            logger.warning("⚠️ 无法获取X平台视频标题")
                else:
                    # 其他平台：基于标题查找（如果还没有尝试过）
                    if not expected_title:
                        logger.info("🔍 其他平台：尝试获取视频标题并查找")
                        info_opts = {
                            "quiet": True,
                            "no_warnings": True,
                            "socket_timeout": 15,
                            "retries": 2,
                        }
                        if self.youtube_cookies_path and os.path.exists(self.youtube_cookies_path):
                            info_opts["cookiefile"] = self.youtube_cookies_path
                        if self.douyin_cookies_path and os.path.exists(self.douyin_cookies_path):
                            info_opts["cookiefile"] = self.douyin_cookies_path

                        with yt_dlp.YoutubeDL(info_opts) as ydl:
                            info = ydl.extract_info(url, download=False)
                            if info and info.get('title'):
                                title = info.get('title')
                                safe_title = self._sanitize_filename(title)
                                if safe_title:
                                    logger.info(f"🔍 其他平台标题: {safe_title}")
                                    # 尝试不同的扩展名
                                    possible_extensions = [".mp4", ".mkv", ".webm", ".avi", ".mov"]
                                    for ext in possible_extensions:
                                        expected_file = download_path / f"{safe_title}{ext}"
                                        logger.info(f"🔍 尝试查找其他平台文件: {expected_file}")
                                        if os.path.exists(expected_file):
                                            logger.info(f"✅ 找到其他平台文件: {expected_file}")
                                            return str(expected_file)

                                    logger.warning(f"⚠️ 未找到其他平台文件，标题: {safe_title}")
            except Exception as e:
                logger.warning(f"⚠️ 平台特定查找失败: {e}")

        # 4. 最后尝试：扫描下载目录中的所有视频文件
        logger.info("🔍 最后尝试：扫描下载目录中的所有视频文件")
        try:
            video_extensions = ['.mp4', '.mkv', '.webm', '.avi', '.mov', '.m4a', '.mp3']
            all_files = []
            
            for file_path in download_path.rglob('*'):
                if file_path.is_file() and file_path.suffix.lower() in video_extensions:
                    # 获取文件的修改时间
                    mtime = file_path.stat().st_mtime
                    all_files.append((file_path, mtime))
            
            if all_files:
                # 按修改时间排序，最新的文件优先
                all_files.sort(key=lambda x: x[1], reverse=True)
                latest_file = all_files[0][0]
                logger.info(f"✅ 找到最新的视频文件: {latest_file}")
                return str(latest_file)
            else:
                logger.warning("⚠️ 下载目录中未找到任何视频文件")
        except Exception as e:
            logger.warning(f"⚠️ 扫描下载目录时出错: {e}")

        # 5. 如果都找不到，记录错误并返回None
        logger.error("❌ 无法找到预期的下载文件")
        return None

    async def _download_with_ytdlp_unified(
        self,
        url: str,
        download_path: Path,
        message_updater=None,
        platform_name: str = "Unknown",
        content_type: str = "video",
        format_spec: str = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        cookies_path: str = None
    ) -> Dict[str, Any]:
        """
        统一的 yt-dlp 下载函数

        Args:
            url: 下载URL
            download_path: 下载目录
            message_updater: 消息更新器
            platform_name: 平台名称
            content_type: 内容类型 (video/image)
            format_spec: 格式规格
            cookies_path: cookies文件路径

        Returns:
            Dict[str, Any]: 下载结果
        """
        try:
            import yt_dlp

            # 确保下载目录存在
            os.makedirs(download_path, exist_ok=True)

            # 配置 yt-dlp
            # 根据设置决定文件名模板
            if hasattr(self, 'bot') and hasattr(self.bot, 'youtube_id_tags') and self.bot.youtube_id_tags and self.is_youtube_url(url):
                outtmpl = '%(title).50s[%(id)s].%(ext)s'
            else:
                outtmpl = '%(title).50s.%(ext)s'

            ydl_opts = {
                'format': format_spec,
                'outtmpl': os.path.join(str(download_path), outtmpl),
                'verbose': False,
                'no_warnings': True,
                'extract_flat': False,
                'ignoreerrors': False,
                'no_check_certificate': True,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }
            }

            # 添加 cookies 支持
            if cookies_path and os.path.exists(cookies_path):
                ydl_opts["cookiefile"] = cookies_path
                logger.info(f"🍪 使用cookies: {cookies_path}")

            # 进度数据存储
            progress_data = {"final_filename": None, "lock": threading.Lock()}

            # 使用统一的单集下载进度回调
            # 检查 message_updater 是否是增强版进度回调函数
            if callable(message_updater) and message_updater.__name__ == 'enhanced_progress_callback':
                # 如果是增强版进度回调，直接使用它返回的 progress_hook
                progress_hook = message_updater(progress_data)
            else:
                # 否则使用标准的 single_video_progress_hook
                progress_hook = single_video_progress_hook(message_updater, progress_data, status_message, context)

            ydl_opts["progress_hooks"] = [progress_hook]

            # 开始下载
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                logger.info(f"🎬 yt-dlp 开始下载 {platform_name} {content_type}...")
                info = ydl.extract_info(url, download=True)

                if not info:
                    raise Exception(f"yt-dlp 未获取到{content_type}信息")

                # 检查info的类型，确保它是字典
                if not isinstance(info, dict):
                    logger.error(f"❌ yt-dlp 返回了非字典类型的结果: {type(info)}, 内容: {info}")
                    raise Exception(f"yt-dlp 返回了意外的数据类型: {type(info)}")

                # 查找下载的文件
                filename = ydl.prepare_filename(info)
                logger.info(f"🔍 yt-dlp 准备的文件名: {filename}")

                if not os.path.exists(filename):
                    logger.info(f"⚠️ 准备的文件名不存在，尝试查找实际下载的文件...")
                    # 尝试查找实际下载的文件
                    download_path_found = self.single_video_find_downloaded_file(
                        download_path,
                        progress_data,
                        info.get('title', ''),
                        url
                    )
                    if download_path_found:
                        filename = download_path_found
                        logger.info(f"✅ 找到实际下载的文件: {filename}")
                    else:
                        raise Exception(f"未找到下载的{content_type}文件")
                else:
                    logger.info(f"✅ 使用yt-dlp准备的文件名: {filename}")

                # 重命名文件以使用清理过的文件名
                try:
                    original_filename = filename
                    file_dir = os.path.dirname(filename)
                    file_ext = os.path.splitext(filename)[1]

                    # 获取原始标题并清理
                    original_title = info.get('title', f'{platform_name}_{content_type}')
                    clean_title = self._sanitize_filename(original_title)

                    # 构建新的文件名
                    new_filename = os.path.join(file_dir, f"{clean_title}{file_ext}")

                    # 如果新文件名与旧文件名不同，则重命名
                    if new_filename != original_filename:
                        # 如果新文件名已存在，添加数字后缀
                        counter = 1
                        final_filename = new_filename
                        while os.path.exists(final_filename):
                            name_without_ext = os.path.splitext(new_filename)[0]
                            final_filename = f"{name_without_ext}_{counter}{file_ext}"
                            counter += 1

                        # 重命名文件
                        os.rename(original_filename, final_filename)
                        filename = final_filename
                        logger.info(f"✅ 文件已重命名为: {os.path.basename(filename)}")
                    else:
                        logger.info(f"✅ 文件名无需重命名")

                except Exception as e:
                    logger.warning(f"⚠️ 重命名文件失败，使用原始文件名: {e}")
                    # 继续使用原始文件名

                # 获取文件信息
                file_size = os.path.getsize(filename)
                size_mb = file_size / 1024 / 1024

                logger.info(f"✅ {platform_name} {content_type}下载成功: {filename} ({size_mb:.1f} MB)")

                # 构建返回结果
                result = {
                    "success": True,
                    "platform": platform_name,
                    "content_type": content_type,
                    "download_path": filename,
                    "full_path": filename,
                    "size_mb": size_mb,
                    "title": info.get('title', f'{platform_name}{content_type}'),
                    "uploader": info.get('uploader', f'{platform_name}用户'),
                    "filename": os.path.basename(filename),
                }

                # 根据内容类型添加特定信息
                if content_type == "video":
                    # 视频特有信息
                    duration = info.get('duration', 0)
                    width = info.get('width', 0)
                    height = info.get('height', 0)
                    resolution = f"{width}x{height}" if width and height else "未知"

                    # 格式化时长
                    if duration:
                        minutes, seconds = divmod(int(duration), 60)
                        hours, minutes = divmod(minutes, 60)
                        if hours > 0:
                            duration_str = f"{hours}:{minutes:02d}:{seconds:02d}"
                        else:
                            duration_str = f"{minutes}:{seconds:02d}"
                    else:
                        duration_str = "未知"

                    result.update({
                        "duration": duration,
                        "duration_str": duration_str,
                        "resolution": resolution,
                        "width": width,
                        "height": height,
                    })
                else:
                    # 图片特有信息
                    width = info.get('width', 0)
                    height = info.get('height', 0)
                    resolution = f"{width}x{height}" if width and height else "未知"

                    result.update({
                        "resolution": resolution,
                        "width": width,
                        "height": height,
                    })

                return result

        except Exception as e:
            logger.error(f"❌ yt-dlp 下载 {platform_name} {content_type}失败: {e}")
            return {
                "success": False,
                "error": f"yt-dlp 下载失败: {str(e)}",
                "platform": platform_name,
                "content_type": content_type
            }

    def cleanup_duplicates(self):
        """清理重复文件"""
        try:
            cleaned_count = 0
            for directory in [self.x_download_path, self.youtube_download_path]:
                if directory.exists():
                    for file in directory.glob("*"):
                        if file.is_file() and " #" in file.name:
                            # 检查是否是视频文件
                            if any(
                                file.name.endswith(ext)
                                for ext in [".mp4", ".mkv", ".webm", ".mov", ".avi"]
                            ):
                                try:
                                    file.unlink()
                                    logger.info(f"删除重复文件: {file.name}")
                                    cleaned_count += 1
                                except Exception as e:
                                    logger.error(f"删除文件失败: {e}")
            return cleaned_count
        except Exception as e:
            logger.error(f"清理重复文件失败: {e}")
            return 0

    def _generate_display_filename(self, original_filename, timestamp):
        """生成用户友好的显示文件名"""
        try:
            # 移除时间戳前缀
            if original_filename.startswith(f"{timestamp}_"):
                display_name = original_filename[len(f"{timestamp}_") :]
            else:
                display_name = original_filename
            # 如果文件名太长，截断它
            if len(display_name) > 35:
                name, ext = os.path.splitext(display_name)
                display_name = name[:30] + "..." + ext
            return display_name
        except BaseException:
            return original_filename

    def _detect_x_content_type(self, url: str) -> str:
        """检测 X 链接的内容类型（图片/视频）"""
        logger.info(f"🔍 开始检测 X 内容类型: {url}")

        # 方法1: 使用 yt-dlp 检测（最准确）
        content_type = self._detect_with_ytdlp(url)
        if content_type:
            return content_type

        # 方法2: 使用 curl 检测（备用）
        content_type = self._detect_with_curl(url)
        if content_type:
            return content_type

        # 方法3: 默认处理 - 当成视频用 yt-dlp 下载
        logger.info("🎬 检测失败，默认为视频类型，使用 yt-dlp 下载")
        return "video"

    def _detect_with_ytdlp(self, url: str) -> str:
        """使用 yt-dlp 检测内容类型"""
        try:
            import yt_dlp

            # 配置 yt-dlp 选项
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": False,  # 不使用 flat 模式，获取完整信息
                "skip_download": True,  # 不下载，只获取信息
                "socket_timeout": 15,   # 15秒超时
                "retries": 2,           # 减少重试次数
            }

            # 添加 cookies 支持
            if self.x_cookies_path and os.path.exists(self.x_cookies_path):
                ydl_opts["cookiefile"] = self.x_cookies_path
                logger.info(f"🍪 yt-dlp 使用X cookies: {self.x_cookies_path}")

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                logger.info("🔍 yt-dlp 开始提取信息...")
                info = ydl.extract_info(url, download=False)

                if not info:
                    logger.warning("⚠️ yt-dlp 未获取到信息")
                    return None

                # 优先检查是否有视频格式（最高优先级）
                formats = info.get('formats', [])
                if formats:
                    # 查找有视频编码的格式
                    video_formats = [f for f in formats if f.get('vcodec') and f.get('vcodec') != 'none']
                    if video_formats:
                        logger.info(f"🎬 yt-dlp 检测到视频内容，找到 {len(video_formats)} 个视频格式")
                        return "video"

                # 检查其他视频指标
                if info.get('duration') and info.get('duration') > 0:
                    logger.info(f"🎬 yt-dlp 通过时长检测到视频内容: {info.get('duration')}秒")
                    return "video"

                # 检查文件扩展名（视频优先）
                filename = info.get('filename', '')
                if any(ext in filename.lower() for ext in ['.mp4', '.webm', '.mov', '.avi']):
                    logger.info(f"🎬 yt-dlp 通过文件名检测到视频内容: {filename}")
                    return "video"

                # 最后检查是否有图片信息
                thumbnails = info.get('thumbnails', [])
                if thumbnails:
                    logger.info(f"📸 yt-dlp 检测到图片内容，找到 {len(thumbnails)} 个缩略图")
                    return "image"

                # 检查图片文件扩展名
                if any(ext in filename.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                    logger.info(f"📸 yt-dlp 通过文件名检测到图片内容: {filename}")
                    return "image"

                logger.info("🎬 yt-dlp 未检测到明确内容类型，默认为视频类型")
                return "video"

        except Exception as e:
            logger.warning(f"⚠️ yt-dlp 检测失败: {e}")
        return None

    def _detect_with_curl(self, url: str) -> str:
        """使用 curl 检测内容类型（备用方法）"""
        try:
            import subprocess
            import re
            import gzip

            # 构建 curl 命令
            curl_cmd = [
                "curl", "-s", "-L", "-k",  # 静默模式，跟随重定向，禁用SSL验证
                "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "-H", "Accept-Language: en-US,en;q=0.5",
                "-H", "Accept-Encoding: gzip, deflate, br",
                "-H", "DNT: 1",
                "-H", "Connection: keep-alive",
                "-H", "Upgrade-Insecure-Requests: 1",
                "--max-time", "10",  # 10秒超时
            ]

            # 如果有 cookies，添加 cookies 文件
            if self.x_cookies_path and os.path.exists(self.x_cookies_path):
                curl_cmd.extend(["-b", self.x_cookies_path])
                logger.info(f"🍪 curl 使用X cookies: {self.x_cookies_path}")

            curl_cmd.append(url)

            # 执行 curl 命令
            logger.info("🔍 curl 开始检测内容类型...")
            result = subprocess.run(curl_cmd, capture_output=True, timeout=15)

            if result.returncode != 0:
                logger.warning(f"⚠️ curl 请求失败: {result.stderr}")
                return None

            # 处理响应内容
            try:
                html_content = result.stdout.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    html_content = gzip.decompress(result.stdout).decode('utf-8')
                except Exception:
                    html_content = result.stdout.decode('utf-8', errors='ignore')

            # 检测视频相关的 HTML 元素
            video_patterns = [
                r'<video[^>]*>',
                r'data-testid="videoPlayer"',
                r'data-testid="video"',
                r'aria-label="[^"]*video[^"]*"',
                r'class="[^"]*video[^"]*"',
            ]

            # 检测图片相关的 HTML 元素
            image_patterns = [
                r'<img[^>]*>',
                r'data-testid="tweetPhoto"',
                r'data-testid="image"',
                r'aria-label="[^"]*image[^"]*"',
                r'class="[^"]*image[^"]*"',
            ]

            # 检查视频模式
            for pattern in video_patterns:
                if re.search(pattern, html_content, re.IGNORECASE):
                    logger.info(f"🎬 curl 检测到视频内容 (模式: {pattern})")
                    return "video"

            # 检查图片模式
            for pattern in image_patterns:
                if re.search(pattern, html_content, re.IGNORECASE):
                    logger.info(f"📸 curl 检测到图片内容 (模式: {pattern})")
                    return "image"

            # 文本检测
            if re.search(r'video|mp4|webm|mov', html_content, re.IGNORECASE):
                logger.info("🎬 curl 通过文本检测到视频内容")
                return "video"

            if re.search(r'image|photo|jpg|jpeg|png|gif|webp', html_content, re.IGNORECASE):
                logger.info("📸 curl 通过文本检测到图片内容")
                return "image"

            logger.info("📸 curl 未检测到明确内容类型")
            return None

        except subprocess.TimeoutExpired:
            logger.warning("⚠️ curl 请求超时")
            return None
        except Exception as e:
            logger.warning(f"⚠️ curl 检测失败: {e}")
            return None

    async def download_video(
        self, url: str, message_updater=None, auto_playlist=False, status_message=None, loop=None, context=None
    ) -> Dict[str, Any]:
        logger.info(f"🚀 [DOWNLOAD_VIDEO] 函数被调用，URL: {url}")
        logger.info(f"🚀 [DOWNLOAD_VIDEO] message_updater类型: {type(message_updater)}")
        logger.info(f"🚀 [DOWNLOAD_VIDEO] message_updater是否为None: {message_updater is None}")
        # 自动修正小红书短链协议
        if url.startswith("tp://"):
            logger.info("检测到 tp:// 协议，自动修正为 http://")
            url = "http://" + url[5:]
        elif url.startswith("tps://"):
            logger.info("检测到 tps:// 协议，自动修正为 https://")
            url = "https://" + url[6:]

        # 自动展开微博短链接
        if self.is_weibo_url(url):
            logger.info(f"🔍 检测到微博URL，开始展开短链接: {url}")
            expanded_url = self._expand_weibo_short_url(url)
            if expanded_url != url:
                logger.info(f"🔄 短链接展开成功: {url} -> {expanded_url}")
                url = expanded_url
                logger.info(f"🔄 使用展开后的微博链接: {url}")
            else:
                logger.info(f"ℹ️ URL无需展开或展开失败，继续使用原URL: {url}")
        
        # 首先进行URL清理，提取纯链接
        original_url = url
        
        # 检查是否需要URL清理（包含中文描述或缺少协议前缀）
        needs_cleanup = (' ' in url or '（' in url or '）' in url or '《' in url or '》' in url or '@' in url or 
                        not url.startswith(('http://', 'https://')))
        
        if needs_cleanup:
            logger.info(f"🔧 检测到需要清理的URL，开始清理: {url}")
            
            # 优先使用专门的网易云音乐URL清理方法
            clean_url = self._clean_netease_url_special(url)
            if clean_url and clean_url != url:
                logger.info(f"🔧 网易云音乐URL清理成功: {url} -> {clean_url}")
                url = clean_url
            else:
                # 如果网易云音乐清理失败，使用通用清理方法
                clean_url = self._extract_clean_url_from_text(url)
                if clean_url and clean_url != url:
                    logger.info(f"🔧 通用URL清理成功: {url} -> {clean_url}")
                    url = clean_url
                else:
                    # 如果清理失败但URL缺少协议前缀，尝试添加
                    if not url.startswith(('http://', 'https://')):
                        logger.info(f"🔧 URL缺少协议前缀，尝试添加: {url}")
                        url = 'https://' + url
                        logger.info(f"🔧 添加协议前缀后: {url}")
                    else:
                        logger.warning(f"⚠️ URL清理失败，使用原始URL: {url}")
        
        # 通用URL重定向检测和平台重新识别（完全跳过网易云音乐链接）
        if not self.is_netease_url(url):
            logger.info(f"🔄 开始URL重定向检测: {url}")
            try:
                # 使用yt-dlp检测URL重定向
                temp_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': True,
                }
                with yt_dlp.YoutubeDL(temp_opts) as ydl:
                    temp_info = ydl.extract_info(url, download=False)
                
                if temp_info and temp_info.get("webpage_url") and temp_info["webpage_url"] != url:
                    redirected_url = temp_info["webpage_url"]
                    logger.info(f"🔄 检测到URL重定向: {url} -> {redirected_url}")
                    
                    # 检查重定向后的URL是否为网易云音乐
                    if self.is_netease_url(redirected_url) and not self.is_netease_url(url):
                        logger.info(f"🎵 重定向后检测到网易云音乐链接，更新URL: {redirected_url}")
                        url = redirected_url
                    elif self.is_apple_music_url(redirected_url) and not self.is_apple_music_url(url):
                        logger.info(f"🍎 重定向后检测到Apple Music链接，更新URL: {redirected_url}")
                        url = redirected_url
                    # 可以添加其他平台的重定向检测
            except Exception as e:
                logger.info(f"URL重定向检测失败: {e}")
        else:
            logger.info(f"🎵 检测到网易云音乐链接，完全跳过URL重定向检测: {url}")
            # 确保网易云音乐链接不会被yt-dlp处理
            logger.info(f"🎵 网易云音乐链接将直接传递给网易云音乐下载器: {url}")
            # 确保URL格式正确
            if not url.startswith(('http://', 'https://')):
                logger.warning(f"⚠️ 网易云音乐URL缺少协议前缀，自动添加: {url}")
                url = 'https://' + url
                logger.info(f"🔧 修复后的URL: {url}")
        
        # 添加详细的调试日志
        logger.info(f"🔍 download_video 开始处理URL: {url}")
        logger.info(f"🔍 自动下载全集模式: {'开启' if auto_playlist else '关闭'}")
        # 检查URL类型
        is_bilibili = self.is_bilibili_url(url)
        is_list, uid, list_id = self.is_bilibili_list_url(url)
        is_user_lists, user_uid = self.is_bilibili_user_lists_url(url)
        is_ugc_season, ugc_bv_id, season_id = self.is_bilibili_ugc_season(url)
        is_multi_part, bv_id = self.is_bilibili_multi_part_video(url)
        logger.info(f"🔍 即将调用is_youtube_playlist_url检查: {url}")
        is_youtube_playlist, playlist_id = self.is_youtube_playlist_url(url)
        logger.info(f"🎯 is_youtube_playlist_url返回结果: is_playlist={is_youtube_playlist}, playlist_id={playlist_id}")

        # 检查是否为Mix播放列表但功能关闭的情况，需要清理URL
        is_mix_playlist_disabled = False
        if not is_youtube_playlist and "list=RDMM" in url:
            logger.info("🎵 检测到Mix播放列表但功能关闭，清理URL中的播放列表参数")
            import re
            # 移除播放列表相关参数
            original_url = url
            url = re.sub(r'[&?]list=[^&]*', '', url)
            url = re.sub(r'[&?]index=[^&]*', '', url)
            # 清理可能的多余&符号
            url = re.sub(r'[&]{2,}', '&', url)
            url = re.sub(r'[?&]$', '', url)
            logger.info(f"🔗 原始URL: {original_url}")
            logger.info(f"🔗 清理后URL: {url}")
            is_mix_playlist_disabled = True
        is_youtube_channel, channel_url = self.is_youtube_channel_playlists_url(url)
        logger.info(f"🔍 YouTube频道识别结果: is_youtube_channel={is_youtube_channel}, channel_url={channel_url}")
        is_x = self.is_x_url(url)
        is_telegraph = self.is_telegraph_url(url)
        is_douyin = self.is_douyin_url(url)
        is_kuaishou = self.is_kuaishou_url(url)
        is_facebook = self.is_facebook_url(url)
        is_netease = self.is_netease_url(url)
        platform = self.get_platform_name(url)
        logger.info(f"🔍 URL识别结果:")
        logger.info(f"  - is_bilibili_url: {is_bilibili}")
        logger.info(
            f"  - is_bilibili_list_url: {is_list}, uid: {uid}, list_id: {list_id}"
        )
        logger.info(
            f"  - is_bilibili_user_lists_url: {is_user_lists}, uid: {user_uid}"
        )
        logger.info(
            f"  - is_bilibili_ugc_season: {is_ugc_season}, bv_id: {ugc_bv_id}, season_id: {season_id}"
        )
        logger.info(
            f"  - is_bilibili_multi_part: {is_multi_part}, bv_id: {bv_id}"
        )
        logger.info(
            f"  - is_youtube_playlist: {is_youtube_playlist}, playlist_id: {playlist_id}"
        )
        logger.info(f"  - is_youtube_channel: {is_youtube_channel}, channel_url: {channel_url if is_youtube_channel else 'None'}")
        logger.info(f"  - is_x_url: {is_x}")
        logger.info(f"  - is_telegraph_url: {is_telegraph}")
        logger.info(f"  - is_netease_url: {is_netease}")
        logger.info(f"  - platform: {platform}")
        download_path = self.get_download_path(url)
        logger.info(f"📁 获取到的下载路径: {download_path}")

        # 处理 X 链接 - 多集检测优先
        if is_x:
            is_x_playlist, playlist_info = self.is_x_playlist_url(url)
            if is_x_playlist:
                logger.info(f"🎬 检测到X多集视频，共{playlist_info['total_videos']}个视频")
                return await self._download_x_playlist(url, download_path, message_updater, playlist_info)
            logger.info("🔍 检测到X链接，开始检测内容类型...")
            # 检测内容类型
            content_type = self._detect_x_content_type(url)
            logger.info(f"📊 检测到内容类型: {content_type}")
            if content_type == "video":
                # 视频使用统一的单视频下载函数
                logger.info("🎬 X 视频使用统一的单视频下载函数")
                return await self._download_single_video(url, download_path, message_updater, status_message=status_message, context=context)
            else:
                # 图片使用 gallery-dl 下载
                logger.info("📸 X 图片使用 gallery-dl 下载")
                return await self.download_with_gallery_dl(url, download_path, message_updater)
        # 处理 Telegraph 链接（使用 gallery-dl）
        if is_telegraph:
            logger.info(f"📸 检测到Telegraph链接，使用 gallery-dl 下载")
            return await self.download_with_gallery_dl(url, download_path, message_updater)

        # 处理抖音链接 - 使用Playwright方法
        if is_douyin:
            logger.info("🎬 检测到抖音链接，使用Playwright方法下载")
            # 创建一个模拟的message对象用于Playwright方法
            class MockMessage:
                def __init__(self, chat_id=0):
                    self.chat_id = chat_id
                    self.message_id = 0

            mock_message = MockMessage()
            return await self._download_douyin_with_playwright(url, mock_message, message_updater)

        # 处理快手链接 - 使用Playwright方法
        if is_kuaishou:
            logger.info("⚡ 检测到快手链接，使用Playwright方法下载")
            # 创建一个模拟的message对象用于Playwright方法
            class MockMessage:
                def __init__(self, chat_id=0):
                    self.chat_id = chat_id
                    self.message_id = 0

            mock_message = MockMessage()
            return await self._download_kuaishou_with_playwright(url, mock_message, message_updater)

        # 处理Facebook链接 - 使用yt-dlp方法（参考YouTube单集下载）
        if self.is_facebook_url(url):
            logger.info("📘 检测到Facebook链接，使用yt-dlp方法下载")
            return await self._download_single_video(url, download_path, message_updater, status_message=status_message, context=context)

        # 处理小红书链接 - 检测内容类型并选择合适的下载方法
        if self.is_xiaohongshu_url(url):
            logger.info("📖 检测到小红书链接")
            
            # 检测内容类型（图片或视频）
            content_type = await self._detect_xiaohongshu_content_type(url)
            logger.info(f"📊 小红书内容类型: {content_type}")
            
            if content_type == "image":
                logger.info("🖼️ 检测到小红书图片，使用xiaohongshu_downloader方法下载")
                return await self._download_xiaohongshu_image_with_downloader(url, message_updater)
            else:
                logger.info("🎬 检测到小红书视频，使用Playwright方法下载")
                # 创建一个模拟的message对象用于Playwright方法
                class MockMessage:
                    def __init__(self, chat_id=0):
                        self.chat_id = chat_id
                        self.message_id = 0

                mock_message = MockMessage()
                return await self._download_xiaohongshu_with_playwright(url, mock_message, message_updater)

        # 处理网易云音乐链接
        if is_netease:
            logger.info("🎵 检测到网易云音乐链接，使用网易云音乐下载器")
            return await self._download_netease_music(url, download_path, message_updater, status_message, context)

        # 处理QQ音乐链接
        if self.is_qqmusic_url(url):
            logger.info("🎵 检测到QQ音乐链接，使用QQ音乐下载器")
            return await self._download_qqmusic_music(url, download_path, message_updater, status_message, context)

        # 处理YouTube Music链接
        if self.is_youtube_music_url(url):
            logger.info("🎵 检测到YouTube Music链接，使用YouTube Music下载器")
            return await self._download_youtubemusic_music(url, download_path, message_updater, status_message, context)

        # 处理 Apple Music 链接
        if self.is_apple_music_url(url):
            # 根据环境变量显示不同的日志信息
            use_amd = os.environ.get("AMDP", "false").lower() == "true"
            if use_amd:
                logger.info("🍎 检测到 Apple Music 链接，使用 Apple Music Plus 下载器 (AMD)")
            else:
                logger.info("🍎 检测到 Apple Music 链接，使用 Apple Music 下载器 (GAMDL)")
            return await self._download_apple_music(url, download_path, message_updater, status_message, context)

        # 处理 YouTube 频道播放列表
        if is_youtube_channel:
            logger.info("✅ 检测到YouTube频道播放列表，开始下载所有播放列表")
            # message_updater参数已正确传递
            return await self._download_youtube_channel_playlists(
                channel_url, download_path, message_updater, status_message, loop
            )
        # 处理 YouTube 播放列表
        logger.info(f"🔍 检查YouTube播放列表分支: is_youtube_playlist={is_youtube_playlist}")
        if is_youtube_playlist:
            logger.info(f"✅ 检测到YouTube播放列表，播放列表ID: {playlist_id}")

            # 为单个播放列表下载创建进度回调
            if message_updater:
                # 创建播放列表专用的进度回调
                playlist_progress_data = {
                    "playlist_index": 1,
                    "total_playlists": 1,
                    "playlist_title": "播放列表",  # 临时标题，会在下载时更新
                    "current_video": 0,
                    "total_videos": 0,
                    "downloaded_videos": 0,
                }

                # 使用与频道下载相同的进度回调创建函数
                def create_single_playlist_progress_callback(progress_data):
                    last_update = {"percent": -1, "time": 0, "text": ""}
                    import time as _time

                    # 捕获外层作用域的变量
                    captured_message_updater = message_updater
                    captured_status_message = status_message if 'status_message' in locals() else None
                    captured_loop = loop if 'loop' in locals() else None

                    def escape_num(text):
                        # 转义MarkdownV2特殊字符，包括小数点
                        if not isinstance(text, str):
                            text = str(text)
                        escape_chars = [
                            "_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"
                        ]
                        for char in escape_chars:
                            text = text.replace(char, "\\" + char)
                        return text

                    def progress_callback(d):
                        # 强制日志，确保能看到进度回调被调用
                        logger.info(f"🔍 [SINGLE_PLAYLIST_PROGRESS_CALLBACK] 被调用: status={d.get('status')}, filename={d.get('filename', 'N/A')}")

                        if d.get("status") == "downloading":
                            logger.info(f"🔍 单个YouTube播放列表进度回调: status={d.get('status')}, filename={d.get('filename', 'N/A')}")
                            # 修正当前视频序号为本播放列表的当前下载视频序号/总数
                            cur_idx = (
                                d.get("playlist_index")
                                or d.get("info_dict", {}).get("playlist_index")
                                or 1
                            )
                            total_idx = (
                                d.get("playlist_count")
                                or d.get("info_dict", {}).get("n_entries")
                                or (progress_data.get("total_videos") if progress_data and isinstance(progress_data, dict) else 0)
                                or 1
                            )
                            if progress_data and isinstance(progress_data, dict):
                                progress_text = (
                                    f"📥 正在下载第{escape_num(progress_data['playlist_index'])}/{escape_num(progress_data['total_playlists'])}个播放列表：{escape_num(progress_data['playlist_title'])}\n\n"
                                    f"📺 当前视频: {escape_num(cur_idx)}/{escape_num(total_idx)}\n"
                                )
                            else:
                                progress_text = f"📺 当前视频: {escape_num(cur_idx)}/{escape_num(total_idx)}\n"
                            percent = 0
                            if d.get("filename"):
                                filename = os.path.basename(d.get("filename", ""))
                                total_bytes = d.get("total_bytes") or d.get(
                                    "total_bytes_estimate", 0
                                )
                                downloaded_bytes = d.get("downloaded_bytes", 0)
                                speed_bytes_s = d.get("speed", 0)
                                eta_seconds = d.get("eta", 0)
                                if total_bytes and total_bytes > 0:
                                    downloaded_mb = downloaded_bytes / (1024 * 1024)
                                    total_mb = total_bytes / (1024 * 1024)
                                    speed_mb_s = (
                                        speed_bytes_s / (1024 * 1024)
                                        if speed_bytes_s
                                        else 0
                                    )
                                    percent = int(downloaded_bytes * 100 / total_bytes)
                                    bar = self._make_progress_bar(percent)
                                    try:
                                        minutes, seconds = divmod(int(eta_seconds), 60)
                                        eta_str = f"{minutes:02d}:{seconds:02d}"
                                    except (ValueError, TypeError):
                                        eta_str = "未知"
                                    downloaded_mb_str = f"{downloaded_mb:.2f}"
                                    total_mb_str = f"{total_mb:.2f}"
                                    speed_mb_s_str = f"{speed_mb_s:.2f}"
                                    percent_str = f"{percent:.1f}"
                                    progress_text += (
                                        f"📝 文件: {escape_num(filename)}\n"
                                        f"💾 大小: {escape_num(downloaded_mb_str)}MB / {escape_num(total_mb_str)}MB\n"
                                        f"⚡ 速度: {escape_num(speed_mb_s_str)}MB/s\n"
                                        f"⏳ 预计剩余: {escape_num(eta_str)}\n"
                                        f"📊 进度: {bar} {escape_num(percent_str)}%"
                                    )
                                else:
                                    downloaded_mb = (
                                        downloaded_bytes / (1024 * 1024)
                                        if downloaded_bytes > 0
                                        else 0
                                    )
                                    speed_mb_s = (
                                        speed_bytes_s / (1024 * 1024)
                                        if speed_bytes_s
                                        else 0
                                    )
                                    downloaded_mb_str = f"{downloaded_mb:.2f}"
                                    speed_mb_s_str = f"{speed_mb_s:.2f}"
                                    progress_text += (
                                        f"📝 文件: {escape_num(filename)}\n"
                                        f"💾 大小: {escape_num(downloaded_mb_str)}MB\n"
                                        f"⚡ 速度: {escape_num(speed_mb_s_str)}MB/s\n"
                                        f"📊 进度: 下载中..."
                                    )
                            now = _time.time()
                            # 参考renlixing.py：每5%进度变化或每1秒更新一次
                            if (abs(percent - last_update["percent"]) >= 5) or (now - last_update["time"] > 1):
                                if progress_text != last_update["text"]:
                                    # 更新进度消息
                                    logger.info(f"🔄 单个播放列表更新进度消息: percent={percent}%")
                                last_update["percent"] = percent
                                last_update["time"] = now
                                last_update["text"] = progress_text
                                import asyncio

                                # 参考renlixing.py：简化的消息更新逻辑
                                if captured_message_updater:
                                    try:
                                        # 直接调用 message_updater
                                        if asyncio.iscoroutinefunction(captured_message_updater):
                                            # 异步函数，需要在事件循环中运行
                                            if captured_loop:
                                                future = asyncio.run_coroutine_threadsafe(
                                                    captured_message_updater(progress_text), captured_loop
                                                )
                                                future.result(timeout=3.0)
                                            else:
                                                logger.warning(f"⚠️ 没有事件循环，无法调用异步函数")
                                        else:
                                            # 同步函数，直接调用
                                            captured_message_updater(progress_text)
                                    except Exception as e:
                                        # 简化错误处理
                                        if "Message is not modified" not in str(e):
                                            logger.warning(f"❌ 进度更新失败: {e}")
                                        # 记录进度到日志（降级处理）
                                        logger.debug(f"📊 进度更新: {progress_text}")

                    return progress_callback

                progress_callback = create_single_playlist_progress_callback(playlist_progress_data)
                logger.info(f"🔧 为单个播放列表创建进度回调函数: {type(progress_callback)}")
            else:
                progress_callback = None
                logger.info(f"⚠️ 没有message_updater，跳过进度回调创建")

            return await self._download_youtube_playlist_with_progress(
                playlist_id, download_path, progress_callback, original_url=url
            )
        else:
            logger.info(f"❌ 不是YouTube播放列表，继续其他处理逻辑")
        # 如果是B站链接，根据设置选择下载器
        if self.is_bilibili_url(url):
            logger.info(f"🔍 B站链接检测结果: is_user_lists={is_user_lists}, user_uid={user_uid}")
            logger.info(f"🔍 B站链接检测结果: is_ugc_season={is_ugc_season}, ugc_bv_id={ugc_bv_id}, season_id={season_id}")
            logger.info(f"🔍 B站链接检测结果: is_multi_part={is_multi_part}, bv_id={bv_id if 'bv_id' in locals() else 'N/A'}")

            # 优先处理UP主合集列表页面
            if is_user_lists:
                logger.info("✅ 检测到B站UP主合集列表页面，开始下载所有视频")
                logger.info(f"🎯 调用 _download_bilibili_user_all_videos(uid={user_uid})")
                result = await self._download_bilibili_user_all_videos(user_uid, download_path, message_updater)
                logger.info(f"🎯 UP主下载结果: {result.get('success', False)}")
                return result

            # 优先处理UGC合集
            if is_ugc_season:
                # 检查UGC播放列表配置
                ugc_playlist_enabled = getattr(self.bot, 'bilibili_ugc_playlist', True) if hasattr(self, 'bot') else True
                if ugc_playlist_enabled:
                    logger.info("✅ 检测到B站UGC合集，且UGC播放列表开启，下载整个合集")
                    return await self._download_bilibili_ugc_season(ugc_bv_id, season_id, download_path, message_updater)
                else:
                    logger.info("✅ 检测到B站UGC合集，但UGC播放列表关闭，只下载当前单集")
                    return await self._download_single_video(url, download_path, message_updater, status_message=status_message, context=context)

            # 优先检查：如果明确检测到是单集视频，直接使用通用下载器
            elif not is_multi_part and not is_list:
                logger.info("✅ 检测到B站单集视频，直接使用通用下载器")
                return await self._download_single_video(url, download_path, message_updater, status_message=status_message, context=context)

            # 如果检测到多P或合集，且开启了自动下载全集，使用专门的B站下载器
            elif auto_playlist and (is_multi_part or is_list):
                logger.info("✅ 检测到B站多P视频或合集，且开启多P自动下载全集，使用专门的B站下载器")
                return await self._download_bilibili_video(
                    url, download_path, message_updater, auto_playlist, status_message, context
                )

            # 其他情况（检测到多P但未开启多P自动下载全集）使用通用下载器
            else:
                logger.info("✅ 检测到B站多P视频或合集，但未开启多P自动下载全集，使用通用下载器下载当前集")
                return await self._download_single_video(url, download_path, message_updater, status_message=status_message, context=context)
        # 处理新增的平台（微博、Instagram、TikTok）
        if self.is_weibo_url(url) or self.is_instagram_url(url) or self.is_tiktok_url(url):
            logger.info(f"✅ 检测到{platform}视频，使用通用下载器")
            return await self._download_single_video(url, download_path, message_updater, status_message=status_message, context=context)

        # 检查是否为B站UP主空间URL，如果是则不应该fallback到单个视频下载
        if self.is_bilibili_url(url) and "space.bilibili.com" in url:
            logger.error(f"❌ B站UP主空间URL不应该fallback到单个视频下载: {url}")
            return {'success': False, 'error': 'B站UP主空间URL处理失败，请检查URL格式或重试'}

        # 检查是否为网易云音乐链接，如果是则不应该fallback到单个视频下载
        if self.is_netease_url(url):
            logger.error(f"❌ 网易云音乐链接不应该fallback到单个视频下载: {url}")
            return {'success': False, 'error': '网易云音乐链接处理失败，请检查URL格式或重试'}

        # 检查是否为QQ音乐链接，如果是则不应该fallback到单个视频下载
        if self.is_qqmusic_url(url):
            logger.error(f"❌ QQ音乐链接不应该fallback到单个视频下载: {url}")
            return {'success': False, 'error': 'QQ音乐链接处理失败，请检查URL格式或重试'}

        # 处理单个视频（包括YouTube单个视频）
        logger.info(f"✅ 使用通用下载器处理单个视频，平台: {platform}")
        logger.info(f"🔍 最终fallback: URL={url}")
        return await self._download_single_video(url, download_path, message_updater, no_playlist=is_mix_playlist_disabled, status_message=status_message, context=context)

    async def _download_bilibili_video(
        self, url: str, download_path: str, message_updater=None, auto_playlist=False, status_message=None, context=None
    ) -> Dict[str, Any]:
        """下载B站多P视频或合集"""
        import os
        from pathlib import Path
        import time
        import re
        logger.info(f"🎬 开始下载B站多P视频或合集: {url}")

        # 检查是否为B站用户自定义列表URL
        is_list, uid, list_id = self.is_bilibili_list_url(url)
        is_multi_part, bv_id = self.is_bilibili_multi_part_video(url)

        # 记录下载开始时间
        download_start_time = time.time()
        logger.info(f"⏰ 下载开始时间: {download_start_time}")

        logger.info(f"🔍 检测结果: 列表={is_list}, 多P={is_multi_part}, BV号={bv_id}")

        # 简化：不需要跟踪下载文件，使用目录遍历

        # 简化方案：直接删除目录遍历，使用现有的进度回调机制

        # 预先获取播放列表信息，以便知道应该有哪些文件
        # 简化：不需要预先获取播放列表信息，直接下载后用目录遍历

        # 使用single_video_progress_hook来获得完整的进度显示功能
        import threading
        progress_data = {"final_filename": None, "lock": threading.Lock()}
        progress_callback = single_video_progress_hook(
            message_updater=message_updater,
            progress_data=progress_data,
            status_message=status_message,
            context=context
        )

        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                self.smart_download_bilibili,
                url,
                str(download_path),
                progress_callback,
                auto_playlist,
            )

            # 检查是否为单视频，如果是则回退到通用下载器
            if isinstance(result, dict) and result.get("status") == "single_video":
                logger.info("🔄 smart_download_bilibili 检测到单视频，回退到通用下载器")
                return await self._download_single_video(url, download_path, message_updater, status_message=status_message, context=context)

            if not result:
                return {'success': False, 'error': 'B站下载失败'}

            # 检查是否为包含完整文件信息的结果（BV号循环法）
            if isinstance(result, dict) and result.get("status") == "success" and "files" in result:
                logger.info("✅ smart_download_bilibili 返回了完整的文件信息，直接使用")
                return {
                    'success': True,
                    'is_playlist': result.get('is_playlist', True),
                    'file_count': result.get('file_count', 0),
                    'total_size_mb': result.get('total_size_mb', 0),
                    'files': result.get('files', []),
                    'platform': result.get('platform', 'bilibili'),
                    'download_path': result.get('download_path', str(download_path)),
                    'filename': result.get('filename', ''),
                    'size_mb': result.get('size_mb', 0),
                    'resolution': result.get('resolution', '未知'),
                    'episode_count': result.get('episode_count', 0),
                    'video_type': result.get('video_type', 'playlist')
                }

            await asyncio.sleep(1)

            # 简化：直接使用目录遍历查找文件
            video_files = []

            # 简化：直接跳到目录遍历，删除所有复杂的文件记录逻辑
            if False:  # 禁用复杂逻辑
                downloaded_files = []  # 定义变量以避免未定义错误
                logger.info(f"📋 找到 {len(downloaded_files)} 个实际下载文件记录")
                for filename in downloaded_files:
                    file_path = Path(filename)
                    if file_path.exists():
                        try:
                            mtime = os.path.getmtime(file_path)
                            video_files.append((file_path, mtime))
                            logger.info(f"✅ 找到本次下载文件: {file_path.name}")
                        except OSError:
                            continue
                    else:
                        logger.warning(f"⚠️ 记录的文件不存在: {filename}")
            elif False:  # 禁用复杂逻辑
                # 检查是否为B站合集下载（有files字段）
                if progress_data and isinstance(progress_data, dict) and progress_data.get("files"):
                    # B站合集下载：直接使用预期文件名查找
                    logger.info("🔍 B站合集下载：使用预期文件名直接查找")
                    logger.info(f"📋 预期文件数量: {len(progress_data['files'])}")
                    logger.info(f"📁 搜索目录: {download_path}")

                    for file_info in progress_data["files"]:
                        expected_filename = file_info['filename']
                        expected_path = download_path / expected_filename

                        if expected_path.exists():
                            try:
                                mtime = os.path.getmtime(expected_path)
                                video_files.append((expected_path, mtime))
                                logger.info(f"✅ 找到预期文件: {expected_filename}")
                            except OSError:
                                logger.warning(f"⚠️ 无法获取文件时间: {expected_filename}")
                        else:
                            logger.warning(f"⚠️ 预期文件不存在: {expected_filename}")
                else:
                    # 其他类型下载：直接使用progress_data中的预期文件列表
                    expected_files_list = progress_data.get('expected_files', []) if progress_data and isinstance(progress_data, dict) else []
                    logger.info("🔍 使用progress_data中的预期文件列表")

                    logger.info(f"📋 预期文件数量: {len(expected_files_list)}")
                    logger.info(f"📁 搜索目录: {download_path}")

                    def clean_filename_for_matching(filename):
                        """清理文件名用于匹配，删除yt-dlp格式代码和ID标识，保留版本号等重要信息"""
                        import re
                        if not filename:
                            return ""

                        # 删除yt-dlp的各种格式代码
                        # 1. 删除 .f137+140 格式（在扩展名前）
                        cleaned = re.sub(r'\.[fm]\d+(\+\d+)*', '', filename)

                        # 2. 删除 .f100026 格式（嵌入在文件名中间）
                        cleaned = re.sub(r'\.f\d+', '', cleaned)

                        # 3. 删除YouTube视频ID标识 [video_id]（仅在启用ID标签时）
                        # 只有启用了ID标签功能时才清理ID
                        if hasattr(self, 'bot') and hasattr(self.bot, 'youtube_id_tags') and self.bot.youtube_id_tags:
                            cleaned = re.sub(r'\[[a-zA-Z0-9_-]{10,12}\]', '', cleaned)

                        # 4. 删除 .m4a, .webm 等临时格式，替换为 .mp4
                        cleaned = re.sub(r'\.(webm|m4a|mp3)$', '.mp4', cleaned)

                        # 修复可能的双扩展名问题（如 .m4a.mp4 -> .mp4）
                        cleaned = re.sub(r'\.(webm|m4a|mp3)\.mp4$', '.mp4', cleaned)

                        # 5. 删除序号前缀（如 "23. "），因为预期文件名没有序号
                        cleaned = re.sub(r'^\d+\.\s*', '', cleaned)

                        # 6. 对B站多P标题进行智能处理（和预期文件名保持一致）
                        # 查找 pxx 模式，如果找到就从 pxx 开始截取
                        pattern = r'\s+[pP](\d{1,3})\s+'
                        match = re.search(pattern, cleaned)
                        if match:
                            start_pos = match.start() + 1  # +1 是为了跳过前面的空格
                            cleaned = cleaned[start_pos:]

                        # 7. 统一特殊字符（解决全角/半角差异）
                        # 将半角竖线转换为全角竖线，与_basic_sanitize_filename保持一致
                        cleaned = cleaned.replace('|', '｜')
                        # 将普通斜杠转换为大斜杠符号，与_basic_sanitize_filename保持一致
                        cleaned = cleaned.replace('/', '⧸')
                        # 保留全角字符，不进行额外转换
                        # cleaned = re.sub(r'[【】]', '_', cleaned)  # 注释掉，保留原始字符

                        # 确保以 .mp4 结尾
                        if not cleaned.endswith('.mp4'):
                            cleaned = cleaned.rstrip('.') + '.mp4'

                        return cleaned

                    for expected_file in expected_files_list:
                        # 尝试多种可能的文件名格式
                        base_title = expected_file.get('title', '')
                        base_filename = expected_file.get('filename', '')

                        possible_names = [
                            base_filename,  # 原始文件名
                            base_title,     # 原始标题
                            f"{base_title}.mp4",  # 标题+.mp4
                            clean_filename_for_matching(base_filename),  # 清理后的文件名
                            clean_filename_for_matching(base_title),     # 清理后的标题
                        ]

                        # 去重并过滤空值
                        possible_names = list(dict.fromkeys([name for name in possible_names if name]))

                        found = False
                        for possible_name in possible_names:
                            # 1. 先在下载目录直接查找
                            expected_path = download_path / possible_name
                            if expected_path.exists():
                                try:
                                    mtime = os.path.getmtime(expected_path)
                                    video_files.append((expected_path, mtime))
                                    logger.info(f"✅ 找到预期文件: {possible_name}")
                                    found = True
                                    break
                                except OSError:
                                    continue

                            # 2. 在子目录中查找（递归搜索）
                            for video_ext in ["*.mp4", "*.mkv", "*.webm", "*.avi", "*.mov", "*.flv"]:
                                matching_files = list(Path(download_path).rglob(video_ext))
                                for file_path in matching_files:
                                    # 检查文件名是否匹配（考虑序号前缀）
                                    actual_filename = file_path.name
                                    cleaned_actual = clean_filename_for_matching(actual_filename)
                                    cleaned_expected = clean_filename_for_matching(possible_name)

                                    if cleaned_actual == cleaned_expected:
                                        try:
                                            mtime = os.path.getmtime(file_path)
                                            video_files.append((file_path, mtime))
                                            logger.info(f"✅ 在子目录找到文件: {file_path.relative_to(download_path)}")
                                            found = True
                                            break
                                        except OSError:
                                            continue
                                if found:
                                    break
                            if found:
                                break

                        if not found:
                            logger.warning(f"⚠️ 未找到预期文件: {expected_file.get('title', 'unknown')}")
                            logger.info(f"   尝试的文件名: {possible_names}")
            else:
                # B站多P下载：智能查找子目录中的文件
                logger.info("🎯 B站多P下载：没有预期文件列表，智能查找子目录中的文件")
                logger.info(f"🔍 搜索路径: {download_path}")

                # 检查下载路径是否存在
                if not Path(download_path).exists():
                    logger.error(f"❌ 下载路径不存在: {download_path}")
                    return {"success": False, "error": "下载路径不存在"}

                # 智能查找：优先查找最新创建的子目录
                try:
                    all_items = list(Path(download_path).iterdir())
                    subdirs = [item for item in all_items if item.is_dir()]

                    if subdirs:
                        # 按修改时间排序，找到最新的子目录
                        latest_subdir = max(subdirs, key=lambda x: x.stat().st_mtime)
                        logger.info(f"📁 找到最新子目录: {latest_subdir.name}")

                        # 在子目录中查找视频文件
                        video_extensions = ["*.mp4", "*.mkv", "*.webm", "*.avi", "*.mov", "*.flv"]
                        for ext in video_extensions:
                            matching_files = list(latest_subdir.glob(ext))
                            if matching_files:
                                logger.info(f"✅ 在子目录中找到 {len(matching_files)} 个 {ext} 文件")
                                for file_path in matching_files:
                                    try:
                                        mtime = os.path.getmtime(file_path)
                                        video_files.append((file_path, mtime))
                                        logger.info(f"✅ 找到文件: {file_path.name}")
                                    except OSError:
                                        continue
                    else:
                        logger.warning("⚠️ 未找到子目录，在根目录查找")
                        # 如果没有子目录，在根目录查找
                        video_extensions = ["*.mp4", "*.mkv", "*.webm", "*.avi", "*.mov", "*.flv"]
                        for ext in video_extensions:
                            matching_files = list(Path(download_path).glob(ext))
                            for file_path in matching_files:
                                try:
                                    mtime = os.path.getmtime(file_path)
                                    video_files.append((file_path, mtime))
                                    logger.info(f"✅ 找到文件: {file_path.name}")
                                except OSError:
                                    continue

                except Exception as e:
                    logger.error(f"❌ 智能查找失败: {e}")
                    return {"success": False, "error": f"文件查找失败: {e}"}

            # 如果没有找到文件，记录详细信息用于调试
            if not video_files:
                logger.warning("⚠️ 未找到任何匹配文件")
                logger.info(f"🔍 搜索路径: {download_path}")
                return {"success": False, "error": "目录遍历未找到视频文件"}

            video_files.sort(key=lambda x: x[0].name)

            # 检测PART文件
            part_files = self._detect_part_files(download_path)
            success_count = len(video_files)
            part_count = len(part_files)

            # 在日志中显示详细统计
            logger.info(f"📊 下载完成统计：")
            logger.info(f"✅ 成功文件：{success_count} 个")
            if part_count > 0:
                logger.warning(f"⚠️ 未完成文件：{part_count} 个")
                self._log_part_files_details(part_files)
            else:
                logger.info("✅ 未发现PART文件，所有下载都已完成")

            if is_list:
                logger.info(f"🎉 B站合集下载完成，统计本次下载文件")
                if video_files:
                    total_size_mb = 0
                    file_info_list = []
                    all_resolutions = set()
                    for file_path, mtime in video_files:
                        size_mb = os.path.getsize(file_path) / (1024 * 1024)
                        total_size_mb += size_mb
                        media_info = self.get_media_info(str(file_path))
                        resolution = media_info.get('resolution', '未知')
                        if resolution != '未知':
                            all_resolutions.add(resolution)
                        file_info_list.append({
                            'filename': os.path.basename(file_path),
                            'size_mb': size_mb,
                            'resolution': resolution,
                            'abr': media_info.get('bit_rate')
                        })
                    filename_list = [info['filename'] for info in file_info_list]
                    filename_display = '\n'.join([f"  {i+1:02d}. {name}" for i, name in enumerate(filename_list)])
                    resolution_display = ', '.join(sorted(all_resolutions)) if all_resolutions else '未知'
                    return {
                        'success': True,
                        'is_playlist': True,
                        'file_count': len(video_files),
                        'total_size_mb': total_size_mb,
                        'files': file_info_list,
                        'platform': 'bilibili',
                        'download_path': str(download_path),
                        'filename': filename_display,
                        'size_mb': total_size_mb,
                        'resolution': resolution_display,
                        'episode_count': len(video_files),
                        # 添加PART文件统计信息
                        'success_count': success_count,
                        'part_count': part_count,
                        'part_files': [str(pf) for pf in part_files] if part_files else []
                    }
                else:
                    return {'success': False, 'error': 'B站合集下载完成但未找到本次下载的文件'}
            else:
                # 多P视频下载，统计本次下载文件
                if video_files:
                    # 如果有多个文件，应该使用播放列表格式显示
                    if len(video_files) > 1:
                        total_size_mb = 0
                        file_info_list = []
                        all_resolutions = set()
                        for file_path, mtime in video_files:
                            size_mb = os.path.getsize(file_path) / (1024 * 1024)
                            total_size_mb += size_mb
                            media_info = self.get_media_info(str(file_path))
                            resolution = media_info.get('resolution', '未知')
                            if resolution != '未知':
                                all_resolutions.add(resolution)
                            file_info_list.append({
                                'filename': os.path.basename(file_path),
                                'size_mb': size_mb,
                                'resolution': resolution,
                                'abr': media_info.get('bit_rate')
                            })
                        filename_list = [info['filename'] for info in file_info_list]
                        filename_display = '\n'.join([f"  {i+1:02d}. {name}" for i, name in enumerate(filename_list)])
                        resolution_display = ', '.join(sorted(all_resolutions)) if all_resolutions else '未知'
                        return {
                            'success': True,
                            'is_playlist': True,
                            'video_type': 'playlist',
                            'file_count': len(video_files),
                            'total_size_mb': total_size_mb,
                            'files': file_info_list,
                            'platform': 'bilibili',
                            'download_path': str(download_path),
                            'filename': filename_display,
                            'size_mb': total_size_mb,
                            'resolution': resolution_display,
                            'episode_count': len(video_files)
                        }
                    else:
                        # 只有一个文件，使用单个视频格式
                        video_files.sort(key=lambda x: x[1], reverse=True)
                        final_file_path = str(video_files[0][0])
                        media_info = self.get_media_info(final_file_path)
                        size_mb = os.path.getsize(final_file_path) / (1024 * 1024)
                        return {
                            'success': True,
                            'filename': os.path.basename(final_file_path),
                            'full_path': final_file_path,
                            'size_mb': size_mb,
                            'platform': 'bilibili',
                            'download_path': str(download_path),
                            'resolution': media_info.get('resolution', '未知'),
                            'abr': media_info.get('bit_rate')
                        }
                else:
                    return {'success': False, 'error': 'B站多P下载完成但未找到本次下载的文件'}

        except Exception as e:
            logger.error(f"B站下载失败: {e}")
            return {"success": False, "error": str(e)}

    async def _download_single_video(
        self, url: str, download_path: Path, message_updater=None, no_playlist: bool = False, status_message=None, context=None
    ) -> Dict[str, Any]:
        """下载单个视频（包括YouTube单个视频）"""
        import os
        logger.info(f"🎬 开始下载单个视频: {url}")
        
        # 检查是否为网易云音乐链接，如果是则不应该调用此函数
        if self.is_netease_url(url):
            logger.error(f"❌ 网易云音乐链接不应该调用_download_single_video函数: {url}")
            return {
                "success": False,
                "error": "网易云音乐链接不应该调用单视频下载函数",
                "platform": "Netease",
                "content_type": "music"
            }

        # 检查是否为QQ音乐链接，如果是则不应该调用此函数
        if self.is_qqmusic_url(url):
            logger.error(f"❌ QQ音乐链接不应该调用_download_single_video函数: {url}")
            return {
                "success": False,
                "error": "QQ音乐链接不应该调用单视频下载函数",
                "platform": "QQMusic",
                "content_type": "music"
            }
        
        # 检查是否为YouTube Music链接，如果是则不应该调用此函数
        if self.is_youtube_music_url(url):
            logger.error(f"❌ YouTube Music链接不应该调用_download_single_video函数: {url}")
            return {
                "success": False,
                "error": "YouTube Music链接不应该调用单视频下载函数",
                "platform": "YouTubeMusic",
                "content_type": "music"
            }
        # 1. 预先获取信息以确定文件名
        try:
            logger.info("🔍 步骤1: 预先获取视频信息...")
            info_opts = {
                "quiet": True,
                "no_warnings": True,
                "socket_timeout": 60,  # 增加到60秒超时
                "retries": 5,  # 增加重试次数
                "noplaylist": True,  # 添加 noplaylist 参数，确保只获取单个视频信息
                "http_headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
            }
            if self.proxy_host:
                info_opts["proxy"] = self.proxy_host
                logger.info(f"🌐 使用代理: {self.proxy_host}")
            if (
                self.is_x_url(url)
                and self.x_cookies_path
                and os.path.exists(self.x_cookies_path)
            ):
                info_opts["cookiefile"] = self.x_cookies_path
                logger.info(f"🍪 使用X cookies: {self.x_cookies_path}")
            if (
                self.is_youtube_url(url)
                and self.youtube_cookies_path
                and os.path.exists(self.youtube_cookies_path)
            ):
                info_opts["cookiefile"] = self.youtube_cookies_path
                logger.info(f"🍪 使用YouTube cookies: {self.youtube_cookies_path}")
            if (
                self.is_douyin_url(url)
                and self.douyin_cookies_path
                and os.path.exists(self.douyin_cookies_path)
            ):
                info_opts["cookiefile"] = self.douyin_cookies_path
                logger.info(f"🍪 使用抖音 cookies: {self.douyin_cookies_path}")
            # Instagram cookies支持（用于预先获取信息）
            if "instagram.com" in url.lower():
                if (
                    hasattr(self, 'instagram_cookies_path') and
                    self.instagram_cookies_path and 
                    os.path.exists(self.instagram_cookies_path)
                ):
                    info_opts["cookiefile"] = self.instagram_cookies_path
                    logger.info(f"🍪 预先获取信息阶段使用Instagram cookies: {self.instagram_cookies_path}")
                else:
                    logger.warning("⚠️ Instagram预先获取信息：cookies未配置，可能导致获取失败")
            logger.info("🔍 步骤2: 开始提取视频信息...")
            # 使用异步执行器来添加超时控制
            loop = asyncio.get_running_loop()

            def extract_video_info():
                with yt_dlp.YoutubeDL(info_opts) as ydl:
                    logger.info("📡 正在从平台获取视频数据...")
                    return ydl.extract_info(url, download=False)

            # 设置30秒超时
            try:
                info = await asyncio.wait_for(
                    loop.run_in_executor(None, extract_video_info), timeout=60.0
                )
                logger.info(f"✅ 视频信息获取完成，数据类型: {type(info)}")

                video_id = info.get("id")
                title = info.get("title")
                # 清理标题中的非法字符
                if title:
                    title = self._sanitize_filename(title)
                else:
                    title = self._sanitize_filename(video_id)
                logger.info(f"📝 视频标题: {title}")
                logger.info(f"🆔 视频ID: {video_id}")
            except asyncio.TimeoutError:
                logger.error("❌ 获取视频信息超时（60秒）")
                return {
                    "success": False,
                    "error": "获取视频信息超时（60秒），请检查网络连接或稍后重试。",
                }
        except Exception as e:
            logger.error(f"❌ 无法预先获取视频信息: {e}")
            # 如果预先获取信息失败，提供一个回退方案
            title = self._sanitize_filename(str(int(time.time())))
            logger.info(f"📝 使用时间戳作为标题: {title}")
        # 2. 根据平台和获取到的信息构造精确的输出模板
        if self.is_youtube_url(url):
            # 检查是否为音频模式，如果是则使用music子目录
            if hasattr(self, 'bot') and hasattr(self.bot, 'youtube_audio_mode') and self.bot.youtube_audio_mode:
                # 音频模式：使用YouTube/music目录
                music_path = download_path / "music"
                music_path.mkdir(exist_ok=True)  # 确保music目录存在
                if hasattr(self, 'bot') and hasattr(self.bot, 'youtube_id_tags') and self.bot.youtube_id_tags:
                    outtmpl = str(music_path.absolute() / f"{title}[%(id)s].%(ext)s")
                else:
                    outtmpl = str(music_path.absolute() / f"{title}.%(ext)s")
                logger.info("🎵 音频模式：文件将保存到YouTube/music目录")
            else:
                # 默认视频模式：使用YouTube根目录
                if hasattr(self, 'bot') and hasattr(self.bot, 'youtube_id_tags') and self.bot.youtube_id_tags:
                    outtmpl = str(download_path.absolute() / f"{title}[%(id)s].%(ext)s")
                else:
                    outtmpl = str(download_path.absolute() / f"{title}.%(ext)s")
        elif self.is_x_url(url):
            outtmpl = str(download_path.absolute() / f"{title}.%(ext)s")
        else:  # 其他平台
            # Instagram专用文件命名优化
            if "instagram.com" in url.lower():
                optimized_title = self._optimize_instagram_filename(title)
                outtmpl = str(download_path.absolute() / f"{optimized_title}.%(ext)s")
                logger.info(f"🎨 Instagram优化文件名: {optimized_title}")
            else:
                outtmpl = str(download_path.absolute() / f"{title}.%(ext)s")
        # 添加明显的outtmpl日志
        logger.info(f"🔧 [SINGLE_VIDEO] outtmpl 绝对路径: {outtmpl}")
        logger.info(f"📁 下载路径: {download_path}")
        logger.info(f"📝 输出模板: {outtmpl}")
        logger.info("🔍 步骤3: 配置下载选项...")

        # 🎯 Instagram专用检测和配置（必须在格式设置之前）
        if "instagram.com" in url.lower():
            logger.info("🎯 Instagram检测：设置最高质量格式选择")
            
            # 检查是否有 Instagram 下载器可用
            if hasattr(self, 'instagram_downloader') and self.instagram_downloader:
                logger.info("📱 使用专门的 Instagram 下载器")
                # 使用最高质量格式选择
                format_spec = "bestvideo+bestaudio/bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio[ext=m4a]/best[height>=1080]/best"
                merge_format = "mp4"
            else:
                logger.info("📱 使用 yt-dlp 处理 Instagram")
                # 使用最高质量格式选择
                format_spec = "bestvideo+bestaudio/bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio[ext=m4a]/best[height>=1080]/best"
                merge_format = "mp4"
            
            # 检查并应用Instagram cookies
            if (
                hasattr(self, 'instagram_cookies_path') and 
                self.instagram_cookies_path and 
                os.path.exists(self.instagram_cookies_path)
            ):
                logger.info(f"🍪 Instagram将使用cookies: {self.instagram_cookies_path}")
            else:
                logger.warning("⚠️ 检测到Instagram链接但未设置cookies文件")
                logger.warning("💡 Instagram大部分内容需要登录才能访问")
                if hasattr(self, 'instagram_cookies_path') and self.instagram_cookies_path:
                    logger.warning(f"⚠️ Instagram cookies文件不存在: {self.instagram_cookies_path}")
                else:
                    logger.warning("⚠️ 未设置INSTAGRAM_COOKIES环境变量")
                logger.warning("📝 请设置INSTAGRAM_COOKIES环境变量指向cookies文件")
        # 根据YouTube音频模式设置format
        elif self.is_youtube_url(url) and hasattr(self, 'bot') and hasattr(self.bot, 'youtube_audio_mode') and self.bot.youtube_audio_mode:
            # YouTube音频模式：优先下载最高码率的MP3格式
            format_spec = "bestaudio[ext=mp3]/bestaudio[acodec=mp3]/bestaudio"
            merge_format = "mp3"
            logger.info("🎵 启用YouTube音频模式，优先下载最高码率MP3")
        else:
            # 默认视频模式 - 为不同平台设置不同的格式选择策略
            if self.is_bilibili_url(url):
                # B站专用格式选择策略
                format_spec = self._get_bilibili_best_format()
                logger.info("🎯 检测到B站URL，使用4K优先格式策略")
                logger.info(f"🔧 设置的格式字符串: {format_spec}")
                
                # 检查B站会员状态
                member_status = self.check_bilibili_member_status()
                logger.info(f"🔍 B站会员状态: {member_status['message']}")
                
                # 调试B站格式
                try:
                    debug_result = self.debug_bilibili_formats(url)
                    if debug_result["success"]:
                        max_height = debug_result["max_height"]
                        logger.info(f"🔍 B站视频最高分辨率: {max_height}p")
                        if max_height >= 2160:
                            logger.info("🎉 该视频支持4K下载（需要B站大会员）")
                            logger.info("💡 提示：要下载4K，需要B站大会员并正确设置cookies")
                        elif max_height >= 1440:
                            logger.info("✅ 该视频支持2K下载（需要B站大会员）")
                            logger.info("💡 提示：要下载2K，需要B站大会员并正确设置cookies")
                        elif max_height >= 1080:
                            logger.info("✅ 该视频支持1080p下载（需要B站会员）")
                            logger.info("💡 提示：要下载1080p，需要B站大会员并正确设置cookies")
                        elif max_height >= 720:
                            logger.info(f"✅ 该视频支持 {max_height}p 下载（非会员最高质量）")
                        else:
                            logger.warning(f"⚠️ 该视频最高分辨率仅 {max_height}p")
                except Exception as e:
                    logger.warning(f"调试B站格式失败: {e}")
            elif self.is_youtube_url(url):
                # YouTube专用格式选择策略 - 明确优先4K
                format_spec = "bestvideo[height>=2160]+bestaudio/bestvideo[height>=1440]+bestaudio/bestvideo[height>=1080]+bestaudio/bestvideo+bestaudio/best"
                logger.info("🎬 检测到YouTube URL，使用4K优先格式策略 (2160p->1440p->1080p)")
            elif self.is_toutiao_url(url):
                # 头条视频专用格式选择策略
                format_spec = "bestvideo+bestaudio/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[height>=1080]/best"
                logger.info("📰 检测到头条视频 URL，使用高质量格式策略")
            else:
                # 其他平台使用通用格式选择
                format_spec = "bestvideo+bestaudio/bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio[ext=m4a]/best[height>=1080]/best"
                logger.info("🌐 其他平台，使用通用1080p优先格式策略")
            merge_format = "mp4"

        # 根据参数和YouTube Mix播放列表配置决定是否使用noplaylist
        if no_playlist:
            # 强制使用noplaylist（用于Mix播放列表功能关闭时，URL已清理）
            noplaylist_setting = True
            logger.info("🎵 Mix播放列表功能关闭，URL已清理，使用单个视频模式")
        elif (self.is_youtube_url(url) and hasattr(self, 'bot') and
              hasattr(self.bot, 'youtube_mix_playlist') and self.bot.youtube_mix_playlist):
            # 如果开启了Mix播放列表下载，不使用noplaylist，允许下载播放列表
            noplaylist_setting = False
            logger.info("🎵 YouTube Mix播放列表下载已开启，允许下载播放列表内容")
        else:
            # 默认使用noplaylist，只下载单个视频
            noplaylist_setting = True
            logger.info("🎬 使用单个视频模式，不下载播放列表内容")

        ydl_opts = {
            "outtmpl": outtmpl,
            "format": format_spec,
            "merge_output_format": merge_format,
            "noplaylist": noplaylist_setting,
            "nocheckcertificate": True,
            "ignoreerrors": True,
            "logtostderr": True,  # 改为True，确保进度回调正常工作
            "quiet": False,  # 改为False，确保进度回调正常工作
            "no_warnings": False,  # 改为False，确保能看到警告信息
            "default_search": "auto",
            "source_address": "0.0.0.0",
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            },
            "retries": 5,  # 减少重试次数
            "fragment_retries": 5,
            "skip_unavailable_fragments": True,
            "keepvideo": False,
            "prefer_ffmpeg": True,
            "no_download_archive": True,  # 强制重新下载已存在的文件，确保进度回调正常工作
            "force_download": True,  # 强制下载，即使文件已存在
            "socket_timeout": 30,  # 30秒超时
            "progress": True,  # 添加这个参数，确保进度回调被启用
            # 🎯 关键修复：确保进度回调被正确调用
            "progress_hooks": [],  # 先设置为空，后面会添加
            # HLS下载特殊配置
            "hls_use_mpegts": False,  # 使用mp4容器而不是ts
            "hls_prefer_native": True,  # 优先使用原生HLS下载器
            "concurrent_fragment_downloads": 3,  # 并发下载分片数量
            "buffersize": 1024,  # 缓冲区大小
            "http_chunk_size": 10485760,  # 10MB分块大小

            # 🎯 修复：移除extractor_args，让yt-dlp使用默认配置获取最高质量
            # 注释掉extractor_args，避免iOS客户端限制格式选择
            # "extractor_args": {
            #     "youtube": {
            #         "player_client": ["ios", "android", "web"],  # iOS优先，获取最高质量
            #         "player_skip": ["configs"],  # 跳过配置检查
            #         "include_dash_manifest": True,  # 包含DASH清单
            #     }
            # },
        }

        # 如果是音频模式，添加音频转换后处理器
        if self.is_youtube_url(url) and hasattr(self, 'bot') and hasattr(self.bot, 'youtube_audio_mode') and self.bot.youtube_audio_mode:
            ydl_opts["postprocessors"] = [
                {
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '320',  # 最高质量320kbps
                }
            ]
            logger.info("🎵 添加音频转换后处理器：转换为320kbps MP3")

        # 如果是YouTube链接且开启了封面下载，添加缩略图下载选项
        if self.is_youtube_url(url) and hasattr(self, 'bot') and hasattr(self.bot, 'youtube_thumbnail_download') and self.bot.youtube_thumbnail_download:
            ydl_opts["writethumbnail"] = True
            # 添加缩略图格式转换后处理器：WebP -> JPG
            if "postprocessors" not in ydl_opts:
                ydl_opts["postprocessors"] = []
            ydl_opts["postprocessors"].append({
                'key': 'FFmpegThumbnailsConvertor',
                'format': 'jpg',
                'when': 'before_dl'
            })
            logger.info("🖼️ 开启YouTube封面下载（转换为JPG格式）")

        # 如果是YouTube链接且开启了字幕下载，添加字幕下载选项
        if self.is_youtube_url(url) and hasattr(self, 'bot') and hasattr(self.bot, 'youtube_subtitle_download') and self.bot.youtube_subtitle_download:
            ydl_opts["writeautomaticsub"] = True  # 下载自动生成的字幕
            ydl_opts["writesubtitles"] = True     # 下载手动字幕
            ydl_opts["subtitleslangs"] = ["zh", "en"]  # 字幕语言：中文和英文
            ydl_opts["convertsubtitles"] = "srt"  # 转换为SRT格式
            ydl_opts["subtitlesformat"] = "best[ext=srt]/srt/best"  # 优先选择SRT格式
            logger.info("📝 开启YouTube字幕下载（中文、英文，SRT格式）")

        # 如果是B站链接且开启了封面下载，添加缩略图下载选项
        if self.is_bilibili_url(url) and hasattr(self, 'bot') and hasattr(self.bot, 'bilibili_thumbnail_download') and self.bot.bilibili_thumbnail_download:
            ydl_opts["writethumbnail"] = True
            # 添加缩略图格式转换后处理器：WebP -> JPG
            if "postprocessors" not in ydl_opts:
                ydl_opts["postprocessors"] = []
            ydl_opts["postprocessors"].append({
                'key': 'FFmpegThumbnailsConvertor',
                'format': 'jpg',
                'when': 'before_dl'
            })
            logger.info("🖼️ 通用下载器开启B站封面下载（转换为JPG格式）")

        # 针对性地添加 Cookies
        if (
            self.is_x_url(url)
            and self.x_cookies_path
            and os.path.exists(self.x_cookies_path)
        ):
            ydl_opts["cookiefile"] = self.x_cookies_path
            logger.info(f"🍪 为X链接添加cookies: {self.x_cookies_path}")
        elif self.is_x_url(url):
            logger.warning("⚠️ 检测到X链接但未设置cookies文件")
            logger.warning("⚠️ NSFW内容需要登录才能下载")
            if self.x_cookies_path:
                logger.warning(f"⚠️ X cookies文件不存在: {self.x_cookies_path}")
            else:
                logger.warning("⚠️ 未设置X_COOKIES环境变量")
            logger.warning("💡 请设置X_COOKIES环境变量指向cookies文件路径")
        if (
            self.is_youtube_url(url)
            and self.youtube_cookies_path
            and os.path.exists(self.youtube_cookies_path)
        ):
            ydl_opts["cookiefile"] = self.youtube_cookies_path
            logger.info(f"🍪 为YouTube链接添加cookies: {self.youtube_cookies_path}")
        if (
            self.is_bilibili_url(url)
            and self.b_cookies_path
            and os.path.exists(self.b_cookies_path)
        ):
            ydl_opts["cookiefile"] = self.b_cookies_path
            logger.info(f"🍪 为B站链接添加cookies: {self.b_cookies_path}")
        if (
            self.is_douyin_url(url)
            and self.douyin_cookies_path
            and os.path.exists(self.douyin_cookies_path)
        ):
            ydl_opts["cookiefile"] = self.douyin_cookies_path
            logger.info(f"🍪 为抖音链接添加cookies: {self.douyin_cookies_path}")
        elif self.is_douyin_url(url):
            logger.warning("⚠️ 检测到抖音链接但未设置cookies文件")
            if self.douyin_cookies_path:
                logger.warning(f"⚠️ 抖音cookies文件不存在: {self.douyin_cookies_path}")
            else:
                logger.warning("⚠️ 未设置DOUYIN_COOKIES环境变量")
        
        # Instagram cookies在前面已经检测过了，这里只需要应用
        if "instagram.com" in url.lower():
            if (
                hasattr(self, 'instagram_cookies_path') and
                self.instagram_cookies_path and 
                os.path.exists(self.instagram_cookies_path)
            ):
                ydl_opts["cookiefile"] = self.instagram_cookies_path
                logger.info(f"🍪 为Instagram链接应用cookies: {self.instagram_cookies_path}")
            else:
                logger.warning("⚠️ Instagram链接：cookies未配置或文件不存在")
            
            # 如果有专门的 Instagram 下载器，使用它来处理
            if hasattr(self, 'instagram_downloader') and self.instagram_downloader:
                logger.info("📱 使用专门的 Instagram 下载器处理")
                try:
                    # 创建进度回调函数
                    async def instagram_progress_callback(text):
                        if message_updater:
                            try:
                                if asyncio.iscoroutinefunction(message_updater):
                                    await message_updater(text)
                                else:
                                    message_updater(text)
                            except Exception as e:
                                logger.warning(f"Instagram 进度回调失败: {e}")
                    
                    # 调用 Instagram 下载器
                    result = await self.instagram_downloader.download_post(
                        url, 
                        str(download_path), 
                        instagram_progress_callback
                    )
                    
                    if result.get("success"):
                        logger.info(f"✅ Instagram 下载成功: {result}")
                        # 查找下载的文件
                        files = result.get("files", [])
                        if files:
                            # 返回第一个文件作为主要结果
                            main_file = files[0]
                            file_path = Path(main_file.get("path", ""))
                            if file_path.exists():
                                return {
                                    "success": True,
                                    "file_path": str(file_path),
                                    "title": title,
                                    "platform": "instagram",
                                    "files": files,
                                    "total_size": result.get("total_size", 0),
                                    "files_count": result.get("files_count", 0)
                                }
                        
                        return {
                            "success": True,
                            "platform": "instagram",
                            "message": "Instagram 内容下载完成",
                            "result": result
                        }
                    else:
                        logger.warning(f"⚠️ Instagram 下载器失败，回退到 yt-dlp: {result.get('error')}")
                        # 继续使用 yt-dlp 处理
                except Exception as e:
                    logger.error(f"❌ Instagram 下载器异常，回退到 yt-dlp: {e}")
                    # 继续使用 yt-dlp 处理
            
        # 添加代理
        if self.proxy_host:
            ydl_opts["proxy"] = self.proxy_host

        # 添加弹幕下载选项
        ydl_opts = self._add_danmaku_options(ydl_opts, url)

        # 3. 设置进度回调
        logger.info("🔍 步骤3: 设置进度回调...")
        progress_data = {"final_filename": None, "lock": threading.Lock()}

        # 使用增强版的 single_video_progress_hook，包含完整的进度显示逻辑
        # 🔧 修复：安全检查 message_updater 是否是增强版进度回调函数
        logger.info(f"🔍 [PROGRESS_SETUP] message_updater类型: {type(message_updater)}")
        logger.info(f"🔍 [PROGRESS_SETUP] status_message: {status_message}")
        logger.info(f"🔍 [PROGRESS_SETUP] context: {context}")
        
        if callable(message_updater) and hasattr(message_updater, '__name__') and message_updater.__name__ == 'enhanced_progress_callback':
            # 如果是增强版进度回调，直接使用它返回的 progress_hook
            logger.info("🔍 [PROGRESS_SETUP] 使用增强版进度回调")
            try:
                progress_hook = message_updater(progress_data)
            except Exception as e:
                logger.error(f"调用增强版进度回调失败: {e}")
                # 回退到标准的 single_video_progress_hook，传递 status_message 和 context
                progress_hook = single_video_progress_hook(message_updater, progress_data, status_message, context)
        else:
            # 否则使用标准的 single_video_progress_hook，传递 status_message 和 context
            logger.info("🔍 [PROGRESS_SETUP] 使用标准进度回调")
            progress_hook = single_video_progress_hook(message_updater, progress_data, status_message, context)

        ydl_opts['progress_hooks'] = [progress_hook]
        logger.info("✅ 进度回调已设置")
        # 4. 运行下载
        logger.info("🔍 步骤4: 开始下载视频（设置60秒超时）...")

        def run_download():
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    logger.info("🚀 开始下载视频...")
                    
                    # 获取视频信息
                    try:
                        info = ydl.extract_info(url, download=False)
                        title = info.get('title', '未知标题')
                        logger.info(f"📺 视频标题: {title}")
                    except Exception as e:
                        logger.warning(f"⚠️ 获取视频信息失败: {e}")
                    
                    # 开始下载
                    ydl.download([url])
                return True
            except KeyboardInterrupt:
                # 🎯 关键修复：处理用户取消
                logger.info("🚫 下载被用户取消")
                if progress_data and isinstance(progress_data, dict):
                    progress_data["error"] = "下载已被用户取消"
                return False
            except Exception as e:
                error_message = str(e)
                logger.error(f"❌ 下载失败: {error_message}")
                if progress_data and isinstance(progress_data, dict):
                    progress_data["error"] = error_message
                return False

        # 设置60秒超时用于下载
        try:
            success = await asyncio.wait_for(
                loop.run_in_executor(None, run_download), timeout=600.0  # 增加到10分钟
            )
        except asyncio.TimeoutError:
            logger.error("❌ 视频下载超时（10分钟）")
            return {
                "success": False,
                "error": "视频下载超时，请检查网络连接或稍后重试。",
            }
        if not success:
            error = progress_data.get("error", "下载器在执行时发生未知错误") if progress_data and isinstance(progress_data, dict) else "下载器在执行时发生未知错误"
            return {"success": False, "error": error}
        # 5. 查找文件并返回结果
        logger.info("🔍 步骤5: 查找下载的文件...")
        time.sleep(1)  # 等待文件系统同步

        # 使用单视频文件查找方法
        final_file_path = self.single_video_find_downloaded_file(download_path, progress_data, title, url)



        # 处理最终文件
        if final_file_path and os.path.exists(final_file_path):
            logger.info("🔍 步骤6: 获取媒体信息...")
            media_info = self.get_media_info(final_file_path)

            # 安全地获取文件大小
            try:
                file_size_bytes = os.path.getsize(final_file_path)
                size_mb = file_size_bytes / (1024 * 1024)
            except (OSError, TypeError):
                size_mb = 0.0

            logger.info("🎉 视频下载任务完成!")
            return {
                "success": True,
                "filename": os.path.basename(final_file_path),
                "full_path": final_file_path,
                "size_mb": size_mb,
                "platform": self.get_platform_name(url),
                "download_path": str(download_path),
                "resolution": media_info.get("resolution", "未知"),
                "abr": media_info.get("bit_rate"),
                "title": title,
            }
        else:
            return {
                "success": False,
                "error": "下载完成但无法在文件系统中找到最终文件。",
            }



    async def _download_youtube_channel_playlists(
        self, channel_url: str, download_path: Path, message_updater=None, status_message=None, loop=None
    ) -> Dict[str, Any]:
        """下载YouTube频道的所有播放列表"""
        logger.info(f"🎬 开始下载YouTube频道播放列表: {channel_url}")
        logger.info(f"📁 下载路径: {download_path}")
        # 移除调试日志

        # 确保事件循环正确设置
        try:
            import asyncio
            self._main_loop = asyncio.get_running_loop()
            logger.info(f"✅ 成功设置事件循环: {self._main_loop}")
        except Exception as e:
            logger.warning(f"⚠️ 无法获取事件循环: {e}")
            self._main_loop = None



        # YouTube频道播放列进度管理器 - 专门用于跟踪YouTube频道播放列表下载的总体进度
        global_progress = {
            "total_playlists": 0,
            "completed_playlists": 0,
            "total_videos": 0,
            "completed_videos": 0,
            "total_size_mb": 0,
            "downloaded_size_mb": 0,
            "channel_name": "",
            "start_time": time.time()
        }

        try:
            # 更新状态消息
            if message_updater:
                try:
                    if asyncio.iscoroutinefunction(message_updater):
                        await message_updater("🔍 正在获取频道信息...")
                    else:
                        message_updater("🔍 正在获取频道信息...")
                except Exception as e:
                    logger.warning(f"更新状态消息失败: {e}")
            logger.info("🔍 步骤1: 准备获取频道信息...")
            # 获取频道信息 - 添加超时控制
            info_opts = {
                "quiet": True,
                "extract_flat": True,
                "ignoreerrors": True,
                "socket_timeout": 30,  # 30秒超时
                "retries": 8,  # 增加重试次数以提高断点续传成功率
                "fragment_retries": 8,
                # 确保只提取播放列表，不提取单个视频
                "playlistend": None,  # 不限制播放列表长度
                "playliststart": 1,   # 从第一个开始
            }
            if self.proxy_host:
                info_opts["proxy"] = self.proxy_host
                logger.info(f"🌐 使用代理: {self.proxy_host}")
            if self.youtube_cookies_path and os.path.exists(self.youtube_cookies_path):
                info_opts["cookiefile"] = self.youtube_cookies_path
                logger.info(f"🍪 使用YouTube cookies: {self.youtube_cookies_path}")
            logger.info("🔍 步骤2: 开始提取频道信息（设置30秒超时）...")
            # 使用异步执行器来添加超时控制
            loop = asyncio.get_running_loop()

            def extract_channel_info():
                logger.info("📡 正在从YouTube获取频道数据...")
                with yt_dlp.YoutubeDL(info_opts) as ydl:
                    logger.info("🔗 开始网络请求...")
                    result = ydl.extract_info(channel_url, download=False)
                    logger.info(f"📊 网络请求完成，结果类型: {type(result)}")
                    return result

            # 设置30秒超时
            try:
                if message_updater:
                    try:
                        if asyncio.iscoroutinefunction(message_updater):
                            await message_updater("⏳ 正在连接YouTube服务器...")
                        else:
                            message_updater("⏳ 正在连接YouTube服务器...")
                    except Exception as e:
                        logger.warning(f"更新状态消息失败: {e}")
                info = await asyncio.wait_for(
                    loop.run_in_executor(None, extract_channel_info), timeout=60.0
                )
                logger.info(f"✅ 频道信息获取完成，数据类型: {type(info)}")
                if message_updater:
                    try:
                        if asyncio.iscoroutinefunction(message_updater):
                            await message_updater("✅ 频道信息获取成功，正在分析...")
                        else:
                            message_updater("✅ 频道信息获取成功，正在分析...")
                    except Exception as e:
                        logger.warning(f"更新状态消息失败: {e}")
            except asyncio.TimeoutError:
                logger.error("❌ 获取频道信息超时（30秒）")
                if message_updater:
                    try:
                        if asyncio.iscoroutinefunction(message_updater):
                            await message_updater(
                                "❌ 获取频道信息超时，请检查网络连接或稍后重试。"
                            )
                        else:
                            message_updater(
                                "❌ 获取频道信息超时，请检查网络连接或稍后重试。"
                            )
                    except Exception as e:
                        logger.warning(f"更新状态消息失败: {e}")
                return {
                    "success": False,
                    "error": "获取频道信息超时，请检查网络连接或稍后重试。",
                }
            logger.info("🔍 步骤3: 检查频道信息结构...")
            if not info:
                logger.error("❌ 频道信息为空")
                if message_updater:
                    try:
                        if asyncio.iscoroutinefunction(message_updater):
                            await message_updater("❌ 无法获取频道信息。")
                        else:
                            message_updater("❌ 无法获取频道信息。")
                    except Exception as e:
                        logger.warning(f"更新状态消息失败: {e}")
                return {"success": False, "error": "无法获取频道信息。"}
            if "entries" not in info:
                logger.warning("❌ 频道信息中没有找到 'entries' 字段")
                logger.info(
                    f"📊 频道信息包含的字段: {list(info.keys()) if isinstance(info, dict) else '非字典类型'}"
                )
                if message_updater:
                    try:
                        if asyncio.iscoroutinefunction(message_updater):
                            await message_updater("❌ 此频道主页未找到任何播放列表。")
                        else:
                            message_updater("❌ 此频道主页未找到任何播放列表。")
                    except Exception as e:
                        logger.warning(f"更新状态消息失败: {e}")
                return {"success": False, "error": "此频道主页未找到任何播放列表。"}
            entries = info.get("entries", [])
            logger.info(f"📊 找到 {len(entries)} 个条目")
            if not entries:
                logger.warning("❌ 频道条目列表为空")
                if message_updater:
                    try:
                        if asyncio.iscoroutinefunction(message_updater):
                            await message_updater("❌ 此频道主页未找到任何播放列表。")
                        else:
                            message_updater("❌ 此频道主页未找到任何播放列表。")
                    except Exception as e:
                        logger.warning(f"更新状态消息失败: {e}")
                return {"success": False, "error": "此频道主页未找到任何播放列表。"}
            logger.info("🔍 步骤4: 分析频道条目...")
            if message_updater:
                try:
                    if asyncio.iscoroutinefunction(message_updater):
                        await message_updater(f"🔍 正在分析 {len(entries)} 个频道条目...")
                    else:
                        message_updater(f"🔍 正在分析 {len(entries)} 个频道条目...")
                except Exception as e:
                    logger.warning(f"更新状态消息失败: {e}")

            # 统计不同类型的条目
            type_counts = {}
            playlist_entries = []

            for i, entry in enumerate(entries):
                if entry:
                    entry_type = entry.get("_type", "unknown")
                    entry_id = entry.get("id", "no_id")
                    entry_title = entry.get("title", "no_title")
                    entry_url = entry.get("url", "")

                    # 统计类型
                    type_counts[entry_type] = type_counts.get(entry_type, 0) + 1

                    logger.info(
                        f"  📋 条目 {i + 1}: 类型={entry_type}, ID={entry_id}, 标题={entry_title[:50]}..."
                    )

                    # 严格过滤：只处理真正的播放列表，忽略单个视频
                    if entry_type == "playlist":
                        playlist_entries.append(entry)
                        logger.info(f"    ✅ 识别为播放列表")
                    elif entry_type == "url" and "playlist?list=" in entry_url:
                        playlist_entries.append(entry)
                        logger.info(f"    ✅ 识别为播放列表URL")
                    elif entry_type == "video":
                        # 明确忽略单个视频，避免下载频道主页上的视频
                        logger.info(f"    ⏭️ 跳过单个视频（只下载播放列表）")
                    else:
                        logger.info(f"    ⏭️ 跳过非播放列表条目（类型: {entry_type}）")
                else:
                    logger.warning(f"  ⚠️ 条目 {i + 1} 为空")

            # 输出统计信息
            logger.info(f"📊 条目类型统计: {type_counts}")
            logger.info(f"📊 过滤结果: 总条目 {len(entries)} 个，播放列表 {len(playlist_entries)} 个")
            logger.info(f"📊 总共找到 {len(playlist_entries)} 个播放列表")

            if not playlist_entries:
                logger.warning("❌ 没有找到任何播放列表")
                if message_updater:
                    try:
                        if asyncio.iscoroutinefunction(message_updater):
                            await message_updater("❌ 频道中没有找到任何播放列表。")
                        else:
                            message_updater("❌ 频道中没有找到任何播放列表。")
                    except Exception as e:
                        logger.warning(f"更新状态消息失败: {e}")
                return {"success": False, "error": "频道中没有找到任何播放列表。"}

            logger.info("🔍 步骤5: 创建频道目录...")
            channel_name = re.sub(
                r'[\\/:*?"<>|]', "_", info.get("uploader", "Unknown Channel")
            ).strip()
            # YouTube频道目录不包含ID，只使用频道名称
            channel_path = download_path / channel_name
            channel_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"📁 频道目录: {channel_path}")

            logger.info("🔍 步骤6: 开始下载播放列表...")
            if message_updater:
                try:
                    if asyncio.iscoroutinefunction(message_updater):
                        await message_updater(
                            f"🎬 开始下载 {len(playlist_entries)} 个播放列表..."
                        )
                    else:
                        message_updater(
                            f"🎬 开始下载 {len(playlist_entries)} 个播放列表..."
                        )
                except Exception as e:
                    logger.warning(f"更新状态消息失败: {e}")

            # 初始化全局进度数据
            global_progress["total_playlists"] = len(playlist_entries)
            global_progress["channel_name"] = channel_name

            # 计算总视频数（如果可能的话）
            total_video_count = 0
            for entry in playlist_entries:
                if entry and "video_count" in entry:
                    total_video_count += entry.get("video_count", 0)

            # 如果无法从API获取视频数量，设置为-1表示需要动态计算
            if total_video_count == 0:
                logger.info("📊 无法从API获取视频数量，将在下载过程中动态计算")
                global_progress["total_videos"] = -1  # 使用-1表示需要动态计算
            else:
                global_progress["total_videos"] = total_video_count

            logger.info(f"📊 全局进度初始化: {global_progress['total_playlists']} 个播放列表, {global_progress['total_videos']} 个视频")

            downloaded_playlists = []
            playlist_stats = []  # 存储每个播放列表的统计信息

            for i, entry in enumerate(playlist_entries, 1):
                playlist_id = entry.get("id")
                playlist_title = entry.get("title", f"Playlist_{playlist_id}")
                logger.info(
                    f"🎬 开始下载第 {i}/{len(playlist_entries)} 个播放列表: {playlist_title}"
                )
                logger.info(f"    📋 播放列表ID: {playlist_id}")

                # 先检查播放列表是否已完整下载
                check_result = self._check_playlist_already_downloaded(playlist_id, channel_path)

                if message_updater:
                    try:
                        if asyncio.iscoroutinefunction(message_updater):
                            if check_result.get("already_downloaded", False):
                                await message_updater(
                                    f"✅ 检查第 {i}/{len(playlist_entries)} 个播放列表：{playlist_title} (已完整下载)"
                                )
                            else:
                                await message_updater(
                                    f"📥 正在下载第 {i}/{len(playlist_entries)} 个播放列表：{playlist_title}"
                                )
                        else:
                            if check_result.get("already_downloaded", False):
                                message_updater(
                                    f"✅ 检查第 {i}/{len(playlist_entries)} 个播放列表：{playlist_title} (已完整下载)"
                                )
                            else:
                                message_updater(
                                    f"📥 正在下载第 {i}/{len(playlist_entries)} 个播放列表：{playlist_title}"
                                )
                    except Exception as e:
                        logger.warning(f"更新状态消息失败: {e}")

                # 创建播放列表专用的进度回调
                playlist_progress_data = {
                    "playlist_index": i,
                    "total_playlists": len(playlist_entries),
                    "playlist_title": playlist_title,
                    "current_video": 0,
                    "total_videos": 0,
                    "downloaded_videos": 0,
                }

                def create_playlist_progress_callback(progress_data):
                    last_update = {"percent": -1, "time": 0, "text": ""}
                    import time as _time



                    def escape_num(text):
                        # 转义MarkdownV2特殊字符，包括小数点
                        if not isinstance(text, str):
                            text = str(text)
                        escape_chars = [
                            "_",
                            "*",
                            "[",
                            "]",
                            "(",
                            ")",
                            "~",
                            "`",
                            ">",
                            "#",
                            "+",
                            "-",
                            "=",
                            "|",
                            "{",
                            "}",
                            ".",
                            "!",
                        ]
                        for char in escape_chars:
                            text = text.replace(char, "\\" + char)
                        return text

                    def progress_callback(d):
                        # 强制日志，确保能看到进度回调被调用
                        logger.info(f"🔍 [PROGRESS_CALLBACK] 被调用: status={d.get('status')}, filename={d.get('filename', 'N/A')}")

                        if d.get("status") == "downloading":
                            logger.info(f"🔍 YouTube播放列表进度回调: status={d.get('status')}, filename={d.get('filename', 'N/A')}")
                            # 修正当前视频序号为本播放列表的当前下载视频序号/总数
                            cur_idx = (
                                d.get("playlist_index")
                                or d.get("info_dict", {}).get("playlist_index")
                                or 1
                            )
                            total_idx = (
                                d.get("playlist_count")
                                or d.get("info_dict", {}).get("n_entries")
                                or (progress_data.get("total_videos") if progress_data and isinstance(progress_data, dict) else 0)
                                or 1
                            )
                            if progress_data and isinstance(progress_data, dict):
                                progress_text = (
                                    f"📥 正在下载第{escape_num(progress_data['playlist_index'])}/{escape_num(progress_data['total_playlists'])}个播放列表：{escape_num(progress_data['playlist_title'])}\n\n"
                                    f"📺 当前视频: {escape_num(cur_idx)}/{escape_num(total_idx)}\n"
                                )
                            else:
                                progress_text = f"📺 当前视频: {escape_num(cur_idx)}/{escape_num(total_idx)}\n"
                            percent = 0
                            if d.get("filename"):
                                filename = os.path.basename(d.get("filename", ""))
                                total_bytes = d.get("total_bytes") or d.get(
                                    "total_bytes_estimate", 0
                                )
                                downloaded_bytes = d.get("downloaded_bytes", 0)
                                speed_bytes_s = d.get("speed", 0)
                                eta_seconds = d.get("eta", 0)
                                if total_bytes and total_bytes > 0:
                                    downloaded_mb = downloaded_bytes / (1024 * 1024)
                                    total_mb = total_bytes / (1024 * 1024)
                                    speed_mb_s = (
                                        speed_bytes_s / (1024 * 1024)
                                        if speed_bytes_s
                                        else 0
                                    )
                                    percent = int(downloaded_bytes * 100 / total_bytes)
                                    bar = self._make_progress_bar(percent)
                                    try:
                                        minutes, seconds = divmod(int(eta_seconds), 60)
                                        eta_str = f"{minutes:02d}:{seconds:02d}"
                                    except (ValueError, TypeError):
                                        eta_str = "未知"
                                    downloaded_mb_str = f"{downloaded_mb:.2f}"
                                    total_mb_str = f"{total_mb:.2f}"
                                    speed_mb_s_str = f"{speed_mb_s:.2f}"
                                    percent_str = f"{percent:.1f}"
                                    progress_text += (
                                        f"📝 文件: {escape_num(filename)}\n"
                                        f"💾 大小: {escape_num(downloaded_mb_str)}MB / {escape_num(total_mb_str)}MB\n"
                                        f"⚡ 速度: {escape_num(speed_mb_s_str)}MB/s\n"
                                        f"⏳ 预计剩余: {escape_num(eta_str)}\n"
                                        f"📊 进度: {bar} {escape_num(percent_str)}%"
                                    )
                                else:
                                    downloaded_mb = (
                                        downloaded_bytes / (1024 * 1024)
                                        if downloaded_bytes > 0
                                        else 0
                                    )
                                    speed_mb_s = (
                                        speed_bytes_s / (1024 * 1024)
                                        if speed_bytes_s
                                        else 0
                                    )
                                    downloaded_mb_str = f"{downloaded_mb:.2f}"
                                    speed_mb_s_str = f"{speed_mb_s:.2f}"
                                    progress_text += (
                                        f"📝 文件: {escape_num(filename)}\n"
                                        f"💾 大小: {escape_num(downloaded_mb_str)}MB\n"
                                        f"⚡ 速度: {escape_num(speed_mb_s_str)}MB/s\n"
                                        f"📊 进度: 下载中..."
                                    )
                            now = _time.time()
                            # 参考renlixing.py：每5%进度变化或每1秒更新一次
                            if (abs(percent - last_update["percent"]) >= 5) or (now - last_update["time"] > 1):
                                if progress_text != last_update["text"]:
                                    # 更新进度消息
                                    logger.info(f"🔄 更新进度消息: percent={percent}%")
                                last_update["percent"] = percent
                                last_update["time"] = now
                                last_update["text"] = progress_text
                                import asyncio

                                # 移除调试日志，直接处理进度更新

                                # 🎯 智能 TG 消息更新：从 message_updater 中提取 TG 对象
                                tg_updated = False

                                # 方法1：如果直接传递了 TG 对象，优先使用
                                if status_message and loop:
                                    try:
                                        def fix_markdown_v2(text):
                                            # 简化版本：移除了粗体标记，直接转义所有特殊字符
                                            text = text.replace('\\', '')
                                            special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
                                            for char in special_chars:
                                                text = text.replace(char, f'\\{char}')
                                            return text

                                        fixed_text = fix_markdown_v2(progress_text)
                                        future = asyncio.run_coroutine_threadsafe(
                                            status_message.edit_text(fixed_text, parse_mode=None),
                                            loop
                                        )
                                        future.result(timeout=3.0)
                                        tg_updated = True
                                    except:
                                        try:
                                            clean_text = progress_text.replace('\\', '')
                                            future = asyncio.run_coroutine_threadsafe(
                                                status_message.edit_text(clean_text),
                                                loop
                                            )
                                            future.result(timeout=3.0)
                                            tg_updated = True
                                        except:
                                            tg_updated = False
                                else:
                                    tg_updated = False

                                # 方法3：修复 message_updater 调用
                                if not tg_updated and message_updater:
                                    try:
                                        # 🔧 修复：创建一个包装函数，让 message_updater 能处理字符串
                                        def fixed_message_updater(text):
                                            """修复的消息更新器，能处理字符串类型的进度"""
                                            # 从 message_updater 的闭包中提取必要的对象
                                            if hasattr(message_updater, '__closure__') and message_updater.__closure__:
                                                for cell in message_updater.__closure__:
                                                    try:
                                                        value = cell.cell_contents
                                                        # 找到 TG 消息对象
                                                        if hasattr(value, 'edit_text') and hasattr(value, 'chat_id'):
                                                            status_msg = value
                                                            # 找到事件循环
                                                            for cell2 in message_updater.__closure__:
                                                                try:
                                                                    value2 = cell2.cell_contents
                                                                    if hasattr(value2, 'run_until_complete'):
                                                                        event_loop = value2
                                                                        # 直接更新 TG 消息
                                                                        def fix_markdown_v2(text):
                                                                            text = text.replace('\\', '')
                                                                            special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
                                                                            for char in special_chars:
                                                                                text = text.replace(char, f'\\{char}')
                                                                            return text

                                                                        try:
                                                                            fixed_text = fix_markdown_v2(text)
                                                                            future = asyncio.run_coroutine_threadsafe(
                                                                                status_msg.edit_text(fixed_text, parse_mode=None),
                                                                                event_loop
                                                                            )
                                                                            future.result(timeout=3.0)
                                                                            return True
                                                                        except:
                                                                            # 降级到普通文本
                                                                            clean_text = text.replace('\\', '')
                                                                            future = asyncio.run_coroutine_threadsafe(
                                                                                status_msg.edit_text(clean_text),
                                                                                event_loop
                                                                            )
                                                                            future.result(timeout=3.0)
                                                                            return True
                                                                except:
                                                                    continue
                                                    except:
                                                        continue

                                            # 如果提取失败，调用原函数（但这会失败）
                                            logger.warning(f"⚠️ 无法从 message_updater 提取 TG 对象，尝试原调用")
                                            return False

                                        # 使用修复的函数
                                        if not fixed_message_updater(progress_text):
                                            logger.warning(f"⚠️ 修复的 message_updater 失败")

                                    except Exception as e:
                                        logger.error(f"❌ 调用修复的 message_updater 失败: {e}")

                                if not tg_updated and not message_updater:
                                    logger.warning(f"⚠️ 没有可用的消息更新方法")
                        elif d.get("status") == "finished":
                            if progress_data and isinstance(progress_data, dict):
                                progress_data["downloaded_videos"] += 1
                                logger.info(
                                    f"✅ 播放列表 {progress_data['playlist_title']} 第 {progress_data['downloaded_videos']} 个视频下载完成"
                                )

                            # 监控文件合并状态
                            if 'filename' in d:
                                filename = d['filename']
                                if filename.endswith('.part'):
                                    logger.warning(f"⚠️ 文件合并可能失败: {filename}")
                                else:
                                    logger.info(f"✅ 文件下载并合并成功: {filename}")

                    return progress_callback

                # 下载播放列表
                logger.info(f"🎬 开始下载播放列表 {i}/{len(playlist_entries)}: {playlist_title}")
                progress_callback = create_playlist_progress_callback(playlist_progress_data)
                logger.info(f"🔧 创建进度回调函数: {type(progress_callback)}")
                logger.info(f"🔧 进度回调函数是否为None: {progress_callback is None}")
                logger.info(f"🔧 message_updater是否为None: {message_updater is None}")
                result = await self._download_youtube_playlist_with_progress(
                    playlist_id,
                    channel_path,
                    progress_callback,
                )

                if result.get("success"):
                    downloaded_playlists.append(
                        result.get("playlist_title", playlist_title)
                    )

                    # 更新完成状态消息
                    if message_updater:
                        try:
                            if asyncio.iscoroutinefunction(message_updater):
                                if result.get("already_downloaded", False):
                                    await message_updater(
                                        f"✅ 第 {i}/{len(playlist_entries)} 个播放列表：{playlist_title} (已存在)"
                                    )
                                else:
                                    await message_updater(
                                        f"✅ 第 {i}/{len(playlist_entries)} 个播放列表：{playlist_title} (下载完成)"
                                    )
                            else:
                                if result.get("already_downloaded", False):
                                    message_updater(
                                        f"✅ 第 {i}/{len(playlist_entries)} 个播放列表：{playlist_title} (已存在)"
                                    )
                                else:
                                    message_updater(
                                        f"✅ 第 {i}/{len(playlist_entries)} 个播放列表：{playlist_title} (下载完成)"
                                    )
                        except Exception as e:
                            logger.warning(f"更新完成状态消息失败: {e}")

                    # 获取视频数量，如果result中没有，则通过扫描目录计算
                    video_count = result.get("video_count", 0)
                    if video_count == 0:
                        # 备用方法：扫描播放列表目录计算实际文件数量
                        playlist_path = Path(result.get("download_path", ""))
                        if playlist_path.exists():
                            video_files = (
                                list(playlist_path.glob("*.mp4"))
                                + list(playlist_path.glob("*.mkv"))
                                + list(playlist_path.glob("*.webm"))
                            )
                            video_count = len(video_files)
                            logger.info(f"📊 通过扫描目录计算播放列表 '{playlist_title}' 的集数: {video_count}")

                    playlist_stats.append(
                        {
                            # 优先使用result中的播放列表标题，如果没有则使用playlist_title
                            "title": result.get("playlist_title", playlist_title),
                            "video_count": video_count,
                            "download_path": result.get("download_path", ""),
                            "total_size_mb": result.get("total_size_mb", 0),
                            "resolution": result.get("resolution", "未知"),
                            # 添加PART文件统计信息
                            "success_count": result.get("success_count", video_count),
                            "part_count": result.get("part_count", 0),
                        }
                    )
                    # 更新全局进度
                    global_progress["completed_playlists"] += 1
                    logger.info(f"    ✅ 播放列表 '{playlist_title}' 下载成功，集数: {video_count}")
                else:
                    error_msg = result.get("error", "未知错误")
                    logger.error(
                        f"    ❌ 播放列表 '{playlist_title}' 下载失败: {error_msg}"
                    )

            logger.info(
                f"📊 下载完成统计: {len(downloaded_playlists)}/{len(playlist_entries)} 个播放列表成功"
            )
            if not downloaded_playlists:
                logger.error("❌ 所有播放列表都下载失败了")
                if message_updater:
                    try:
                        if asyncio.iscoroutinefunction(message_updater):
                            await message_updater("❌ 频道中的所有播放列表都下载失败了。")
                        else:
                            message_updater("❌ 频道中的所有播放列表都下载失败了。")
                    except Exception as e:
                        logger.warning(f"更新状态消息失败: {e}")
                return {"success": False, "error": "频道中的所有播放列表都下载失败了。"}
            logger.info("🎉 频道播放列表下载任务完成!")

            # 构建详细的完成统计信息
            total_videos = sum(stat["video_count"] for stat in playlist_stats)
            total_size_mb = sum(stat["total_size_mb"] for stat in playlist_stats)

            # 按先获取下载列表的文件查找逻辑：根据下载列表中的文件名精确查找
            downloaded_files = []
            for stat in playlist_stats:
                playlist_path = Path(stat["download_path"])
                if playlist_path.exists():
                    # 先获取该播放列表的下载信息，然后根据文件名精确查找
                    try:
                        # 获取播放列表信息以获取预期的文件名列表
                        info_opts = {
                            "quiet": True,
                            "extract_flat": True,
                            "ignoreerrors": True,
                        }
                        if self.proxy_host:
                            info_opts["proxy"] = self.proxy_host
                        if self.youtube_cookies_path and os.path.exists(
                            self.youtube_cookies_path
                        ):
                            info_opts["cookiefile"] = self.youtube_cookies_path

                        # 从播放列表路径中提取playlist_id - 改进版本
                        playlist_id = ""
                        path_name = playlist_path.name

                        # 尝试从方括号中提取完整的播放列表ID
                        if path_name.startswith("[") and path_name.endswith("]"):
                            playlist_id = path_name[1:-1]  # 移除方括号
                            logger.info(f"🔍 从路径提取播放列表ID: {playlist_id}")
                        else:
                            # 回退方案：从下划线分割
                            playlist_id = (
                                path_name.split("_")[-1]
                                if "_" in path_name
                                else ""
                            )
                            logger.info(f"🔍 从下划线分割提取播放列表ID: {playlist_id}")

                        if not playlist_id:
                            # 如果无法从路径提取，尝试从stat中获取
                            playlist_id = stat.get("playlist_id", "")
                            logger.info(f"🔍 从stat获取播放列表ID: {playlist_id}")

                        if playlist_id:
                            with yt_dlp.YoutubeDL(info_opts) as ydl:
                                playlist_info = ydl.extract_info(
                                    f"https://www.youtube.com/playlist?list={playlist_id}",
                                    download=False,
                                )
                                entries = playlist_info.get("entries", [])

                                # 根据下载列表中的条目查找对应的文件
                                for i, entry in enumerate(entries, 1):
                                    if entry:
                                        # 构造预期的文件名 - 修复版本
                                        title = entry.get("title", f"Video_{i}")

                                        # 更准确的文件名处理，保持与yt-dlp一致
                                        # 1. 只移除真正有问题的后缀模式（不移除｜符号）
                                        clean_title = re.sub(r'#.*$', '', title)  # 只移除#后的内容

                                        # 2. 清理文件系统不支持的特殊字符，但保留｜符号
                                        # yt-dlp通常只清理真正有问题的字符
                                        safe_title = re.sub(r'[\\/:*?"<>]', "", clean_title)

                                        # 3. 限制长度（但不要太短，避免截断重要信息）
                                        safe_title = safe_title.strip()[:80]  # 增加到80字符

                                        expected_filename = f"{i:02d}. {safe_title}.mp4"

                                        # 精确查找该文件
                                        expected_file_path = (
                                            playlist_path / expected_filename
                                        )
                                        if expected_file_path.exists():
                                            file_size = (
                                                expected_file_path.stat().st_size
                                                / (1024 * 1024)
                                            )  # MB
                                            downloaded_files.append(
                                                {
                                                    "filename": expected_filename,
                                                    "path": str(expected_file_path),
                                                    "size_mb": file_size,
                                                    "playlist": stat["title"],
                                                    "video_title": title,
                                                }
                                            )
                                            logger.info(
                                                f"✅ 找到文件: {expected_filename} ({file_size:.2f}MB)")
                                        else:
                                            # 如果精确匹配失败，尝试智能模糊匹配
                                            logger.info(f"🔍 精确匹配失败，尝试智能模糊匹配: {expected_filename}")

                                            # 多种匹配策略
                                            found_file = None

                                            # 策略1: 按编号匹配（最宽松）
                                            matching_files = list(playlist_path.glob(f"{i:02d}.*"))
                                            if not matching_files:
                                                matching_files = list(playlist_path.glob(f"{i}.*"))

                                            if matching_files:
                                                found_file = matching_files[0]
                                                logger.info(f"✅ 通过编号匹配找到文件: {found_file.name}")
                                            else:
                                                # 策略2: 按标题关键词匹配
                                                # 提取标题的前几个关键词
                                                title_words = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', title)
                                                if title_words and len(title_words) >= 2:
                                                    # 使用前两个关键词搜索
                                                    keyword1 = title_words[0][:10]  # 限制长度
                                                    keyword2 = title_words[1][:10] if len(title_words) > 1 else ""

                                                    for file_path in playlist_path.glob("*.mp4"):
                                                        if keyword1 in file_path.name and (not keyword2 or keyword2 in file_path.name):
                                                            found_file = file_path
                                                            logger.info(f"✅ 通过关键词匹配找到文件: {found_file.name}")
                                                            break

                                            if found_file:
                                                # 找到匹配的文件
                                                file_size = (
                                                    found_file.stat().st_size
                                                    / (1024 * 1024)
                                                )  # MB
                                                downloaded_files.append(
                                                    {
                                                        "filename": found_file.name,
                                                        "path": str(found_file),
                                                        "size_mb": file_size,
                                                        "playlist": stat["title"],
                                                        "video_title": title,
                                                    }
                                                )
                                                logger.info(
                                                    f"✅ 通过智能匹配找到文件: {found_file.name} ({file_size:.2f}MB)"
                                                )
                                            else:
                                                logger.warning(
                                                    f"⚠️ 模糊匹配也未找到文件，编号: {i}, 标题: {safe_title}"
                                                )
                    except Exception as e:
                        logger.warning(f"⚠️ 获取播放列表信息失败 (ID: {playlist_id}): {e}")
                        logger.info(f"💡 这通常是因为播放列表已被删除或设为私有，不影响已下载的文件")
                        logger.info(f"🔄 回退到目录扫描模式来统计文件...")
                        # 如果获取列表失败，回退到扫描目录
                        video_files = (
                            list(playlist_path.glob("*.mp4"))
                            + list(playlist_path.glob("*.mkv"))
                            + list(playlist_path.glob("*.webm"))
                        )
                        for video_file in video_files:
                            file_size = video_file.stat().st_size / (1024 * 1024)  # MB
                            downloaded_files.append(
                                {
                                    "filename": video_file.name,
                                    "path": str(video_file),
                                    "size_mb": file_size,
                                    "playlist": stat["title"],
                                }
                            )

            # 计算总文件大小和PART文件统计
            total_size_mb = sum(stat['total_size_mb'] for stat in playlist_stats)
            total_size_gb = total_size_mb / 1024

            # 计算总的成功和未完成文件数量
            total_success_count = sum(stat.get('success_count', stat.get('video_count', 0)) for stat in playlist_stats)
            total_part_count = sum(stat.get('part_count', 0) for stat in playlist_stats)

            # 计算总计数量和失败数量
            total_video_count = sum(stat.get('video_count', 0) for stat in playlist_stats)
            total_failed_count = total_video_count - total_success_count

            # 格式化总大小显示 - 只显示一个单位
            if total_size_gb >= 1.0:
                total_size_str = f"{total_size_gb:.2f}GB"
            else:
                total_size_str = f"{total_size_mb:.2f}MB"

            # 计算成功率
            if total_video_count > 0:
                success_rate = (total_success_count / total_video_count) * 100
            else:
                success_rate = 0.0

            # 构建完成消息
            completion_text = (
                f"📺 YouTube频道播放列表下载完成\n\n"
                f"📺 频道: {channel_name}\n"
                f"📊 播放列表数量: {len(downloaded_playlists)}\n\n"
                f"已下载的播放列表:\n\n"
            )

            for i, stat in enumerate(playlist_stats, 1):
                completion_text += (
                    f"    {i}. {stat['title']} ({stat['video_count']} 集)\n"
                )

            # 构建下载统计信息
            stats_text = f"总计: {total_video_count} 个\n✅ 成功: {total_success_count} 个\n❌ 失败: {total_failed_count} 个\n📊成功率: {success_rate:.1f}%"

            if total_part_count > 0:
                stats_text += f"\n⚠️ 未完成: {total_part_count} 个"
                stats_text += f"\n💡 提示: 发现未完成文件，可能需要重新下载"

            # 添加统计信息、总大小和保存位置（在文件总大小前加空行）
            completion_text += (
                f"\n📊 下载统计:\n{stats_text}\n\n"
                f"💾 文件总大小: {total_size_str}\n"
                f"📂 保存位置: {channel_path}"
            )

            if message_updater:
                try:
                    if asyncio.iscoroutinefunction(message_updater):
                        await message_updater(completion_text)
                    else:
                        message_updater(completion_text)
                except Exception as e:
                    logger.warning(f"更新状态消息失败: {e}")

            return {
                "success": True,
                "is_channel": True,
                "channel_title": channel_name,
                    "download_path": str(channel_path),
                    "playlists_downloaded": downloaded_playlists,
                    "playlist_stats": playlist_stats,
                    "total_videos": total_videos,
                    "total_size_mb": total_size_mb,
                    "downloaded_files": downloaded_files,
                }

        except Exception as e:
            logger.error(f"❌ YouTube频道播放列表下载失败: {e}")
            import traceback

            logger.error(f"详细错误信息: {traceback.format_exc()}")
            if message_updater:
                try:
                    if asyncio.iscoroutinefunction(message_updater):
                        await message_updater(f"❌ 下载失败: {str(e)}")
                    else:
                        message_updater(f"❌ 下载失败: {str(e)}")
                except Exception as e2:
                    logger.warning(f"更新状态消息失败: {e2}")
            return {"success": False, "error": str(e)}

    def smart_download_bilibili(
        self, url: str, download_path: str, progress_callback=None, auto_playlist=False
    ):
        """智能下载B站视频，支持单视频、分集、合集"""
        import re
        import subprocess
        import os
        import threading
        import asyncio
        from pathlib import Path

        logger.info(f"🎬 开始智能下载B站视频: {url}")
        logger.info(f"📁 下载路径: {download_path}")
        logger.info(f"🔄 自动下载全集: {auto_playlist}")

        # 保存原始工作目录
        original_cwd = os.getcwd()
        logger.info(f"📁 原始工作目录: {original_cwd}")

        try:
            # 检查是否为B站用户列表URL
            is_list, uid, list_id = self.is_bilibili_list_url(url)
            if is_list:
                logger.info(f"📋 检测到B站用户列表: UID={uid}, ListID={list_id}")

                # 使用BV号循环法下载用户列表
                bv_list = self.get_bilibili_list_videos(uid, list_id)
                if not bv_list:
                    return {"status": "failure", "error": "无法获取用户列表视频信息"}

                logger.info(f"📋 获取到 {len(bv_list)} 个视频")

                # 获取列表标题
                try:
                    list_info = self.get_bilibili_list_info(uid, list_id)
                    playlist_title = list_info.get("title", f"BilibiliList-{list_id}")
                except BaseException:
                    playlist_title = f"BilibiliList-{list_id}"
                safe_playlist_title = re.sub(
                    r'[\\/:*?"<>|]', "_", playlist_title
                ).strip()
                final_download_path = Path(download_path) / safe_playlist_title
                final_download_path.mkdir(parents=True, exist_ok=True)
                logger.info(f"📁 为合集创建下载目录: {final_download_path}")
                # 使用yt-dlp print记录文件名的方案（与多P下载保持一致）
                success_count = 0
                downloaded_files = []  # 记录实际下载的文件信息

                for idx, (bv, title) in enumerate(bv_list, 1):
                    safe_title = re.sub(r'[\\/:*?"<>|]', "", title)[:60]
                    # 使用绝对路径构建输出模板
                    outtmpl = str(
                        final_download_path / f"{idx:02d}. {safe_title}.%(ext)s"
                    )

                    # 更新下载进度显示
                    if progress_callback:
                        progress_callback({
                            'status': 'downloading',
                            'filename': f'{idx:02d}. {safe_title}',
                            '_percent_str': f'{idx}/{len(bv_list)}',
                            '_eta_str': f'第{idx}个，共{len(bv_list)}个',
                            'info_dict': {'title': title}
                        })

                    # 1. 先用yt-dlp print获取实际文件名
                    video_url = f"https://www.bilibili.com/video/{bv}"
                    cmd_print = [
                        "yt-dlp", "--print", "filename", "-o", outtmpl, video_url
                    ]

                    try:
                        print_result = subprocess.run(cmd_print, capture_output=True, text=True, cwd=str(final_download_path))
                        if print_result.returncode == 0:
                            full_expected_path = print_result.stdout.strip()
                            # 只保留文件名部分，不包含路径
                            expected_filename = os.path.basename(full_expected_path)
                            logger.info(f"📝 预期文件名: {expected_filename}")
                        else:
                            # 如果print失败，使用构造的文件名
                            expected_filename = f"{idx:02d}. {safe_title}.mp4"
                            logger.warning(f"⚠️ print文件名失败，使用构造文件名: {expected_filename}")
                    except Exception as e:
                        expected_filename = f"{idx:02d}. {safe_title}.mp4"
                        logger.warning(f"⚠️ print文件名异常: {e}，使用构造文件名: {expected_filename}")

                    # 2. 执行下载（使用yt-dlp Python API支持进度回调）
                    # 创建安全的进度回调函数，避免 'NoneType' object is not callable 错误
                    def safe_progress_hook(d):
                        try:
                            if progress_callback and callable(progress_callback):
                                if asyncio.iscoroutinefunction(progress_callback):
                                    # 异步函数处理
                                    try:
                                        loop = asyncio.get_running_loop()
                                        asyncio.run_coroutine_threadsafe(progress_callback(d), loop)
                                    except RuntimeError:
                                        logger.warning("没有运行的事件循环，跳过异步进度回调")
                                else:
                                    # 同步函数，直接调用
                                    progress_callback(d)
                            # 如果progress_callback为None或不可调用，静默忽略
                        except Exception as e:
                            logger.error(f"B站下载进度回调错误: {e}")
                    
                    ydl_opts_single = {
                        'outtmpl': outtmpl,
                        'merge_output_format': 'mp4',
                        'quiet': False,
                        'no_warnings': False,
                        'progress_hooks': [safe_progress_hook],
                        # 🎯 B站4K支持：使用多策略格式选择，优先4K，回退到会员/非会员可用格式
                        'format': self._get_bilibili_best_format(),
                    }

                    # 添加代理和cookies配置
                    if self.proxy_host:
                        ydl_opts_single['proxy'] = self.proxy_host
                if self.b_cookies_path and os.path.exists(self.b_cookies_path):
                    ydl_opts_single['cookiefile'] = self.b_cookies_path

                    logger.info(f"🚀 下载第{idx}个: {bv} - {title}")
                    logger.info(f"📝 文件名模板: {outtmpl}")

                    try:
                        # 使用yt-dlp Python API，支持进度回调
                        with yt_dlp.YoutubeDL(ydl_opts_single) as ydl:
                            ydl.download([video_url])
                        success_count += 1
                        logger.info(f"✅ 第{idx}个下载成功")

                        # 3. 根据预期文件名查找实际文件
                        expected_path = final_download_path / expected_filename
                        if expected_path.exists():
                            size_mb = os.path.getsize(expected_path) / (1024 * 1024)
                            media_info = self.get_media_info(str(expected_path))
                            downloaded_files.append({
                                'filename': expected_filename,
                                'size_mb': size_mb,
                                'resolution': media_info.get('resolution', '未知'),
                                'abr': media_info.get('bit_rate')
                            })
                            logger.info(f"📁 记录文件: {expected_filename} ({size_mb:.1f}MB)")
                        else:
                            logger.warning(f"⚠️ 预期文件不存在: {expected_filename}")
                    except Exception as e:
                        logger.error(f"❌ 第{idx}个下载失败: {e}")

                logger.info(
                    f"🎉 BV号循环法下载完成: {success_count}/{len(bv_list)} 个成功"
                )

                if success_count > 0:
                    # 使用已记录的文件信息（不遍历目录）
                    total_size_mb = sum(file_info['size_mb'] for file_info in downloaded_files)
                    all_resolutions = {file_info['resolution'] for file_info in downloaded_files if file_info['resolution'] != '未知'}

                    filename_list = [info['filename'] for info in downloaded_files]
                    filename_display = '\n'.join([f"  {i+1:02d}. {name}" for i, name in enumerate(filename_list)])
                    resolution_display = ', '.join(sorted(all_resolutions)) if all_resolutions else '未知'

                    logger.info(f"📊 用户列表下载统计: {len(downloaded_files)}个文件, 总大小{total_size_mb:.1f}MB")

                    return {
                        "status": "success",
                        "video_type": "playlist",
                        "count": success_count,
                        "playlist_title": safe_playlist_title,
                        "download_path": str(final_download_path),
                        # 使用预期文件信息，避免目录遍历
                        "is_playlist": True,
                        "file_count": len(downloaded_files),
                        "total_size_mb": total_size_mb,
                        "files": downloaded_files,
                        "platform": "bilibili",
                        "filename": filename_display,
                        "size_mb": total_size_mb,
                        "resolution": resolution_display,
                        "episode_count": len(downloaded_files)
                    }
                else:
                    return {"status": "failure", "error": "用户列表视频全部下载失败"}
            # 下面是原有的B站单视频/合集/分集下载逻辑
            logger.info(f"🔍 正在检查视频类型: {url}")

            # 处理短链接，提取BV号
            original_url = url
            if "b23.tv" in url or "b23.wtf" in url:
                logger.info("🔄 检测到B站短链接，尝试提取BV号...")
                try:
                    # 先获取重定向后的URL
                    temp_opts = {
                        "quiet": True,
                        "no_warnings": True,
                    }
                    with yt_dlp.YoutubeDL(temp_opts) as ydl:
                        temp_info = ydl.extract_info(url, download=False)

                    if temp_info.get("webpage_url"):
                        redirected_url = temp_info["webpage_url"]
                        logger.info(f"🔄 短链接重定向到: {redirected_url}")

                        # 从重定向URL中提取BV号
                        bv_match = re.search(r"BV[0-9A-Za-z]+", redirected_url)
                        if bv_match:
                            bv_id = bv_match.group()
                            # 构造原始链接（不带分P标识）
                            original_url = f"https://www.bilibili.com/video/{bv_id}/"
                            logger.info(f"🔄 提取到BV号: {bv_id}")
                            logger.info(f"🔄 使用原始链接: {original_url}")
                        else:
                            logger.warning("⚠️ 无法从重定向URL中提取BV号")
                    else:
                        logger.warning("⚠️ 短链接重定向失败")
                except Exception as e:
                    logger.warning(f"⚠️ 处理短链接时出错: {e}")

            # 修改检测逻辑，确保能正确识别多P视频
            if auto_playlist:
                # 开启自动下载全集时，强制检测playlist
                check_opts = {
                    "quiet": True,
                    "flat_playlist": True,
                    "extract_flat": True,
                    "print": "%(id)s %(title)s",
                    "noplaylist": False,  # 关键：不阻止playlist检测
                    "yes_playlist": True,  # 关键：允许playlist检测
                    "extract_flat": True,  # 确保提取所有条目
                }
            else:
                # 关闭自动下载全集时，阻止playlist检测
                check_opts = {
                    "quiet": True,
                    "flat_playlist": True,
                    "extract_flat": True,
                    "print": "%(id)s %(title)s",
                    "noplaylist": True,  # 阻止playlist检测
                }

            # 使用处理后的URL进行检测
            with yt_dlp.YoutubeDL(check_opts) as ydl:
                info = ydl.extract_info(original_url, download=False)

            entries = info.get("entries", [])
            count = len(entries) if entries else 1
            logger.info(f"📋 检测到 {count} 个视频")

            # 如果只有一个视频，尝试anthology检测和强制playlist检测
            if count == 1:
                # 特殊检测：使用模拟下载检测anthology
                logger.info("🔍 使用模拟下载检测anthology...")
                anthology_detected = False
                try:
                    # 捕获yt-dlp的输出来检测anthology
                    cmd_simulate = ['yt-dlp', '--simulate', '--verbose', original_url]
                    result = subprocess.run(cmd_simulate, capture_output=True, text=True)
                    output = result.stdout + result.stderr

                    if 'extracting videos in anthology' in output.lower():
                        anthology_detected = True
                        logger.info("✅ 检测到anthology关键词，这是一个合集")
                    else:
                        logger.info("❌ 未检测到anthology关键词")

                except Exception as e:
                    logger.warning(f"⚠️ anthology检测失败: {e}")

                # 如果检测到anthology或开启了auto_playlist，尝试强制检测playlist
                if anthology_detected or auto_playlist:
                    if anthology_detected:
                        logger.info("🔄 检测到anthology，强制使用合集模式")
                    else:
                        logger.info("🔄 开启自动下载全集，尝试强制检测playlist...")

                    force_check_opts = {
                        "quiet": True,
                        "flat_playlist": True,
                        "extract_flat": True,
                        "print": "%(id)s %(title)s",
                        "noplaylist": False,
                        "yes_playlist": True,
                    }

                    try:
                        with yt_dlp.YoutubeDL(force_check_opts) as ydl:
                            force_info = ydl.extract_info(original_url, download=False)
                        force_entries = force_info.get("entries", [])
                        force_count = len(force_entries) if force_entries else 1

                        if force_count > count:
                            logger.info(f"🔄 强制检测成功！检测到 {force_count} 个视频")
                            entries = force_entries
                            count = force_count
                            info = force_info
                        elif anthology_detected:
                            # 检测到anthology，但需要进一步确认是否真的是多集
                            logger.info("🔄 anthology检测成功，但需要确认是否真的是多集")
                            # 不强制设置count，保持原有的检测结果
                            if count <= 1:
                                logger.info("🔍 anthology检测到，但实际只有1集，按单集处理")
                            else:
                                logger.info(f"🔍 anthology检测到，确认有{count}集，按合集处理")
                    except Exception as e:
                        logger.warning(f"⚠️ 强制检测失败: {e}")
                        if anthology_detected:
                            # 如果anthology检测成功但强制检测失败，需要谨慎处理
                            logger.info("🔄 anthology检测成功，但强制检测失败，按实际检测结果处理")
                            # 不强制设置count，保持原有的检测结果
                            if count <= 1:
                                logger.info("🔍 anthology检测到但强制检测失败，且实际只有1集，按单集处理")
                            else:
                                logger.info(f"🔍 anthology检测到，实际有{count}集，按合集处理")
            playlist_title = info.get("title", "Unknown Playlist")
            safe_playlist_title = re.sub(r'[\\/:*?"<>|]', "_", playlist_title).strip()

            if count > 1 and auto_playlist:
                final_download_path = Path(download_path) / safe_playlist_title
                final_download_path.mkdir(parents=True, exist_ok=True)
                logger.info(
                    f"📁 为合集 '{safe_playlist_title}' 创建下载目录: {final_download_path}"
                )
            else:
                final_download_path = Path(download_path)
                logger.info(f"📁 使用默认下载目录: {final_download_path}")
            # 移除 os.chdir() 调用，使用绝对路径

            if count == 1:
                video_type = "single"
                logger.info("🎬 检测到单视频")
            else:
                first_id = entries[0].get("id", "") if entries else ""
                all_same_id = all(
                    entry.get("id", "") == first_id for entry in entries if entry
                )
                if all_same_id:
                    video_type = "episodes"
                    logger.info(f"📺 检测到分集视频，共 {count} 集")
                    logger.info("📋 分集详情:")
                    for i, entry in enumerate(entries, 1):
                        if entry:
                            episode_title = entry.get("title", "unknown")
                            episode_id = entry.get("id", "unknown")
                            logger.info(
                                f"  {i:02d}. {episode_title} (ID: {episode_id})"
                            )
                else:
                    video_type = "playlist"
                    logger.info(f"📚 检测到合集，共 {count} 个视频")
                    logger.info("📋 合集详情:")
                    for i, entry in enumerate(entries, 1):
                        if entry:
                            video_title = entry.get("title", "unknown")
                            video_id = entry.get("id", "unknown")
                            logger.info(f"  {i:02d}. {video_title} (ID: {video_id})")

            # 根据视频类型决定下载策略
            if video_type == "single":
                # smart_download_bilibili 专门处理多P和合集，单视频应该由通用下载器处理
                logger.info("⚠️ smart_download_bilibili 检测到单视频")
                if auto_playlist:
                    logger.info("💡 虽然开启了自动下载全集，但这确实是单视频，建议使用通用下载器")
                else:
                    logger.info("💡 这是单视频，建议使用通用下载器")

                # 返回特殊状态，让调用方知道这是单视频
                return {
                    "status": "single_video",
                    "message": "这是单视频，建议使用通用下载器",
                    "video_type": "single"
                }
            elif video_type == "episodes":
                if auto_playlist:
                    # 自动下载全集 - 直接使用完整标题，不做复杂处理
                    output_template = str(
                        final_download_path / "%(title)s.%(ext)s"
                    )
                    # 添加明显的outtmpl日志
                    logger.info(
                        f"🔧 [BILIBILI_EPISODES] outtmpl 使用完整标题: {output_template}"
                    )

                    # 创建简单的进度回调，不需要重命名
                    def enhanced_progress_callback(d):
                        # 执行原有的进度回调逻辑（显示完整标题）
                        if progress_callback:
                            progress_callback(d)

                    ydl_opts = {
                        "outtmpl": output_template,
                        "merge_output_format": "mp4",
                        "quiet": False,
                        "yes_playlist": True,
                        "extract_flat": False,
                        "progress_hooks": [enhanced_progress_callback],
                        # 🎯 B站4K支持：使用多策略格式选择，优先4K，回退到会员/非会员可用格式
                        "format": self._get_bilibili_best_format(),
                    }
                    logger.info("🔄 自动下载全集模式：将下载所有分P视频")
                else:
                    # 只下载当前分P
                    output_template = str(final_download_path / "%(title)s.%(ext)s")
                    # 添加明显的outtmpl日志
                    logger.info(
                        f"🔧 [BILIBILI_SINGLE_EPISODE] outtmpl 绝对路径: {output_template}"
                    )
                    ydl_opts = {
                        "outtmpl": output_template,
                        "merge_output_format": "mp4",
                        "quiet": False,
                        "noplaylist": True,
                        "progress_hooks": [
                            lambda d: (
                                progress_callback(d) if progress_callback else None
                            )
                        ],
                        # 🎯 B站4K支持：使用多策略格式选择，优先4K，回退到会员/非会员可用格式
                        "format": self._get_bilibili_best_format(),
                    }
                    logger.info("🔄 单P模式：只下载当前分P视频")
            else:  # playlist - 和多P下载一样简单
                # 对于合集，直接使用yt-dlp播放列表功能（和多P下载一样）
                logger.info(f"🔧 检测到合集，使用yt-dlp播放列表功能下载")
                logger.info(f"   - 视频数量: {count}")

                # 使用和多P下载完全相同的逻辑，B站不使用ID标签
                output_template = str(
                    final_download_path / "%(playlist_index)s. %(title)s.%(ext)s"
                )
                logger.info(f"🔧 [BILIBILI_PLAYLIST] outtmpl 绝对路径: {output_template}")

                # 使用增强版进度回调来生成详细的进度显示格式
                progress_data = {
                    "final_filename": None,
                    "lock": threading.Lock(),
                    "downloaded_files": [],  # 添加下载文件列表
                    "expected_files": []     # 添加预期文件列表
                }

                # 检查 progress_callback 是否是增强版进度回调函数
                if callable(progress_callback) and progress_callback.__name__ == 'enhanced_progress_callback':
                    # 如果是增强版进度回调，直接使用它返回的 progress_hook
                    progress_hook = progress_callback(progress_data)
                else:
                    # 否则使用标准的 single_video_progress_hook
                    progress_hook = single_video_progress_hook(message_updater=progress_callback, progress_data=progress_data, status_message=status_message, context=context)

                ydl_opts = {
                    "outtmpl": output_template,
                    "merge_output_format": "mp4",
                    "quiet": False,
                    "yes_playlist": True,
                    "extract_flat": False,
                    "progress_hooks": [progress_hook],
                    # 🎯 B站4K支持：使用多策略格式选择，优先4K，回退到会员/非会员可用格式
                    "format": self._get_bilibili_best_format(),
                }
                logger.info("🔄 合集模式：将下载所有合集视频")

            # 对于单视频和分集视频，使用yt-dlp下载
            if video_type in ["single", "episodes"]:
                # 添加代理和cookies配置
                if self.proxy_host:
                    ydl_opts["proxy"] = self.proxy_host
                if self.b_cookies_path and os.path.exists(self.b_cookies_path):
                    ydl_opts["cookiefile"] = self.b_cookies_path
                    logger.info(f"🍪 使用B站cookies: {self.b_cookies_path}")
                else:
                    logger.warning("⚠️ 未设置B站cookies，可能无法下载某些视频")
                    logger.warning("💡 请设置BILIBILI_COOKIES环境变量指向cookies文件")

                # 为B站添加更强的重试和延迟机制
                if self.is_bilibili_url(url):
                    ydl_opts.update({
                        "retries": 10,  # 增加重试次数
                        "fragment_retries": 10,
                        "socket_timeout": 60,  # 增加超时时间
                        "sleep_interval": 2,   # 添加请求间隔
                        "max_sleep_interval": 5,
                        # 添加更详细的错误处理
                        "ignoreerrors": False,  # 不忽略错误，便于调试
                    })
                    logger.info("🔧 为B站链接启用增强重试机制")

                # 添加弹幕下载选项
                ydl_opts = self._add_danmaku_options(ydl_opts, url)

                # 如果是B站链接且开启了封面下载，添加缩略图下载选项
                if hasattr(self, 'bot') and hasattr(self.bot, 'bilibili_thumbnail_download') and self.bot.bilibili_thumbnail_download:
                    ydl_opts["writethumbnail"] = True
                    # 添加缩略图格式转换后处理器：WebP -> JPG
                    if "postprocessors" not in ydl_opts:
                        ydl_opts["postprocessors"] = []
                    ydl_opts["postprocessors"].append({
                        'key': 'FFmpegThumbnailsConvertor',
                        'format': 'jpg',
                        'when': 'before_dl'
                    })
                    logger.info("🖼️ 开启B站封面下载（转换为JPG格式）")

                logger.info(f"🔧 [BILIBILI_DOWNLOAD] 最终ydl_opts: {ydl_opts}")
                logger.info(f"📝 最终输出模板: {output_template}")
                logger.info(f"📁 下载目录: {final_download_path}")

                # 执行下载
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([original_url])

                logger.info("✅ B站视频下载完成")
                logger.info("🎯 使用postprocessor智能文件名，无需重命名")

                # 简化：B站多P下载完成，直接返回成功，文件查找交给目录遍历
                logger.info("🎯 B站多P下载完成，使用目录遍历查找文件")

                return {
                    "status": "success",
                    "video_type": video_type,
                    "count": count,
                    "playlist_title": safe_playlist_title if count > 1 else None,
                    "download_path": str(final_download_path),
                    # 简化：不传递预期文件信息，使用目录遍历
                }

        except Exception as e:
            logger.error(f"❌ B站视频下载失败: {e}")
            return {"status": "failure", "error": str(e)}
        finally:
            # 恢复原始工作目录
            try:
                os.chdir(original_cwd)
                logger.info(f"📁 已恢复工作目录: {original_cwd}")
            except Exception as e:
                logger.warning(f"⚠️ 恢复工作目录失败: {e}")

    def get_bilibili_list_videos(self, uid: str, list_id: str) -> list:
        """
        通过B站API获取用户自定义列表中的视频

        Args:
            uid: 用户ID (如 477348669)
            list_id: 列表ID (如 2111173)

        Returns:
            list: [(bv, title), ...]
        """
        try:
            # B站用户列表API
            api_url = f"https://api.bilibili.com/x/space/fav/season/list"
            params = {
                "season_id": list_id,
                "pn": 1,
                "ps": 20,  # 每页20个
                "jsonp": "jsonp",
            }

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Referer": f"https://space.bilibili.com/{uid}/lists/{list_id}",
            }

            logger.info(f"🔍 获取B站列表API: {api_url}")
            response = requests.get(api_url, params=params, headers=headers, timeout=10, verify=False)
            response.raise_for_status()

            data = response.json()
            if data.get("code") != 0:
                logger.error(f"❌ API返回错误: {data.get('message', '未知错误')}")
                return []

            # 解析视频列表
            videos = []
            archives = data.get("data", {}).get("medias", [])

            for archive in archives:
                bv = archive.get("bvid", "")
                title = archive.get("title", "")
                if bv and title:
                    videos.append((bv, title))
                    logger.info(f"  📺 {bv}: {title}")

            logger.info(f"📦 从API获取到 {len(videos)} 个视频")
            return videos

        except Exception as e:
            logger.error(f"❌ 获取B站列表失败: {e}")
            return []

    def download_bilibili_list_bv_method(
        self, uid: str, list_id: str, download_path: str
    ) -> bool:
        """
        使用BV号循环法下载B站用户自定义列表

        Args:
            uid: 用户ID
            list_id: 列表ID
            download_path: 下载路径

        Returns:
            bool: 下载是否成功
        """
        import subprocess
        import re

        logger.info(f"🔧 使用BV号循环法下载B站列表:")
        logger.info(f"   - 用户ID: {uid}")
        logger.info(f"   - 列表ID: {list_id}")

        # 1. 通过API获取视频列表
        bv_list = self.get_bilibili_list_videos(uid, list_id)

        if not bv_list:
            logger.error("❌ 未找到任何视频")
            return False

        logger.info(f"📦 找到 {len(bv_list)} 个视频，开始逐个下载")

        # 2. 依次下载每个BV号
        success_count = 0
        for idx, (bv, title) in enumerate(bv_list, 1):
            # 清理标题中的非法字符
            safe_title = re.sub(r'[\\/:*?"<>|]', "", title)[:60]
            outtmpl = f"{idx:02d}. {safe_title}.%(ext)s"
            cmd_dl = [
                "yt-dlp",
                "-o",
                outtmpl,
                "--merge-output-format",
                "mp4",
                f"https://www.bilibili.com/video/{bv}",
            ]
            logger.info(f"🚀 下载第{idx}个: {bv} - {title}")
            logger.info(f"📝 文件名模板: {outtmpl}")

            result = subprocess.run(cmd_dl, cwd=download_path)
            if result.returncode == 0:
                success_count += 1
                logger.info(f"✅ 第{idx}个下载成功")
            else:
                logger.error(f"❌ 第{idx}个下载失败")

        logger.info(f"🎉 BV号循环法下载完成: {success_count}/{len(bv_list)} 个成功")
        return success_count > 0

    async def _download_bilibili_ugc_season(
        self, bv_id: str, season_id: str, download_path: Path, message_updater=None
    ) -> Dict[str, Any]:
        """下载B站UGC合集"""
        logger.info(f"🎬 开始下载B站UGC合集: BV={bv_id}, Season={season_id}")

        try:
            # 步骤1: 获取合集信息
            logger.info("🔍 步骤1: 获取UGC合集信息...")

            import requests
            api_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bv_id}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://www.bilibili.com/',
            }

            if message_updater:
                try:
                    import asyncio
                    if asyncio.iscoroutinefunction(message_updater):
                        await message_updater("🔍 正在获取UGC合集信息...")
                    else:
                        message_updater("🔍 正在获取UGC合集信息...")
                except Exception as e:
                    logger.warning(f"更新状态消息失败: {e}")

            try:
                response = requests.get(api_url, headers=headers, timeout=30)
                response.raise_for_status()  # 检查HTTP状态码
                data = response.json()
            except requests.exceptions.HTTPError as e:
                if response.status_code == 404:
                    error_msg = f"视频不存在: BV号 {bv_id} 无效或视频已被删除"
                else:
                    error_msg = f"HTTP请求失败: {e}"
                logger.error(error_msg)
                return {'success': False, 'error': error_msg}
            except requests.exceptions.RequestException as e:
                error_msg = f"网络请求失败: {e}"
                logger.error(error_msg)
                return {'success': False, 'error': error_msg}
            except ValueError as e:
                error_msg = f"响应解析失败: {e}"
                logger.error(error_msg)
                return {'success': False, 'error': error_msg}

            if data.get('code') != 0:
                error_msg = f"获取合集信息失败: {data.get('message', '未知错误')}"
                logger.error(error_msg)
                return {'success': False, 'error': error_msg}

            ugc_season = data.get('data', {}).get('ugc_season')
            if not ugc_season:
                error_msg = "视频不属于UGC合集"
                logger.error(error_msg)
                return {'success': False, 'error': error_msg}

            season_title = ugc_season.get('title', '未知合集')
            logger.info(f"📋 合集标题: {season_title}")

            # 创建合集专用子目录
            safe_season_title = self._sanitize_filename(season_title, max_length=50)
            season_download_path = download_path / safe_season_title
            season_download_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"📁 创建合集目录: {season_download_path}")

            # 步骤2: 提取所有视频
            all_videos = []
            sections = ugc_season.get('sections', [])

            for section in sections:
                episodes = section.get('episodes', [])
                for episode in episodes:
                    video_info = {
                        'bvid': episode.get('bvid'),
                        'title': episode.get('title'),
                        'aid': episode.get('aid'),
                        'cid': episode.get('cid'),
                    }
                    if video_info['bvid']:
                        all_videos.append(video_info)

            if not all_videos:
                error_msg = "合集中没有找到视频"
                logger.error(error_msg)
                return {'success': False, 'error': error_msg}

            logger.info(f"📋 找到 {len(all_videos)} 个视频:")
            for i, video in enumerate(all_videos, 1):
                logger.info(f"  {i:02d}. {video['title']} ({video['bvid']})")

            # 步骤3: 逐个下载视频
            logger.info("🔍 步骤3: 开始逐个下载视频...")

            downloaded_files = []
            success_count = 0
            total_size_mb = 0
            failed_videos = []

            # 创建增强的进度回调函数，用于显示合集下载进度
            def create_ugc_progress_callback(video_index, video_title, total_count):
                """为UGC合集中的每个视频创建专门的进度回调"""
                def ugc_video_progress_hook(d):
                    try:
                        if d.get('status') == 'downloading':
                            downloaded_bytes = d.get('downloaded_bytes', 0)
                            total_bytes = d.get('total_bytes', 0)
                            speed = d.get('speed', 0)
                            eta = d.get('eta', 0)
                            filename = d.get('filename', video_title)

                            if total_bytes and total_bytes > 0:
                                percent = (downloaded_bytes / total_bytes) * 100
                                downloaded_mb = downloaded_bytes / (1024 * 1024)
                                total_mb = total_bytes / (1024 * 1024)
                                speed_mb = speed / (1024 * 1024) if speed else 0

                                # 创建进度条 (20个字符)
                                progress_bar_length = 20
                                # 修复进度条计算：确保至少显示1个实心块当进度>0时
                                if percent > 0:
                                    filled_length = max(1, int(progress_bar_length * percent / 100))
                                else:
                                    filled_length = 0
                                bar = '█' * filled_length + '░' * (progress_bar_length - filled_length)

                                # 格式化ETA
                                if eta and eta > 0:
                                    if eta < 60:
                                        eta_str = f"{int(eta)}秒"
                                    elif eta < 3600:
                                        eta_str = f"{int(eta//60)}分{int(eta%60)}秒"
                                    else:
                                        eta_str = f"{int(eta//3600)}时{int((eta%3600)//60)}分"
                                else:
                                    eta_str = "计算中..."

                                # 构建图片格式的进度消息
                                # 使用上面已经计算好的bar

                                progress_msg = (
                                    f"📥 下载中\n"
                                    f"📝 文件名: {filename}\n"
                                    f"💾 大小: {downloaded_mb:.2f}MB / {total_mb:.2f}MB\n"
                                    f"⚡ 速度: {speed_mb:.2f}MB/s\n"
                                    f"⏳ 预计剩余: {eta_str}\n"
                                    f"📊 进度: {bar} {percent:.1f}%"
                                )

                                # 更新状态消息
                                if message_updater:
                                    try:
                                        import asyncio
                                        if asyncio.iscoroutinefunction(message_updater):
                                            # 对于协程函数，需要在事件循环中运行
                                            try:
                                                loop = asyncio.get_running_loop()
                                                asyncio.run_coroutine_threadsafe(message_updater(progress_msg), loop)
                                            except RuntimeError:
                                                pass  # 如果没有运行的事件循环，跳过
                                        else:
                                            message_updater(progress_msg)
                                    except Exception as e:
                                        logger.debug(f"更新进度消息失败: {e}")

                        elif d.get('status') == 'finished':
                            filename = d.get('filename', '')
                            if filename:
                                logger.info(f"✅ [{video_index}/{total_count}] 下载完成: {filename}")

                                # 显示完成消息
                                complete_msg = (
                                    f"✅ 下载完成 [{video_index}/{total_count}]\n"
                                    f"📝 文件名：{filename}\n"
                                    f"📊 进度：████████████████████ 100.0%"
                                )
                                if message_updater:
                                    try:
                                        import asyncio
                                        if asyncio.iscoroutinefunction(message_updater):
                                            try:
                                                loop = asyncio.get_running_loop()
                                                asyncio.run_coroutine_threadsafe(message_updater(complete_msg), loop)
                                            except RuntimeError:
                                                pass
                                        else:
                                            message_updater(complete_msg)
                                    except Exception as e:
                                        logger.debug(f"更新完成消息失败: {e}")

                    except Exception as e:
                        logger.debug(f"UGC进度回调处理失败: {e}")

                return ugc_video_progress_hook

            for i, video in enumerate(all_videos, 1):
                try:
                    # 显示开始下载的消息 - 使用详细格式
                    start_msg = (
                        f"📥 准备下载 [{i}/{len(all_videos)}]\n"
                        f"📝 文件名：{video['title']}\n"
                        f"💾 大小：获取中...\n"
                        f"⚡ 速度：准备中...\n"
                        f"⏳ 预计剩余：计算中...\n"
                        f"📊 进度：░░░░░░░░░░░░░░░░░░░░ 0.0%"
                    )
                    logger.info(f"🎬 开始下载: {video['title']}")

                    if message_updater:
                        try:
                            import asyncio
                            if asyncio.iscoroutinefunction(message_updater):
                                await message_updater(start_msg)
                            else:
                                message_updater(start_msg)
                        except Exception as e:
                            logger.warning(f"更新状态消息失败: {e}")

                    # 构建单个视频的URL
                    video_url = f"https://www.bilibili.com/video/{video['bvid']}/"

                    # 使用标准的single_video_progress_hook，但添加UGC合集信息
                    import threading
                    progress_data = {"final_filename": None, "lock": threading.Lock()}

                    # 创建UGC专用的消息更新器，在标准进度消息前添加合集信息
                    def ugc_message_updater(msg_or_dict):
                        """UGC专用消息更新器，添加合集信息"""
                        try:
                            if isinstance(msg_or_dict, str):
                                # 字符串消息，直接传递
                                ugc_msg = f"📥 UGC合集 [{i}/{len(all_videos)}]\n{msg_or_dict}"
                                if message_updater:
                                    message_updater(ugc_msg)
                            elif isinstance(msg_or_dict, dict):
                                # 字典消息，传递给原始更新器处理
                                if message_updater:
                                    message_updater(msg_or_dict)
                        except Exception as e:
                            logger.error(f"❌ UGC消息更新器失败: {e}")

                    # 使用标准的single_video_progress_hook
                    progress_callback = single_video_progress_hook(
                        message_updater=ugc_message_updater,
                        progress_data=progress_data,
                        status_message=status_message,
                        context=context
                    )

                    # 使用smart_download_bilibili下载B站视频，获得更好的进度显示
                    # 对于UGC合集，即使是单视频也应该继续下载
                    import asyncio
                    loop = asyncio.get_running_loop()
                    result = await loop.run_in_executor(
                        None,
                        self.smart_download_bilibili_for_ugc,
                        video_url,
                        str(season_download_path),
                        progress_callback,
                        False  # auto_playlist=False，只下载单个视频
                    )

                    # 处理smart_download_bilibili的返回结果
                    if isinstance(result, dict) and result.get('status') == 'success':
                        success_count += 1
                        file_info = {
                            'filename': result.get('filename', ''),
                            'full_path': result.get('download_path', ''),
                            'size_mb': result.get('size_mb', 0),
                            'title': video['title'],
                            'bvid': video['bvid'],
                            'resolution': result.get('resolution', ''),
                            'duration': result.get('duration', ''),
                        }
                        downloaded_files.append(file_info)
                        total_size_mb += result.get('size_mb', 0)

                        success_msg = f"✅ 第 {i}/{len(all_videos)} 个视频下载成功: {result.get('filename', '')}"
                        logger.info(success_msg)

                    elif result is True:
                        # smart_download_bilibili有时返回True表示成功，需要从目录中查找实际文件
                        success_count += 1

                        # 尝试从下载目录中找到实际的文件名
                        actual_filename = None
                        logger.info(f"🔍 查找第{i}个视频的实际文件名，目录: {season_download_path}")
                        try:
                            import os
                            all_files = os.listdir(season_download_path)
                            logger.info(f"📁 目录中的所有文件: {all_files}")

                            video_files = [f for f in all_files if f.endswith(('.mp4', '.mkv', '.avi', '.flv', '.webm'))]
                            logger.info(f"🎬 视频文件: {video_files}")

                            for file in video_files:
                                # 检查文件是否与当前视频相关（简单的标题匹配）
                                if any(word in file for word in video['title'].split()[:3]):
                                    actual_filename = file
                                    logger.info(f"✅ 找到匹配文件: {actual_filename}")
                                    break

                            # 如果没找到匹配的文件，使用最新的视频文件
                            if not actual_filename and video_files:
                                # 按修改时间排序，取最新的
                                video_files.sort(key=lambda x: os.path.getmtime(season_download_path / x), reverse=True)
                                actual_filename = video_files[0]
                                logger.info(f"📊 使用最新文件: {actual_filename}")
                        except Exception as e:
                            logger.warning(f"查找实际文件名失败: {e}")

                        if not actual_filename:
                            actual_filename = f"{video['title']}.mp4"
                            logger.warning(f"⚠️ 未找到实际文件，使用默认名称: {actual_filename}")

                        # 获取文件大小
                        file_size_mb = 0
                        try:
                            file_path = season_download_path / actual_filename
                            if file_path.exists():
                                file_size_mb = file_path.stat().st_size / (1024 * 1024)
                        except Exception as e:
                            logger.debug(f"获取文件大小失败: {e}")

                        # 检测文件分辨率和时长
                        resolution_info = ''
                        duration_info = ''
                        try:
                            file_path = season_download_path / actual_filename
                            if file_path.exists():
                                # 使用现有的get_media_info方法检测视频信息
                                media_info = self.get_media_info(str(file_path))
                                resolution_info = media_info.get('resolution', '')
                                duration_info = media_info.get('duration', '')
                                logger.info(f"🔍 检测到视频信息: 分辨率={resolution_info}, 时长={duration_info}")
                        except Exception as e:
                            logger.debug(f"检测视频信息失败: {e}")

                        file_info = {
                            'filename': actual_filename,
                            'full_path': str(season_download_path / actual_filename),
                            'size_mb': file_size_mb,
                            'title': video['title'],
                            'bvid': video['bvid'],
                            'resolution': resolution_info,
                            'duration': duration_info,
                        }
                        downloaded_files.append(file_info)
                        total_size_mb += file_size_mb

                        success_msg = f"✅ 第 {i}/{len(all_videos)} 个视频下载成功: {actual_filename}"
                        logger.info(success_msg)
                    else:
                        error_msg = f"❌ 第 {i}/{len(all_videos)} 个视频下载失败"
                        if isinstance(result, dict):
                            error_msg += f": {result.get('error', '未知错误')}"
                        logger.error(error_msg)
                        failed_videos.append({
                            'index': i,
                            'title': video['title'],
                            'bvid': video['bvid'],
                            'error': result.get('error', '未知错误') if isinstance(result, dict) else '下载失败'
                        })

                except Exception as e:
                    error_msg = f"❌ 下载第 {i}/{len(all_videos)} 个视频时出错: {e}"
                    logger.error(error_msg)
                    failed_videos.append({
                        'index': i,
                        'title': video['title'],
                        'bvid': video['bvid'],
                        'error': str(e)
                    })

            # 步骤4: 生成详细的下载结果报告
            logger.info("🔍 步骤4: 生成下载结果报告...")

            # 计算总时长和平均文件大小
            total_duration_seconds = 0
            for file_info in downloaded_files:
                duration_str = file_info.get('duration', '')
                if duration_str and ':' in duration_str:
                    try:
                        parts = duration_str.split(':')
                        if len(parts) == 2:  # MM:SS
                            minutes, seconds = map(int, parts)
                            total_duration_seconds += minutes * 60 + seconds
                        elif len(parts) == 3:  # HH:MM:SS
                            hours, minutes, seconds = map(int, parts)
                            total_duration_seconds += hours * 3600 + minutes * 60 + seconds
                    except ValueError:
                        pass

            # 格式化总时长
            if total_duration_seconds > 0:
                hours = total_duration_seconds // 3600
                minutes = (total_duration_seconds % 3600) // 60
                seconds = total_duration_seconds % 60
                if hours > 0:
                    total_duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                else:
                    total_duration_str = f"{minutes:02d}:{seconds:02d}"
            else:
                total_duration_str = "未知"

            # 生成详细的结果报告
            if success_count > 0:
                # 成功下载的统计
                avg_size_mb = total_size_mb / success_count if success_count > 0 else 0

                logger.info("🎬 **视频下载完成**")
                logger.info(f"📋 合集标题: {season_title}")
                logger.info("")
                logger.info("📝 文件名:")

                # 显示文件列表，格式与最终消息一致
                for i, file_info in enumerate(downloaded_files, 1):
                    logger.info(f"  {i:02d}. {file_info['filename']}")

                logger.info("")
                logger.info(f"💾 文件大小: {total_size_mb:.2f} MB")
                logger.info(f"📊 集数: {success_count} 集")

                # 获取分辨率信息 - 使用ffprobe检测实际文件
                resolution_display = "未知"
                logger.info(f"🔍 开始分辨率检测，下载文件数量: {len(downloaded_files) if downloaded_files else 0}")
                logger.info(f"🔍 初始resolution_display值: '{resolution_display}'")

                if downloaded_files:
                    logger.info(f"✅ 有下载文件信息，开始检测分辨率")
                    # 尝试从第一个下载的文件获取分辨率
                    first_file = downloaded_files[0]
                    file_path = first_file.get('full_path', '')
                    logger.info(f"🔍 检测文件路径: {file_path}")

                    import os
                    if file_path and os.path.exists(file_path):
                        logger.info(f"✅ 文件存在，开始检测分辨率")
                        try:
                            logger.info(f"🔍 使用get_media_info检测分辨率: {file_path}")

                            # 使用现有的get_media_info方法
                            media_info = self.get_media_info(file_path)
                            if media_info.get('resolution'):
                                resolution_display = media_info['resolution']
                                logger.info(f"✅ 成功获取分辨率: {resolution_display}")
                                logger.info(f"🔍 resolution_display变量当前值: '{resolution_display}'")
                            else:
                                logger.warning("⚠️ 无法获取分辨率信息")

                        except Exception as e:
                            logger.warning(f"⚠️ ffprobe输出解析失败: {e}")
                        except Exception as e:
                            logger.warning(f"⚠️ 获取分辨率时发生错误: {e}")
                    else:
                        logger.warning(f"⚠️ 文件不存在或路径无效: {file_path}")
                else:
                    logger.warning("⚠️ 没有下载文件信息，无法检测分辨率")

                logger.info(f"📊 最终分辨率值: '{resolution_display}'")
                logger.info(f"🖼️ 分辨率: {resolution_display}")

                logger.info(f"📂 保存位置: {season_download_path}")

                # 显示详细统计信息（仅在日志中）
                logger.info("")
                logger.info("📊 详细统计:")
                logger.info(f"  ✅ 成功: {success_count}/{len(all_videos)} 个视频")
                logger.info(f"  📏 平均大小: {avg_size_mb:.1f}MB")
                logger.info(f"  ⏱️ 总时长: {total_duration_str}")

                if failed_videos:
                    logger.info(f"  ❌ 失败: {len(failed_videos)} 个视频")
                    for failed in failed_videos:
                        logger.warning(f"    - 第{failed['index']}个: {failed['title']} (错误: {failed['error']})")

                # 生成美化的最终状态消息
                logger.info(f"🔍 开始生成最终消息，当前resolution_display值: '{resolution_display}'")
                final_msg = f"🎬 视频下载完成\n\n"
                final_msg += f"📝 文件名:\n"

                # 添加文件列表，按序号排列
                for i, file_info in enumerate(downloaded_files, 1):
                    filename = file_info['filename']
                    final_msg += f"  {i:02d}. {filename}\n"

                # 添加统计信息
                final_msg += f"\n💾 文件大小: {total_size_mb:.2f} MB\n"
                final_msg += f"📊 下载统计:\n"
                final_msg += f"✅ 成功: {success_count} 个\n"

                # 添加分辨率信息到最终消息
                logger.info(f"🔍 添加分辨率到消息，resolution_display值: '{resolution_display}'")
                final_msg += f"🖼️ 分辨率: {resolution_display}\n"
                final_msg += f"📂 保存位置: {season_download_path}"

                logger.info(f"🔍 最终消息生成完成，消息长度: {len(final_msg)} 字符")
                logger.info(f"🔍 最终消息预览: {final_msg[:200]}...")

                if failed_videos:
                    final_msg += f"\n\n❌ 失败: {len(failed_videos)} 个视频"
                    for failed in failed_videos:
                        final_msg += f"\n  - {failed['title']}"

                # 不在这里发送消息，让主程序处理
                logger.info(f"🔍 UGC合集下载完成，返回结果给主程序处理消息")

                return {
                    'success': True,
                    'is_playlist': True,  # 改为True，让主程序处理消息
                    'file_count': success_count,
                    'total_size_mb': total_size_mb,
                    'files': downloaded_files,
                    'platform': 'bilibili',  # 使用标准的bilibili标识
                    'download_path': str(season_download_path),  # 使用合集子目录
                    'base_download_path': str(download_path),    # 保留基础下载路径
                    'season_title': season_title,
                    'season_id': season_id,
                    'failed_count': len(failed_videos),
                    'failed_videos': failed_videos,
                    'total_duration': total_duration_str,
                    'average_size_mb': avg_size_mb,
                    'ugc_season': True,  # 保留UGC合集标识
                    'video_type': 'playlist',  # 标识为播放列表类型
                    'count': success_count,  # 添加count字段
                    'resolution': resolution_display,  # 添加分辨率信息
                }
            else:
                error_msg = f"UGC合集下载失败: 所有 {len(all_videos)} 个视频都下载失败"
                logger.error(error_msg)
                logger.error("失败详情:")
                for failed in failed_videos:
                    logger.error(f"  - 第{failed['index']}个: {failed['title']} (错误: {failed['error']})")

                if message_updater:
                    try:
                        import asyncio
                        if asyncio.iscoroutinefunction(message_updater):
                            await message_updater(f"❌ UGC合集下载失败: 所有视频都下载失败")
                        else:
                            message_updater(f"❌ UGC合集下载失败: 所有视频都下载失败")
                    except Exception as e:
                        logger.warning(f"更新状态消息失败: {e}")

                return {
                    'success': False,
                    'error': error_msg,
                    'failed_videos': failed_videos,
                    'season_title': season_title,
                    'season_id': season_id,
                    'download_path': str(season_download_path),
                    'base_download_path': str(download_path),
                }

        except Exception as e:
            error_msg = f"UGC合集下载过程中出错: {e}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}

    async def _download_bilibili_user_all_videos(
        self, uid: str, download_path: Path, message_updater=None
    ) -> Dict[str, Any]:
        """下载B站UP主的所有视频（参考YouTube频道下载模式）"""
        import re  # 在函数开头导入，确保整个函数都能使用
        import time
        import os

        logger.info(f"🎬 开始下载B站UP主的所有视频: UID={uid}")
        logger.info(f"🔍 message_updater参数: type={type(message_updater)}, callable={callable(message_updater)}")

        try:
            # 步骤1: 使用yt-dlp获取UP主的视频列表
            logger.info("🔍 步骤1: 使用yt-dlp获取UP主的视频列表...")

            if message_updater:
                try:
                    import asyncio
                    if asyncio.iscoroutinefunction(message_updater):
                        await message_updater("🔍 正在获取UP主的视频列表...")
                    else:
                        message_updater("🔍 正在获取UP主的视频列表...")
                except Exception as e:
                    logger.warning(f"更新状态消息失败: {e}")

            # 构建UP主空间URL
            user_space_url = f"https://space.bilibili.com/{uid}"

            # 配置yt-dlp选项，增强对B站的兼容性
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": True,
                "socket_timeout": 120,  # 增加超时时间
                "retries": 10,  # 增加重试次数
                "playlistend": None,  # 不限制，获取所有视频
                "sleep_interval": 2,  # 添加请求间隔
                "max_sleep_interval": 5,
                "sleep_interval_subtitles": 1,
                # 添加更多B站兼容性选项
                "extractor_args": {
                    "bilibili": {
                        "api_version": "app",  # 使用APP API
                    }
                },
                # 添加用户代理
                "http_headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Referer": "https://www.bilibili.com/",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
                    "Accept-Encoding": "gzip, deflate, br",
                }
            }

            if self.proxy_host:
                ydl_opts["proxy"] = self.proxy_host
            if self.b_cookies_path and os.path.exists(self.b_cookies_path):
                ydl_opts["cookiefile"] = self.b_cookies_path
                logger.info(f"🍪 使用B站cookies文件: {self.b_cookies_path}")

                # 检查cookies文件内容
                try:
                    with open(self.b_cookies_path, 'r', encoding='utf-8') as f:
                        cookies_content = f.read()
                        if 'SESSDATA' in cookies_content:
                            logger.info("✅ Cookies文件包含SESSDATA，格式正确")
                        else:
                            logger.warning("⚠️ Cookies文件可能缺少SESSDATA字段")

                        # 检查文件大小
                        file_size = len(cookies_content)
                        logger.info(f"📊 Cookies文件大小: {file_size} 字符")

                except Exception as e:
                    logger.warning(f"⚠️ 无法读取cookies文件内容: {e}")
            else:
                logger.warning("⚠️ 未配置B站cookies，可能无法访问某些内容")

            import yt_dlp

            # 尝试多种方式获取UP主的视频列表
            info = None
            last_error = None

            # 方式1: 直接访问UP主空间
            try:
                logger.info(f"🔍 方式1: 直接访问UP主空间 {user_space_url}")
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(user_space_url, download=False)
                logger.info("✅ 方式1成功")
            except Exception as e:
                last_error = str(e)
                logger.warning(f"❌ 方式1失败: {e}")

                # 方式2: 尝试使用投稿页面
                try:
                    video_url = f"https://space.bilibili.com/{uid}/video"
                    logger.info(f"🔍 方式2: 尝试投稿页面 {video_url}")
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(video_url, download=False)
                    logger.info("✅ 方式2成功")
                except Exception as e2:
                    last_error = str(e2)
                    logger.warning(f"❌ 方式2失败: {e2}")

                    # 方式3: 尝试使用不同的URL格式
                    try:
                        channel_url = f"https://space.bilibili.com/{uid}/channel/series"
                        logger.info(f"🔍 方式3: 尝试频道系列页面 {channel_url}")
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            info = ydl.extract_info(channel_url, download=False)
                        logger.info("✅ 方式3成功")
                    except Exception as e3:
                        last_error = str(e3)
                        logger.warning(f"❌ 方式3失败: {e3}")

                        # 方式4: 降级处理，使用更宽松的配置
                        try:
                            logger.info(f"🔍 方式4: 降级处理，使用更宽松的配置")
                            limited_opts = {
                                "quiet": True,
                                "extract_flat": True,
                                "socket_timeout": 180,
                                "retries": 3,
                                "playlistend": None,  # 不限制，获取所有视频
                                "sleep_interval": 1,  # 减少请求间隔
                            }
                            if self.proxy_host:
                                limited_opts["proxy"] = self.proxy_host
                            if self.b_cookies_path and os.path.exists(self.b_cookies_path):
                                limited_opts["cookiefile"] = self.b_cookies_path

                            with yt_dlp.YoutubeDL(limited_opts) as ydl:
                                info = ydl.extract_info(user_space_url, download=False)
                            logger.info("✅ 方式4成功（宽松配置）")
                        except Exception as e4:
                            last_error = str(e4)
                            logger.error(f"❌ 方式4失败: {e4}")

                            # 方式5: 最后尝试，使用最简单的配置但获取所有视频
                            try:
                                logger.info(f"🔍 方式5: 最简配置尝试（获取所有视频）")
                                simple_opts = {
                                    "quiet": True,
                                    "extract_flat": True,
                                    "playlistend": None,  # 不限制，获取所有视频
                                    "socket_timeout": 120,
                                    "retries": 3,
                                }
                                if self.b_cookies_path and os.path.exists(self.b_cookies_path):
                                    simple_opts["cookiefile"] = self.b_cookies_path

                                with yt_dlp.YoutubeDL(simple_opts) as ydl:
                                    info = ydl.extract_info(user_space_url, download=False)
                                logger.info("✅ 方式5成功（最简模式，获取所有视频）")
                            except Exception as e5:
                                last_error = str(e5)
                                logger.error(f"❌ 方式5失败: {e5}")

                                # 方式6: 如果还是失败，尝试分页获取
                                try:
                                    logger.info(f"🔍 方式6: 分页获取模式")
                                    paginated_opts = {
                                        "quiet": True,
                                        "extract_flat": True,
                                        "playlistend": 500,  # 限制为500个，避免超时
                                        "socket_timeout": 180,
                                        "retries": 2,
                                    }
                                    if self.b_cookies_path and os.path.exists(self.b_cookies_path):
                                        paginated_opts["cookiefile"] = self.b_cookies_path

                                    with yt_dlp.YoutubeDL(paginated_opts) as ydl:
                                        info = ydl.extract_info(user_space_url, download=False)
                                    logger.info("✅ 方式6成功（分页模式）")
                                except Exception as e6:
                                    last_error = str(e6)
                                    logger.error(f"❌ 方式6失败: {e6}")

            if not info:
                error_msg = f"无法获取UP主 {uid} 的视频信息。最后错误: {last_error}"
                logger.error(error_msg)

                # 检查是否是B站限制问题
                if "352" in str(last_error) or "rejected by server" in str(last_error).lower():
                    error_msg += "\n\n💡 建议解决方案:\n1. 配置B站cookies文件\n2. 使用代理服务器\n3. 稍后重试"

                return {'success': False, 'error': error_msg}

            # 获取UP主信息
            uploader_name = info.get('uploader', f'UP主_{uid}')
            uploader_id = info.get('uploader_id', uid)

            # 获取视频列表
            entries = info.get('entries', [])
            if not entries:
                error_msg = f"UP主 {uid} 没有任何视频"
                logger.error(error_msg)
                return {'success': False, 'error': error_msg}

            logger.info(f"📊 找到 {len(entries)} 个视频")

            # 检查是否获取完整
            total_count = info.get('playlist_count') or info.get('_total_count') or len(entries)
            if total_count and total_count > len(entries):
                logger.warning(f"⚠️ 可能未获取完整视频列表: 获取到 {len(entries)} 个，预期 {total_count} 个")
            else:
                logger.info(f"✅ 成功获取完整视频列表: {len(entries)} 个视频")

            if message_updater:
                try:
                    # message_updater是同步函数，直接调用
                    message_updater(f"🔍 正在分析 {len(entries)} 个视频...")
                except Exception as e:
                    logger.warning(f"更新状态消息失败: {e}")

            # 步骤2: 创建UP主专用下载目录（参考YouTube频道模式）
            # 清理UP主名称，移除文件系统不支持的字符
            clean_uploader_name = re.sub(r'[\\/:*?"<>|]', "_", uploader_name).strip()
            user_download_path = download_path / clean_uploader_name
            user_download_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"📁 UP主目录: {user_download_path}")

            # 步骤3: 简化分析：按播放列表分组，但不进行复杂的类型检测
            logger.info("🚀 采用简化播放列表分文件夹模式")
            logger.info("🔍 步骤3: 简单分析播放列表...")

            if message_updater and callable(message_updater):
                try:
                    # message_updater是同步函数，直接调用
                    message_updater(f"🔍 正在分析 {len(entries)} 个视频的播放列表...")
                except Exception as e:
                    logger.warning(f"更新状态消息失败: {e}")
            elif message_updater:
                logger.warning("⚠️ message_updater 不是可调用对象")

            # 增强合集识别：基于URL特征、标题模式和BV号
            playlists = {}
            single_videos = []

            # 用于存储BV号对应的合集信息
            bv_playlists = {}

            for entry in entries:
                if not entry:
                    continue

                video_url = entry.get('url') or entry.get('webpage_url')
                video_title = entry.get('title', '')

                if not video_url:
                    single_videos.append(entry)
                    continue

                # 检查URL中是否有明显的播放列表标识
                playlist_id = None
                playlist_name = "未知播放列表"
                playlist_type = "unknown"

                # 检查UGC合集 (list_id参数)
                if 'list_id=' in video_url:
                    match = re.search(r'list_id=(\d+)', video_url)
                    if match:
                        playlist_id = f"ugc_{match.group(1)}"
                        playlist_name = f"UGC合集_{match.group(1)}"
                        playlist_type = "ugc"

                # 检查多P视频 (p=参数)
                elif '?p=' in video_url or '&p=' in video_url:
                    bv_match = re.search(r'BV([A-Za-z0-9]+)', video_url)
                    if bv_match:
                        bv_id = bv_match.group(1)
                        playlist_id = f"multipart_{bv_id}"
                        # 从标题中提取合集名称
                        if '【' in video_title and '】' in video_title:
                            # 提取【】中的内容作为合集名
                            title_match = re.search(r'【([^】]+)】', video_title)
                            if title_match:
                                playlist_name = title_match.group(1)
                            else:
                                playlist_name = f"多P视频_{bv_id}"
                        else:
                            playlist_name = f"多P视频_{bv_id}"
                        playlist_type = "multipart"

                # 增强：检查标题模式识别合集
                if not playlist_id and video_title:
                    # 检查标题中的合集标识
                    title_patterns = [
                        r'第(\d+)集',           # 第X集
                        r'Part\s*(\d+)',       # Part X
                        r'(\d+)\s*[话話]',     # X话
                        r'第(\d+)章',           # 第X章
                        r'第(\d+)回',           # 第X回
                        r'(\d+)\s*[期期]',     # X期
                        r'第(\d+)课',           # 第X课
                        r'第(\d+)讲',           # 第X讲
                    ]

                    for pattern in title_patterns:
                        match = re.search(pattern, video_title)
                        if match:
                            episode_num = match.group(1)
                            # 提取合集名称（去掉集数部分）
                            clean_title = re.sub(pattern, '', video_title).strip()
                            clean_title = re.sub(r'[【】\[\]\(\)（）]', '', clean_title).strip()

                            if clean_title:
                                # 使用清理后的标题作为合集名
                                playlist_id = f"title_pattern_{clean_title}"
                                playlist_name = clean_title
                                playlist_type = "title_pattern"
                                break

                # 如果通过标题模式识别到合集，检查是否有对应的BV号
                if playlist_id and playlist_type == "title_pattern":
                    bv_match = re.search(r'BV([A-Za-z0-9]+)', video_url)
                    if bv_match:
                        bv_id = bv_match.group(1)
                        # 检查是否有相同BV号的其他视频
                        if bv_id in bv_playlists:
                            # 如果BV号已存在，使用相同的playlist_id
                            playlist_id = bv_playlists[bv_id]
                        else:
                            # 记录这个BV号对应的playlist_id
                            bv_playlists[bv_id] = playlist_id

                if playlist_id:
                    if playlist_id not in playlists:
                        playlists[playlist_id] = {
                            'name': playlist_name,
                            'type': playlist_type,
                            'videos': []
                        }
                    playlists[playlist_id]['videos'].append(entry)
                else:
                    single_videos.append(entry)

            logger.info(f"📊 简单分组结果: {len(playlists)} 个播放列表, {len(single_videos)} 个单独视频")

            # 显示预期的目录结构
            logger.info("📁 预期目录结构:")
            logger.info(f"  📂 UP主目录: {user_download_path}")
            for playlist_id, playlist_info in playlists.items():
                playlist_name = playlist_info['name']
                logger.info(f"    📁 合集: {playlist_name}/")
            if single_videos:
                logger.info(f"    📁 单独视频/")

            # 步骤5: 使用现有下载方法，复用进度显示和完成逻辑
            logger.info("🔍 步骤5: 使用现有下载方法处理各类视频...")

            downloaded_results = []
            total_downloaded = 0
            total_failed = 0
            total_size_mb = 0

            # 处理播放列表（UGC合集、多P视频等）
            playlist_index = 0
            for playlist_id, playlist_info in playlists.items():
                try:
                    playlist_index += 1
                    playlist_name = playlist_info['name']
                    videos = playlist_info['videos']

                    if message_updater:
                        try:
                            initial_msg = f"""📥 正在下载第{playlist_index}/{len(playlists)}个播放列表：{playlist_name}

📺 总视频数: {len(videos)}
📊 状态: 开始下载..."""
                            import asyncio
                            if asyncio.iscoroutinefunction(message_updater):
                                await message_updater(initial_msg)
                            elif callable(message_updater):
                                message_updater(initial_msg)
                        except Exception as e:
                            logger.warning(f"更新状态消息失败: {e}")

                    logger.info(f"🎬 开始处理播放列表: {playlist_name} ({len(videos)} 个视频)")

                    # 为播放列表中的每个视频调用现有的下载方法
                    playlist_downloaded = 0
                    playlist_failed = 0

                    # 创建播放列表目录
                    playlist_path = user_download_path / playlist_name
                    playlist_path.mkdir(parents=True, exist_ok=True)
                    logger.info(f"📁 创建播放列表目录: {playlist_path}")

                    for video_idx, video in enumerate(videos, 1):
                        video_url = video.get('url') or video.get('webpage_url')
                        video_title = video.get('title', '')

                        if video_url:
                            try:
                                logger.info(f"🎬 调用现有下载方法处理视频 {video_idx}/{len(videos)}: {video_url}")
                                logger.info(f"🔍 传递给download_video的message_updater: {type(message_updater)}, callable: {callable(message_updater)}")

                                # 生成更好的文件名
                                clean_title = re.sub(r'[\\/:*?"<>|]', "_", video_title).strip()
                                if playlist_type == "multipart":
                                    # 多P视频使用集数命名
                                    episode_match = re.search(r'p=(\d+)', video_url)
                                    if episode_match:
                                        episode_num = episode_match.group(1)
                                        filename = f"{episode_num:02d}. {clean_title}.mp4"
                                    else:
                                        filename = f"{video_idx:02d}. {clean_title}.mp4"
                                elif playlist_type == "title_pattern":
                                    # 标题模式识别的合集，尝试提取集数
                                    episode_patterns = [
                                        r'第(\d+)集', r'Part\s*(\d+)', r'(\d+)\s*[话話]',
                                        r'第(\d+)章', r'第(\d+)回', r'(\d+)\s*[期期]',
                                        r'第(\d+)课', r'第(\d+)讲'
                                    ]
                                    episode_num = None
                                    for pattern in episode_patterns:
                                        match = re.search(pattern, video_title)
                                        if match:
                                            episode_num = int(match.group(1))
                                            break

                                    if episode_num:
                                        filename = f"{episode_num:02d}. {clean_title}.mp4"
                                    else:
                                        filename = f"{video_idx:02d}. {clean_title}.mp4"
                                else:
                                    # 其他类型使用索引命名
                                    filename = f"{video_idx:02d}. {clean_title}.mp4"

                                logger.info(f"📝 生成文件名: {filename}")



                                # 临时修改下载路径到播放列表目录
                                original_bilibili_path = self.bilibili_download_path
                                self.bilibili_download_path = playlist_path
                                logger.info(f"🔧 临时修改B站下载路径: {self.bilibili_download_path}")

                                try:
                                    # 创建同步进度更新器，兼容yt-dlp的进度回调
                                    def progress_updater(progress_text):
                                        logger.info(f"🔍 播放列表进度更新器被调用: type={type(progress_text)}")

                                        if isinstance(progress_text, str):
                                            # 如果是字符串，直接显示
                                            logger.info(f"🔍 收到字符串消息: {progress_text[:100]}...")
                                            # 对于字符串消息，我们暂时跳过，因为异步调用复杂
                                            logger.info(f"⚠️ 跳过字符串消息的异步调用")
                                        else:
                                            # 如果是字典（yt-dlp进度数据），转换为格式化消息
                                            d = progress_text
                                            logger.info(f"🔍 收到进度字典: status={d.get('status')}, filename={d.get('filename', 'N/A')}")

                                            if d.get("status") == "downloading":
                                                # 控制更新频率
                                                import time
                                                current_time = time.time()
                                                if not hasattr(progress_updater, 'last_update'):
                                                    progress_updater.last_update = 0

                                                if current_time - progress_updater.last_update < 3:  # 3秒更新一次
                                                    return
                                                progress_updater.last_update = current_time
                                                # 获取进度信息
                                                filename = d.get("filename", "未知文件")
                                                if filename:
                                                    filename = os.path.basename(filename)

                                                # 调试：打印所有可用的字段
                                                logger.info(f"🔍 播放列表进度字典所有字段: {list(d.keys())}")
                                                logger.info(f"🔍 播放列表进度字典内容: {d}")

                                                downloaded_bytes = d.get("downloaded_bytes", 0)
                                                total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                                                speed = d.get("speed", 0)

                                                # 调试：打印原始数值
                                                logger.info(f"🔍 播放列表原始数值: downloaded_bytes={downloaded_bytes}, total_bytes={total_bytes}, speed={speed}")

                                                # 格式化大小和速度
                                                downloaded_mb = downloaded_bytes / (1024 * 1024) if downloaded_bytes else 0
                                                total_mb = total_bytes / (1024 * 1024) if total_bytes else 0
                                                speed_mb = speed / (1024 * 1024) if speed else 0

                                                # 计算进度
                                                if total_bytes > 0:
                                                    progress_percent = (downloaded_bytes / total_bytes) * 100
                                                else:
                                                    progress_percent = 0

                                                # 计算预计剩余时间
                                                eta_seconds = d.get("eta", 0)
                                                if eta_seconds and eta_seconds > 0:
                                                    eta_minutes = eta_seconds // 60
                                                    eta_secs = eta_seconds % 60
                                                    eta_str = f"{eta_minutes:02d}:{eta_secs:02d}"
                                                else:
                                                    eta_str = "未知"

                                                # 创建进度条
                                                bar_length = 20
                                                filled_length = int(bar_length * progress_percent / 100)
                                                bar = '█' * filled_length + '░' * (bar_length - filled_length)

                                                # 构建详细的进度消息
                                                progress_text = f"""📥 正在下载第{playlist_index}/{len(playlists)}个播放列表：{playlist_name}

📺 当前视频: {video_idx}/{len(videos)}
📝 文件: {filename}
💾 大小: {downloaded_mb:.2f}MB / {total_mb:.2f}MB
⚡️ 速度: {speed_mb:.2f}MB/s
⏳ 预计剩余: {eta_str}
📊 进度: [{bar}] {progress_percent:.1f}%"""

                                                # 发送进度消息（使用线程安全的方式）
                                                if message_updater and callable(message_updater):
                                                    try:
                                                        import asyncio
                                                        import threading

                                                        # 直接调用同步的message_updater（update_progress），线程安全地编辑TG消息
                                                        try:
                                                            message_updater(progress_text)
                                                            logger.info(f"✅ 播放列表进度消息发送成功")
                                                        except Exception as e:
                                                            logger.warning(f"发送播放列表进度消息失败: {e}")

                                                    except Exception as e:
                                                        logger.warning(f"创建播放列表进度消息线程失败: {e}")

                                    # 创建简化的进度更新器
                                    async def simple_progress_updater(progress_text):
                                        try:
                                            logger.info(f"🔍 [DEBUG] 播放列表simple_progress_updater被调用: type={type(progress_text)}")
                                            logger.info(f"🔍 [DEBUG] 播放列表message_updater状态: {message_updater}, type={type(message_updater)}")

                                            if isinstance(progress_text, str):
                                                # 字符串消息直接发送
                                                if message_updater and callable(message_updater):
                                                    logger.info(f"🔍 [DEBUG] 播放列表准备调用message_updater")
                                                    # message_updater是同步函数，直接调用
                                                    message_updater(progress_text)
                                                    logger.info(f"✅ [DEBUG] 播放列表message_updater调用成功")
                                                else:
                                                    logger.warning(f"⚠️ [DEBUG] 播放列表message_updater不可用: {message_updater}")
                                            else:
                                                # 字典数据处理，转换为进度消息
                                                logger.info(f"🔍 [DEBUG] 播放列表处理字典数据: {progress_text}")

                                                if isinstance(progress_text, dict) and progress_text.get("status") == "downloading":
                                                    d = progress_text

                                                    # 获取进度信息
                                                    filename = d.get("filename", "未知文件")
                                                    if filename:
                                                        filename = os.path.basename(filename)

                                                    downloaded_bytes = d.get("downloaded_bytes", 0)
                                                    total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                                                    speed = d.get("speed", 0)

                                                    # 格式化大小和速度
                                                    downloaded_mb = downloaded_bytes / (1024 * 1024) if downloaded_bytes else 0
                                                    total_mb = total_bytes / (1024 * 1024) if total_bytes else 0
                                                    speed_mb = speed / (1024 * 1024) if speed else 0

                                                    # 计算进度
                                                    if total_bytes > 0:
                                                        progress_percent = (downloaded_bytes / total_bytes) * 100
                                                    else:
                                                        progress_percent = 0

                                                    # 计算预计剩余时间
                                                    eta_seconds = d.get("eta", 0)
                                                    if eta_seconds and eta_seconds > 0:
                                                        if eta_seconds >= 3600:  # 超过1小时
                                                            eta_hours = eta_seconds // 3600
                                                            eta_minutes = (eta_seconds % 3600) // 60
                                                            eta_str = f"{eta_hours}小时{eta_minutes}分钟"
                                                        elif eta_seconds >= 60:  # 超过1分钟
                                                            eta_minutes = eta_seconds // 60
                                                            eta_secs = eta_seconds % 60
                                                            eta_str = f"{eta_minutes}分{eta_secs:02d}秒"
                                                        else:  # 小于1分钟
                                                            eta_str = f"{eta_seconds}秒"
                                                    else:
                                                        eta_str = "未知"

                                                    # 创建进度条（使用你要的格式）
                                                    bar_length = 20
                                                    filled_length = int(bar_length * progress_percent / 100)
                                                    bar = '█' * filled_length + '░' * (bar_length - filled_length)

                                                    # 构建简洁的进度消息（你要的格式）
                                                    progress_text = f"""📥 下载中 ({video_idx}/{len(videos)})
📝 文件名: {filename}
💾 大小: {downloaded_mb:.2f}MB / {total_mb:.2f}MB
⚡️ 速度: {speed_mb:.2f}MB/s
⏳ 预计剩余: {eta_str}
📊 进度: {bar} {progress_percent:.1f}%"""

                                                    # 发送进度消息
                                                    if message_updater and callable(message_updater):
                                                        logger.info(f"🔍 [DEBUG] 播放列表发送实时进度消息")
                                                        try:
                                                            # message_updater是同步函数，直接调用
                                                            logger.info(f"🔍 [DEBUG] 播放列表调用message_updater(dict): {type(message_updater)}")
                                                            message_updater(d)
                                                            logger.info(f"✅ [DEBUG] 播放列表实时进度字典发送成功")
                                                        except Exception as e:
                                                            logger.warning(f"❌ [DEBUG] 播放列表实时进度消息发送失败: {e}")
                                                            logger.warning(f"🔍 [DEBUG] 播放列表message_updater详情: {type(message_updater)}")
                                                            import traceback
                                                            logger.warning(f"🔍 [DEBUG] 播放列表完整错误堆栈: {traceback.format_exc()}")
                                                else:
                                                    logger.info(f"🔍 [DEBUG] 播放列表跳过非下载状态的字典数据: {progress_text.get('status') if isinstance(progress_text, dict) else 'unknown'}")
                                        except Exception as e:
                                            logger.warning(f"播放列表简化进度更新失败: {e}")
                                            logger.warning(f"🔍 [DEBUG] 播放列表异常详情: message_updater={message_updater}, progress_text={progress_text}")

                                    # 调用download_video，直接传递上层的message_updater以使用统一的进度管道
                                    result = await self.download_video(video_url, message_updater if message_updater else None)

                                    # 手动发送进度更新（简化版本）
                                    if message_updater and callable(message_updater):
                                        try:
                                            # 获取文件名
                                            filename = "未知文件"
                                            if result.get('success', False) and result.get('filename'):
                                                filename = os.path.basename(result.get('filename'))

                                            progress_msg = f"""📥 正在下载第{playlist_index}/{len(playlists)}个播放列表：{playlist_name}

📺 当前视频: {video_idx}/{len(videos)}
📝 文件: {filename}
📊 状态: ✅ 下载完成
💾 大小: {result.get('size_mb', 0):.2f} MB"""
                                            # message_updater是同步函数，直接调用
                                            message_updater(progress_msg)
                                            logger.info(f"✅ 手动发送播放列表进度更新成功")
                                        except Exception as e:
                                            logger.warning(f"手动发送播放列表进度更新失败: {e}")

                                    # 发送简洁的进度更新，而不是详细的完成消息
                                    if result.get('success', False) and message_updater and callable(message_updater):
                                        try:
                                            # 只显示简单的进度更新，详细总结在最后显示
                                            progress_text = f"""📥 正在下载第{playlist_index}/{len(playlists)}个播放列表：{playlist_name}

📺 当前视频: {video_idx}/{len(videos)} ✅ 下载完成
📝 文件: {os.path.basename(result.get('filename', '未知文件'))}
💾 大小: {result.get('size_mb', 0):.2f} MB"""
                                            # message_updater是同步函数，直接调用
                                            message_updater(progress_text)
                                            logger.info(f"✅ 播放列表视频进度更新已发送")
                                        except Exception as e:
                                            logger.warning(f"发送播放列表视频进度更新失败: {e}")

                                except Exception as e:
                                    logger.error(f"播放列表视频下载异常: {e}")
                                    if message_updater and callable(message_updater):
                                        try:
                                            # message_updater是同步函数，直接调用
                                            message_updater(f"❌ 视频下载失败: {str(e)}")
                                        except Exception as msg_e:
                                            logger.warning(f"发送错误消息失败: {msg_e}")
                                    result = {'success': False, 'error': str(e)}
                                finally:
                                    # 恢复原始下载路径
                                    self.bilibili_download_path = original_bilibili_path
                                    logger.info(f"🔧 恢复B站下载路径: {self.bilibili_download_path}")

                                if result.get('success', False):
                                    playlist_downloaded += 1
                                    total_downloaded += 1
                                    # 累计文件大小
                                    if 'size_mb' in result:
                                        total_size_mb += result['size_mb']
                                    logger.info(f"✅ 播放列表视频下载成功: {video_idx}/{len(videos)}")
                                else:
                                    playlist_failed += 1
                                    total_failed += 1
                                    logger.error(f"❌ 播放列表视频下载失败: {video_idx}/{len(videos)} - {result.get('error', '未知错误')}")

                            except Exception as e:
                                playlist_failed += 1
                                total_failed += 1
                                logger.error(f"❌ 播放列表视频下载异常: {video_idx}/{len(videos)} - {e}")

                    # 记录播放列表结果
                    if playlist_downloaded > 0:
                        playlist_result = {
                            'title': playlist_name,
                            'type': '播放列表',
                            'video_count': playlist_downloaded,
                            'failed_count': playlist_failed,
                            'download_path': str(user_download_path / playlist_name)
                        }
                        downloaded_results.append(playlist_result)
                        logger.info(f"✅ 播放列表处理完成: {playlist_name} (成功: {playlist_downloaded}, 失败: {playlist_failed})")

                except Exception as e:
                    logger.error(f"❌ 播放列表处理异常: {playlist_name} - {e}")
                    total_failed += len(videos)

            # 下载单独视频
            if single_videos:
                try:
                    single_playlist_index = len(playlists) + 1
                    total_playlists_with_single = len(playlists) + 1

                    if message_updater:
                        try:
                            initial_msg = f"""📥 正在下载第{single_playlist_index}/{total_playlists_with_single}个播放列表：单独视频

📺 总视频数: {len(single_videos)}
📊 状态: 开始下载..."""
                            import asyncio
                            if asyncio.iscoroutinefunction(message_updater):
                                await message_updater(initial_msg)
                            elif callable(message_updater):
                                message_updater(initial_msg)
                        except Exception as e:
                            logger.warning(f"更新状态消息失败: {e}")

                    logger.info(f"🎬 开始处理单独视频: {len(single_videos)} 个")

                    # 为每个单独视频调用现有的下载方法
                    single_downloaded = 0
                    single_failed = 0

                    for video_idx, video in enumerate(single_videos, 1):
                        video_url = video.get('url') or video.get('webpage_url')
                        if video_url:
                            try:
                                logger.info(f"🎬 调用现有下载方法处理单独视频 {video_idx}/{len(single_videos)}: {video_url}")
                                logger.info(f"🔍 传递给download_video的message_updater: {type(message_updater)}, callable: {callable(message_updater)}")



                                # 创建单独视频目录（与合集同级）
                                single_video_path = user_download_path / "单独视频"
                                single_video_path.mkdir(parents=True, exist_ok=True)
                                logger.info(f"📁 创建单独视频目录: {single_video_path}")

                                # 生成更好的文件名
                                video_title = video.get('title', '')
                                clean_title = re.sub(r'[\\/:*?"<>|]', '_', video_title).strip()
                                filename = f"{video_idx:02d}. {clean_title}.mp4"
                                logger.info(f"📝 生成单视频文件名: {filename}")



                                # 临时修改下载路径到单独视频目录
                                original_bilibili_path = self.bilibili_download_path
                                self.bilibili_download_path = single_video_path
                                logger.info(f"🔧 临时修改B站下载路径: {self.bilibili_download_path}")

                                try:
                                    # 创建简化的进度更新器，确保能正常工作
                                    def progress_updater(progress_text):
                                        logger.info(f"🔍 [DEBUG] 单独视频进度更新器被调用: type={type(progress_text)}")

                                        if isinstance(progress_text, str):
                                            # 如果是字符串，直接显示
                                            logger.info(f"🔍 [DEBUG] 收到字符串消息: {progress_text[:100]}...")
                                        else:
                                            # 如果是字典（yt-dlp进度数据），转换为格式化消息
                                            d = progress_text
                                            logger.info(f"🔍 [DEBUG] 收到进度字典: status={d.get('status')}")

                                            if d.get("status") == "downloading":
                                                logger.info(f"🔍 [DEBUG] 处理下载进度...")

                                                # 简化的进度消息，先确保基本功能工作
                                                filename = d.get("filename", "未知文件")
                                                if filename:
                                                    filename = os.path.basename(filename)

                                                simple_progress = f"""📥 正在下载第{single_playlist_index}/{total_playlists_with_single}个播放列表：单独视频

📺 当前视频: {video_idx}/{len(single_videos)}
📝 文件: {filename}
📊 状态: 下载中..."""

                                                logger.info(f"🔍 [DEBUG] 准备发送简化进度消息")

                                                # 直接尝试发送消息，不使用复杂的线程
                                                if message_updater and callable(message_updater):
                                                    try:
                                                        logger.info(f"🔍 [DEBUG] 尝试发送进度消息...")
                                                        # 暂时跳过异步调用，只记录日志
                                                        logger.info(f"✅ [DEBUG] 模拟发送进度消息成功")
                                                    except Exception as e:
                                                        logger.warning(f"❌ [DEBUG] 发送进度消息失败: {e}")
                                                # 获取进度信息
                                                filename = d.get("filename", "未知文件")
                                                if filename:
                                                    filename = os.path.basename(filename)

                                                # 调试：打印所有可用的字段
                                                logger.info(f"🔍 进度字典所有字段: {list(d.keys())}")
                                                logger.info(f"🔍 进度字典内容: {d}")

                                                downloaded_bytes = d.get("downloaded_bytes", 0)
                                                total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                                                speed = d.get("speed", 0)

                                                # 调试：打印原始数值
                                                logger.info(f"🔍 原始数值: downloaded_bytes={downloaded_bytes}, total_bytes={total_bytes}, speed={speed}")

                                                # 格式化大小和速度
                                                downloaded_mb = downloaded_bytes / (1024 * 1024) if downloaded_bytes else 0
                                                total_mb = total_bytes / (1024 * 1024) if total_bytes else 0
                                                speed_mb = speed / (1024 * 1024) if speed else 0

                                                # 计算进度
                                                if total_bytes > 0:
                                                    progress_percent = (downloaded_bytes / total_bytes) * 100
                                                else:
                                                    progress_percent = 0

                                                # 计算预计剩余时间
                                                eta_seconds = d.get("eta", 0)
                                                if eta_seconds and eta_seconds > 0:
                                                    eta_minutes = eta_seconds // 60
                                                    eta_secs = eta_seconds % 60
                                                    eta_str = f"{eta_minutes:02d}:{eta_secs:02d}"
                                                else:
                                                    eta_str = "未知"

                                                # 创建进度条
                                                bar_length = 20
                                                filled_length = int(bar_length * progress_percent / 100)
                                                bar = '█' * filled_length + '░' * (bar_length - filled_length)

                                                # 构建详细的进度消息
                                                progress_text = f"""📥 正在下载第{single_playlist_index}/{total_playlists_with_single}个播放列表：单独视频

📺 当前视频: {video_idx}/{len(single_videos)}
📝 文件: {filename}
💾 大小: {downloaded_mb:.2f}MB / {total_mb:.2f}MB
⚡️ 速度: {speed_mb:.2f}MB/s
⏳ 预计剩余: {eta_str}
📊 进度: [{bar}] {progress_percent:.1f}%"""

                                                # 发送进度消息（使用线程安全的方式）
                                                if message_updater and callable(message_updater):
                                                    try:
                                                        import asyncio
                                                        import threading

                                                        # 创建一个新线程来处理异步调用
                                                        def send_progress_message():
                                                            try:
                                                                # 在新线程中创建事件循环
                                                                loop = asyncio.new_event_loop()
                                                                asyncio.set_event_loop(loop)

                                                                # 运行异步函数
                                                                loop.run_until_complete(message_updater(progress_text))
                                                                loop.close()

                                                                logger.info(f"✅ 线程中成功发送进度消息")
                                                            except Exception as e:
                                                                logger.warning(f"线程中发送进度消息失败: {e}")

                                                        # 启动线程（不等待完成）
                                                        thread = threading.Thread(target=send_progress_message, daemon=True)
                                                        thread.start()

                                                    except Exception as e:
                                                        logger.warning(f"创建进度消息线程失败: {e}")

                                    # 创建简化的进度更新器
                                    async def simple_progress_updater(progress_text):
                                        try:
                                            logger.info(f"🔍 [DEBUG] simple_progress_updater被调用: type={type(progress_text)}")
                                            logger.info(f"🔍 [DEBUG] message_updater状态: {message_updater}, type={type(message_updater)}")

                                            if isinstance(progress_text, str):
                                                # 字符串消息直接发送
                                                if message_updater and callable(message_updater):
                                                    logger.info(f"🔍 [DEBUG] 准备调用message_updater")
                                                    # message_updater是同步函数，直接调用
                                                    message_updater(progress_text)
                                                    logger.info(f"✅ [DEBUG] message_updater调用成功")
                                                else:
                                                    logger.warning(f"⚠️ [DEBUG] message_updater不可用: {message_updater}")
                                            else:
                                                # 字典数据处理，转换为进度消息
                                                logger.info(f"🔍 [DEBUG] 处理字典数据: {progress_text}")

                                                if isinstance(progress_text, dict) and progress_text.get("status") == "downloading":
                                                    d = progress_text

                                                    # 获取进度信息
                                                    filename = d.get("filename", "未知文件")
                                                    if filename:
                                                        filename = os.path.basename(filename)

                                                    downloaded_bytes = d.get("downloaded_bytes", 0)
                                                    total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                                                    speed = d.get("speed", 0)

                                                    # 格式化大小和速度
                                                    downloaded_mb = downloaded_bytes / (1024 * 1024) if downloaded_bytes else 0
                                                    total_mb = total_bytes / (1024 * 1024) if total_bytes else 0
                                                    speed_mb = speed / (1024 * 1024) if speed else 0

                                                    # 计算进度
                                                    if total_bytes > 0:
                                                        progress_percent = (downloaded_bytes / total_bytes) * 100
                                                    else:
                                                        progress_percent = 0

                                                    # 计算预计剩余时间
                                                    eta_seconds = d.get("eta", 0)
                                                    if eta_seconds and eta_seconds > 0:
                                                        if eta_seconds >= 3600:  # 超过1小时
                                                            eta_hours = eta_seconds // 3600
                                                            eta_minutes = (eta_seconds % 3600) // 60
                                                            eta_str = f"{eta_hours}小时{eta_minutes}分钟"
                                                        elif eta_seconds >= 60:  # 超过1分钟
                                                            eta_minutes = eta_seconds // 60
                                                            eta_secs = eta_seconds % 60
                                                            eta_str = f"{eta_minutes}分{eta_secs:02d}秒"
                                                        else:  # 小于1分钟
                                                            eta_str = f"{eta_seconds}秒"
                                                    else:
                                                        eta_str = "未知"

                                                    # 创建进度条（使用你要的格式）
                                                    bar_length = 20
                                                    filled_length = int(bar_length * progress_percent / 100)
                                                    bar = '░' * bar_length  # 先全部用空心
                                                    # 然后填充实心部分（从左到右）
                                                    bar = '█' * filled_length + '░' * (bar_length - filled_length)

                                                    # 构建简洁的进度消息（你要的格式）
                                                    progress_text = f"""📥 下载中
📝 文件名: {filename}
💾 大小: {downloaded_mb:.2f}MB / {total_mb:.2f}MB
⚡️ 速度: {speed_mb:.2f}MB/s
⏳ 预计剩余: {eta_str}
📊 进度: {bar} {progress_percent:.1f}%"""

                                                    # 发送进度消息
                                                    if message_updater and callable(message_updater):
                                                        logger.info(f"🔍 [DEBUG] 发送实时进度消息")
                                                        try:
                                                            # message_updater是同步函数，直接调用
                                                            logger.info(f"🔍 [DEBUG] 调用message_updater: {type(message_updater)}")
                                                            message_updater(progress_text)
                                                            logger.info(f"✅ [DEBUG] 实时进度消息发送成功")
                                                        except Exception as e:
                                                            logger.warning(f"❌ [DEBUG] 实时进度消息发送失败: {e}")
                                                            logger.warning(f"🔍 [DEBUG] message_updater详情: {type(message_updater)}")
                                                            import traceback
                                                            logger.warning(f"🔍 [DEBUG] 完整错误堆栈: {traceback.format_exc()}")
                                                else:
                                                    logger.info(f"🔍 [DEBUG] 跳过非下载状态的字典数据: {progress_text.get('status') if isinstance(progress_text, dict) else 'unknown'}")
                                        except Exception as e:
                                            logger.warning(f"简化进度更新失败: {e}")
                                            logger.warning(f"🔍 [DEBUG] 异常详情: message_updater={message_updater}, progress_text={progress_text}")

                                    # 调用download_video，直接传递上层的message_updater以使用统一的进度管道
                                    result = await self.download_video(video_url, message_updater if message_updater else None)

                                    # 手动发送进度更新（简化版本）
                                    logger.info(f"🔍 检查message_updater状态: type={type(message_updater)}, callable={callable(message_updater) if message_updater else False}")
                                    if message_updater and callable(message_updater):
                                        try:
                                            # 获取文件名
                                            filename = "未知文件"
                                            if result.get('success', False) and result.get('filename'):
                                                filename = os.path.basename(result.get('filename'))

                                            progress_msg = f"""📥 正在下载第{single_playlist_index}/{total_playlists_with_single}个播放列表：单独视频

📺 当前视频: {video_idx}/{len(single_videos)}
📝 文件: {filename}
📊 状态: ✅ 下载完成
💾 大小: {result.get('size_mb', 0):.2f} MB"""

                                            logger.info(f"🔍 准备发送进度消息，message_updater类型: {type(message_updater)}")
                                            # message_updater是同步函数，直接调用
                                            message_updater(progress_msg)
                                            logger.info(f"✅ 手动发送进度更新成功")
                                        except Exception as e:
                                            logger.warning(f"手动发送进度更新失败: {e}")
                                    else:
                                        logger.warning(f"⚠️ message_updater不可用: {message_updater}")

                                    # 发送简洁的进度更新，而不是详细的完成消息
                                    logger.info(f"🔍 检查进度更新发送条件: success={result.get('success', False)}, message_updater={type(message_updater)}")
                                    if result.get('success', False) and message_updater and callable(message_updater):
                                        try:
                                            # 检查所有变量是否为None
                                            filename = result.get('filename', '未知文件')
                                            size_mb = result.get('size_mb', 0)

                                            logger.info(f"🔍 [DEBUG] 进度更新变量检查: filename={filename}, size_mb={size_mb}, single_video_path={single_video_path}")

                                            # 只显示简单的进度更新，详细总结在最后显示
                                            progress_text = f"""📥 正在下载第{single_playlist_index}/{total_playlists_with_single}个播放列表：单独视频

📺 当前视频: {video_idx}/{len(single_videos)} ✅ 下载完成
📝 文件: {os.path.basename(filename)}
💾 大小: {size_mb:.2f} MB"""

                                            logger.info(f"🔍 准备发送进度更新，message_updater类型: {type(message_updater)}")
                                            logger.info(f"🔍 [DEBUG] 进度更新内容: {progress_text}")

                                            # message_updater是同步函数，直接调用
                                            message_updater(progress_text)
                                            logger.info(f"✅ 单独视频进度更新已发送")
                                        except Exception as e:
                                            logger.warning(f"发送单独视频进度更新失败: {e}")
                                            import traceback
                                            logger.warning(f"🔍 [DEBUG] 进度更新发送错误堆栈: {traceback.format_exc()}")
                                    else:
                                        logger.warning(f"⚠️ 跳过进度更新发送: success={result.get('success', False)}, message_updater={message_updater}")

                                except Exception as e:
                                    logger.error(f"单独视频下载异常: {e}")
                                    if message_updater and callable(message_updater):
                                        try:
                                            # message_updater是同步函数，直接调用
                                            message_updater(f"❌ 视频下载失败: {str(e)}")
                                        except Exception as msg_e:
                                            logger.warning(f"发送错误消息失败: {msg_e}")
                                    result = {'success': False, 'error': str(e)}
                                finally:
                                    # 恢复原始下载路径
                                    self.bilibili_download_path = original_bilibili_path
                                    logger.info(f"🔧 恢复B站下载路径: {self.bilibili_download_path}")

                                if result.get('success', False):
                                    single_downloaded += 1
                                    total_downloaded += 1
                                    # 累计文件大小
                                    if 'size_mb' in result:
                                        total_size_mb += result['size_mb']
                                    logger.info(f"✅ 单独视频下载成功: {video_idx}/{len(single_videos)}")
                                else:
                                    single_failed += 1
                                    total_failed += 1
                                    logger.error(f"❌ 单独视频下载失败: {video_idx}/{len(single_videos)} - {result.get('error', '未知错误')}")

                            except Exception as e:
                                single_failed += 1
                                total_failed += 1
                                logger.error(f"❌ 单独视频下载异常: {video_idx}/{len(single_videos)} - {e}")

                    # 记录单独视频结果
                    if single_downloaded > 0:
                        single_result = {
                            'title': '单独视频',
                            'type': '单独视频',
                            'video_count': single_downloaded,
                            'failed_count': single_failed,
                            'download_path': str(user_download_path / "单独视频")
                        }
                        downloaded_results.append(single_result)
                        logger.info(f"✅ 单独视频处理完成: (成功: {single_downloaded}, 失败: {single_failed})")

                except Exception as e:
                    logger.error(f"❌ 单独视频下载异常: {e}")
                    total_failed += len(single_videos)

            # 步骤6: 统计下载结果
            logger.info("🔍 步骤6: 统计下载结果...")

            # 计算成功率和失败数量
            total_videos = len(entries)
            success_rate = (total_downloaded / total_videos) * 100 if total_videos > 0 else 0

            # 格式化总大小显示
            if total_size_mb >= 1024:
                total_size_str = f"{total_size_mb / 1024:.2f}GB"
            else:
                total_size_str = f"{total_size_mb:.2f}MB"

            logger.info(f"📊 下载统计: {total_downloaded}/{total_videos} 个视频成功，成功率: {success_rate:.1f}%")
            logger.info(f"📊 播放列表统计: {len(downloaded_results)} 个播放列表")

            # 步骤7: 构建完成消息
            if message_updater and callable(message_updater):
                try:
                    completion_text = f"""📺 B站UP主播放列表下载完成

📺 UP主: {clean_uploader_name}
📊 播放列表数量: {len(downloaded_results)}
📊 单集数量: {total_videos}

已下载的播放列表:

"""

                    # 添加每个播放列表的详细信息（参考YouTube格式）
                    for i, playlist in enumerate(downloaded_results, 1):
                        playlist_title = playlist.get('title', f'播放列表{i}')
                        video_count = playlist.get('video_count', 0)
                        failed_count = playlist.get('failed_count', 0)

                        # 显示成功和失败的视频数量
                        if failed_count > 0:
                            completion_text += f"  {i}. {playlist_title} ({video_count} 集, ❌ {failed_count} 失败)\n"
                        else:
                            completion_text += f"  {i}. {playlist_title} ({video_count} 集)\n"

                    completion_text += f"""

📊 下载统计:
总计: {total_videos} 个
✅ 成功: {total_downloaded} 个
❌ 失败: {total_failed} 个
💾 文件总大小: {total_size_str}
📂 保存位置: {user_download_path}"""

                    # message_updater是同步函数，直接调用
                    message_updater(completion_text)
                except Exception as e:
                    logger.warning(f"更新完成消息失败: {e}")

            # 步骤8: 返回结果
            if total_downloaded > 0:
                logger.info(f"🎉 UP主所有视频下载完成: {total_downloaded}/{total_videos} 个成功")

                # 添加详细的下载总结日志
                logger.info("=" * 60)
                logger.info("📊 B站UP主下载完成总结")
                logger.info("=" * 60)
                logger.info(f"🎯 UP主: {clean_uploader_name} (UID: {uid})")
                logger.info(f"📁 下载目录: {user_download_path}")
                logger.info(f"📊 总视频数: {total_videos}")
                logger.info(f"✅ 成功下载: {total_downloaded}")
                logger.info(f"❌ 下载失败: {total_failed}")
                logger.info(f"📈 成功率: {success_rate:.1f}%")
                logger.info(f"💾 总文件大小: {total_size_str}")

                # 显示播放列表详情
                if downloaded_results:
                    logger.info(f"\n📋 播放列表详情:")
                    for i, playlist in enumerate(downloaded_results, 1):
                        playlist_title = playlist.get('title', f'播放列表{i}')
                        video_count = playlist.get('video_count', 0)
                        failed_count = playlist.get('failed_count', 0)
                        download_path = playlist.get('download_path', '未知')
                        logger.info(f"  {i}. {playlist_title}")
                        logger.info(f"     视频数: {video_count}, 失败: {failed_count}")
                        logger.info(f"     保存位置: {download_path}")

                # 显示目录结构
                logger.info(f"\n📂 最终目录结构:")
                try:
                    def log_directory_structure(path, indent=""):
                        if os.path.isdir(path):
                            logger.info(f"{indent}📁 {os.path.basename(path)}/")
                            try:
                                for item in sorted(os.listdir(path)):
                                    item_path = os.path.join(path, item)
                                    if os.path.isdir(item_path):
                                        log_directory_structure(item_path, indent + "  ")
                                    else:
                                        size = os.path.getsize(item_path) / (1024 * 1024)  # MB
                                        logger.info(f"{indent}  📄 {item} ({size:.2f}MB)")
                            except PermissionError:
                                logger.warning(f"{indent}  ⚠️ 无法访问目录内容")
                        else:
                            logger.info(f"{indent}📄 {os.path.basename(path)}")

                    log_directory_structure(user_download_path)
                except Exception as e:
                    logger.warning(f"无法显示目录结构: {e}")

                logger.info("=" * 60)

                return {
                    'success': True,
                    'is_channel': True,
                    'platform': 'bilibili',
                    'video_type': 'user_all_videos',
                    'channel_title': clean_uploader_name,
                    'uploader_id': uploader_id,
                    'uid': uid,
                    'total_videos': total_videos,
                    'downloaded_videos': total_downloaded,
                    'failed_videos': total_failed,
                    'success_rate': success_rate,
                    'total_size_mb': total_size_mb,
                    'download_path': str(user_download_path),
                    'playlists_downloaded': [p['title'] for p in downloaded_results],
                    'playlist_stats': downloaded_results
                }
            else:
                return {'success': False, 'error': '所有视频下载都失败了'}

        except Exception as e:
            error_msg = f"UP主合集下载过程中出错: {e}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}

    async def _download_bilibili_list(
        self, uid: str, list_id: str, download_path: Path, message_updater=None
    ) -> Dict[str, Any]:
        """下载Bilibili播放列表"""
        logger.info(f"🎬 开始下载Bilibili播放列表: UID={uid}, ListID={list_id}")

        try:
            logger.info("🔍 步骤1: 准备获取播放列表信息...")
            # 获取播放列表信息 - 添加超时控制
            info_opts = {
                "quiet": True,
                "extract_flat": True,
                "ignoreerrors": True,
                "socket_timeout": 30,  # 30秒超时
                "retries": 8,  # 增加重试次数以提高断点续传成功率
                "fragment_retries": 8,
            }
            if self.proxy_host:
                info_opts["proxy"] = self.proxy_host
                logger.info(f"🌐 使用代理: {self.proxy_host}")

            logger.info("🔍 步骤2: 开始提取播放列表信息（设置30秒超时）...")

            # 使用异步执行器来添加超时控制
            loop = asyncio.get_running_loop()

            def extract_playlist_info():
                with yt_dlp.YoutubeDL(info_opts) as ydl:
                    logger.info("📡 正在从Bilibili获取播放列表数据...")
                    return ydl.extract_info(
                        f"https://www.bilibili.com/medialist/play/{uid}?business=space_series&business_id={list_id}",
                        download=False,
                    )

            # 设置30秒超时
            try:
                info = await asyncio.wait_for(
                    loop.run_in_executor(None, extract_playlist_info), timeout=60.0
                )
                logger.info(f"✅ 播放列表信息获取完成，数据类型: {type(info)}")
            except asyncio.TimeoutError:
                logger.error("❌ 获取播放列表信息超时（30秒）")
                return {
                    "success": False,
                    "error": "获取播放列表信息超时，请检查网络连接或稍后重试。",
                }

            if not info:
                logger.error("❌ 播放列表信息为空")
                return {"success": False, "error": "无法获取播放列表信息"}

            if "entries" not in info:
                logger.error("❌ 播放列表信息中没有找到 'entries' 字段")
                return {"success": False, "error": "无法获取播放列表信息"}

            entries = info.get("entries", [])
            logger.info(f"📊 播放列表包含 {len(entries)} 个视频")

            if not entries:
                logger.warning("⚠️ 播放列表为空")
                return {"success": False, "error": "播放列表为空"}

            logger.info("🔍 步骤3: 创建播放列表目录...")
            # Bilibili播放列表目录只使用list_id
            playlist_path = download_path / list_id
            playlist_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"📁 播放列表目录: {playlist_path}")

            logger.info("🔍 步骤4: 配置下载选项...")
            # 设置输出模板，B站播放列表保持原有格式（包含ID）
            outtmpl = str(
                playlist_path.absolute()
                / "%(playlist_index)02d - %(title)s [%(id)s].%(ext)s"
            )
            # 添加明显的outtmpl日志
            logger.info(f"🔧 [BILIBILI_PLAYLIST] outtmpl 绝对路径: {outtmpl}")

            # 配置下载选项 - 优化性能
            ydl_opts = {
                "outtmpl": outtmpl,
                "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "merge_output_format": "mp4",
                "ignoreerrors": True,
                "retries": 8,  # 增加重试次数以提高断点续传成功率
                "fragment_retries": 8,
                "skip_unavailable_fragments": True,
                "quiet": True,
                "no_warnings": True,
                "socket_timeout": 30,  # 30秒超时
                "extract_flat": False,  # 完整提取
            }

            if self.proxy_host:
                ydl_opts["proxy"] = self.proxy_host

            if message_updater:
                ydl_opts["progress_hooks"] = [message_updater]

            # 添加弹幕下载选项 (构造B站URL)
            bilibili_url = f"https://www.bilibili.com/medialist/play/{uid}?business=space_series&business_id={list_id}"
            ydl_opts = self._add_danmaku_options(ydl_opts, bilibili_url)

            # 如果开启了B站封面下载，添加缩略图下载选项
            if hasattr(self, 'bot') and hasattr(self.bot, 'bilibili_thumbnail_download') and self.bot.bilibili_thumbnail_download:
                ydl_opts["writethumbnail"] = True
                # 添加缩略图格式转换后处理器：WebP -> JPG
                if "postprocessors" not in ydl_opts:
                    ydl_opts["postprocessors"] = []
                ydl_opts["postprocessors"].append({
                    'key': 'FFmpegThumbnailsConvertor',
                    'format': 'jpg',
                    'when': 'before_dl'
                })
                logger.info("🖼️ B站播放列表开启封面下载（转换为JPG格式）")

            logger.info("🔍 步骤5: 开始下载播放列表（设置60秒超时）...")

            def download_playlist():
                logger.info(f"🔧 [BILIBILI_PLAYLIST_DOWNLOAD] 最终ydl_opts: {ydl_opts}")
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    logger.info("🚀 开始下载Bilibili播放列表视频...")
                    return ydl.download(
                        [
                            f"https://www.bilibili.com/medialist/play/{uid}?business=space_series&business_id={list_id}"
                        ]
                    )

            # 设置60秒超时用于下载
            try:
                await asyncio.wait_for(
                    loop.run_in_executor(None, download_playlist), timeout=120.0
                )
                logger.info("✅ Bilibili播放列表下载完成")

                # 重命名弹幕文件（如果有的话）
                self._rename_danmaku_files(str(playlist_path))

            except asyncio.TimeoutError:
                logger.error("❌ Bilibili播放列表下载超时（60秒）")
                return {
                    "success": False,
                    "error": "Bilibili播放列表下载超时，请检查网络连接或稍后重试。",
                }

            return {
                "success": True,
                "is_playlist": True,
                "playlist_title": list_id,  # 使用list_id作为标题
                "download_path": str(playlist_path),
                "video_count": len(entries),
            }

        except Exception as e:
            logger.error(f"❌ Bilibili播放列表下载失败: {e}")
            import traceback

            logger.error(f"详细错误信息: {traceback.format_exc()}")
            return {"success": False, "error": str(e)}

    async def _download_youtube_playlist_with_progress(
        self, playlist_id: str, download_path: Path, progress_callback=None, original_url: str = None
    ) -> Dict[str, Any]:
        """下载YouTube播放列表（带详细进度）"""
        logger.info(f"🎬 开始下载YouTube播放列表: {playlist_id}")
        logger.info(f"📁 下载路径: {download_path}")

        try:
            # 检查播放列表是否已经完整下载
            logger.info("🔍 检查播放列表是否已完整下载...")
            check_result = self._check_playlist_already_downloaded(
                playlist_id, download_path
            )

            if check_result.get("already_downloaded", False):
                logger.info("✅ 播放列表已完整下载，直接返回结果")
                return {
                    "success": True,
                    "already_downloaded": True,
                    "playlist_title": check_result.get("playlist_title", ""),
                    "video_count": check_result.get("video_count", 0),
                    "download_path": check_result.get("download_path", ""),
                    "total_size_mb": check_result.get("total_size_mb", 0),
                    "resolution": check_result.get("resolution", "未知"),
                    "downloaded_files": check_result.get("downloaded_files", []),
                    "completion_rate": check_result.get("completion_rate", 100),
                }
            else:
                logger.info(f"📥 播放列表未完整下载，原因: {check_result.get('reason', '未知')}")
                if check_result.get("completion_rate", 0) > 0:
                    logger.info(
                        f"📊 当前完成度: {check_result.get('completion_rate', 0):.1f}%"
                    )

            # 获取播放列表信息 - 使用增强配置
                # 获取播放列表信息 - 使用增强配置
                info_opts = {
                    "quiet": False,  # 显示详细信息
                    "ignoreerrors": True,
                    "socket_timeout": 60,
                    "retries": 3,
                    "age_limit": 99,  # 绕过年龄限制
                    "geo_bypass": True,  # 尝试绕过地理限制
                    "geo_bypass_country": "US",  # 使用美国作为绕过国家
                    "extractor_args": {
                        "youtube": {
                            # 🎯 真正修复：绕过YouTube 2024年底的PO Token限制
                            "player_client": ["ios", "mweb"],  # 使用iOS和移动网页客户端
                            "player_skip": ["configs", "webpage"],  # 跳过配置和网页检查
                            "include_dash_manifest": True,  # 包含DASH清单
                            "formats": "missing_pot",  # 允许缺少PO Token的格式
                        }
                    },
                }
                if self.proxy_host:
                    info_opts["proxy"] = self.proxy_host
                    logger.info(f"🌐 使用代理: {self.proxy_host}")
                if self.youtube_cookies_path and os.path.exists(self.youtube_cookies_path):
                    info_opts["cookiefile"] = self.youtube_cookies_path
                    logger.info(
                        f"🍪 使用YouTube cookies: {self.youtube_cookies_path}"
                    )

                def extract_playlist_info():
                    logger.info("📡 正在从YouTube获取播放列表数据...")
                    with yt_dlp.YoutubeDL(info_opts) as ydl:
                        result = ydl.extract_info(
                            f"https://www.youtube.com/playlist?list={playlist_id}",
                            download=False,
                        )
                        return result

                loop = asyncio.get_running_loop()
                info = await loop.run_in_executor(None, extract_playlist_info)

                if not info:
                    logger.error("❌ 播放列表信息为空")
                    return {"success": False, "error": "无法获取播放列表信息。"}

                entries = info.get("entries", [])
                if not entries:
                    logger.warning("❌ 播放列表为空")
                    return {"success": False, "error": "播放列表为空。"}

                logger.info(f"📊 播放列表包含 {len(entries)} 个视频")

                # 调试：检查播放列表信息
                logger.info(f"🔍 播放列表原始标题: {info.get('title', 'N/A')}")
                logger.info(f"🔍 播放列表ID: {playlist_id}")
                logger.info(f"🔍 播放列表其他字段: uploader={info.get('uploader', 'N/A')}, uploader_id={info.get('uploader_id', 'N/A')}")

                # 创建播放列表目录
                # 尝试从不同字段获取播放列表标题
                raw_title = info.get("title", f"Playlist_{playlist_id}")
                if raw_title == playlist_id or raw_title.startswith("Playlist_"):
                    # 如果标题就是ID，尝试从其他字段获取
                    raw_title = info.get("uploader", info.get("channel", f"Playlist_{playlist_id}"))
                    logger.info(f"🔧 使用备用标题: {raw_title}")

                playlist_title = re.sub(r'[\\/:*?"<>|]', "_", raw_title).strip()
                # 根据设置决定文件夹名称格式
                if hasattr(self, 'bot') and hasattr(self.bot, 'youtube_id_tags') and self.bot.youtube_id_tags:
                    playlist_title_with_id = f"[{playlist_id}]"
                else:
                    playlist_title_with_id = playlist_title
                playlist_path = download_path / playlist_title_with_id
                playlist_path.mkdir(parents=True, exist_ok=True)
                logger.info(f"📁 播放列表目录: {playlist_path}")

                # 预先记录预期文件信息（像B站多P下载一样）
                expected_files = []
                for i, entry in enumerate(entries, 1):
                    title = entry.get("title", f"Video_{i}")
                    safe_title = re.sub(r'[\\/:*?"<>|]', "_", title).strip()
                    video_id = entry.get('id', '')

                    # 根据设置决定文件名格式，与实际下载时的模板保持一致
                    if hasattr(self, 'bot') and hasattr(self.bot, 'youtube_id_tags') and self.bot.youtube_id_tags:
                        expected_filename = f"{i:02d}. {safe_title}[{video_id}].mp4"
                    else:
                        expected_filename = f"{i:02d}. {safe_title}.mp4"

                    expected_files.append({
                        'title': title,
                        'filename': expected_filename,
                        'index': i,
                        'id': video_id,
                    })

            logger.info(f"📋 预期文件列表: {len(expected_files)} 个文件")

            # 下载播放列表（带进度回调）
            def download_playlist():
                logger.info("🚀 开始下载播放列表...")

                # 检查是否为音频模式，决定使用哪个目录
                if hasattr(self, 'bot') and hasattr(self.bot, 'youtube_audio_mode') and self.bot.youtube_audio_mode:
                    # 音频模式：使用播放列表目录下的music子目录
                    music_playlist_path = playlist_path / "music"
                    music_playlist_path.mkdir(exist_ok=True)  # 确保music目录存在
                    actual_path = music_playlist_path
                    logger.info("🎵 音频模式：播放列表将保存到music子目录")
                else:
                    # 默认视频模式：使用原播放列表目录
                    actual_path = playlist_path

                # 使用绝对路径构建outtmpl，根据设置决定文件名前缀和是否添加视频ID
                # 检查是否开启时间戳命名
                use_timestamp = hasattr(self, 'bot') and hasattr(self.bot, 'youtube_timestamp_naming') and self.bot.youtube_timestamp_naming
                use_id_tags = hasattr(self, 'bot') and hasattr(self.bot, 'youtube_id_tags') and self.bot.youtube_id_tags

                if use_timestamp:
                    # 使用时间戳作为前缀
                    if use_id_tags:
                        filename_template = "%(upload_date)s. %(title)s[%(id)s].%(ext)s"
                    else:
                        filename_template = "%(upload_date)s. %(title)s.%(ext)s"
                else:
                    # 使用序号作为前缀（保持原有逻辑）
                    if use_id_tags:
                        filename_template = "%(playlist_index)02d. %(title)s[%(id)s].%(ext)s"
                    else:
                        filename_template = "%(playlist_index)02d. %(title)s.%(ext)s"

                abs_outtmpl = str(actual_path.absolute() / filename_template)
                logger.info(
                    f"🔧 [YT_PLAYLIST_WITH_PROGRESS] outtmpl 绝对路径: {abs_outtmpl}"
                )
                # 根据YouTube音频模式设置format和输出格式
                if hasattr(self, 'bot') and hasattr(self.bot, 'youtube_audio_mode') and self.bot.youtube_audio_mode:
                    # YouTube音频模式：优先下载最高码率的MP3格式
                    format_spec = "bestaudio[ext=mp3]/bestaudio[acodec=mp3]/bestaudio"
                    merge_format = "mp3"
                    logger.info("🎵 启用YouTube音频模式，播放列表优先下载最高码率MP3")
                else:
                    # 🎯 真正修复：恢复v0.4-dev3的成功方式 - 让yt-dlp自己选择最佳格式
                    format_spec = None  # 不设置format，使用yt-dlp默认的"best"
                    merge_format = "mp4"
                    logger.info("🎬 YouTube频道下载使用yt-dlp原生最佳格式选择（恢复v0.4-dev3成功方式）")

                # 使用增强配置，避免PART文件
                logger.info(f"🔧 [PROGRESS_HOOKS] progress_callback是否为None: {progress_callback is None}")
                logger.info(f"🔧 [PROGRESS_HOOKS] progress_callback类型: {type(progress_callback)}")
                base_opts = {
                    "outtmpl": abs_outtmpl,
                    "merge_output_format": merge_format,
                    "ignoreerrors": True,
                    "progress_hooks": [progress_callback] if progress_callback else [],
                }
                logger.info(f"🔧 [PROGRESS_HOOKS] base_opts中的progress_hooks: {len(base_opts['progress_hooks'])} 个回调")

                # 🎯 关键修复：无论音频还是视频模式，都要添加format设置
                if format_spec:
                    base_opts["format"] = format_spec
                    logger.info(f"🎯 [FORMAT_FIX] 已设置format到base_opts: {format_spec}")

                ydl_opts = self._get_enhanced_ydl_opts(base_opts)
                logger.info("🛡️ 使用增强配置，避免PART文件产生")

                # 如果是音频模式，添加音频转换后处理器
                if hasattr(self, 'bot') and hasattr(self.bot, 'youtube_audio_mode') and self.bot.youtube_audio_mode:
                    ydl_opts["postprocessors"] = ydl_opts.get("postprocessors", []) + [
                        {
                            'key': 'FFmpegExtractAudio',
                            'preferredcodec': 'mp3',
                            'preferredquality': '320',  # 最高质量320kbps
                        }
                    ]
                    logger.info("🎵 播放列表添加音频转换后处理器：转换为320kbps MP3")

                # 如果开启了封面下载，添加缩略图下载选项
                if hasattr(self, 'bot') and hasattr(self.bot, 'youtube_thumbnail_download') and self.bot.youtube_thumbnail_download:
                    ydl_opts["writethumbnail"] = True
                    # 添加缩略图格式转换后处理器：WebP -> JPG
                    if "postprocessors" not in ydl_opts:
                        ydl_opts["postprocessors"] = []
                    ydl_opts["postprocessors"].append({
                        'key': 'FFmpegThumbnailsConvertor',
                        'format': 'jpg',
                        'when': 'before_dl'
                    })
                    logger.info("🖼️ 播放列表开启YouTube封面下载（转换为JPG格式）")

                # 如果开启了字幕下载，添加字幕下载选项
                if hasattr(self, 'bot') and hasattr(self.bot, 'youtube_subtitle_download') and self.bot.youtube_subtitle_download:
                    ydl_opts["writeautomaticsub"] = True  # 下载自动生成的字幕
                    ydl_opts["writesubtitles"] = True     # 下载手动字幕
                    ydl_opts["subtitleslangs"] = ["zh", "en"]  # 字幕语言：中文和英文
                    ydl_opts["convertsubtitles"] = "srt"  # 转换为SRT格式
                    ydl_opts["subtitlesformat"] = "best[ext=srt]/srt/best"  # 优先选择SRT格式
                    logger.info("📝 播放列表开启YouTube字幕下载（中文、英文，SRT格式）")

                logger.info(f"🔧 [YT_PLAYLIST_WITH_PROGRESS] 最终ydl_opts关键配置: outtmpl={abs_outtmpl}")

                # 使用原始URL（如果提供）或构造播放列表URL
                if original_url:
                    playlist_url = original_url
                    logger.info(f"🔗 使用原始URL: {playlist_url}")
                else:
                    playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"
                    logger.info(f"📋 使用构造的播放列表URL: {playlist_url}")

                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([playlist_url])

                    # 下载完成后检查并处理PART文件
                    logger.info("🔍 检查YouTube播放列表下载完成状态...")
                    resume_success = self._resume_failed_downloads(download_path, playlist_url, max_retries=5)

                    if not resume_success:
                        logger.warning("⚠️ 部分文件下载未完成，但已达到最大重试次数")
                    else:
                        logger.info("✅ YouTube播放列表所有文件下载完成")

                except Exception as e:
                    logger.error(f"❌ YouTube播放列表下载过程中出现错误: {e}")
                    # 即使出错也尝试断点续传PART文件
                    logger.info("🔄 尝试断点续传未完成的文件...")
                    self._resume_part_files(download_path, playlist_url)
                    raise

            await loop.run_in_executor(None, download_playlist)

            logger.info("🎉 播放列表下载完成!")

            # 查找下载的文件
            downloaded_files = []
            total_size_mb = 0
            all_resolutions = set()

            # 使用预期文件名精确查找（现在动态播放列表也有预期文件信息了）
            logger.info("🔍 使用预期文件名查找下载的文件")
            for expected_file in expected_files:
                    expected_filename = expected_file['filename']
                    expected_path = playlist_path / expected_filename

                    # 检查预期文件是否存在
                    actual_path = expected_path
                    if expected_path.exists():
                        # 文件存在，直接使用
                        pass
                    elif (hasattr(self, 'bot') and hasattr(self.bot, 'youtube_audio_mode') and
                          self.bot.youtube_audio_mode):
                        # 音频模式：检查是否存在对应的MP3文件
                        mp3_path = expected_path.with_suffix('.mp3')
                        if mp3_path.exists():
                            actual_path = mp3_path
                            logger.info(f"🎵 播放列表音频模式：找到转换后的MP3文件: {mp3_path.name}")
                        else:
                            logger.warning(f"⚠️ 播放列表音频模式：未找到文件: {expected_filename} 或 {mp3_path.name}")
                            continue
                    else:
                        logger.warning(f"⚠️ 未找到预期文件: {expected_filename}")
                        continue

                    # 处理找到的文件
                    try:
                        file_size = actual_path.stat().st_size
                        if file_size > 0:
                            file_size_mb = file_size / (1024 * 1024)
                            total_size_mb += file_size_mb

                            # 获取媒体信息
                            media_info = self.get_media_info(str(actual_path))
                            resolution = media_info.get('resolution', '未知')
                            if resolution != '未知':
                                all_resolutions.add(resolution)

                            downloaded_files.append({
                                "filename": actual_path.name,  # 使用实际文件名
                                "path": str(actual_path),      # 使用实际路径
                                "size_mb": file_size_mb,
                                "video_title": expected_file['title'],
                            })
                            logger.info(f"✅ 找到预期文件: {actual_path.name} ({file_size_mb:.2f}MB)")
                        else:
                            logger.warning(f"⚠️ 预期文件为空: {actual_path.name}")
                    except Exception as e:
                        logger.warning(f"⚠️ 无法检查预期文件: {actual_path.name}, 错误: {e}")

            # 计算分辨率显示
            resolution = ', '.join(sorted(all_resolutions)) if all_resolutions else '未知'

            logger.info(f"📊 播放列表找到文件数量: {len(downloaded_files)}/{len(expected_files)}")
            logger.info(f"📊 总大小: {total_size_mb:.2f}MB")

            return {
                "success": True,
                "playlist_title": playlist_title_with_id,  # 使用实际的目录名作为标题
                "video_count": len(downloaded_files),
                "download_path": str(playlist_path),
                "total_size_mb": total_size_mb,
                "size_mb": total_size_mb,  # 添加这个字段以兼容main.py
                "resolution": resolution,
                "downloaded_files": downloaded_files,
            }

        except Exception as e:
            logger.error(f"❌ YouTube播放列表下载失败: {e}")
            import traceback

            logger.error(f"详细错误信息: {traceback.format_exc()}")
            return {"success": False, "error": str(e)}



    def _make_progress_bar(self, percent: float) -> str:
        """生成进度条"""
        bar_length = 20
        filled_length = int(bar_length * percent / 100)
        bar = "█" * filled_length + "░" * (bar_length - filled_length)
        return f"[{bar}] {percent:.1f}%"

    def _check_playlist_already_downloaded(
        self, playlist_id: str, download_path: Path
    ) -> Dict[str, Any]:
        """
        检查YouTube播放列表是否已经完整下载（使用预期文件名方式）

        Args:
            playlist_id: 播放列表ID
            download_path: 下载路径

        Returns:
            Dict: 包含检查结果的字典
        """
        logger.info(f"🔍 检查播放列表是否已下载: {playlist_id}")

        try:
            # 获取播放列表信息
            info_opts = {
                "quiet": True,
                "extract_flat": True,
                "ignoreerrors": True,
                "socket_timeout": 10,
                "retries": 2,
            }
            if self.proxy_host:
                info_opts["proxy"] = self.proxy_host
            if self.youtube_cookies_path and os.path.exists(self.youtube_cookies_path):
                info_opts["cookiefile"] = self.youtube_cookies_path

            with yt_dlp.YoutubeDL(info_opts) as ydl:
                info = ydl.extract_info(
                    f"https://www.youtube.com/playlist?list={playlist_id}",
                    download=False,
                )

            if not info:
                logger.warning("❌ 无法获取播放列表信息")
                return {"already_downloaded": False, "reason": "无法获取播放列表信息"}

            entries = info.get("entries", [])
            if not entries:
                logger.warning("❌ 播放列表为空")
                return {"already_downloaded": False, "reason": "播放列表为空"}

            # 构建预期文件列表（和下载时一致）
            expected_files = []
            for i, entry in enumerate(entries, 1):
                title = entry.get("title", f"Video_{i}")
                safe_title = re.sub(r'[\\/:*?"<>|]', "_", title).strip()
                video_id = entry.get('id', '')

                # 根据设置决定文件名格式，与实际下载时的模板保持一致
                if hasattr(self, 'bot') and hasattr(self.bot, 'youtube_id_tags') and self.bot.youtube_id_tags:
                    expected_filename = f"{i:02d}. {safe_title}[{video_id}].mp4"
                else:
                    expected_filename = f"{i:02d}. {safe_title}.mp4"

                expected_files.append({
                    'title': title,
                    'filename': expected_filename,
                    'index': i,
                    'id': video_id,
                })

            # 创建播放列表目录名
            playlist_title = re.sub(
                r'[\\/:*?"<>|]', "_", info.get("title", f"Playlist_{playlist_id}")
            ).strip()
            # 根据设置决定文件夹名称格式
            if hasattr(self, 'bot') and hasattr(self.bot, 'youtube_id_tags') and self.bot.youtube_id_tags:
                playlist_title_with_id = f"[{playlist_id}]"
            else:
                playlist_title_with_id = playlist_title
            playlist_path = download_path / playlist_title_with_id

            if not playlist_path.exists():
                logger.info(f"📁 播放列表目录不存在: {playlist_path}")
                return {"already_downloaded": False, "reason": "目录不存在"}

            logger.info(f"📁 检查播放列表目录: {playlist_path}")

            # 使用预期文件名检查文件是否存在（和下载逻辑一致）
            missing_files = []
            existing_files = []
            total_size_mb = 0
            all_resolutions = set()

            def clean_filename_for_matching(filename):
                """清理文件名用于匹配"""
                import re
                if not filename:
                    return ""

                # 删除yt-dlp的各种格式代码
                cleaned = re.sub(r'\.[fm]\d+(\+\d+)*', '', filename)
                cleaned = re.sub(r'\.f\d+', '', cleaned)

                # 删除YouTube视频ID标识（仅在启用ID标签时）
                if hasattr(self, 'bot') and hasattr(self.bot, 'youtube_id_tags') and self.bot.youtube_id_tags:
                    cleaned = re.sub(r'\[[a-zA-Z0-9_-]{10,12}\]', '', cleaned)

                cleaned = re.sub(r'\.(webm|m4a|mp3)$', '.mp4', cleaned)

                # 确保以 .mp4 结尾
                if not cleaned.endswith('.mp4'):
                    cleaned = cleaned.rstrip('.') + '.mp4'

                return cleaned

            for expected_file in expected_files:
                expected_filename = expected_file['filename']
                expected_path = playlist_path / expected_filename
                title = expected_file['title']

                if expected_path.exists():
                    try:
                        file_size = expected_path.stat().st_size
                        if file_size > 0:
                            file_size_mb = file_size / (1024 * 1024)
                            total_size_mb += file_size_mb

                            # 获取媒体信息
                            media_info = self.get_media_info(str(expected_path))
                            resolution = media_info.get('resolution', '未知')
                            if resolution != '未知':
                                all_resolutions.add(resolution)

                            existing_files.append({
                                "filename": expected_filename,
                                "path": str(expected_path),
                                "size_mb": file_size_mb,
                                "video_title": title,
                            })
                            logger.info(f"✅ 找到文件: {expected_filename} ({file_size_mb:.2f}MB)")
                        else:
                            missing_files.append(f"{expected_file['index']}. {title}")
                            logger.warning(f"⚠️ 文件为空: {expected_filename}")
                    except Exception as e:
                        missing_files.append(f"{expected_file['index']}. {title}")
                        logger.warning(f"⚠️ 无法检查文件: {expected_filename}, 错误: {e}")
                else:
                    # 尝试智能匹配（处理格式代码等）
                    found = False
                    for video_ext in ["*.mp4", "*.mkv", "*.webm", "*.avi", "*.mov", "*.flv"]:
                        matching_files = list(playlist_path.glob(video_ext))
                        for file_path in matching_files:
                            actual_filename = file_path.name
                            cleaned_actual = clean_filename_for_matching(actual_filename)
                            cleaned_expected = clean_filename_for_matching(expected_filename)

                            if cleaned_actual == cleaned_expected:
                                try:
                                    file_size = file_path.stat().st_size
                                    if file_size > 0:
                                        file_size_mb = file_size / (1024 * 1024)
                                        total_size_mb += file_size_mb

                                        # 获取媒体信息
                                        media_info = self.get_media_info(str(file_path))
                                        resolution = media_info.get('resolution', '未知')
                                        if resolution != '未知':
                                            all_resolutions.add(resolution)

                                        existing_files.append({
                                            "filename": actual_filename,
                                            "path": str(file_path),
                                            "size_mb": file_size_mb,
                                            "video_title": title,
                                        })
                                        logger.info(f"✅ 通过模糊匹配找到文件: {actual_filename} ({file_size_mb:.2f}MB)")
                                        found = True
                                        break
                                except Exception as e:
                                    continue
                        if found:
                            break

                    if not found:
                        missing_files.append(f"{expected_file['index']}. {title}")
                        logger.warning(f"⚠️ 未找到文件: {expected_filename}")

            # 计算完成度
            total_videos = len(expected_files)
            downloaded_videos = len(existing_files)
            completion_rate = (
                (downloaded_videos / total_videos) * 100 if total_videos > 0 else 0
            )

            logger.info(
                f"📊 下载完成度: {downloaded_videos}/{total_videos} ({completion_rate:.1f}%)"
            )

            # 如果完成度达到95%以上，认为已经下载完成
            if completion_rate >= 95:
                logger.info(f"✅ 播放列表已完整下载 ({completion_rate:.1f}%)")

                # 计算分辨率信息
                resolution = ', '.join(sorted(all_resolutions)) if all_resolutions else '未知'
                if existing_files:
                    try:
                        import subprocess

                        first_file_path = existing_files[0]["path"]
                        result = subprocess.run(
                            [
                                "ffprobe",
                                "-v",
                                "quiet",
                                "-print_format",
                                "json",
                                "-show_streams",
                                first_file_path,
                            ],
                            capture_output=True,
                            text=True,
                        )
                        if result.returncode == 0:
                            import json

                            data = json.loads(result.stdout)
                            for stream in data.get("streams", []):
                                if stream.get("codec_type") == "video":
                                    width = stream.get("width", 0)
                                    height = stream.get("height", 0)
                                    if width and height:
                                        resolution = f"{width}x{height}"
                                        break
                    except Exception as e:
                        logger.warning(f"无法获取视频分辨率: {e}")

                return {
                    "already_downloaded": True,
                    "playlist_title": playlist_title_with_id,  # 使用实际的目录名作为标题
                    "video_count": downloaded_videos,
                    "total_videos": total_videos,
                    "completion_rate": completion_rate,
                    "download_path": str(playlist_path),
                    "total_size_mb": total_size_mb,
                    "resolution": resolution,
                    "downloaded_files": existing_files,
                    "missing_files": missing_files,
                }
            else:
                logger.info(f"📥 播放列表未完整下载 ({completion_rate:.1f}%)")
                return {
                    "already_downloaded": False,
                    "reason": f"完成度不足 ({completion_rate:.1f}%)",
                    "downloaded_videos": downloaded_videos,
                    "total_videos": total_videos,
                    "completion_rate": completion_rate,
                    "missing_files": missing_files,
                }

        except Exception as e:
            logger.error(f"❌ 检查播放列表下载状态时出错: {e}")
            return {"already_downloaded": False, "reason": f"检查失败: {str(e)}"}

    def _convert_cookies_to_json(self, cookies_path: str) -> dict:
        """将 Netscape 格式的 cookies 转换为 gallery-dl 支持的 JSON 格式"""
        try:
            import http.cookiejar

            # 创建 cookie jar 并加载 cookies
            cookie_jar = http.cookiejar.MozillaCookieJar(cookies_path)
            cookie_jar.load()

            # 转换为字典格式
            cookies_dict = {}
            for cookie in cookie_jar:
                cookies_dict[cookie.name] = cookie.value

            logger.info(f"✅ 成功转换 cookies，共 {len(cookies_dict)} 个")
            return cookies_dict

        except Exception as e:
            logger.error(f"❌ cookies 转换失败: {e}")
            return {}

    async def download_with_gallery_dl(
        self, url: str, download_path: Path, message_updater=None
    ) -> Dict[str, Any]:
        """使用 gallery-dl 下载图片"""
        if not GALLERY_DL_AVAILABLE:
            return {
                "success": False,
                "error": "gallery-dl 未安装，无法下载图片。请运行: pip install gallery-dl"
            }

        try:
            # 确保下载目录存在
            download_path.mkdir(parents=True, exist_ok=True)
            download_path_str = str(download_path)

            # 使用我们创建的 gallery-dl.conf 配置文件 - 与容器中完全一致
            config_path = Path(self.download_path / "gallery-dl.conf")
            if config_path.exists():
                logger.info(f"📄 使用 gallery-dl.conf 配置文件: {config_path}")
                # 加载配置文件 - 与容器中完全一致
                gallery_dl.config.load([str(config_path)])
            else:
                logger.warning(f"⚠️ gallery-dl.conf 配置文件不存在: {config_path}")
                return {
                    "success": False,
                    "error": "gallery-dl.conf 配置文件不存在"
                }

            # 获取 gallery-dl 实际使用的下载目录
            try:
                # 直接从配置文件中读取 base-directory
                import json
                if config_path.exists():
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config_data = json.load(f)
                    actual_download_dir = config_data.get("base-directory", str(download_path))
                else:
                    actual_download_dir = str(download_path)
                logger.info(f"🎯 gallery-dl 实际下载目录: {actual_download_dir}")
            except Exception as e:
                logger.warning(f"⚠️ 无法从配置文件读取下载目录: {e}")
                actual_download_dir = str(download_path)
                logger.info(f"🎯 使用默认下载目录: {actual_download_dir}")

            # 记录下载前的文件
            actual_download_path = Path(actual_download_dir)
            before_files = set()
            if actual_download_path.exists():
                for file_path in actual_download_path.rglob("*"):
                    if file_path.is_file():
                        relative_path = str(file_path.relative_to(actual_download_path))
                        before_files.add(relative_path)

            logger.info(f"📊 下载前文件数量: {len(before_files)}")
            if before_files:
                logger.info(f"📊 下载前文件示例: {list(before_files)[:5]}")

            # 发送开始下载消息
            if message_updater:
                try:
                    if asyncio.iscoroutinefunction(message_updater):
                        await message_updater("🖼️ **图片下载中**\n📝 当前下载：准备中...\n🖼️ 已完成：0 张")
                    else:
                        message_updater("🖼️ **图片下载中**\n📝 当前下载：准备中...\n🖼️ 已完成：0 张")
                except Exception as e:
                    logger.warning(f"⚠️ 发送开始消息失败: {e}")

            # 创建进度监控任务
            progress_task = None
            if message_updater:
                progress_task = asyncio.create_task(self._monitor_gallery_dl_progress(
                    actual_download_path, before_files, message_updater
                ))

            # 使用正确的 gallery-dl API - 与容器中完全一致
            job = gallery_dl.job.DownloadJob(url, None)

            logger.info("📸 gallery-dl 开始下载...")

            # 添加重试机制
            max_retries = 3
            retry_count = 0

            while retry_count < max_retries:
                try:
                    # 在异步执行器中运行同步的 job.run()，让进度监控能够持续运行
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, job.run)

                    logger.info("📸 gallery-dl 下载任务完成")
                    break  # 成功完成，跳出重试循环

                except Exception as e:
                    retry_count += 1
                    error_str = str(e).lower()

                    if ("403" in error_str or "forbidden" in error_str) and retry_count < max_retries:
                        logger.warning(f"⚠️ 遇到 403 错误，第 {retry_count} 次重试...")
                        await asyncio.sleep(10)  # 等待10秒后重试
                        continue
                    else:
                        # 其他错误或重试次数用完，抛出异常
                        raise e

            # 等待一下确保文件写入完成
            await asyncio.sleep(3)

            # 取消进度监控任务
            if progress_task:
                progress_task.cancel()
                try:
                    await progress_task
                except asyncio.CancelledError:
                    logger.info("📊 进度监控任务已取消")
                    pass

            # 查找新下载的文件（在 gallery-dl 实际下载目录中）
            downloaded_files = []
            total_size_bytes = 0
            file_formats = set()

            logger.info(f"🔍 开始查找新下载的文件...")
            logger.info(f"🔍 查找目录: {actual_download_dir}")
            logger.info(f"🔍 下载前文件数量: {len(before_files)}")

            if actual_download_path.exists():
                # 获取当前所有文件
                current_files = set()
                for file_path in actual_download_path.rglob("*"):
                    if file_path.is_file():
                        relative_path = str(file_path.relative_to(actual_download_path))
                        current_files.add(relative_path)

                logger.info(f"🔍 当前文件数量: {len(current_files)}")

                # 计算新文件
                new_files = current_files - before_files
                logger.info(f"🔍 新文件数量: {len(new_files)}")

                # 记录一些新文件作为示例
                if new_files:
                    sample_files = list(new_files)[:5]  # 前5个文件
                    logger.info(f"🔍 新文件示例: {sample_files}")

                    # 直接处理新文件，不需要额外遍历
                    for relative_path in new_files:
                        file_path = actual_download_path / relative_path
                        if file_path.is_file():
                            # 检查是否为图片或视频文件
                            if file_path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.mp4', '.mov', '.avi', '.mkv']:
                                downloaded_files.append(file_path)
                                try:
                                    file_size = file_path.stat().st_size
                                    total_size_bytes += file_size
                                    file_formats.add(file_path.suffix.lower())
                                    logger.info(f"✅ 找到下载文件: {relative_path} ({file_size} bytes)")
                                except OSError as e:
                                    logger.warning(f"无法获取文件大小: {file_path} - {e}")
                else:
                    # 如果没有找到新文件，尝试查找最近修改的文件
                    logger.warning(f"⚠️ 没有找到新文件，尝试查找最近修改的文件...")
                    try:
                        recent_files = []
                        for file_path in actual_download_path.rglob("*"):
                            if file_path.is_file():
                                # 检查文件修改时间是否在最近5分钟内
                                file_mtime = file_path.stat().st_mtime
                                if time.time() - file_mtime < 300:  # 5分钟
                                    recent_files.append(file_path)

                        logger.info(f"🔍 最近5分钟内修改的文件数量: {len(recent_files)}")
                        if recent_files:
                            logger.info(f"🔍 最近修改的文件示例: {[f.name for f in recent_files[:3]]}")
                            # 将这些最近修改的文件作为下载的文件
                            for file_path in recent_files:
                                if file_path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.mp4', '.mov', '.avi', '.mkv']:
                                    downloaded_files.append(file_path)
                                    try:
                                        file_size = file_path.stat().st_size
                                        total_size_bytes += file_size
                                        file_formats.add(file_path.suffix.lower())
                                        logger.info(f"✅ 找到最近修改的文件: {file_path.name} ({file_size} bytes)")
                                    except OSError as e:
                                        logger.warning(f"无法获取文件大小: {file_path} - {e}")
                    except Exception as e:
                        logger.error(f"❌ 查找最近修改文件时出错: {e}")
            else:
                logger.warning(f"⚠️ 下载目录不存在: {actual_download_dir}")

            logger.info(f"🔍 最终找到的下载文件数量: {len(downloaded_files)}")

            if downloaded_files:
                # 计算总大小
                size_mb = total_size_bytes / (1024 * 1024)

                # 格式化文件格式显示
                format_str = ", ".join(sorted(file_formats)) if file_formats else "未知格式"

                # 生成详细的结果信息
                result = {
                    "success": True,
                    "message": f"✅ 图片下载完成！\n\n🖼️ 图片数量：{len(downloaded_files)} 张\n📝 保存位置：{actual_download_dir}\n💾 总大小：{size_mb:.1f} MB\n📄 文件格式：{format_str}",
                    "files_count": len(downloaded_files),
                    "failed_count": 0,
                    "files": [str(f) for f in downloaded_files],
                    "size_mb": size_mb,
                    "filename": downloaded_files[0].name if downloaded_files else "未知文件",
                    "download_path": actual_download_dir,
                    "full_path": str(downloaded_files[0]) if downloaded_files else "",
                    "resolution": "图片",
                    "abr": None,
                    "file_formats": list(file_formats)
                }

                logger.info(f"✅ gallery-dl 下载成功: {len(downloaded_files)} 个文件, 总大小: {size_mb:.1f} MB")
                return result
            else:
                logger.warning(f"⚠️ 未找到新下载的文件，查找目录: {actual_download_dir}")
                logger.warning(f"⚠️ 下载前文件数量: {len(before_files)}")
                return {
                    "success": False,
                    "error": "未找到下载的文件"
                }

        except Exception as e:
            logger.error(f"gallery-dl 下载失败: {e}")

            # 特殊处理不同类型的错误
            error_str = str(e).lower()
            if "403" in error_str or "forbidden" in error_str:
                error_msg = (
                    f"❌ 访问被拒绝 (403 Forbidden)\n\n"
                    f"可能的原因：\n"
                    f"1. 服务器检测到爬虫行为\n"
                    f"2. IP地址被临时封禁\n"
                    f"3. 需要特定的请求头或cookies\n"
                    f"4. 内容需要登录才能访问\n\n"
                    f"建议解决方案：\n"
                    f"1. 等待几分钟后重试\n"
                    f"2. 检查cookies文件是否有效\n"
                    f"3. 尝试使用代理\n"
                    f"4. 联系管理员获取帮助"
                )
            elif "nsfw" in error_str or "authorizationerror" in error_str:
                error_msg = (
                    f"❌ NSFW内容下载失败\n\n"
                    f"请确保：\n"
                    f"1. 已配置有效的X cookies文件路径\n"
                    f"2. X账户允许查看NSFW内容\n"
                    f"3. 账户已完成年龄验证\n"
                    f"4. cookies文件格式正确（Netscape格式）\n"
                    f"5. cookies文件包含有效的认证信息"
                )
            elif "timeout" in error_str or "connection" in error_str:
                error_msg = (
                    f"❌ 网络连接超时\n\n"
                    f"可能的原因：\n"
                    f"1. 网络连接不稳定\n"
                    f"2. 服务器响应慢\n"
                    f"3. 防火墙阻止连接\n\n"
                    f"建议解决方案：\n"
                    f"1. 检查网络连接\n"
                    f"2. 稍后重试\n"
                    f"3. 尝试使用代理"
                )
            else:
                error_msg = f"❌ gallery-dl 下载失败: {str(e)}"

            return {
                "success": False,
                "error": error_msg
            }

    async def _monitor_gallery_dl_progress(self, download_path: Path, before_files: set, message_updater):
        """监控 gallery-dl 下载进度"""
        try:
            last_count = 0
            last_update_time = time.time()
            update_interval = 3  # 每3秒更新一次进度

            logger.info(f"📊 开始监控 gallery-dl 进度")
            logger.info(f"📊 监控目录: {download_path}")
            logger.info(f"📊 下载前文件数量: {len(before_files)}")
            if before_files:
                logger.info(f"📊 下载前文件示例: {list(before_files)[:3]}")

            while True:
                await asyncio.sleep(2)  # 每2秒检查一次

                # 计算当前文件数量
                current_files = set()
                if download_path.exists():
                    for file_path in download_path.rglob("*"):
                        if file_path.is_file():
                            relative_path = str(file_path.relative_to(download_path))
                            current_files.add(relative_path)

                # 计算新文件数量
                new_files = current_files - before_files
                current_count = len(new_files)

                logger.info(f"📊 当前文件数量: {len(current_files)}, 新文件数量: {current_count}")
                if new_files:
                    logger.info(f"📊 新文件示例: {list(new_files)[:3]}")

                # 如果文件数量有变化或时间间隔到了，更新进度
                if current_count != last_count or time.time() - last_update_time > update_interval:
                    last_count = current_count
                    last_update_time = time.time()

                    # 获取当前正在下载的文件路径
                    current_file_path = "准备中..."
                    if new_files:
                        # 获取最新的文件
                        latest_file = sorted(new_files)[-1]
                        # 显示完整的相对路径
                        current_file_path = latest_file

                    progress_text = (
                        f"🖼️ **图片下载中**\n"
                        f"📝 当前下载：{current_file_path}\n"
                        f"🖼️ 已完成：{current_count} 张"
                    )

                    try:
                        # 检查message_updater是否为None
                        if message_updater is None:
                            logger.warning(f"⚠️ message_updater为None，跳过进度更新")
                            continue

                        # 检查message_updater的类型并安全调用
                        if asyncio.iscoroutinefunction(message_updater):
                            await message_updater(progress_text)
                        else:
                            message_updater(progress_text)
                        logger.info(f"📊 gallery-dl 进度更新: {current_count} 张图片, 当前文件: {current_file_path}")
                    except Exception as e:
                        logger.warning(f"⚠️ 更新进度消息失败: {e}")
                        # 不退出循环，继续监控
                        continue

        except asyncio.CancelledError:
            logger.info("📊 进度监控任务已取消")
        except Exception as e:
            logger.error(f"❌ 进度监控任务错误: {e}")

    async def download_x_content(self, url: str, message: types.Message) -> dict:
        """下载 X 内容（图片或视频）"""
        logger.info(f"🚀 开始下载 X 内容: {url}")

        # 检测内容类型
        content_type = self._detect_x_content_type(url)
        logger.info(f"📊 检测到内容类型: {content_type}")

        if content_type == "video":
            # 视频使用 yt-dlp 下载
            logger.info("🎬 使用 yt-dlp 下载 X 视频")

            # 创建 message_updater 函数
            async def message_updater(text_or_dict):
                try:
                    if isinstance(text_or_dict, dict):
                        await message.reply(str(text_or_dict))
                    else:
                        await message.reply(text_or_dict)
                except Exception as e:
                    logger.warning(f"⚠️ 更新进度消息失败: {e}")

            return await self._download_x_video_with_ytdlp(url, message_updater)
        else:
            # 图片使用 gallery-dl 下载
            logger.info("📸 使用 gallery-dl 下载 X 图片")
            return await self._download_x_image_with_gallerydl(url, message)

    async def _download_x_video_with_ytdlp(self, url: str, message_updater=None) -> dict:
        """使用 yt-dlp 下载 X 视频"""
        return await self._download_with_ytdlp_unified(
            url=url,
            download_path=self.x_download_path,
            message_updater=message_updater,
            platform_name="X",
            content_type="video",
            format_spec="bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            cookies_path=self.x_cookies_path
        )



    async def _download_x_playlist(self, url: str, download_path: Path, message_updater=None, playlist_info: dict = None) -> Dict[str, Any]:
        """下载X播放列表中的所有视频"""
        import os
        import time
        from pathlib import Path
        import asyncio

        logger.info(f"🎬 开始下载X播放列表: {url}")
        logger.info(f"📊 播放列表信息: {playlist_info}")

        if not playlist_info:
            return {'success': False, 'error': '播放列表信息为空'}

        total_videos = playlist_info.get('total_videos', 0)
        if total_videos == 0:
            return {'success': False, 'error': '播放列表中没有视频'}

        # 记录下载开始时间
        download_start_time = time.time()
        logger.info(f"⏰ 下载开始时间: {download_start_time}")

        # 创建进度跟踪
        progress_data = {
            'current': 0,
            'total': total_videos,
            'start_time': download_start_time,
            'downloaded_files': []
        }

        # 记录下载开始时间
        download_start_time = time.time()
        logger.info(f"⏰ 下载开始时间: {download_start_time}")

        def create_playlist_progress_callback(progress_data):
            def escape_num(text):
                # 只转义MarkdownV2特殊字符，不转义小数点
                special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
                for char in special_chars:
                    text = text.replace(char, f'\\{char}')
                return text

            def calculate_overall_progress():
                if not progress_data or not isinstance(progress_data, dict) or progress_data['total'] == 0:
                    return 0
                return (progress_data['current'] / progress_data['total']) * 100

            def progress_callback(d):
                try:
                    if not progress_data or not isinstance(progress_data, dict):
                        return
                    current = progress_data['current']
                    total = progress_data['total']
                    overall_percent = calculate_overall_progress()

                    if d.get('status') == 'finished':
                        progress_data['current'] += 1
                        current = progress_data['current']
                        overall_percent = calculate_overall_progress()

                        # 记录下载的文件并监控合并状态
                        if 'filename' in d:
                            filename = d['filename']
                            if 'downloaded_files' not in progress_data:
                                progress_data['downloaded_files'] = []
                            progress_data['downloaded_files'].append(filename)

                            # 监控文件合并状态
                            if filename.endswith('.part'):
                                logger.warning(f"⚠️ 文件合并可能失败: {filename}")
                            else:
                                logger.info(f"✅ 文件下载并合并成功: {filename}")

                    # 创建进度消息
                    progress_bar = self._make_progress_bar(overall_percent)
                    elapsed_time = time.time() - (progress_data['start_time'] if progress_data and isinstance(progress_data, dict) else time.time())

                    status_text = f"🎬 X播放列表下载进度\n"
                    status_text += f"📊 总体进度: {progress_bar} {overall_percent:.1f}%\n"
                    status_text += f"📹 当前: {current}/{total} 个视频\n"
                    status_text += f"⏱️ 已用时: {elapsed_time:.0f}秒\n"

                    if d.get('status') == 'downloading':
                        if '_percent_str' in d:
                            status_text += f"📥 当前视频: {d.get('_percent_str', '0%')}\n"
                        if '_speed_str' in d:
                            status_text += f"🚀 速度: {d.get('_speed_str', 'N/A')}\n"

                    # 转义Markdown特殊字符
                    escaped_text = escape_num(status_text)

                    # 使用asyncio.run_coroutine_threadsafe来更新进度
                    try:
                        if message_updater:
                            # 检查message_updater的类型
                            if asyncio.iscoroutinefunction(message_updater):
                                # 安全地获取事件循环
                                try:
                                    loop = asyncio.get_running_loop()
                                except RuntimeError:
                                    try:
                                        loop = asyncio.get_event_loop()
                                    except RuntimeError:
                                        loop = asyncio.new_event_loop()
                                        asyncio.set_event_loop(loop)

                                # 调用异步函数并获取协程对象
                                coro = message_updater(escaped_text)
                                asyncio.run_coroutine_threadsafe(coro, loop)
                            else:
                                # 如果是同步函数，直接调用
                                message_updater(escaped_text)
                    except Exception as e:
                        if "Message is not modified" not in str(e):
                            logger.warning(f"⚠️ 更新播放列表进度失败: {e}")
                        # 如果message_updater失败，记录日志
                        logger.info(f"进度更新: {escaped_text}")

                except Exception as e:
                    logger.warning(f"⚠️ 更新播放列表进度失败: {e}")

            return progress_callback

        try:
            # 使用增强的yt-dlp配置下载整个播放列表
            # 根据设置决定是否在文件名添加视频ID
            if hasattr(self, 'bot') and hasattr(self.bot, 'youtube_id_tags') and self.bot.youtube_id_tags:
                outtmpl = str(download_path / '%(title)s[%(id)s].%(ext)s')
            else:
                outtmpl = str(download_path / '%(title)s.%(ext)s')

            base_opts = {
                'outtmpl': outtmpl,
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'progress_hooks': [create_playlist_progress_callback(progress_data)],
            }

            # 获取增强配置，避免PART文件
            ydl_opts = self._get_enhanced_ydl_opts(base_opts)
            logger.info("🛡️ 使用增强配置，避免PART文件产生")

            # 确保为X链接添加正确的cookies（覆盖增强配置中的通用cookies）
            if (
                self.is_x_url(url)
                and self.x_cookies_path
                and os.path.exists(self.x_cookies_path)
            ):
                ydl_opts["cookiefile"] = self.x_cookies_path
                logger.info(f"🍪 为X播放列表添加cookies: {self.x_cookies_path}")
            elif self.is_x_url(url):
                logger.warning("⚠️ 检测到X播放列表但未设置cookies文件")
                logger.warning("⚠️ NSFW内容需要登录才能下载")
                if self.x_cookies_path:
                    logger.warning(f"⚠️ X cookies文件不存在: {self.x_cookies_path}")
                else:
                    logger.warning("⚠️ 未设置X_COOKIES环境变量")
                logger.warning("💡 请设置X_COOKIES环境变量指向cookies文件路径")

            # 下载播放列表
            loop = asyncio.get_running_loop()
            try:
                await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).download([url]))

                # 下载完成后检查并处理PART文件
                logger.info("🔍 检查下载完成状态...")
                resume_success = self._resume_failed_downloads(download_path, url, max_retries=5)

                if not resume_success:
                    logger.warning("⚠️ 部分文件下载未完成，但已达到最大重试次数")
                else:
                    logger.info("✅ 所有文件下载完成")

            except Exception as e:
                logger.error(f"❌ 下载过程中出现错误: {e}")
                # 即使出错也尝试断点续传PART文件
                logger.info("🔄 尝试断点续传未完成的文件...")
                self._resume_part_files(download_path, url)

            await asyncio.sleep(1)

            # 使用progress_data中记录的文件列表来检测下载的文件
            video_files = []
            downloaded_files = progress_data.get('downloaded_files', []) if progress_data and isinstance(progress_data, dict) else []
            logger.info(f"📊 progress_data中记录的文件: {downloaded_files}")

            # 首先尝试使用progress_data中记录的文件
            if downloaded_files:
                for filename in downloaded_files:
                    file_path = download_path / filename
                    if file_path.exists():
                        video_files.append((file_path, os.path.getmtime(file_path)))
                        logger.info(f"✅ 找到本次下载文件: {filename}")
                    else:
                        logger.warning(f"⚠️ 文件不存在: {filename}")

            # 如果progress_data中没有记录，则使用时间检测
            if not video_files:
                logger.info("🔄 使用时间检测方法查找下载文件")
                for file in download_path.glob("*.mp4"):
                    try:
                        mtime = os.path.getmtime(file)
                        # 如果文件修改时间在下载开始时间之后，认为是本次下载的文件
                        if mtime >= download_start_time:
                            video_files.append((file, mtime))
                            logger.info(f"✅ 找到本次下载文件: {file.name}, 修改时间: {mtime}")
                    except OSError:
                        continue

            video_files.sort(key=lambda x: x[0].name)

            # 检测PART文件
            part_files = self._detect_part_files(download_path)
            success_count = len(video_files)
            part_count = len(part_files)

            # 在日志中显示详细统计
            logger.info(f"📊 下载完成统计：")
            logger.info(f"✅ 成功文件：{success_count} 个")
            if part_count > 0:
                logger.warning(f"⚠️ 未完成文件：{part_count} 个")
                self._log_part_files_details(part_files)
            else:
                logger.info("✅ 未发现PART文件，所有下载都已完成")

            if video_files:
                total_size_mb = 0
                file_info_list = []
                all_resolutions = set()

                for file_path, mtime in video_files:
                    size_mb = os.path.getsize(file_path) / (1024 * 1024)
                    total_size_mb += size_mb
                    media_info = self.get_media_info(str(file_path))
                    resolution = media_info.get('resolution', '未知')
                    if resolution != '未知':
                        all_resolutions.add(resolution)
                    file_info_list.append({
                        'filename': os.path.basename(file_path),
                        'size_mb': size_mb,
                        'resolution': resolution,
                        'abr': media_info.get('bit_rate')
                    })

                filename_list = [info['filename'] for info in file_info_list]
                filename_display = '\n'.join([f"  {i+1:02d}. {name}" for i, name in enumerate(filename_list)])
                resolution_display = ', '.join(sorted(all_resolutions)) if all_resolutions else '未知'

                return {
                    'success': True,
                    'is_playlist': True,
                    'file_count': len(video_files),
                    'total_size_mb': total_size_mb,
                    'files': file_info_list,
                    'platform': 'X',
                    'download_path': str(download_path),
                    'filename': filename_display,
                    'size_mb': total_size_mb,
                    'resolution': resolution_display,
                    'episode_count': len(video_files),
                    # 添加PART文件统计信息
                    'success_count': success_count,
                    'part_count': part_count,
                    'part_files': [str(pf) for pf in part_files] if part_files else []
                }
            else:
                return {'success': False, 'error': 'X播放列表下载完成但未找到本次下载的文件'}

        except Exception as e:
            logger.error(f"❌ X播放列表下载失败: {e}")
            return {"success": False, "error": str(e)}
        finally:
            # 记录下载完成时间
            download_end_time = time.time()
            total_time = download_end_time - download_start_time
            logger.info(f"⏰ 下载完成时间: {download_end_time}, 总用时: {total_time:.1f}秒")

    async def _download_x_image_with_gallerydl(self, url: str, message: types.Message) -> dict:
        """使用 gallery-dl 下载 X 图片，遇到NSFW错误时fallback到yt-dlp"""
        try:
            # 创建 message_updater 函数
            async def message_updater(text_or_dict):
                try:
                    if isinstance(text_or_dict, dict):
                        await message.reply(str(text_or_dict))
                    else:
                        await message.reply(text_or_dict)
                except Exception as e:
                    logger.warning(f"⚠️ 更新进度消息失败: {e}")

            # 使用现有的 download_with_gallery_dl 函数，传递 message_updater
            download_path = self.x_download_path
            result = await self.download_with_gallery_dl(url, download_path, message_updater)

            if result.get("success"):
                return {
                    "success": True,
                    "platform": "X",
                    "content_type": "image",
                    "download_path": result.get("download_path", ""),
                    "full_path": result.get("full_path", ""),
                    "filename": result.get("filename", ""),
                    "size_mb": result.get("size_mb", 0),
                    "title": f"X图片 ({result.get('files_count', 0)}张)",
                    "resolution": "图片",  # 添加 resolution 字段，确保识别为图片
                    "files_count": result.get("files_count", 0),
                    "file_formats": result.get("file_formats", []),
                }
            else:
                # 检查是否为NSFW错误，如果是则返回错误信息
                error_msg = result.get("error", "")
                if "NSFW" in error_msg or "AuthorizationError" in error_msg:
                    logger.info("🔄 检测到NSFW错误，gallery-dl无法下载此内容")
                    return {
                        "success": False,
                        "error": "此内容包含NSFW内容，无法下载",
                        "platform": "X",
                        "content_type": "image"
                    }
                else:
                    return result

        except Exception as e:
            logger.error(f"❌ gallery-dl 下载 X 图片失败: {e}")
            return {
                "success": False,
                "error": f"gallery-dl 下载失败: {str(e)}",
                "platform": "X",
                "content_type": "image"
            }



    async def _download_xiaohongshu_image_with_downloader(self, url: str, message_updater=None) -> dict:
        """使用 xiaohongshu_downloader.py 下载小红书图片"""
        try:
            # 导入小红书下载器
            from xiaohongshu_downloader import XiaohongshuDownloader
            
            # 创建下载器实例
            downloader = XiaohongshuDownloader()
            
            # 小红书图片下载目录
            download_dir = str(self.xiaohongshu_download_path)
            os.makedirs(download_dir, exist_ok=True)
            
            logger.info(f"🖼️ 使用 xiaohongshu_downloader 下载小红书图片: {url}")
            
            # 创建进度回调函数
            async def progress_callback(text):
                if message_updater:
                    try:
                        logger.info(f"📱 小红书进度回调收到消息: {text}")
                        
                        # 检查消息类型，区分开始下载、进度更新和完成消息
                        if "🚀 开始下载" in text:
                            logger.info("🚀 检测到开始下载消息")
                        elif "⚡ 速度: `完成`" in text:
                            logger.info("✅ 检测到下载完成消息")
                        elif "📊 进度:" in text:
                            logger.info("📊 检测到进度更新消息")
                        
                        # 移除跳过完成消息的逻辑，让xiaohongshu_downloader的完成消息正常显示
                        
                        # 检查是否为异步函数
                        if asyncio.iscoroutinefunction(message_updater):
                            # 异步函数，直接await调用
                            await message_updater(text)
                        else:
                            # 同步函数，直接调用
                            message_updater(text)
                    except Exception as e:
                        logger.warning(f"⚠️ 进度回调失败: {e}")
                        import traceback
                        logger.warning(f"⚠️ 异常堆栈: {traceback.format_exc()}")
            
            # 调用下载器
            result = downloader.download_note(url, download_dir, progress_callback)
            
            if result.get("success"):
                logger.info(f"✅ 小红书图片下载成功: {result}")
                # 从files中提取文件格式
                files = result.get("files", [])
                file_formats = set()
                for file_info in files:
                    file_path = file_info.get('path', '')
                    if file_path:
                        ext = os.path.splitext(file_path)[1].lower().lstrip('.')
                        if ext:
                            file_formats.add(ext.upper())
                file_formats = list(file_formats)
                
                return {
                    "success": True,
                    "title": result.get("title", "小红书图片"),
                    "author": result.get("author", "未知作者"),
                    "files_count": len(result.get("files", [])),
                    "total_size_mb": result.get("total_size", 0) / (1024 * 1024),
                    "download_path": result.get("save_dir", download_dir),
                    "files": result.get("files", []),
                    "file_formats": file_formats,
                    "platform": "Xiaohongshu",
                    "content_type": "image"
                }
            else:
                logger.error(f"❌ 小红书图片下载失败: {result.get('error')}")
                return {
                    "success": False,
                    "error": result.get("error", "未知错误"),
                    "platform": "Xiaohongshu",
                    "content_type": "image"
                }
                
        except Exception as e:
            logger.error(f"❌ 下载小红书图片失败: {e}")
            return {
                "success": False,
                "error": f"下载小红书图片失败: {str(e)}",
                "platform": "Xiaohongshu",
                "content_type": "image"
            }

    async def _download_xiaohongshu_with_playwright(self, url: str, message: types.Message, message_updater=None) -> dict:
        """使用 Playwright 下载小红书视频"""
        # 自动提取小红书链接
        real_url = extract_xiaohongshu_url(url)
        if real_url:
            url = real_url
        else:
            logger.warning('未检测到小红书链接，原样使用参数')
        if not PLAYWRIGHT_AVAILABLE:
            return {
                "success": False,
                "error": "Playwright 未安装，无法下载小红书视频",
                "platform": "Xiaohongshu",
                "content_type": "video"
            }

        try:
            from playwright.async_api import async_playwright
            import httpx
            from dataclasses import dataclass
            from typing import Optional
            from enum import Enum
            import re
            import time

            # 数据类定义
            @dataclass
            class VideoInfo:
                video_id: str
                platform: str
                share_url: str
                download_url: Optional[str] = None
                title: Optional[str] = None
                author: Optional[str] = None
                create_time: Optional[str] = None
                quality: Optional[str] = None
                thumbnail_url: Optional[str] = None

            # 使用类级别的 Platform 枚举

            # 检测平台
            def detect_platform(url: str) -> VideoDownloader.Platform:
                if any(domain in url.lower() for domain in ['douyin.com', 'iesdouyin.com']):
                    return VideoDownloader.Platform.DOUYIN
                elif any(domain in url.lower() for domain in ['kuaishou.com']):
                    return VideoDownloader.Platform.KUAISHOU
                elif any(domain in url.lower() for domain in ['xiaohongshu.com', 'xhslink.com']):
                    return VideoDownloader.Platform.XIAOHONGSHU
                else:
                    return VideoDownloader.Platform.UNKNOWN

            platform = VideoDownloader.Platform.XIAOHONGSHU

            # 发送开始下载消息（如果bot可用）
            start_message = None
            if hasattr(self, 'bot') and self.bot:
                try:
                    start_message = await self.bot.send_message(
                        message.chat.id,
                        f"🎬 开始下载{platform.value}视频..."
                    )
                except Exception as e:
                    logger.warning(f"⚠️ 发送开始消息失败: {e}")
            else:
                logger.info(f"🎬 开始下载{platform.value}视频...")

            # 小红书下载目录
            download_dir = str(self.xiaohongshu_download_path)

            os.makedirs(download_dir, exist_ok=True)

            # 使用 Playwright 提取视频信息
            async with async_playwright() as p:
                # 小红书不需要 cookies

                # 小红书浏览器配置 - 参考douyin.py
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080},
                    device_scale_factor=1,
                    locale='zh-CN',
                    timezone_id='Asia/Shanghai',
                    is_mobile=False,
                    has_touch=False,
                    color_scheme='light',
                    extra_http_headers={
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,video/mp4,*/*;q=0.8',
                        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                    }
                )

                # 小红书不需要 cookies

                page = await context.new_page()

                # 设置平台特定的请求头
                await self._set_platform_headers(page, platform)

                # 监听网络请求，捕获小红书视频URL
                video_url_holder = {'url': None}
                def handle_request(request):
                    req_url = request.url
                    if any(ext in req_url.lower() for ext in ['.mp4', '.m3u8']):
                        if 'xhscdn.com' in req_url or 'xiaohongshu.com' in req_url:
                            # 只保存第一个捕获到的视频URL，避免被后续请求覆盖
                            if not video_url_holder['url']:
                                video_url_holder['url'] = req_url
                                logger.info(f"[cat-catch] 嗅探到小红书视频流: {req_url}")
                page.on("request", handle_request)

                # 访问页面 - 参考douyin.py的实现
                logger.info("[extract] goto 前")
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                logger.info("[extract] goto 后，开始极速嗅探")

                # 极速嗅探：只监听network，不做任何交互 - 参考douyin.py
                for _ in range(5):  # 1.5秒内监听
                    if video_url_holder['url']:
                        logger.info(f"[cat-catch][fast] 极速嗅探到小红书视频流: {video_url_holder['url']}")
                        # 立即获取标题和作者，参考douyin.py
                        title = await self._get_video_title(page, platform)
                        author = await self._get_video_author(page, platform)
                        # 直接返回结果，不继续后续逻辑
                        video_info = VideoInfo(
                            video_id=str(int(time.time())),
                            platform=platform.value,
                            share_url=url,
                            download_url=video_url_holder['url'],
                            title=title,
                            author=author)
                        logger.info("[cat-catch][fast] 极速嗅探流程完成")
                        # 关闭浏览器
                        await page.close()
                        await context.close()
                        await browser.close()

                        # 下载视频
                        return await self._download_video_file(video_info, download_dir, message_updater, start_message)
                    await asyncio.sleep(0.3)
                # 兜底：未捕获到流，直接进入正则/其它逻辑（不再做自动交互）

                # 检查是否捕获到视频URL
                if not video_url_holder['url']:
                    logger.warning(f"⚠️ 网络嗅探未捕获到小红书视频流")
                else:
                    logger.info(f"✅ 网络嗅探成功捕获到小红书视频流: {video_url_holder['url']}")

                # 如果网络嗅探失败，尝试从页面提取
                if not video_url_holder['url']:
                    html = await page.content()
                    logger.info(f"🔍 开始从HTML提取小红书视频直链...")

                    # 小红书HTML正则提取 - 参考douyin.py的简化模式
                    patterns = [
                        r'(https://sns-[^"\']+\.xhscdn\.com/stream/[^"\']+\.mp4)',
                        r'(https://ci[^"\']+\.xhscdn\.com/[^"\']+\.mp4)',
                        r'(https://[^"\']+\.xhscdn\.com/[^"\']+\.mp4)',
                        r'"videoUrl":"(https://[^"\\]+)"',
                        r'"video_url":"(https://[^"\\]+)"',
                        r'"url":"(https://[^"\\]+\.mp4)"'
                    ]

                    # 直接使用HTML正则提取 - 参考douyin.py的简单方法
                    for i, pattern in enumerate(patterns):
                        m = re.search(pattern, html)
                        if m:
                            url = m.group(1).replace('\\u002F', '/').replace('\\u0026', '&')
                            # 验证URL是否有效，并且网络嗅探没有捕获到URL时才使用
                            if self._is_valid_xiaohongshu_url(url) and not video_url_holder['url']:
                                video_url_holder['url'] = url
                                logger.info(f"✅ 使用模式{i+1}提取到小红书视频URL: {url}")
                                break
                            elif self._is_valid_xiaohongshu_url(url) and video_url_holder['url']:
                                logger.info(f"⚠️ 网络嗅探已捕获到URL，跳过HTML提取的URL: {url}")
                                break

                # 如果HTML提取成功，获取标题和作者
                title = None
                author = None
                if video_url_holder['url']:
                    try:
                        title = await self._get_video_title(page, platform)
                        author = await self._get_video_author(page, platform)
                        logger.info(f"📝 获取到标题: {title}")
                        logger.info(f"👤 获取到作者: {author}")
                    except Exception as e:
                        logger.warning(f"⚠️ 获取标题和作者失败: {e}")

                # 关闭浏览器
                await page.close()
                await context.close()
                await browser.close()

                if not video_url_holder['url']:
                    # 如果仍然没有获取到视频URL，保存调试信息
                    debug_html_path = f"/tmp/xiaohongshu_debug_{int(time.time())}.html"
                    try:
                        with open(debug_html_path, 'w', encoding='utf-8') as f:
                            f.write(html)
                        logger.error(f"❌ 无法提取小红书视频直链，已保存调试HTML到: {debug_html_path}")
                    except Exception as e:
                        logger.error(f"❌ 无法提取小红书视频直链，保存调试文件失败: {e}")

                    raise Exception(f"无法提取小红书视频直链，请检查链接有效性")

                # 创建VideoInfo对象
                video_info = VideoInfo(
                    video_id=str(int(time.time())),
                    platform=platform.value,
                    share_url=url,
                    download_url=video_url_holder['url'],
                    title=title,
                    author=author)

                # 使用统一的下载方法
                result = await self._download_video_file(video_info, download_dir, message_updater, start_message)

                if not result.get("success"):
                    raise Exception(result.get("error", "下载失败"))

                # 删除开始消息（如果存在）
                if start_message and hasattr(self, 'bot') and self.bot:
                    try:
                        await start_message.delete()
                    except Exception as e:
                        logger.warning(f"⚠️ 删除开始消息失败: {e}")

                # 文件信息现在在 _download_video_file 方法中处理
                logger.info(f"✅ {platform.value}视频下载成功")

                # 返回下载结果
                return result

        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Playwright 下载小红书视频失败: {error_msg}")

            # 删除开始消息（如果存在）
            if 'start_message' in locals() and start_message and hasattr(self, 'bot') and self.bot:
                try:
                    await self.bot.delete_message(message.chat.id, start_message.message_id)
                except Exception as del_e:
                    logger.warning(f"⚠️ 删除开始消息失败: {del_e}")

            return {
                "success": False,
                "error": f"Playwright 下载失败: {error_msg}",
                "platform": "Xiaohongshu",
                "content_type": "video"
            }

    async def _extract_douyin_url_from_html(self, html: str) -> Optional[str]:
        """从抖音HTML源码中提取视频直链 - 使用简单有效的逻辑"""
        try:
            logger.info(f"[extract] HTML长度: {len(html)} 字符")

            # 查找包含视频数据的script标签
            script_matches = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)

            for script_content in script_matches:
                if 'aweme_id' in script_content and 'status_code' in script_content:
                    # 尝试提取JSON部分
                    json_matches = re.findall(r'({.*?"errors":\s*null\s*})', script_content, re.DOTALL)
                    for json_str in json_matches:
                        try:
                            # 清理JSON
                            brace_count = 0
                            json_end = -1
                            for i, char in enumerate(json_str):
                                if char == '{':
                                    brace_count += 1
                                elif char == '}':
                                    brace_count -= 1
                                    if brace_count == 0:
                                        json_end = i + 1
                                        break

                            if json_end > 0:
                                clean_json = json_str[:json_end]
                                data = json.loads(clean_json)

                                # 专门查找video字段中的无水印视频URL
                                def find_video_url(obj):
                                    if isinstance(obj, dict):
                                        for key, value in obj.items():
                                            # 专门查找video字段
                                            if key == "video" and isinstance(value, dict):
                                                logger.info(f"[extract] 找到video字段: {list(value.keys())}")

                                                # 优先查找play_url字段（无水印）
                                                if "play_url" in value:
                                                    play_url = value["play_url"]
                                                    logger.info(f"[extract] play_url字段内容: {play_url}")
                                                    logger.info(f"[extract] play_url类型: {type(play_url)}")
                                                    # 处理play_url字典格式
                                                    if isinstance(play_url, dict) and "url_list" in play_url:
                                                        url_list = play_url["url_list"]
                                                        if isinstance(url_list, list) and url_list:
                                                            video_url = url_list[0]
                                                            if video_url.startswith("http"):
                                                                logger.info(f"[extract] 从play_url.url_list找到无水印视频URL: {video_url}")
                                                                return video_url
                                                    # 处理play_url字符串格式
                                                    elif isinstance(play_url, str) and play_url.startswith("http"):
                                                        if any(ext in play_url.lower() for ext in [".mp4", ".m3u8", ".ts", "douyinvod.com", "snssdk.com"]):
                                                            logger.info(f"[extract] 找到无水印视频URL: {play_url}")
                                                            return play_url

                                                # 兜底：如果没有play_url，再查找play_addr字段（有水印）
                                                if "play_addr" in value:
                                                    play_addr = value["play_addr"]
                                                    logger.info(f"[extract] play_addr字段内容: {play_addr}")
                                                    logger.info(f"[extract] play_addr类型: {type(play_addr)}")
                                                    # 处理play_addr字典格式
                                                    if isinstance(play_addr, dict) and "url_list" in play_addr:
                                                        url_list = play_addr["url_list"]
                                                        if isinstance(url_list, list) and url_list:
                                                            video_url = url_list[0]
                                                            if video_url.startswith("http"):
                                                                logger.info(f"[extract] 从play_addr.url_list找到有水印视频URL: {video_url}")
                                                                return video_url
                                                    # 查找playAddr
                                                    if isinstance(play_addr, list) and play_addr:
                                                        video_url = play_addr[0]
                                                        if video_url.startswith("http") and any(ext in video_url.lower() for ext in [".mp4", ".m3u8", ".ts", "douyinvod.com", "snssdk.com"]):
                                                            logger.info(f"[extract] 找到有水印视频URL: {video_url}")
                                                            return video_url
                                                    elif isinstance(play_addr, str) and play_addr.startswith("http"):
                                                        if any(ext in play_addr.lower() for ext in [".mp4", ".m3u8", ".ts", "douyinvod.com", "snssdk.com"]):
                                                            logger.info(f"[extract] 找到有水印视频URL: {play_addr}")
                                                            return play_addr
                                            elif isinstance(value, (dict, list)):
                                                result = find_video_url(value)
                                                if result:
                                                    return result
                                    elif isinstance(obj, list):
                                        for item in obj:
                                            result = find_video_url(item)
                                            if result:
                                                return result
                                    return None

                                video_url = find_video_url(data)
                                if video_url:
                                    return video_url

                        except json.JSONDecodeError:
                            continue

            return None

        except Exception as e:
            logger.warning(f"抖音HTML正则提取失败: {str(e)}")
        return None

    async def _get_douyin_no_watermark_url(self, video_id: str) -> str:
        """通过抖音官方接口获取无水印视频直链"""
        try:
            # 抖音官方API列表
            apis = [
                f'https://aweme.snssdk.com/aweme/v1/play/?video_id={video_id}&ratio=1080p&line=1',
                f'https://aweme.snssdk.com/aweme/v1/play/?video_id={video_id}&ratio=720p&line=0',
                f'https://aweme.snssdk.com/aweme/v1/play/?video_id={video_id}&ratio=540p&line=2',
                f'https://aweme.snssdk.com/aweme/v1/play/?video_id={video_id}&ratio=1080p&line=0',
                f'https://aweme.snssdk.com/aweme/v1/play/?video_id={video_id}&ratio=720p&line=1',
            ]

            headers = {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
                'Accept': '*/*',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Referer': 'https://www.douyin.com/',
                'Connection': 'keep-alive',
                'Range': 'bytes=0-1',  # 只请求开头1个字节，验证可访问性
            }

            async def validate_url(api_url: str) -> Optional[str]:
                """验证单个API URL的可用性，检查content-length"""
                try:
                    async with httpx.AsyncClient(follow_redirects=True, timeout=5.0) as client:
                        # 先用 HEAD 请求快速验证
                        try:
                            head_resp = await client.head(
                                api_url,
                                headers=headers,
                                timeout=3.0
                            )
                            if head_resp.status_code in [200, 206]:
                                # 检查content-length，如果为0则认为API失效
                                content_length = int(head_resp.headers.get("content-length", 0))
                                if content_length > 0:
                                    logger.info(f"[douyin_api] HEAD请求成功: {api_url} (大小: {content_length})")
                                    return api_url
                                else:
                                    logger.warning(f"[douyin_api] HEAD请求成功但content-length为0: {api_url}")
                                    return None
                        except Exception:
                            pass  # HEAD 失败就用 GET 试试

                        # HEAD 失败的话用 GET 请求重试
                        resp = await client.get(
                            api_url,
                            headers=headers,
                            timeout=3.0
                        )
                        if resp.status_code in [200, 206]:
                            content_length = int(resp.headers.get("content-length", 0))
                            if content_length > 0:
                                logger.info(f"[douyin_api] GET请求成功: {api_url} (大小: {content_length})")
                                return api_url
                            else:
                                logger.warning(f"[douyin_api] GET请求成功但content-length为0: {api_url}")
                                return None

                except Exception as e:
                    logger.warning(f"[douyin_api] 验证失败: {api_url} - {str(e)}")
                return None

            # 最多重试2次
            for attempt in range(2):
                try:
                    logger.info(f"[douyin_api] 第{attempt + 1}次尝试验证API")
                    # 并发验证所有API
                    tasks = [validate_url(api) for api in apis]
                    results = await asyncio.gather(*tasks)

                    # 返回第一个可用的URL
                    for url in results:
                        if url:
                            logger.info(f"[douyin_api] 找到可用API: {url}")
                            return url

                    logger.warning(f"[douyin_api] 第{attempt + 1}次尝试所有API都返回0字节")
                    if attempt < 1:  # 如果不是最后一次重试
                        await asyncio.sleep(1)  # 等待1秒后重试

                except Exception as e:
                    logger.error(f"[douyin_api] 第{attempt + 1}次尝试发生错误: {str(e)}")
                    if attempt < 1:
                        await asyncio.sleep(1)

            logger.warning("[douyin_api] 所有API都返回0字节，API可能已失效")
            return None

        except Exception as e:
            logger.error(f"[douyin_api] 获取无水印直链异常: {str(e)}")
            return None

    async def _get_video_title(self, page, platform: 'VideoDownloader.Platform') -> str:
        """获取视频标题 - 针对不同平台优化"""
        try:
            # 快手特殊处理
            if platform == VideoDownloader.Platform.KUAISHOU:
                return await self._get_kuaishou_video_title(page)

            # 其他平台使用通用方法
            page_title = await page.title()
            if page_title and page_title.strip():
                logger.info(f"📝 通过<title>标签获取标题成功")
                logger.info(f"📝 原始<title> repr: {repr(page_title)}")
                clean_title = page_title.strip()
                return re.sub(r'[<>:"/\\|?*]', '_', clean_title)[:100]
        except Exception as e:
            logger.warning(f"获取标题失败: {str(e)}")
        return None

    async def _get_kuaishou_video_title(self, page) -> str:
        """专门获取快手视频标题"""
        try:
            # 方法1: 尝试从页面的JSON数据中提取标题
            html = await page.content()

            # 查找包含视频信息的script标签
            script_matches = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
            for script_content in script_matches:
                if 'caption' in script_content or 'title' in script_content:
                    # 尝试提取JSON中的标题字段
                    title_patterns = [
                        r'"caption":"([^"]+)"',
                        r'"title":"([^"]+)"',
                        r'"content":"([^"]+)"',
                        r'"text":"([^"]+)"',
                        r'"description":"([^"]+)"'
                    ]

                    for pattern in title_patterns:
                        matches = re.findall(pattern, script_content)
                        for match in matches:
                            # 清理和验证标题
                            title = match.replace('\\u002F', '/').replace('\\u0026', '&').replace('\\n', ' ').replace('\\', '')
                            title = title.strip()
                            # 过滤掉明显不是标题的内容
                            if (len(title) > 5 and len(title) < 200 and
                                not title.startswith('http') and
                                not all(c.isdigit() or c in '.-_' for c in title) and
                                '快手' not in title and 'kuaishou' not in title.lower()):
                                logger.info(f"📝 从JSON提取到快手标题: {title}")
                                return re.sub(r'[<>:"/\\|?*]', '_', title)[:100]

            # 方法2: 尝试从页面元素中提取标题
            title_selectors = [
                '.video-info-title',
                '.content-text',
                '.video-title',
                '.caption',
                '[data-testid="video-title"]',
                '.description',
                'h1', 'h2', 'h3'
            ]

            for selector in title_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    for element in elements:
                        text = await element.text_content()
                        if text and len(text.strip()) > 5 and len(text.strip()) < 200:
                            title = text.strip()
                            if (not title.startswith('http') and
                                not all(c.isdigit() or c in '.-_' for c in title)):
                                logger.info(f"📝 从元素{selector}提取到快手标题: {title}")
                                return re.sub(r'[<>:"/\\|?*]', '_', title)[:100]
                except:
                    continue

            # 方法3: 从页面title中提取，去除快手相关后缀
            page_title = await page.title()
            if page_title and page_title.strip():
                title = page_title.strip()
                # 去除快手相关的后缀
                title = re.sub(r'[-_\s]*快手[-_\s]*', '', title)
                title = re.sub(r'[-_\s]*kuaishou[-_\s]*', '', title, flags=re.IGNORECASE)
                title = re.sub(r'[-_\s]*短视频[-_\s]*', '', title)
                title = title.strip()
                if len(title) > 3:
                    logger.info(f"📝 从页面title提取快手标题: {title}")
                    return re.sub(r'[<>:"/\\|?*]', '_', title)[:100]

            logger.warning("📝 未能提取到快手视频标题")
            return None

        except Exception as e:
            logger.warning(f"获取快手标题失败: {str(e)}")
            return None

    async def _get_video_author(self, page, platform: 'VideoDownloader.Platform') -> str:
        """获取视频作者"""
        try:
            # 快手特殊处理
            if platform == VideoDownloader.Platform.KUAISHOU:
                return await self._get_kuaishou_video_author(page)

            # 其他平台使用通用方法
            selectors = {
                VideoDownloader.Platform.DOUYIN: '[data-e2e="user-name"]',
                VideoDownloader.Platform.XIAOHONGSHU: '.user-name, .author, .nickname, [data-e2e="user-name"], .user-info .name',
            }

            selector = selectors.get(platform, '.author, .username')
            author_element = await page.query_selector(selector)

            if author_element:
                return await author_element.text_content()
        except Exception as e:
            logger.warning(f"获取作者失败: {str(e)}")
        return None

    async def _get_kuaishou_video_author(self, page) -> str:
        """专门获取快手视频作者"""
        try:
            # 方法1: 从页面的JSON数据中提取作者
            html = await page.content()

            # 查找包含用户信息的script标签
            script_matches = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
            for script_content in script_matches:
                if 'user' in script_content or 'author' in script_content:
                    # 尝试提取JSON中的作者字段
                    author_patterns = [
                        r'"userName":"([^"]+)"',
                        r'"user_name":"([^"]+)"',
                        r'"nickname":"([^"]+)"',
                        r'"name":"([^"]+)"',
                        r'"author":"([^"]+)"',
                        r'"performer":"([^"]+)"'
                    ]

                    for pattern in author_patterns:
                        matches = re.findall(pattern, script_content)
                        for match in matches:
                            # 清理和验证作者名
                            author = match.replace('\\u002F', '/').replace('\\u0026', '&').replace('\\', '')
                            author = author.strip()
                            # 过滤掉明显不是作者名的内容
                            if (len(author) > 1 and len(author) < 50 and
                                not author.startswith('http') and
                                not all(c.isdigit() or c in '.-_' for c in author) and
                                author not in ['null', 'undefined', 'true', 'false']):
                                logger.info(f"👤 从JSON提取到快手作者: {author}")
                                return re.sub(r'[<>:"/\\|?*]', '_', author)[:30]

            # 方法2: 从页面元素中提取作者
            author_selectors = [
                '.user-name',
                '.author-name',
                '.nickname',
                '.username',
                '.user-info .name',
                '.profile-name',
                '[data-testid="user-name"]',
                '.creator-name'
            ]

            for selector in author_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    for element in elements:
                        text = await element.text_content()
                        if text and len(text.strip()) > 1 and len(text.strip()) < 50:
                            author = text.strip()
                            if (not author.startswith('http') and
                                not all(c.isdigit() or c in '.-_' for c in author)):
                                logger.info(f"👤 从元素{selector}提取到快手作者: {author}")
                                return re.sub(r'[<>:"/\\|?*]', '_', author)[:30]
                except:
                    continue

            logger.warning("👤 未能提取到快手视频作者")
            return None

        except Exception as e:
            logger.warning(f"获取快手作者失败: {str(e)}")
            return None

    def _is_valid_xiaohongshu_url(self, url: str) -> bool:
        """验证小红书视频URL是否有效"""
        if not url:
            return False

        url_lower = url.lower()

        # 检查是否是视频文件
        if not any(ext in url_lower for ext in ['.mp4', '.m3u8', '.ts', '.flv', '.webm']):
            return False

        # 检查是否是来自小红书的CDN
        if not any(cdn in url_lower for cdn in ['xhscdn.com', 'xiaohongshu.com']):
            return False

        # 排除一些无效的URL
        if any(x in url_lower for x in ['static', 'avatar', 'icon', 'logo', 'banner']):
            return False

        return True

    async def _set_platform_headers(self, page, platform: 'VideoDownloader.Platform'):
        """设置平台特定的请求头"""
        headers = {
            self.Platform.DOUYIN: {'Referer': 'https://www.douyin.com/'},
            self.Platform.KUAISHOU: {'Referer': 'https://www.kuaishou.com/'},
            self.Platform.XIAOHONGSHU: {'Referer': 'https://www.xiaohongshu.com/'},
        }

        if platform in headers:
            await page.set_extra_http_headers(headers[platform])
            logger.info(f"🎬 已设置 {platform.value} 平台请求头")

    async def _download_douyin_with_playwright(self, url: str, message: types.Message, message_updater=None) -> dict:
        """使用Playwright下载抖音视频 - 完全复制douyin.py的extract逻辑"""
        if not PLAYWRIGHT_AVAILABLE:
            return {
                "success": False,
                "error": "Playwright 未安装，无法下载抖音视频",
                "platform": "Douyin",
                "content_type": "video"
            }

        try:
            from playwright.async_api import async_playwright
            import httpx
            from dataclasses import dataclass
            from typing import Optional
            import re
            import time

            @dataclass
            class VideoInfo:
                video_id: str
                platform: str
                share_url: str
                download_url: Optional[str] = None
                title: Optional[str] = None
                author: Optional[str] = None
                create_time: Optional[str] = None
                quality: Optional[str] = None
                thumbnail_url: Optional[str] = None

            class Platform(str, Enum):
                DOUYIN = "douyin"
                XIAOHONGSHU = "xiaohongshu"
                UNKNOWN = "unknown"

            logger.info(f"🎬 开始下载抖音视频: {url}")

            total_start = time.time()
            platform = Platform.DOUYIN

            async with async_playwright() as p:
                # 按照douyin.py启动浏览器（无特殊参数）
                browser = await p.chromium.launch(headless=True)

                # 按照douyin.py的context配置（抖音用手机版）
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
                    viewport={'width': 375, 'height': 667},
                    device_scale_factor=2,
                    locale='zh-CN',
                    timezone_id='Asia/Shanghai',
                    is_mobile=True,
                    has_touch=True,
                    color_scheme='light',
                    extra_http_headers={
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,video/mp4,*/*;q=0.8',
                        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                    }
                )

                page = await context.new_page()

                # 尝试加载cookies（如果存在）
                if self.douyin_cookies_path and os.path.exists(self.douyin_cookies_path):
                    try:
                        cookies_dict = self._parse_douyin_cookies_file(self.douyin_cookies_path)
                        cookies = []
                        for name, value in cookies_dict.items():
                            cookies.append({
                                'name': name,
                                'value': value,
                                'domain': '.douyin.com',
                                'path': '/'
                            })
                        await context.add_cookies(cookies)
                        logger.info(f"[extract] 成功加载{len(cookies)}个cookies")
                    except Exception as e:
                        logger.warning(f"[extract] cookies加载失败: {e}")

                # 准备video_id监听
                video_id_holder = {'id': None}

                # 备用：监听网络请求中的video_id
                def handle_video_id(request):
                    request_url = request.url
                    if 'video_id=' in request_url:
                        m = re.search(r'video_id=([a-zA-Z0-9]+)', request_url)
                        if m:
                            video_id_holder['id'] = m.group(1)
                            logger.info(f"[extract] 网络请求中捕获到 video_id: {m.group(1)}")
                page.on("request", handle_video_id)

                try:
                    # 按照douyin.py设置headers
                    await self._set_platform_headers(page, platform)

                    # 处理短链接重定向（关键修复）
                    if 'v.douyin.com' in url:
                        logger.info(f"[extract] 检测到短链接，先获取重定向: {url}")
                        response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                        real_url = page.url
                        logger.info(f"[extract] 短链接重定向到: {real_url}")

                        # 提取video_id并构造标准douyin.com链接
                        import re
                        video_id_match = re.search(r'/video/(\d+)', real_url)
                        if video_id_match:
                            video_id = video_id_match.group(1)
                            standard_url = f"https://www.douyin.com/video/{video_id}"
                            logger.info(f"[extract] 转换为标准链接: {standard_url}")
                            await page.goto(standard_url, wait_until="domcontentloaded", timeout=30000)
                            logger.info(f"[extract] 访问标准链接完成")
                        else:
                            # 如果提取不到video_id，直接用重定向的URL
                            if real_url != url:
                                await page.goto(real_url, wait_until="domcontentloaded", timeout=30000)
                                logger.info(f"[extract] 重新访问真实URL完成")
                    else:
                        logger.info("[extract] goto 前")
                        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                        logger.info("[extract] goto 后，等待 video_id")

                    # 调试：检查页面是否正确加载
                    page_title = await page.title()
                    current_url = page.url
                    logger.info(f"[debug] 页面标题: {repr(page_title)}")
                    logger.info(f"[debug] 当前URL: {current_url}")

                    # 直接从URL提取video_id（最关键的修复）
                    video_id_match = re.search(r'/video/(\d+)', current_url)
                    if video_id_match:
                        video_id_holder['id'] = video_id_match.group(1)
                        logger.info(f"[extract] 从当前URL直接提取到 video_id: {video_id_holder['id']}")
                    else:
                        # 如果当前URL提取失败，从原始URL提取
                        video_id_match = re.search(r'/video/(\d+)', url)
                        if video_id_match:
                            video_id_holder['id'] = video_id_match.group(1)
                            logger.info(f"[extract] 从原始URL提取到 video_id: {video_id_holder['id']}")

                    # 按照douyin.py：抖音先等2秒
                    await asyncio.sleep(2)

                    # 按照douyin.py：等待video_id出现，最多等3秒
                    wait_start = time.time()
                    max_wait = 3  # 最多等3秒
                    while time.time() - wait_start < max_wait:
                        if video_id_holder['id']:
                            break
                        await asyncio.sleep(0.1)
                    logger.info(f"[extract] video_id 等待用时: {time.time() - wait_start:.2f}s")

                    # 如果还没有video_id，最后一次尝试从URL提取
                    if not video_id_holder['id']:
                        logger.info("[extract] 网络监听未捕获到video_id，尝试从URL直接提取")
                        # 尝试从各种可能的URL格式中提取
                        for test_url in [current_url, url]:
                            video_id_match = re.search(r'/video/(\d+)', test_url)
                            if video_id_match:
                                video_id_holder['id'] = video_id_match.group(1)
                                logger.info(f"[extract] 从URL直接提取到 video_id: {video_id_holder['id']} (来源: {test_url})")
                                break

                    video_url = None
                    # 直接使用HTML提取方式（抖音官方API已失效）
                    logger.info("[extract] 进入HTML提取流程")
                    html = await page.content()

                    # 根据平台选择不同的提取方法
                    if platform == Platform.DOUYIN:
                        video_url = await self._extract_douyin_url_from_html(html)
                    else:
                        # 通用提取方法
                        video_url = await self._extract_douyin_url_from_html(html)

                    logger.info(f"[extract] 正则提取结果: {video_url}")

                    if video_url:
                        # 如果是带水印的URL，尝试转换为无水印URL
                        if 'playwm' in video_url:
                            logger.info("[extract] 检测到带水印URL，尝试转换为无水印URL")
                            no_watermark_url = video_url.replace('playwm', 'play')
                            logger.info(f"[extract] 转换后的无水印URL: {no_watermark_url}")
                            video_url = no_watermark_url
                        # 验证URL有效性
                        is_valid = False
                        if platform == Platform.DOUYIN:
                            def is_valid_video_url(u):
                                u = u.lower()
                                # 抖音视频URL通常不包含文件扩展名，而是通过参数指定
                                # 检查是否是抖音的CDN域名
                                if any(domain in u for domain in ['aweme.snssdk.com', 'douyinvod.com', 'snssdk.com']):
                                    return True
                                # 检查是否包含视频相关参数
                                if any(param in u for param in ['video_id', 'play', 'aweme']):
                                    return True
                                # 排除一些无效的URL
                                if any(x in u for x in ['client.mp4', 'static', 'eden-cn', 'download/douyin_pc_client', 'douyin_pc_client.mp4']):
                                    return False
                                return True
                            is_valid = is_valid_video_url(video_url)
                        else:
                            # 通用验证
                            is_valid = any(ext in video_url.lower() for ext in ['.mp4', '.m3u8', '.ts', '.flv', '.webm'])

                        if is_valid:
                            logger.info(f"[extract] 正则流程命中: {video_url}")
                            title = await self._get_video_title(page, platform)
                            author = await self._get_video_author(page, platform)
                            video_info = VideoInfo(
                                video_id=str(int(time.time())),
                                platform=platform,
                                share_url=url,
                                download_url=video_url,
                                title=title,
                                author=author,
                                thumbnail_url=None
                            )
                            logger.info("[extract] 正则流程完成")

                            # 下载视频
                            download_result = await self._download_video_file(
                                video_info,
                                str(self.douyin_download_path),
                                message_updater,
                                None
                            )

                            await page.close()
                            await context.close()
                            await browser.close()
                            return download_result
                        else:
                            logger.warning(f"[extract] 提取的URL无效: {video_url}")
                            video_url = None

                    if not video_url:
                        logger.info("[extract] 所有流程均未捕获到视频数据，抛出 TimeoutError")
                        raise TimeoutError("未能捕获到视频数据")

                finally:
                    logger.info("[extract] 关闭 page/context 前")
                    await page.close()
                    await context.close()
                    logger.info("[extract] 关闭 page/context 后")

                await browser.close()

        except Exception as e:
            logger.error(f"抖音下载异常: {str(e)}")
            return {
                "success": False,
                "error": f"下载失败: {str(e)}",
                "platform": "Douyin",
                "content_type": "video"
            }

    async def _download_kuaishou_with_playwright(self, url: str, message, message_updater=None) -> dict:
        """使用Playwright下载快手视频 - 参考抖音实现"""
        if not PLAYWRIGHT_AVAILABLE:
            return {
                "success": False,
                "error": "Playwright 未安装，无法下载快手视频",
                "platform": "Kuaishou",
                "content_type": "video"
            }

        try:
            from playwright.async_api import async_playwright
            import httpx
            from dataclasses import dataclass
            from typing import Optional
            from enum import Enum
            import time
            import re

            @dataclass
            class VideoInfo:
                video_id: str
                title: str
                author: str
                download_url: str
                platform: str = "kuaishou"
                create_time: Optional[str] = None
                quality: Optional[str] = None
                thumbnail_url: Optional[str] = None

            class Platform(str, Enum):
                KUAISHOU = "kuaishou"
                DOUYIN = "douyin"
                XIAOHONGSHU = "xiaohongshu"
                UNKNOWN = "unknown"

            # 首先清理URL，提取纯链接
            clean_url = self._extract_clean_url_from_text(url)
            if not clean_url:
                return {
                    "success": False,
                    "error": "无法从文本中提取有效的快手链接",
                    "platform": "Kuaishou",
                    "content_type": "video"
                }

            logger.info(f"⚡ 开始下载快手视频: {clean_url}")
            if clean_url != url:
                logger.info(f"🔧 URL已清理: {url} -> {clean_url}")

            url = clean_url  # 使用清理后的URL

            total_start = time.time()
            platform = Platform.KUAISHOU

            async with async_playwright() as p:
                # 启动浏览器（参考抖音配置）
                browser = await p.chromium.launch(headless=True)

                # 快手使用手机版配置
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
                    viewport={'width': 375, 'height': 667},
                    device_scale_factor=2,
                    locale='zh-CN',
                    timezone_id='Asia/Shanghai',
                    permissions=['geolocation'],
                    geolocation={'latitude': 39.9042, 'longitude': 116.4074},
                    extra_http_headers={
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                        'Accept-Encoding': 'gzip, deflate, br',
                        'DNT': '1',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                    }
                )

                page = await context.new_page()

                # 尝试加载cookies（如果存在）
                if self.kuaishou_cookies_path and os.path.exists(self.kuaishou_cookies_path):
                    try:
                        cookies_dict = self._parse_kuaishou_cookies_file(self.kuaishou_cookies_path)
                        cookies = []
                        for name, value in cookies_dict.items():
                            cookies.append({
                                'name': name,
                                'value': value,
                                'domain': '.kuaishou.com',
                                'path': '/'
                            })
                        await context.add_cookies(cookies)
                        logger.info(f"[extract] 成功加载{len(cookies)}个快手cookies")
                    except Exception as e:
                        logger.warning(f"[extract] 加载快手cookies失败: {e}")

                # 监听网络请求，捕获视频ID和视频URL
                video_id_holder = {'id': None}
                video_url_holder = {'url': None}

                def handle_video_id(request):
                    req_url = request.url
                    # 快手视频ID模式
                    m = re.search(r'photoId[=:]([a-zA-Z0-9_-]+)', req_url)
                    if m and not video_id_holder['id']:
                        video_id_holder['id'] = m.group(1)
                        logger.info(f"[extract] 网络请求中捕获到快手 photo_id: {m.group(1)}")

                    # 监听视频文件请求 - 改进过滤逻辑
                    if not video_url_holder['url']:
                        # 排除日志、统计、API等非视频请求
                        exclude_patterns = [
                            'log', 'collect', 'radar', 'stat', 'track', 'analytics',
                            'api', 'rest', 'sdk', 'report', 'beacon', 'ping'
                        ]

                        # 检查是否为视频文件请求
                        is_video_request = False
                        if '.mp4' in req_url and any(domain in req_url for domain in ['kwaicdn.com', 'ksapisrv.com', 'kuaishou.com']):
                            # 确保不是日志或API请求
                            if not any(pattern in req_url.lower() for pattern in exclude_patterns):
                                is_video_request = True

                        # 或者检查是否为快手CDN的视频流
                        elif any(domain in req_url for domain in ['kwaicdn.com']) and any(ext in req_url for ext in ['.mp4', '.m3u8', '.ts']):
                            if not any(pattern in req_url.lower() for pattern in exclude_patterns):
                                is_video_request = True

                        if is_video_request:
                            video_url_holder['url'] = req_url
                            logger.info(f"[extract] 网络请求中捕获到快手视频URL: {req_url}")
                        elif any(pattern in req_url.lower() for pattern in exclude_patterns):
                            logger.debug(f"[extract] 跳过非视频请求: {req_url}")

                page.on("request", handle_video_id)

                try:
                    # 设置快手平台headers
                    await self._set_platform_headers(page, platform)

                    # 访问页面
                    logger.info(f"[extract] 开始访问快手页面: {url}")
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    logger.info(f"[extract] 页面访问完成")

                    # 等待页面加载更长时间，让JavaScript执行
                    logger.info(f"[extract] 等待页面JavaScript执行...")
                    await asyncio.sleep(5)

                    # 尝试等待视频元素出现
                    try:
                        await page.wait_for_selector('video, [data-testid*="video"], .video-player', timeout=10000)
                        logger.info(f"[extract] 检测到视频元素")
                    except:
                        logger.warning(f"[extract] 未检测到视频元素，继续处理")

                    # 尝试一些页面交互来触发视频加载
                    try:
                        # 滚动页面
                        await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                        await asyncio.sleep(1)
                        await page.evaluate('window.scrollTo(0, 0)')
                        await asyncio.sleep(1)

                        # 尝试点击播放按钮（如果存在）
                        play_selectors = [
                            '.play-button', '.video-play', '[data-testid="play"]',
                            '.player-play', 'button[aria-label*="play"]', '.play-icon'
                        ]
                        for selector in play_selectors:
                            try:
                                play_button = await page.query_selector(selector)
                                if play_button:
                                    await play_button.click()
                                    logger.info(f"[extract] 点击了播放按钮: {selector}")
                                    await asyncio.sleep(2)
                                    break
                            except:
                                continue

                        # 尝试鼠标悬停在视频区域
                        try:
                            video_area = await page.query_selector('video, .video-container, .player-container')
                            if video_area:
                                await video_area.hover()
                                await asyncio.sleep(1)
                        except:
                            pass

                    except Exception as e:
                        logger.warning(f"[extract] 页面交互失败: {e}")

                    # 再等待一段时间确保内容加载完成
                    await asyncio.sleep(3)

                    # 尝试从URL中提取photo_id
                    if not video_id_holder['id']:
                        photo_id_match = re.search(r'/short-video/([a-zA-Z0-9_-]+)', url)
                        if photo_id_match:
                            video_id_holder['id'] = photo_id_match.group(1)
                            logger.info(f"[extract] 从URL提取到快手 photo_id: {video_id_holder['id']}")

                    # 优先使用网络监听捕获的视频URL
                    video_url = video_url_holder['url']

                    if not video_url:
                        # 如果网络监听没有捕获到，从HTML中提取视频直链
                        logger.info(f"[extract] 网络监听未捕获到视频URL，尝试从HTML提取")
                        html = await page.content()
                        video_url = await self._extract_kuaishou_url_from_html(html)
                        logger.info(f"[extract] 快手HTML提取结果: {video_url}")
                    else:
                        logger.info(f"[extract] 使用网络监听捕获的视频URL: {video_url}")

                    if video_url:
                        # 获取标题和作者
                        title = await self._get_video_title(page, platform)
                        author = await self._get_video_author(page, platform)

                        # 创建视频信息对象
                        video_info = VideoInfo(
                            video_id=video_id_holder['id'] or str(int(time.time())),
                            title=title or f"快手视频_{int(time.time())}",
                            author=author or "未知作者",
                            download_url=video_url,
                            platform="kuaishou"
                        )

                        logger.info(f"[extract] 快手视频信息: 标题={video_info.title}, 作者={video_info.author}")
                        logger.info("[extract] 正则流程完成")

                        # 下载视频
                        download_result = await self._download_video_file(
                            video_info,
                            str(self.kuaishou_download_path),
                            message_updater,
                            None
                        )

                        await page.close()
                        await context.close()
                        return download_result
                    else:
                        logger.error("[extract] 未能提取到快手视频直链")
                        await page.close()
                        await context.close()
                        return {
                            "success": False,
                            "error": "未能提取到快手视频直链",
                            "platform": "Kuaishou",
                            "content_type": "video"
                        }

                except Exception as e:
                    logger.error(f"[extract] 快手页面处理异常: {str(e)}")
                    try:
                        await page.close()
                        await context.close()
                    except:
                        pass
                    logger.info("[extract] 关闭 page/context 后")

                await browser.close()

        except Exception as e:
            logger.error(f"快手下载异常: {str(e)}")
            return {
                "success": False,
                "error": f"下载失败: {str(e)}",
                "platform": "Kuaishou",
                "content_type": "video"
            }

    async def _extract_kuaishou_url_from_html(self, html: str) -> Optional[str]:
        """从快手HTML源码中提取视频直链"""
        try:
            logger.info(f"[extract] 快手HTML长度: {len(html)} 字符")

            # 先保存HTML到文件用于调试
            try:
                debug_path = '/tmp/kuaishou_debug.html'
                with open(debug_path, 'w', encoding='utf-8') as f:
                    f.write(html)
                logger.info(f"[extract] 已保存HTML到 {debug_path} 用于调试")

                # 输出HTML的前500个字符用于快速分析
                logger.info(f"[extract] HTML开头内容: {html[:500]}")

                # 检查HTML中是否包含关键词
                keywords = ['video', 'mp4', 'src', 'url', 'play', 'kwai']
                for keyword in keywords:
                    count = html.lower().count(keyword)
                    if count > 0:
                        logger.info(f"[extract] HTML中包含 '{keyword}': {count} 次")

            except Exception as e:
                logger.warning(f"[extract] 保存HTML调试文件失败: {e}")

            # 快手视频URL的正则模式 - 扩展更多模式
            patterns = [
                # 快手视频直链模式
                r'"srcNoMark":"(https://[^"]+\.mp4[^"]*)"',
                r'"playUrl":"(https://[^"]+\.mp4[^"]*)"',
                r'"videoUrl":"(https://[^"]+\.mp4[^"]*)"',
                r'"src":"(https://[^"]+\.mp4[^"]*)"',
                r'"url":"(https://[^"]+\.mp4[^"]*)"',
                # 快手CDN模式
                r'(https://[^"\']+\.kwaicdn\.com/[^"\']+\.mp4[^"\']*)',
                r'(https://[^"\']+\.kuaishou\.com/[^"\']+\.mp4[^"\']*)',
                r'(https://[^"\']+\.ksapisrv\.com/[^"\']+\.mp4[^"\']*)',
                # JSON中的视频URL
                r'"photoUrl":"(https://[^"]+\.mp4[^"]*)"',
                r'"manifest":"(https://[^"]+\.mp4[^"]*)"',
                # 通用视频URL模式
                r'(https://[^"\'>\s]+\.mp4[^"\'>\s]*)',
                # 查找包含video的JSON字段
                r'"[^"]*[Vv]ideo[^"]*":"(https://[^"]+)"',
                r'"[^"]*[Pp]lay[^"]*":"(https://[^"]+\.mp4[^"]*)"',
            ]

            for i, pattern in enumerate(patterns):
                matches = re.findall(pattern, html)
                if matches:
                    for match in matches:
                        # 清理URL
                        video_url = match.replace('\\u002F', '/').replace('\\u0026', '&').replace('\\/', '/').replace('\\', '')
                        # 验证URL格式
                        if (video_url.startswith('http') and
                            ('.mp4' in video_url or 'kwaicdn.com' in video_url or 'kuaishou.com' in video_url) and
                            len(video_url) > 20):  # 基本长度检查
                            logger.info(f"[extract] 快手模式{i+1}找到视频URL: {video_url}")
                            return video_url

            # 如果正则都失败，尝试查找script标签中的JSON数据
            logger.info("[extract] 正则模式失败，尝试解析script标签中的JSON")
            script_matches = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
            for script_content in script_matches:
                if 'mp4' in script_content or 'video' in script_content.lower():
                    # 尝试从script中提取视频URL
                    video_patterns = [
                        r'"(https://[^"]+\.mp4[^"]*)"',
                        r"'(https://[^']+\.mp4[^']*)'",
                        r'(https://[^\s"\']+\.mp4[^\s"\']*)',
                    ]
                    for pattern in video_patterns:
                        matches = re.findall(pattern, script_content)
                        for match in matches:
                            video_url = match.replace('\\u002F', '/').replace('\\u0026', '&').replace('\\/', '/').replace('\\', '')
                            if (video_url.startswith('http') and
                                ('.mp4' in video_url or 'kwaicdn.com' in video_url) and
                                len(video_url) > 20):
                                logger.info(f"[extract] 从script标签找到视频URL: {video_url}")
                                return video_url

            logger.warning("[extract] 所有快手正则模式都未匹配到视频URL")

            # 输出一些HTML片段用于调试
            if 'mp4' in html:
                mp4_contexts = []
                for match in re.finditer(r'.{0,50}mp4.{0,50}', html, re.IGNORECASE):
                    mp4_contexts.append(match.group())
                logger.info(f"[extract] HTML中包含mp4的上下文: {mp4_contexts[:3]}")  # 只显示前3个

            return None

        except Exception as e:
            logger.warning(f"快手HTML正则提取失败: {str(e)}")
        return None

    async def _download_video_file(self, video_info, download_dir, message_updater=None, start_message=None):
        """下载视频文件"""
        try:
            # 生成文件名
            if video_info.title:
                # 清理标题，去除特殊字符和平台后缀
                clean_title = self._sanitize_filename(video_info.title)
                # 小红书、抖音和快手的特殊命名逻辑
                if video_info.platform in ["xiaohongshu", "douyin", "kuaishou"]:
                    # 去掉开头的#和空格
                    clean_title = clean_title.lstrip('#').strip()
                    # 用#分割，取第一个分割后的内容（即第2个#前的内容）
                    clean_title = clean_title.split('#')[0].strip()
                    # 如果处理后标题为空，使用平台+时间戳
                    if not clean_title:
                        clean_title = f"{video_info.platform}_{int(time.time())}"
                else:
                    # 其他平台保持原有逻辑
                    clean_title = re.split(r'#', clean_title)[0].strip()
                # 去除平台后缀
                clean_title = re.sub(r'[-_ ]*(抖音|快手|小红书|YouTube|youtube)$', '', clean_title, flags=re.IGNORECASE).strip()
                filename = f"{clean_title}.mp4"
            else:
                # 如果获取标题失败，使用时间戳
                filename = f"{video_info.platform}_{int(time.time())}.mp4"

            file_path = os.path.join(download_dir, filename)

            # 小红书使用简单下载逻辑，抖音保持现有逻辑
            if video_info.platform == 'xiaohongshu':
                # 小红书：简单下载逻辑，参考douyin.py
                async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                        'Referer': 'https://www.xiaohongshu.com/'
                    }

                    logger.info(f"🎬 开始下载小红书视频: {video_info.download_url}")

                    # 先检查响应状态和头信息
                    try:
                        async with client.stream("GET", video_info.download_url, headers=headers) as resp:
                            logger.info(f"📊 HTTP状态码: {resp.status_code}")
                            logger.info(f"📊 响应头: {dict(resp.headers)}")

                            total = int(resp.headers.get("content-length", 0))
                            logger.info(f"📊 文件大小: {total} bytes")

                            if resp.status_code != 200:
                                logger.error(f"❌ HTTP状态码错误: {resp.status_code}")
                                # 读取错误响应内容
                                error_content = await resp.aread()
                                logger.error(f"❌ 错误响应内容: {error_content[:500]}")
                                raise Exception(f"HTTP状态码错误: {resp.status_code}")

                            with open(file_path, "wb") as f:
                                downloaded = 0
                                chunk_size = 1024 * 256

                                async for chunk in resp.aiter_bytes(chunk_size=chunk_size):
                                    f.write(chunk)
                                    downloaded += len(chunk)

                                    # 更新进度 - 使用与 YouTube 相同的格式
                                    if total > 0:
                                        progress = downloaded / total * 100
                                    else:
                                        # 如果没有content-length，使用下载的字节数作为进度指示
                                        progress = min(downloaded / (1024 * 1024), 99)  # 假设至少1MB

                                    # 计算速度（每秒更新一次）
                                    current_time = time.time()
                                    if not hasattr(self, '_last_update_time'):
                                        self._last_update_time = current_time
                                        self._last_downloaded = 0

                                    if current_time - self._last_update_time >= 1.0:
                                        speed = (downloaded - self._last_downloaded) / (current_time - self._last_update_time)
                                        self._last_update_time = current_time
                                        self._last_downloaded = downloaded
                                    else:
                                        speed = 0

                                    # 计算ETA
                                    if speed > 0 and total > 0:
                                        remaining_bytes = total - downloaded
                                        eta_seconds = remaining_bytes / speed
                                    else:
                                        eta_seconds = 0

                                    # 构建进度数据，格式与 yt-dlp 一致
                                    progress_data = {
                                        'status': 'downloading',
                                        'downloaded_bytes': downloaded,
                                        'total_bytes': total,
                                        'speed': speed,
                                        'eta': eta_seconds,
                                        'filename': filename
                                    }

                                    # 使用 message_updater 更新进度
                                    if message_updater:
                                        try:
                                            import asyncio
                                            if asyncio.iscoroutinefunction(message_updater):
                                                # 如果是协程函数，需要在事件循环中运行
                                                try:
                                                    loop = asyncio.get_running_loop()
                                                except RuntimeError:
                                                    try:
                                                        loop = asyncio.get_event_loop()
                                                    except RuntimeError:
                                                        loop = asyncio.new_event_loop()
                                                        asyncio.set_event_loop(loop)
                                                asyncio.run_coroutine_threadsafe(message_updater(progress_data), loop)
                                            else:
                                                # 同步函数，直接调用
                                                message_updater(progress_data)
                                        except Exception as e:
                                            logger.warning(f"⚠️ 更新进度失败: {e}")

                                # 下载完成后的最终更新
                                logger.info(f"✅ 小红书视频下载完成: {downloaded} bytes @{video_info.download_url}")
                                if message_updater:
                                    try:
                                        final_progress_data = {
                                            'status': 'finished',
                                            'downloaded_bytes': downloaded,
                                            'total_bytes': total,
                                            'filename': filename
                                        }
                                        message_updater(final_progress_data)
                                    except Exception as e:
                                        logger.warning(f"⚠️ 更新完成状态失败: {e}")
                    except Exception as e:
                        logger.error(f"❌ 小红书下载异常: {e}")
                        raise
            else:
                # 抖音等其他平台：处理API重定向
                # 准备cookies（如果有）
                cookies_dict = {}
                if video_info.platform == 'douyin' and self.douyin_cookies_path and os.path.exists(self.douyin_cookies_path):
                    try:
                        cookies_dict = self._parse_douyin_cookies_file(self.douyin_cookies_path)
                        logger.info(f"📊 加载了{len(cookies_dict)}个cookies用于下载")
                    except Exception as e:
                        logger.warning(f"⚠️ 加载cookies失败: {e}")

                async with httpx.AsyncClient(follow_redirects=True, timeout=60, cookies=cookies_dict) as client:
                    # 使用手机版User-Agent（按照原始douyin.py）
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
                        'Accept': '*/*',
                        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                        'Referer': 'https://www.douyin.com/' if video_info.platform == 'douyin' else 'https://www.xiaohongshu.com/',
                        'Connection': 'keep-alive',
                    }

                    # 对于抖音API链接，直接使用stream下载（按照原始douyin.py的方式）
                    logger.info(f"🎬 开始下载抖音视频: {video_info.download_url}")

                    with open(file_path, "wb") as f:
                        async with client.stream("GET", video_info.download_url, headers=headers) as resp:
                            total = int(resp.headers.get("content-length", 0))
                            downloaded = 0
                            chunk_size = 1024 * 256
                            last_update_time = time.time()
                            last_downloaded = 0

                            logger.info(f"📊 Stream响应状态码: {resp.status_code}")
                            logger.info(f"📊 Stream文件大小: {total} bytes")
                            logger.info(f"📊 实际请求URL: {resp.url}")
                            logger.info(f"📊 响应头: {dict(resp.headers)}")

                            if resp.status_code != 200:
                                raise Exception(f"HTTP状态码错误: {resp.status_code}")

                            async for chunk in resp.aiter_bytes(chunk_size=chunk_size):
                                if not chunk:
                                    break
                                f.write(chunk)
                                downloaded += len(chunk)
                                current_time = time.time()

                                # 更新进度 - 使用与 YouTube 相同的格式
                                if total > 0:
                                    progress = downloaded / total * 100
                                else:
                                    # 如果没有content-length，使用下载的字节数作为进度指示
                                    progress = min(downloaded / (1024 * 1024), 99)  # 假设至少1MB

                                # 计算速度（每秒更新一次）
                                if current_time - last_update_time >= 1.0:
                                    speed = (downloaded - last_downloaded) / (current_time - last_update_time)
                                    last_update_time = current_time
                                    last_downloaded = downloaded

                                    # 计算ETA
                                    if speed > 0 and total > 0:
                                        remaining_bytes = total - downloaded
                                        eta_seconds = remaining_bytes / speed
                                    else:
                                        eta_seconds = 0

                                    # 构建进度数据，格式与 yt-dlp 一致
                                    progress_data = {
                                        'status': 'downloading',
                                        'downloaded_bytes': downloaded,
                                        'total_bytes': total,
                                        'speed': speed,
                                        'eta': eta_seconds,
                                        'filename': filename
                                    }

                                    # 使用 message_updater 更新进度
                                    if message_updater:
                                        try:
                                            import asyncio
                                            if asyncio.iscoroutinefunction(message_updater):
                                                # 如果是协程函数，需要在事件循环中运行
                                                try:
                                                    loop = asyncio.get_running_loop()
                                                except RuntimeError:
                                                    try:
                                                        loop = asyncio.get_event_loop()
                                                    except RuntimeError:
                                                        loop = asyncio.new_event_loop()
                                                        asyncio.set_event_loop(loop)
                                                asyncio.run_coroutine_threadsafe(message_updater(progress_data), loop)
                                            else:
                                                # 同步函数，直接调用
                                                message_updater(progress_data)
                                        except Exception as e:
                                            logger.warning(f"⚠️ 更新进度失败: {e}")
                                    else:
                                        # 如果没有 message_updater，使用原来的简单更新
                                        if start_message and hasattr(self, 'bot') and self.bot:
                                            try:
                                                await start_message.edit_text(
                                                    f"📥 下载中... {progress:.1f}% ({downloaded/(1024*1024):.1f}MB)"
                                                )
                                            except Exception as e:
                                                logger.warning(f"⚠️ 更新进度消息失败: {e}")
                                        else:
                                            logger.info(f"📥 下载中... {progress:.1f}% ({downloaded/(1024*1024):.1f}MB)")

                            # 下载完成后的最终更新
                            logger.info(f"✅ 下载完成: {downloaded} bytes")
                            if message_updater:
                                try:
                                    final_progress_data = {
                                        'status': 'finished',
                                        'downloaded_bytes': downloaded,
                                        'total_bytes': total,
                                        'filename': filename
                                    }
                                    import asyncio
                                    if asyncio.iscoroutinefunction(message_updater):
                                        # 如果是协程函数，需要在事件循环中运行
                                        try:
                                            loop = asyncio.get_running_loop()
                                        except RuntimeError:
                                            try:
                                                loop = asyncio.get_event_loop()
                                            except RuntimeError:
                                                loop = asyncio.new_event_loop()
                                                asyncio.set_event_loop(loop)
                                        asyncio.run_coroutine_threadsafe(message_updater(final_progress_data), loop)
                                    else:
                                        # 同步函数，直接调用
                                        message_updater(final_progress_data)
                                except Exception as e:
                                    logger.warning(f"⚠️ 更新完成状态失败: {e}")

            # 删除开始消息（如果存在）
            if start_message and hasattr(self, 'bot') and self.bot:
                try:
                    await start_message.delete()
                except Exception as e:
                    logger.warning(f"⚠️ 删除开始消息失败: {e}")

            # 获取文件信息
            file_size = os.path.getsize(file_path)
            size_mb = file_size / (1024 * 1024)

            # 使用 ffprobe 获取视频分辨率信息
            resolution = "未知"
            try:
                media_info = self.get_media_info(file_path)
                if media_info.get("resolution"):
                    resolution = media_info["resolution"]
                    logger.info(f"📺 获取到视频分辨率: {resolution}")
            except Exception as e:
                logger.warning(f"⚠️ 获取视频分辨率失败: {e}")

            logger.info(f"✅ {video_info.platform}视频下载成功: {filename} ({size_mb:.1f} MB, 分辨率: {resolution})")

            return {
                "success": True,
                "file_path": file_path,
                "filename": filename,
                "title": video_info.title,
                "author": video_info.author,
                "platform": video_info.platform,
                "content_type": "video",
                "size_mb": size_mb,
                "resolution": resolution,
                "download_path": download_dir,
                "full_path": file_path,
                "file_count": 1,
                "files": [file_path]
            }

        except Exception as e:
            logger.error(f"❌ 下载视频文件失败: {e}")
            # 确保在异常情况下也能返回有效的结果
            return {
                "success": False,
                "error": f"下载视频文件失败: {e}",
                "platform": video_info.platform,
                "content_type": "video",
                "downloaded_bytes": 0,
                "total_bytes": 0,
                "filename": video_info.title or f"{video_info.platform}_{int(time.time())}.mp4"
            }



    def _build_bilibili_rename_script(self):
        """
        构建B站多P视频智能重命名脚本

        基于您的优秀建议：使用yt-dlp的--exec功能在下载完成后立即重命名
        避免了下载完成后的批量重命名操作，更高效更准确

        Returns:
            str: 重命名脚本命令
        """
        import shlex

        # 构建重命名脚本
        # 1. 获取当前文件的URL（从文件名推导）
        # 2. 使用yt-dlp --get-title获取完整标题
        # 3. 使用grep提取pxx部分
        # 4. 重命名文件

        script = '''
        # 获取文件信息
        file_path="{}"
        file_dir=$(dirname "$file_path")
        file_name=$(basename "$file_path")
        file_ext="${file_name##*.}"
        video_id="${file_name%.*}"

        # 构建URL（假设是B站视频）
        if [[ $video_id == *"_p"* ]]; then
            # 多P视频格式：BV1Jgf6YvE8e_p1
            bv_id="${video_id%_p*}"
            part_num="${video_id#*_p}"
            video_url="https://www.bilibili.com/video/${bv_id}?p=${part_num}"
        else
            # 单P视频格式：BV1Jgf6YvE8e
            video_url="https://www.bilibili.com/video/${video_id}"
        fi

        # 获取完整标题并提取pxx部分
        full_title=$(yt-dlp --get-title --skip-download "$video_url" 2>/dev/null)
        if [[ $? -eq 0 && -n "$full_title" ]]; then
            # 提取pxx及后续内容
            new_name=$(echo "$full_title" | grep -o "p[0-9]\\{1,3\\}.*" | head -1)
            if [[ -n "$new_name" ]]; then
                # 清理文件名中的特殊字符
                new_name=$(echo "$new_name" | sed 's/[\\/:*?"<>|【】｜]/\\_/g' | sed 's/\\s\\+/ /g')
                new_file_path="$file_dir/${new_name}.${file_ext}"

                # 执行重命名
                if [[ "$file_path" != "$new_file_path" ]]; then
                    mv "$file_path" "$new_file_path"
                    echo "✅ 智能重命名: $(basename "$file_path") -> ${new_name}.${file_ext}"
                else
                    echo "📝 文件名已正确: ${new_name}.${file_ext}"
                fi
            else
                echo "⚠️ 未找到pxx模式，保持原文件名: $file_name"
            fi
        else
            echo "⚠️ 无法获取标题，保持原文件名: $file_name"
        fi
        '''

        return script.strip()

    def _is_temp_format_file(self, filename):
        """
        检查是否是临时格式文件（包含yt-dlp格式代码）

        Args:
            filename: 文件路径

        Returns:
            bool: 如果是临时格式文件返回True
        """
        import re
        from pathlib import Path

        file_name = Path(filename).name

        # 检查是否包含yt-dlp的格式代码
        # 例如：.f100026, .f137+140, .m4a, .webm 等
        temp_patterns = [
            r'\.f\d+',           # .f100026
            r'\.f\d+\+\d+',      # .f137+140
            r'\.m4a$',           # .m4a
            r'\.webm$',          # .webm
        ]

        for pattern in temp_patterns:
            if re.search(pattern, file_name):
                return True

        return False

    def _get_final_filename_from_mapping(self, filename, title_mapping):
        """
        从标题映射表中获取最终文件名

        Args:
            filename: 当前下载的文件名
            title_mapping: 视频ID到最终文件名的映射表

        Returns:
            str: 最终文件名，如果找不到则返回None
        """
        import re
        from pathlib import Path

        try:
            file_path = Path(filename)

            # 从文件名中提取视频ID
            # 例如：BV1aDMezREUj_p1.f100026.mp4 -> BV1aDMezREUj_p1
            raw_video_id = file_path.stem
            video_id = re.sub(r'\.f\d+.*$', '', raw_video_id)

            # 从映射表中查找最终文件名
            final_filename = title_mapping.get(video_id)
            if final_filename:
                logger.debug(f"📋 映射查找: {video_id} -> {final_filename}")
                return final_filename
            else:
                logger.debug(f"⚠️ 未找到映射: {video_id}")
                return None

        except Exception as e:
            logger.debug(f"映射查找失败: {e}")
            return None

    def _optimize_filename_display_for_telegram(self, filename_display, file_count, total_size_mb, resolution_display, download_path):
        """
        动态优化文件名显示，最大化利用TG消息空间

        Args:
            filename_display: 原始文件名显示字符串
            file_count: 文件数量
            total_size_mb: 总文件大小
            resolution_display: 分辨率显示
            download_path: 下载路径

        Returns:
            str: 优化后的文件名显示字符串
        """
        # TG消息最大长度限制
        MAX_MESSAGE_LENGTH = 4096

        # 构建消息的其他部分（不包括文件名列表）
        other_parts = (
            f"🎬 视频下载完成\n\n"
            f"📝 文件名:\n"
            f"FILENAME_PLACEHOLDER\n\n"
            f"💾 文件大小: {total_size_mb:.2f} MB\n"
            f"📊 集数: {file_count} 集\n"
            f"🖼️ 分辨率: {resolution_display}\n"
            f"📂 保存位置: {download_path}"
        )

        # 计算除文件名列表外的消息长度
        other_parts_length = len(other_parts) - len("FILENAME_PLACEHOLDER")

        # 可用于文件名列表的最大长度
        available_length = MAX_MESSAGE_LENGTH - other_parts_length - 100  # 留100字符缓冲

        lines = filename_display.split('\n')

        # 如果原始文件名列表不超过可用长度，直接返回
        if len(filename_display) <= available_length:
            return filename_display

        # 需要截断，找到能显示的最大文件数量
        result_lines = []
        current_length = 0

        # 省略提示的模板
        omit_template = "  ... (省略 {} 个文件，受限于TG消息限制，完整文件列表请到下载目录查看) ..."

        for i, line in enumerate(lines):
            # 计算加上这一行和可能的省略提示后的总长度
            remaining_files = len(lines) - i - 1
            if remaining_files > 0:
                omit_text = omit_template.format(remaining_files)
                projected_length = current_length + len(line) + 1 + len(omit_text)  # +1 for newline
            else:
                projected_length = current_length + len(line)

            # 如果加上这一行会超过限制
            if projected_length > available_length:
                # 如果还有剩余文件，添加省略提示
                if remaining_files > 0:
                    omit_text = omit_template.format(remaining_files)
                    result_lines.append(omit_text)
                break
            else:
                # 可以添加这一行
                result_lines.append(line)
                current_length = projected_length

        return '\n'.join(result_lines)

    def _rename_bilibili_file_from_full_title(self, filename):
        """
        从完整标题文件名重命名为简洁的pxx格式

        例如：
        输入: 尚硅谷Cursor使用教程，2小时玩转cursor p01 01-Cursor教程简介.mp4
        输出: p01 01-Cursor教程简介.mp4

        Args:
            filename: 下载完成的文件路径（包含完整标题）
        """
        import re
        from pathlib import Path

        try:
            file_path = Path(filename)
            if not file_path.exists():
                logger.warning(f"⚠️ 文件不存在: {filename}")
                return

            file_name = file_path.name
            file_ext = file_path.suffix
            title_without_ext = file_path.stem

            logger.info(f"🔍 处理完整标题文件: {file_name}")

            # 使用智能处理逻辑提取pxx部分
            processed_title = self._process_bilibili_multipart_title(title_without_ext)

            if processed_title != title_without_ext:
                # 标题被处理了，说明找到了pxx部分
                safe_title = self._sanitize_filename(processed_title)
                new_file_path = file_path.parent / f"{safe_title}{file_ext}"

                logger.info(f"🎯 简洁文件名: {safe_title}{file_ext}")

                # 执行重命名
                if file_path != new_file_path:
                    try:
                        file_path.rename(new_file_path)
                        logger.info(f"✅ 智能重命名成功: {file_name} -> {safe_title}{file_ext}")
                    except Exception as e:
                        logger.warning(f"⚠️ 重命名失败: {e}")
                else:
                    logger.info(f"📝 文件名已是简洁格式: {safe_title}{file_ext}")
            else:
                logger.info(f"📝 未找到pxx模式，保持原文件名: {file_name}")

        except Exception as e:
            logger.error(f"❌ 处理文件名失败: {e}")

    def _get_processed_filename_for_display(self, filename):
        """
        获取用于显示的处理后文件名

        这个函数用于在下载进度中显示用户友好的文件名，
        而不是技术性的临时文件名

        Args:
            filename: 原始文件名

        Returns:
            str: 处理后的显示文件名
        """
        import re
        from pathlib import Path

        try:
            file_path = Path(filename)
            file_name = file_path.name
            file_ext = file_path.suffix

            # 如果是临时格式文件，尝试推导最终文件名
            if self._is_temp_format_file(filename):
                # 从临时文件名推导视频ID
                # 例如：BV1aDMezREUj_p1.f100026.mp4 -> BV1aDMezREUj_p1
                raw_video_id = file_path.stem
                video_id = re.sub(r'\.f\d+.*$', '', raw_video_id)

                # 尝试从缓存的标题信息获取处理后的文件名
                # 这里我们使用一个简化的方法：直接显示视频ID
                if "_p" in video_id:
                    # 多P视频：显示分集信息
                    parts = video_id.split("_p")
                    part_num = parts[1]
                    return f"p{part_num.zfill(2)} 下载中...{file_ext}"
                else:
                    # 单P视频
                    return f"视频下载中...{file_ext}"
            else:
                # 如果是最终文件，检查是否需要处理标题
                # 这里我们假设文件名可能包含完整的标题
                if any(keyword in file_name for keyword in ["尚硅谷", "教程", "课程"]):
                    # 尝试提取pxx部分
                    pattern = r'p(\d{1,3})\s+'
                    match = re.search(pattern, file_name, re.IGNORECASE)
                    if match:
                        # 找到pxx，尝试提取后续内容
                        start_pos = match.start()
                        remaining = file_name[start_pos:]
                        # 简化处理：只取前50个字符
                        if len(remaining) > 50:
                            remaining = remaining[:47] + "..."
                        return remaining

                # 默认返回原文件名
                return file_name

        except Exception as e:
            logger.debug(f"处理显示文件名失败: {e}")
            return Path(filename).name

    def _rename_bilibili_file_immediately(self, filename):
        """
        立即重命名B站多P文件（基于您的优秀建议的Python实现）

        在每个文件下载完成时立即执行重命名，避免批量处理

        Args:
            filename: 下载完成的文件路径
        """
        import re
        import os
        from pathlib import Path

        try:
            file_path = Path(filename)
            if not file_path.exists():
                logger.warning(f"⚠️ 文件不存在: {filename}")
                return

            file_name = file_path.name
            file_ext = file_path.suffix
            raw_video_id = file_path.stem

            logger.info(f"🔍 分析文件: {file_name}")
            logger.info(f"📝 原始视频ID: {raw_video_id}")

            # 清理视频ID，去除格式代码
            # 例如：BV1aDMezREUj_p2.f100026 -> BV1aDMezREUj_p2
            video_id = re.sub(r'\.f\d+.*$', '', raw_video_id)
            logger.info(f"🧹 清理后视频ID: {video_id}")

            # 构建URL（从文件名推导）
            if "_p" in video_id:
                # 多P视频格式：BV1aDMezREUj_p1
                parts = video_id.split("_p")
                bv_id = parts[0]
                part_num = parts[1]
                video_url = f"https://www.bilibili.com/video/{bv_id}?p={part_num}"
            else:
                # 单P视频格式：BV1aDMezREUj
                video_url = f"https://www.bilibili.com/video/{video_id}"

            logger.info(f"🔗 构建URL: {video_url}")

            # 使用yt-dlp获取完整标题
            try:
                import subprocess
                result = subprocess.run(
                    ["yt-dlp", "--get-title", "--skip-download", video_url],
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                if result.returncode == 0 and result.stdout.strip():
                    full_title = result.stdout.strip()
                    logger.info(f"📋 获取标题: {full_title}")

                    # 提取pxx及后续内容
                    pattern = r'p(\d{1,3}).*'
                    match = re.search(pattern, full_title, re.IGNORECASE)

                    if match:
                        # 从pxx开始截取
                        start_pos = match.start()
                        new_name = full_title[start_pos:]

                        # 清理文件名中的特殊字符
                        new_name = re.sub(r'[\\/:*?"<>|【】｜]', '_', new_name)
                        new_name = re.sub(r'\s+', ' ', new_name).strip()

                        new_file_path = file_path.parent / f"{new_name}{file_ext}"

                        logger.info(f"🎯 新文件名: {new_name}{file_ext}")

                        # 执行重命名
                        if file_path != new_file_path:
                            file_path.rename(new_file_path)
                            logger.info(f"✅ 智能重命名成功: {file_name} -> {new_name}{file_ext}")
                        else:
                            logger.info(f"📝 文件名已正确: {new_name}{file_ext}")
                    else:
                        logger.warning(f"⚠️ 未找到pxx模式，保持原文件名: {file_name}")
                else:
                    logger.warning(f"⚠️ 无法获取标题，保持原文件名: {file_name}")
                    logger.warning(f"yt-dlp错误: {result.stderr}")

            except subprocess.TimeoutExpired:
                logger.warning(f"⚠️ 获取标题超时，保持原文件名: {file_name}")
            except Exception as e:
                logger.warning(f"⚠️ 获取标题失败: {e}，保持原文件名: {file_name}")

        except Exception as e:
            logger.error(f"❌ 重命名文件失败: {e}")

    def _rename_bilibili_multipart_files(self, download_path, expected_files):
        """
        重命名B站多P下载的文件，使其匹配预期文件名

        Args:
            download_path: 下载目录路径
            expected_files: 预期文件列表
        """
        import os
        from pathlib import Path

        logger.info(f"🔄 开始重命名B站多P文件，目录: {download_path}")
        logger.info(f"📋 预期文件数量: {len(expected_files)}")

        # 获取目录中所有视频文件
        video_extensions = ["*.mp4", "*.mkv", "*.webm", "*.avi", "*.mov", "*.flv"]
        all_video_files = []
        for ext in video_extensions:
            all_video_files.extend(list(Path(download_path).glob(ext)))

        logger.info(f"📁 找到视频文件数量: {len(all_video_files)}")

        renamed_count = 0
        for expected_file in expected_files:
            expected_filename = expected_file['filename']
            original_title = expected_file['title']

            # 查找匹配的实际文件
            for actual_file in all_video_files:
                actual_filename = actual_file.name

                # 使用智能匹配逻辑检查是否匹配
                def clean_filename_for_matching(filename):
                    """清理文件名用于匹配"""
                    import re
                    if not filename:
                        return ""

                    # 删除yt-dlp的各种格式代码
                    cleaned = re.sub(r'\.[fm]\d+(\+\d+)*', '', filename)
                    cleaned = re.sub(r'\.f\d+', '', cleaned)

                    # 删除YouTube视频ID标识（仅在启用ID标签时）
                    if hasattr(self, 'bot') and hasattr(self.bot, 'youtube_id_tags') and self.bot.youtube_id_tags:
                        cleaned = re.sub(r'\[[a-zA-Z0-9_-]{10,12}\]', '', cleaned)

                    cleaned = re.sub(r'\.(webm|m4a|mp3)$', '.mp4', cleaned)
                    cleaned = re.sub(r'\.(webm|m4a|mp3)\.mp4$', '.mp4', cleaned)

                    # 删除序号前缀
                    cleaned = re.sub(r'^\d+\.\s*', '', cleaned)

                    # 对B站多P标题进行智能处理
                    pattern = r'\s+[pP](\d{1,3})\s+'
                    match = re.search(pattern, cleaned)
                    if match:
                        start_pos = match.start() + 1
                        cleaned = cleaned[start_pos:]

                    # 统一特殊字符（解决全角/半角差异）
                    # 将各种竖线统一为下划线，与_sanitize_filename保持一致
                    cleaned = re.sub(r'[|｜]', '_', cleaned)
                    # 统一其他特殊字符
                    cleaned = re.sub(r'[【】]', '_', cleaned)

                    # 确保以 .mp4 结尾
                    if not cleaned.endswith('.mp4'):
                        cleaned = cleaned.rstrip('.') + '.mp4'

                    return cleaned

                cleaned_actual = clean_filename_for_matching(actual_filename)
                cleaned_expected = clean_filename_for_matching(expected_filename)

                if cleaned_actual == cleaned_expected:
                    # 找到匹配的文件，进行重命名
                    new_file_path = actual_file.parent / expected_filename

                    if actual_file != new_file_path:  # 避免重命名为相同名称
                        try:
                            actual_file.rename(new_file_path)
                            logger.info(f"✅ 重命名成功: {actual_filename} -> {expected_filename}")
                            renamed_count += 1
                        except Exception as e:
                            logger.warning(f"⚠️ 重命名失败: {actual_filename} -> {expected_filename}, 错误: {e}")
                    else:
                        logger.info(f"📝 文件名已正确: {expected_filename}")
                        renamed_count += 1
                    break
            else:
                logger.warning(f"⚠️ 未找到匹配文件: {expected_filename}")

        logger.info(f"🎉 重命名完成: {renamed_count}/{len(expected_files)} 个文件")

    def _process_bilibili_multipart_title(self, title):
        """
        智能处理B站多P视频标题，去除pxx前面的冗长内容

        例如：
        输入: "3小时超快速入门Python | 动画教学【2025新版】【自学Python教程】【零基础Python】【计算机二级Python】【Python期末速成】 p01 先导篇 | 为什么做这个教程"
        输出: "p01 先导篇 | 为什么做这个教程"
        """
        if not title:
            return title

        import re

        # 查找 pxx 模式（p + 数字）
        # 支持 p01, p1, P01, P1 等格式
        pattern = r'\s+[pP](\d{1,3})\s+'
        match = re.search(pattern, title)

        if match:
            # 找到 pxx，从 pxx 开始截取
            start_pos = match.start() + 1  # +1 是为了跳过前面的空格
            processed_title = title[start_pos:]
            logger.info(f"🔧 B站多P标题处理: '{title}' -> '{processed_title}'")
            return processed_title
        else:
            # 没有找到 pxx 模式，返回原标题
            return title

    def _basic_sanitize_filename(self, filename):
        """
        基本的文件名清理，与yt-dlp保持一致
        只替换文件系统不支持的字符，保留其他字符

        注意：这个函数需要完全模拟yt-dlp的字符处理行为
        """
        if not filename:
            return "video"

        # yt-dlp的字符处理规则（基于观察到的实际行为）：
        # 1. 半角 | 转换为全角 ｜
        filename = filename.replace('|', '｜')

        # 2. 斜杠 / 转换为大斜杠符号 ⧸ （这是yt-dlp的实际行为）
        filename = filename.replace('/', '⧸')

        # 3. 只替换文件系统绝对不支持的字符
        # 保留 ｜ 【】 ⧸ 等字符，因为yt-dlp也会保留它们
        filename = re.sub(r'[\\:*?"<>]', '_', filename)

        # 3. 去除多余空格
        filename = re.sub(r'\s+', ' ', filename).strip()

        # 4. 去除开头和结尾的下划线和空格
        filename = re.sub(r'^[_\s]+|[_\s]+$', '', filename)

        # 确保文件名不为空
        if not filename or filename.isspace():
            filename = "video"

        return filename

    def _detect_part_files(self, download_path):
        """检测PART文件"""
        from pathlib import Path
        part_files = list(Path(download_path).rglob("*.part"))
        return part_files

    def _analyze_failure_reason(self, part_file):
        """分析PART文件失败原因"""
        try:
            file_size = part_file.stat().st_size
            if file_size == 0:
                return "下载未开始或立即失败"
            elif file_size < 1024 * 1024:  # < 1MB
                return "下载刚开始就中断，可能是网络问题"
            elif file_size < 10 * 1024 * 1024:  # < 10MB
                return "下载进行中被中断，可能是网络问题"
            else:
                return "下载进行中被中断，可能是网络或磁盘问题"
        except Exception:
            return "无法分析失败原因"

    def _log_part_files_details(self, part_files):
        """在日志中记录PART文件详细信息"""
        if part_files:
            logger.warning(f"⚠️ 发现 {len(part_files)} 个未完成的PART文件")
            logger.warning("⚠️ 未完成的文件列表：")
            for part_file in part_files:
                reason = self._analyze_failure_reason(part_file)
                logger.warning(f"   - {part_file.name} ({reason})")
        else:
            logger.info("✅ 未发现PART文件，所有下载都已完成")

    def _get_enhanced_ydl_opts(self, base_opts=None):
        """获取增强的yt-dlp配置，避免PART文件产生"""
        enhanced_opts = {
            # 基础配置
            'quiet': False,
            'no_warnings': False,

            # 网络和重试配置 - 避免网络中断导致的PART文件
            'socket_timeout': 60,           # 增加超时时间到60秒
            'retries': 10,                  # 增加重试次数
            'fragment_retries': 10,         # 分片重试次数
            'retry_sleep_functions': {      # 重试间隔配置
                'http': lambda n: min(5 * (2 ** n), 60),  # 指数退避，最大60秒
                'fragment': lambda n: min(2 * (2 ** n), 30),  # 分片重试间隔
            },

            # 防止YouTube限流的配置
            'sleep_interval': 2,            # 每个视频之间等待2秒
            'max_sleep_interval': 5,        # 最大等待5秒
            'sleep_interval_requests': 1,   # 每个请求之间等待1秒

            # 地理和年龄限制绕过配置
            'age_limit': 99,                # 绕过年龄限制
            'geo_bypass': True,             # 尝试绕过地理限制
            'geo_bypass_country': 'US',     # 使用美国作为绕过国家
            # 🎯 完全恢复v0.4-dev3方式：移除所有extractor_args，使用yt-dlp默认配置
            # v0.4-dev3版本没有extractor_args，这是它成功的关键！

            # 🎯 修复：下载配置 - 优先高质量，允许跳过不可用分片
            'skip_unavailable_fragments': True,   # 跳过不可用分片，允许下载高质量视频
            'abort_on_unavailable_fragment': False,  # 允许部分分片失败，支持断点续传
            'keep_fragments': False,        # 不保留分片，避免临时文件堆积
            'continue_dl': True,            # 启用断点续传
            'part': True,                   # 允许生成.part文件用于断点续传
            'mtime': True,                  # 保持文件修改时间，有助于断点续传

            # 合并配置 - 确保合并成功
            'merge_output_format': 'mp4',   # 强制合并为mp4
            'postprocessor_args': {         # 后处理参数
                'ffmpeg': ['-y']            # ffmpeg强制覆盖输出文件
            },

            # 🎯 修复：添加高质量下载的关键配置（与单独下载保持一致）
            'hls_use_mpegts': False,        # 使用mp4容器而不是ts
            'hls_prefer_native': True,      # 优先使用原生HLS下载器
            'concurrent_fragment_downloads': 3,  # 并发下载分片数量
            'buffersize': 1024,             # 缓冲区大小
            'http_chunk_size': 10485760,    # 10MB分块大小

            # 错误处理配置 - 注意：base_opts 中的 ignoreerrors 会覆盖这个设置
            'abort_on_error': False,        # 单个文件错误时不中止整个下载

            # 临时文件配置
            'writeinfojson': False,         # 不写入info.json，减少临时文件
            'writesubtitles': False,        # 不下载字幕，减少复杂性
            'writeautomaticsub': False,     # 不下载自动字幕
        }

        # 合并基础配置
        if base_opts:
            logger.info(f"🔧 [ENHANCED_OPTS] 合并前progress_hooks: {enhanced_opts.get('progress_hooks', [])}")
            logger.info(f"🔧 [ENHANCED_OPTS] base_opts中的progress_hooks: {base_opts.get('progress_hooks', [])}")
            enhanced_opts.update(base_opts)
            logger.info(f"🔧 [ENHANCED_OPTS] 合并后progress_hooks: {len(enhanced_opts.get('progress_hooks', []))} 个回调")

        # 🎯 真正修复：恢复v0.4-dev3成功方式 - 不设置默认format，让yt-dlp使用原生"best"
        # v0.4-dev3版本没有设置默认format，这是它能下载最高清视频的关键！
        # 不设置format，让yt-dlp自己选择最佳格式

        # 添加代理配置
        if self.proxy_host:
            enhanced_opts['proxy'] = self.proxy_host

        # 添加cookies配置 - 注意：这里无法判断URL类型，所以优先使用YouTube cookies
        # 实际的URL特定cookies应该在调用方处理
        if hasattr(self, 'youtube_cookies_path') and self.youtube_cookies_path and os.path.exists(self.youtube_cookies_path):
            enhanced_opts['cookiefile'] = self.youtube_cookies_path
        elif hasattr(self, 'x_cookies_path') and self.x_cookies_path and os.path.exists(self.x_cookies_path):
            enhanced_opts['cookiefile'] = self.x_cookies_path

        return enhanced_opts

    def _add_danmaku_options(self, ydl_opts, url):
        """为B站URL添加弹幕下载选项"""
        if not self.is_bilibili_url(url):
            return ydl_opts

        # 检查是否启用了B站弹幕下载
        if hasattr(self, 'bot') and hasattr(self.bot, 'bilibili_danmaku_download') and self.bot.bilibili_danmaku_download:
            logger.info("🎭 启用B站弹幕下载")

            # 添加弹幕下载选项
            ydl_opts.update({
                'writesubtitles': True,  # 下载字幕
                'writeautomaticsub': False,  # 不下载自动生成的字幕
                'subtitlesformat': 'danmaku',  # 弹幕格式
                'postprocessors': ydl_opts.get('postprocessors', []) + [
                    {
                        'key': 'danmaku',  # 使用danmaku后处理器
                    }
                ],
                'postprocessor_args': {
                    'danmaku': ['filename=%(title)s.ass']  # 直接指定弹幕文件名，去掉.danmaku后缀
                }
            })

            logger.info("✅ 已添加弹幕下载配置")
        else:
            logger.info("📝 B站弹幕下载已关闭")

        return ydl_opts


    def _resume_part_files(self, download_path, original_url):
        """断点续传PART文件"""
        from pathlib import Path
        part_files = self._detect_part_files(download_path)
        resumed_count = 0

        if not part_files:
            return 0

        logger.info(f"🔄 发现 {len(part_files)} 个PART文件，尝试断点续传")

        for part_file in part_files:
            try:
                # 获取PART文件信息
                file_size = part_file.stat().st_size
                logger.info(f"📥 断点续传: {part_file.name} (已下载: {file_size / (1024*1024):.1f}MB)")

                # 使用yt-dlp的断点续传功能
                # 根据设置决定文件名模板
                if hasattr(self, 'bot') and hasattr(self.bot, 'youtube_id_tags') and self.bot.youtube_id_tags and self.is_youtube_url(original_url):
                    outtmpl = str(download_path / '%(title)s[%(id)s].%(ext)s')
                else:
                    outtmpl = str(download_path / '%(title)s.%(ext)s')

                resume_opts = self._get_enhanced_ydl_opts({
                    'outtmpl': outtmpl,
                    'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                    'continue_dl': True,  # 启用断点续传
                    'part': True,         # 允许PART文件
                })

                import yt_dlp
                with yt_dlp.YoutubeDL(resume_opts) as ydl:
                    ydl.download([original_url])

                resumed_count += 1
                logger.info(f"✅ 断点续传成功: {part_file.name}")

            except Exception as e:
                logger.warning(f"⚠️ 断点续传失败: {part_file.name}, 错误: {e}")
                # 如果断点续传失败，可以选择删除PART文件重新下载
                try:
                    logger.info(f"🗑️ 删除损坏的PART文件: {part_file.name}")
                    part_file.unlink()
                except Exception as del_e:
                    logger.warning(f"⚠️ 删除PART文件失败: {del_e}")

        if resumed_count > 0:
            logger.info(f"✅ 成功断点续传 {resumed_count} 个文件")

        return resumed_count

    def smart_download_bilibili_for_ugc(self, url, download_path, progress_callback=None, auto_playlist=False):
        """UGC合集专用的B站下载器，强制下载单视频而不返回建议状态"""
        logger.info(f"🎬 UGC合集模式：开始下载B站视频: {url}")

        # 调用原始的smart_download_bilibili，但修改单视频处理逻辑
        try:
            # 先获取视频信息
            import yt_dlp
            from pathlib import Path
            import os
            import re

            # 保存原始工作目录
            original_cwd = os.getcwd()
            logger.info(f"📁 原始工作目录: {original_cwd}")

            try:
                # 检查视频类型
                logger.info(f"🔍 正在检查视频类型: {url}")

                info_opts = {
                    "quiet": True,
                    "no_warnings": True,
                    "socket_timeout": 15,
                    "retries": 2,
                }
                if self.proxy_host:
                    info_opts["proxy"] = self.proxy_host

                with yt_dlp.YoutubeDL(info_opts) as ydl:
                    try:
                        info = ydl.extract_info(url, download=False)
                        entries = info.get("entries", [info] if info else [])
                        count = len([e for e in entries if e])
                        logger.info(f"📋 检测到 {count} 个视频")
                    except Exception as e:
                        logger.warning(f"获取视频信息失败: {e}")
                        count = 1  # 默认为单视频

                # 对于UGC合集，即使检测到单视频也要继续下载
                if count == 1:
                    logger.info("🎬 UGC合集模式：检测到单视频，继续使用smart_download_bilibili下载")

                    # 设置下载路径
                    final_download_path = Path(download_path)
                    final_download_path.mkdir(parents=True, exist_ok=True)

                    # 构建输出模板
                    output_template = str(final_download_path / "%(title)s.%(ext)s")

                    # 配置下载选项
                    ydl_opts = {
                        "outtmpl": output_template,
                        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                        "merge_output_format": "mp4",
                        "ignoreerrors": True,
                        "retries": 8,
                        "fragment_retries": 8,
                        "skip_unavailable_fragments": True,
                        "quiet": True,
                        "no_warnings": True,
                        "socket_timeout": 30,
                    }

                    if self.proxy_host:
                        ydl_opts["proxy"] = self.proxy_host

                    if progress_callback:
                        ydl_opts["progress_hooks"] = [progress_callback]

                    # 如果开启了B站封面下载，添加缩略图下载选项
                    if hasattr(self, 'bot') and hasattr(self.bot, 'bilibili_thumbnail_download') and self.bot.bilibili_thumbnail_download:
                        ydl_opts["writethumbnail"] = True
                        # 添加缩略图格式转换后处理器：WebP -> JPG
                        if "postprocessors" not in ydl_opts:
                            ydl_opts["postprocessors"] = []
                        ydl_opts["postprocessors"].append({
                            'key': 'FFmpegThumbnailsConvertor',
                            'format': 'jpg',
                            'when': 'before_dl'
                        })
                        logger.info("🖼️ UGC合集开启B站封面下载（转换为JPG格式）")

                    # 执行下载
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([url])

                    logger.info("✅ UGC合集单视频下载完成")
                    return True
                else:
                    # 多视频情况，调用原始的smart_download_bilibili
                    logger.info(f"🎬 UGC合集模式：检测到多视频({count}个)，调用原始下载器")
                    return self.smart_download_bilibili(url, download_path, progress_callback, auto_playlist)

            finally:
                # 恢复工作目录
                os.chdir(original_cwd)
                logger.info(f"📁 已恢复工作目录: {original_cwd}")

        except Exception as e:
            logger.error(f"❌ UGC合集下载失败: {e}")
            return False

    def _resume_failed_downloads(self, download_path, original_url, max_retries=5):
        """检测并断点续传失败的下载"""
        part_files = self._detect_part_files(download_path)

        if not part_files:
            return True  # 没有PART文件，下载成功

        if max_retries <= 0:
            logger.warning(f"⚠️ 重试次数已用完，仍有 {len(part_files)} 个未完成文件")
            return False

        logger.info(f"🔄 检测到 {len(part_files)} 个未完成文件，尝试断点续传 (剩余重试: {max_retries})")

        # 尝试断点续传PART文件
        resumed_count = self._resume_part_files(download_path, original_url)

        # 等待一段时间再检查
        import time
        time.sleep(1)

        # 递归检查是否还有PART文件
        remaining_part_files = self._detect_part_files(download_path)

        if not remaining_part_files:
            logger.info("✅ 所有PART文件已成功续传完成")
            return True
        elif len(remaining_part_files) < len(part_files):
            logger.info(f"📈 部分文件续传成功，剩余 {len(remaining_part_files)} 个文件")
            # 继续尝试剩余文件
            return self._resume_failed_downloads(download_path, original_url, max_retries - 1)
        else:
            logger.warning(f"⚠️ 断点续传未能减少PART文件数量，剩余重试: {max_retries - 1}")
            if max_retries > 1:
                return self._resume_failed_downloads(download_path, original_url, max_retries - 1)
            else:
                return False

    def _sanitize_filename(self, filename, max_length=200):
        """清理文件名，去除特殊字符，限制长度"""
        if not filename:
            return "video"

        # 去除特殊字符（保留中文字符，只移除真正危险的字符）
        filename = re.sub(r'[\\/:*?"<>|]', '_', filename)
        # 去除多余空格
        filename = re.sub(r'\s+', ' ', filename).strip()
        # 去除开头和结尾的特殊字符
        filename = re.sub(r'^[_\s]+|[_\s]+$', '', filename)

        # 如果文件名太长，进行智能截断
        if len(filename) > max_length:
            # 保留扩展名（如果有）
            name, ext = os.path.splitext(filename)
            if ext:
                # 如果有扩展名，保留扩展名，截断主文件名
                max_name_length = max_length - len(ext) - 3  # 3是"..."的长度
                if max_name_length > 0:
                    filename = name[:max_name_length] + "..." + ext
                else:
                    # 如果扩展名太长，只保留扩展名
                    filename = "..." + ext
            else:
                # 没有扩展名，直接截断
                filename = filename[:max_length-3] + "..."

        # 确保文件名不为空
        if not filename or filename.isspace():
            filename = "video"

        return filename

    def _optimize_instagram_filename(self, title, video_info=None):
        """
        Instagram专用文件名优化
        
        Args:
            title: 原始标题
            video_info: 视频信息字典（可选）
            
        Returns:
            优化后的文件名
        """
        if not title:
            return f"instagram_{int(time.time())}"
        
        # 去除常见的Instagram标题前缀
        optimized = title
        
        # 去除 "Video by" 前缀
        if optimized.startswith("Video by "):
            optimized = optimized[9:]  # 去除 "Video by "
        
        # 去除 "Photo by" 前缀
        if optimized.startswith("Photo by "):
            optimized = optimized[9:]  # 去除 "Photo by "
        
        # 去除 "Reel by" 前缀  
        if optimized.startswith("Reel by "):
            optimized = optimized[8:]  # 去除 "Reel by "
        
        # 处理作者名称后的内容
        if " • " in optimized:
            # 如果有 " • " 分隔符，取后面的内容作为主要标题
            parts = optimized.split(" • ", 1)
            if len(parts) > 1 and parts[1].strip():
                optimized = parts[1].strip()
            else:
                optimized = parts[0].strip()
        elif ": " in optimized:
            # 如果有 ": " 分隔符，取后面的内容
            parts = optimized.split(": ", 1)
            if len(parts) > 1 and parts[1].strip():
                optimized = parts[1].strip()
            else:
                optimized = parts[0].strip()
        
        # 去除末尾的常见标签和符号（在短标题检查之前）
        optimized = re.sub(r'\s*[#@]\s*.*$', '', optimized)  # 去除末尾的#标签和@提及
        optimized = re.sub(r'\s*\.\.\.$', '', optimized)     # 去除末尾的省略号
        
        # 如果处理后的标题太短（可能只是用户名），添加Instagram前缀和时间戳
        if len(optimized.strip()) <= 3:  # 修改为 <= 3
            timestamp = int(time.time()) % 100000  # 使用时间戳后5位避免太长
            optimized = f"instagram_{optimized}_{timestamp}" if optimized.strip() else f"instagram_{timestamp}"
        
        # 限制长度并清理
        optimized = self._sanitize_filename(optimized.strip(), max_length=50)
        
        # 如果最终结果为空，使用默认名称
        if not optimized or optimized.isspace():
            return f"instagram_{int(time.time())}"
        
        # 添加时间戳后缀避免重复（可选，取决于用户偏好）
        # 可以根据需要启用这个功能
        # timestamp = int(time.time()) % 10000
        # optimized = f"{optimized}_{timestamp}"
        
        return optimized

    def _create_gallery_dl_config(self):
        """创建 gallery-dl.conf 配置文件"""
        import json

        config_path = Path(self.download_path / "gallery-dl.conf")

        # 使用 GALLERY_DL_DOWNLOAD_PATH 环境变量，如果没有设置则使用默认值
        gallery_dl_download_path = os.environ.get("GALLERY_DL_DOWNLOAD_PATH")
        if not gallery_dl_download_path:
            # 本地开发环境默认值
            gallery_dl_download_path = str(self.download_path / "gallery")
            logger.info(f"⚠️ 未设置 GALLERY_DL_DOWNLOAD_PATH 环境变量，使用默认值: {gallery_dl_download_path}")
        else:
            logger.info(f"✅ 使用 GALLERY_DL_DOWNLOAD_PATH 环境变量: {gallery_dl_download_path}")

        logger.info(f"🎯 使用 GALLERY_DL_DOWNLOAD_PATH: {gallery_dl_download_path}")

        # 从环境变量获取X_COOKIES路径
        x_cookies_env = os.environ.get("X_COOKIES")
        if x_cookies_env:
            cookies_path = x_cookies_env
            logger.info(f"🍪 从环境变量获取X_COOKIES: {cookies_path}")
        else:
            cookies_path = str(self.x_cookies_path) if self.x_cookies_path else None
            logger.info(f"🍪 使用初始化参数中的X cookies: {cookies_path}")

        config = {
            "base-directory": gallery_dl_download_path,
            "extractor": {
                "twitter": {
                    "cookies": cookies_path
                }
            },
            "downloader": {
                "http": {
                    "timeout": 120,
                    "retries": 15,
                    "sleep": 5,
                    "verify": False,
                    "headers": {
                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
                        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                        "Accept-Encoding": "gzip, deflate, br",
                        "DNT": "1",
                        "Connection": "keep-alive",
                        "Upgrade-Insecure-Requests": "1",
                        "Sec-Fetch-Dest": "document",
                        "Sec-Fetch-Mode": "navigate",
                        "Sec-Fetch-Site": "cross-site",
                        "Sec-Fetch-User": "?1",
                        "Cache-Control": "max-age=0",
                        "Referer": "https://telegra.ph/",
                        "Origin": "https://telegra.ph"
                    },
                    "max_retries": 15,
                    "retry_delay": 5,
                    "connection_timeout": 60,
                    "read_timeout": 120,
                    "chunk_size": 8192,
                    "stream": True,
                    "allow_redirects": True,
                    "max_redirects": 10
                }
            }
        }

        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        logger.info(f"已成功创建 gallery-dl.conf 配置文件: {config_path}")
        logger.info(f"配置文件内容:\n{json.dumps(config, indent=2, ensure_ascii=False)}")

    async def _download_apple_music(self, url: str, download_path: str, message_updater=None, status_message=None, context=None) -> dict:
        """下载 Apple Music"""
        try:
            if not self.apple_music_downloader:
                # 尝试重新初始化
                try:
                    from applemusic_downloader_plus import AppleMusicDownloaderPlus
                    
                    self.apple_music_downloader = AppleMusicDownloaderPlus(
                        output_dir=str(self.apple_music_download_path),
                        cookies_path=self.apple_music_cookies_path
                    )
                    
                    # 检查是否成功
                    if not (self.apple_music_downloader and self.apple_music_downloader.is_available()):
                        self.apple_music_downloader = None
                        
                except Exception:
                    self.apple_music_downloader = None
                
                # 如果重新初始化也失败，返回错误
                if not self.apple_music_downloader:
                    return {
                        "success": False,
                        "error": "Apple Music 下载器未初始化",
                        "platform": "AppleMusic",
                        "content_type": "music"
                    }

            # 更新消息状态
            if message_updater and callable(message_updater):
                try:
                    if asyncio.iscoroutinefunction(message_updater):
                        await message_updater("🍎 正在解析 Apple Music 链接...")
                    else:
                        message_updater("🍎 正在解析 Apple Music 链接...")
                except Exception as e:
                    logger.warning(f"消息更新失败: {e}")

            # 检查是否为有效的 Apple Music 链接
            if not self.apple_music_downloader.is_apple_music_url(url):
                return {
                    "success": False,
                    "error": "不是有效的 Apple Music 链接",
                    "platform": "AppleMusic",
                    "content_type": "music"
                }

            # 提取音乐信息
            music_info = self.apple_music_downloader.extract_music_info(url)
            logger.info(f"🍎 Apple Music 信息: {music_info}")

            # 创建进度回调
            progress_data = {"final_filename": None, "lock": threading.Lock()}

            # 使用 Apple Music 进度回调
            progress_callback = apple_music_progress_hook(
                message_updater=message_updater,
                progress_data=progress_data,
                status_message=status_message,
                context=context
            )

            # 执行下载
            try:
                # 根据音乐类型选择下载方法，并添加超时控制
                if music_info.get('type') == 'album':
                    # 专辑下载：设置较长的超时时间（15分钟）
                    logger.info("🍎 开始下载专辑，超时时间：15分钟")
                    try:
                        result = await asyncio.wait_for(
                            self.apple_music_downloader.download_album(url, progress_callback),
                            timeout=900.0  # 15分钟超时
                        )
                    except asyncio.TimeoutError:
                        logger.error("⏰ Apple Music专辑下载超时（15分钟）")
                        return {
                            "success": False,
                            "error": "专辑下载超时，请稍后重试或检查网络连接",
                            "platform": "AppleMusic",
                            "content_type": "album",
                            "url": url
                        }
                else:
                    # 单曲下载：设置较短的超时时间（5分钟）
                    logger.info("🍎 开始下载单曲，超时时间：5分钟")
                    try:
                        result = await asyncio.wait_for(
                            self.apple_music_downloader.download_song(url, progress_callback),
                            timeout=300.0  # 5分钟超时
                        )
                    except asyncio.TimeoutError:
                        logger.error("⏰ Apple Music单曲下载超时（5分钟）")
                        return {
                            "success": False,
                            "error": "单曲下载超时，请稍后重试或检查网络连接",
                            "platform": "AppleMusic",
                            "content_type": "song",
                            "url": url
                        }
                
                if result.get('success'):
                    logger.info(f"🍎 Apple Music 下载成功: {result}")
                    return {
                        "success": True,
                        "platform": "AppleMusic",
                        "content_type": music_info.get('type', 'music'),
                        "download_path": str(self.apple_music_download_path),
                        "files_count": result.get('files_count', 0),
                        "total_size_mb": result.get('total_size_mb', 0),  # 🔧 修复：只使用total_size_mb字段
                        "file_formats": result.get('file_formats', []),
                        "music_type": music_info.get('type'),
                        "country": music_info.get('country'),
                        "url": url,  # 修复：添加原始URL字段，用于后续的专辑/单曲类型判断
                        "music_info": result.get('music_info', {})  # 添加音乐信息字段
                    }
                else:
                    logger.error(f"🍎 Apple Music 下载失败: {result.get('error')}")
                    return {
                        "success": False,
                        "error": result.get('error', '未知错误'),
                        "platform": "AppleMusic",
                        "content_type": "music",
                        "url": url  # 添加URL字段
                    }
                    
            except Exception as e:
                logger.error(f"🍎 Apple Music 下载异常: {e}")
                return {
                    "success": False,
                    "error": f"下载异常: {str(e)}",
                    "platform": "AppleMusic",
                    "content_type": "music",
                    "url": url  # 添加URL字段
                }

        except Exception as e:
            logger.error(f"🍎 Apple Music 下载器调用失败: {e}")
            return {
                "success": False,
                "error": f"下载器调用失败: {str(e)}",
                "platform": "AppleMusic",
                "content_type": "music",
                "url": url  # 添加URL字段
            }


    async def _download_netease_music(self, url: str, download_path: str, message_updater=None, status_message=None, context=None) -> dict:
        """下载网易云音乐"""
        import threading
        try:
            if not self.netease_downloader:
                # 尝试重新初始化网易云音乐下载器
                try:
                    # 动态导入neteasecloud_music模块，避免全局导入失败的影响
                    import neteasecloud_music
                    from neteasecloud_music import NeteaseDownloader
                    
                    # 直接使用NeteaseDownloader，不需要适配器
                    self.netease_downloader = NeteaseDownloader(bot=self)
                    logger.info(f"🎵 网易云音乐下载器重新初始化成功 (模块: {neteasecloud_music.__file__})")
                except Exception as e:
                    logger.warning(f"网易云音乐下载器重新初始化失败: {e}")
                    return {
                        "success": False,
                        "error": "网易云音乐下载器未初始化且重新初始化失败",
                        "platform": "Netease",
                        "content_type": "music"
                    }

            # 更新消息状态
            if message_updater and callable(message_updater):
                try:
                    if asyncio.iscoroutinefunction(message_updater):
                        await message_updater("🎵 正在解析网易云音乐链接...")
                    else:
                        message_updater("🎵 正在解析网易云音乐链接...")
                except Exception as e:
                    logger.warning(f"消息更新失败: {e}")

            # 设置音质
            quality = self.netease_downloader.get_quality_setting()

            # 创建进度回调
            progress_data = {"final_filename": None, "lock": threading.Lock()}

            if message_updater:
                progress_callback = netease_music_progress_hook(
                    message_updater=message_updater,
                    progress_data=progress_data,
                    status_message=status_message,
                    context=context
                )
            else:
                progress_callback = lambda d: None

            # 使用新的download_by_url方法，自动处理所有链接格式
            logger.info(f"🔗 使用新的download_by_url方法处理链接: {url}")
            
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.get_event_loop()

            if loop is None:
                return {
                    "success": False,
                    "error": "无法获取事件循环",
                    "platform": "Netease",
                    "content_type": "music"
                }

            # 调用download_by_url方法，它会自动识别链接类型并调用相应的下载方法
            result = await loop.run_in_executor(
                None,
                self.netease_downloader.download_by_url,
                url,
                str(download_path),
                self.netease_downloader.quality_map.get(quality, '320k'),
                progress_callback
            )

            if result.get('success'):
                # 根据下载类型返回相应的结果
                if 'playlist_name' in result:
                    # 歌单下载结果
                    return {
                        "success": True,
                        "message": result.get('message', '网易云音乐歌单下载完成'),
                        "platform": "Netease",
                        "content_type": "music",
                        "download_path": result.get('download_path', ''),
                        "playlist_name": result.get('playlist_name', ''),
                        "creator": result.get('creator', ''),
                        "total_songs": result.get('total_songs', 0),
                        "downloaded_songs": result.get('downloaded_songs', 0),
                        "failed_songs": result.get('failed_songs', 0),
                        "total_size_mb": result.get('total_size_mb', 0),
                        "songs": result.get('songs', []),
                        "quality": result.get('quality', quality),
                        "failed_details": result.get('failed_details', [])
                    }
                elif 'album_name' in result:
                    # 专辑下载结果
                    return {
                        "success": True,
                        "message": result.get('message', '网易云音乐专辑下载完成'),
                        "platform": "Netease",
                        "content_type": "music",
                        "download_path": result.get('download_path', ''),
                        "album_name": result.get('album_name', ''),
                        "total_songs": result.get('total_songs', 0),
                        "downloaded_songs": result.get('downloaded_songs', 0),
                        "total_size_mb": result.get('total_size_mb', 0),
                        "songs": result.get('songs', []),
                        "quality": result.get('quality', quality)
                    }
                else:
                    # 单曲下载结果
                    return {
                        "success": True,
                        "message": result.get('message', '网易云音乐单曲下载完成'),
                        "platform": "Netease",
                        "content_type": "music",
                        "download_path": result.get('download_path', ''),
                        "filename": result.get('filename', ''),
                        "size_mb": result.get('size_mb', 0),
                        "song_title": result.get('song_title', ''),
                        "song_artist": result.get('song_artist', ''),
                        "quality": result.get('quality', quality),
                        "quality_name": result.get('quality_name', '未知'),
                        "bitrate": result.get('bitrate', '未知'),
                        "duration": result.get('duration', '未知'),
                        "file_format": result.get('file_format', 'MP3')
                    }
            else:
                return {
                    "success": False,
                    "error": result.get('error', '下载失败'),
                    "platform": "Netease",
                    "content_type": "music"
                }

                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = asyncio.get_event_loop()

                if loop is None:
                    return {
                        "success": False,
                        "error": "无法获取事件循环",
                        "platform": "Netease",
                        "content_type": "music"
                    }

                if song_id:
                    # 直接使用歌曲ID下载单曲
                    result = await loop.run_in_executor(
                        None,
                        self.netease_downloader.download_song_by_id,
                        song_id,
                        str(download_path),
                        self.netease_downloader.quality_map.get(quality, '320k'),
                        progress_callback
                    )
                else:
                    # 如果无法提取ID，使用通用搜索
                    search_keyword = "热门歌曲"
                    result = await loop.run_in_executor(
                        None,
                        self.netease_downloader.download_song_by_search,
                        search_keyword,
                        "",  # artist
                        str(download_path),
                        self.netease_downloader.quality_map.get(quality, '320k'),
                        progress_callback
                    )

                if result.get('success'):
                    return {
                        "success": True,
                        "message": result.get('message', '网易云音乐单曲下载完成'),
                        "platform": "Netease",
                        "content_type": "music",
                        "download_path": result.get('download_path', ''),
                        "filename": result.get('filename', ''),
                        "size_mb": result.get('size_mb', 0),
                        "song_title": result.get('song_title', ''),
                        "song_artist": result.get('song_artist', ''),
                        "quality": result.get('quality', quality),
                        "quality_name": result.get('quality_name', '未知'),
                        "bitrate": result.get('bitrate', '未知'),
                        "duration": result.get('duration', '未知'),
                        "file_format": result.get('file_format', 'MP3')
                    }
                else:
                    return {
                        "success": False,
                        "error": result.get('error', '单曲下载失败'),
                        "platform": "Netease",
                        "content_type": "music"
                    }

        except Exception as e:
            logger.error(f"网易云音乐下载异常: {str(e)}")
            return {
                "success": False,
                "error": f"下载失败: {str(e)}",
                "platform": "Netease",
                "content_type": "music"
            }

    async def _download_qqmusic_music(self, url: str, download_path: str, message_updater=None, status_message=None, context=None) -> dict:
        """下载QQ音乐"""
        import threading
        try:
            if not self.qqmusic_downloader:
                # 尝试重新初始化QQ音乐下载器
                try:
                    # 动态导入qqmusic_downloader模块，避免全局导入失败的影响
                    import qqmusic_downloader
                    from qqmusic_downloader import QQMusicDownloader
                    
                    # 直接使用QQMusicDownloader
                    self.qqmusic_downloader = QQMusicDownloader(bot=self)
                    logger.info(f"🎵 QQ音乐下载器重新初始化成功 (模块: {qqmusic_downloader.__file__})")
                except Exception as e:
                    logger.warning(f"QQ音乐下载器重新初始化失败: {e}")
                    return {
                        "success": False,
                        "error": "QQ音乐下载器不可用",
                        "platform": "QQMusic",
                        "content_type": "music"
                    }

            # 更新状态消息
            if message_updater:
                try:
                    message_updater("🎵 正在解析QQ音乐链接...")
                except Exception as e:
                    logger.warning(f"消息更新失败: {e}")

            # 创建进度回调
            progress_data = {"final_filename": None, "lock": threading.Lock()}

            if message_updater:
                # 添加速度计算所需的时间跟踪
                import time
                last_time = time.time()
                last_downloaded = 0
                last_update_time = time.time()
                
                def progress_callback(progress, downloaded, total, filename=None):
                    nonlocal last_time, last_downloaded, last_update_time
                    try:
                        with progress_data["lock"]:
                            if total > 0:
                                # 添加频率控制：每0.2秒更新一次（提高更新频率）
                                current_time = time.time()
                                if current_time - last_update_time < 0.2:
                                    return
                                last_update_time = current_time
                                progress_percent = (downloaded / total) * 100
                                total_mb = total / (1024 * 1024)
                                downloaded_mb = downloaded / (1024 * 1024)
                                
                                # 计算真正的下载速度
                                time_diff = current_time - last_time
                                downloaded_diff = downloaded - last_downloaded
                                
                                if time_diff > 0 and downloaded_diff > 0:
                                    speed_bytes_per_sec = downloaded_diff / time_diff
                                    speed_mb = speed_bytes_per_sec / (1024 * 1024)
                                elif progress_percent >= 100:
                                    # 下载完成时，显示"完成"
                                    speed_mb = "完成"
                                else:
                                    speed_mb = 0
                                
                                # 更新时间和下载量
                                last_time = current_time
                                last_downloaded = downloaded
                                
                                # 计算预计剩余时间
                                if isinstance(speed_mb, (int, float)) and speed_mb > 0 and total > downloaded:
                                    remaining = total - downloaded
                                    eta_seconds = int(remaining / (speed_bytes_per_sec))
                                    mins, secs = divmod(eta_seconds, 60)
                                    if mins > 0:
                                        eta_str = f"{mins:02d}:{secs:02d}"
                                    else:
                                        eta_str = f"00:{secs:02d}"
                                else:
                                    eta_str = "未知"
                                
                                # 创建进度条（参考网易云音乐格式）
                                def _create_progress_bar(percent: float, length: int = 20) -> str:
                                    filled_length = int(length * percent / 100)
                                    return "█" * filled_length + "░" * (length - filled_length)
                                
                                progress_bar = _create_progress_bar(progress_percent)
                                
                                # 处理文件名显示
                                display_filename = "正在下载..."
                                if filename:
                                    # 清理文件名显示（参考网易云音乐格式）
                                    import os
                                    display_filename = os.path.basename(filename)
                                    if len(display_filename) > 35:
                                        name, ext = os.path.splitext(display_filename)
                                        display_filename = name[:30] + "..." + ext
                                
                                # 使用和网易云音乐相同的格式
                                if isinstance(speed_mb, str):
                                    speed_display = speed_mb
                                else:
                                    speed_display = f"{speed_mb:.2f}MB/s"
                                
                                progress_text = (
                                    f"🎵 音乐: QQ音乐下载中...\n"
                                    f"📝 文件: {display_filename}\n"
                                    f"💾 大小: {downloaded_mb:.2f}MB / {total_mb:.2f}MB\n"
                                    f"⚡ 速度: {speed_display}\n"
                                    f"⏳ 预计剩余: {eta_str}\n"
                                    f"📊 进度: {progress_bar} ({progress_percent:.1f}%)"
                                )
                                
                                # 处理异步函数
                                if asyncio.iscoroutinefunction(message_updater):
                                    # 异步函数，使用 run_coroutine_threadsafe
                                    try:
                                        loop = asyncio.get_running_loop()
                                        asyncio.run_coroutine_threadsafe(
                                            message_updater(progress_text), loop
                                        )
                                    except Exception as e:
                                        logger.warning(f"异步消息更新失败: {e}")
                                else:
                                    # 同步函数，直接调用
                                    message_updater(progress_text)
                    except Exception as e:
                        logger.warning(f"QQ音乐进度更新失败: {e}")
            else:
                progress_callback = None

            # 使用asyncio.run_in_executor在独立线程中运行同步的下载函数
            import asyncio
            loop = asyncio.get_event_loop()
            
            # 调用download_by_url方法
            result = await loop.run_in_executor(
                None,
                self.qqmusic_downloader.download_by_url,
                url,
                str(download_path),
                'best',  # 使用最高音质
                progress_callback
            )

            if result.get('success'):
                # 检查是否为歌单下载
                if result.get('playlist_name'):
                    # 歌单下载结果
                    return {
                        "success": True,
                        "platform": "QQMusic",
                        "content_type": "music",
                        "download_path": result.get('download_path', ''),
                        "playlist_name": result.get('playlist_name', ''),
                        "total_songs": result.get('total_songs', 0),
                        "downloaded_songs": result.get('downloaded_songs', 0),
                        "failed_songs": result.get('failed_songs', 0),
                        "total_size_mb": result.get('total_size_mb', 0),
                        "quality": result.get('quality', '未知'),
                        "downloaded_list": result.get('downloaded_list', []),
                        "failed_list": result.get('failed_list', []),
                        "url": url
                    }
                # 检查是否为专辑下载
                elif result.get('album_name'):
                    # 专辑下载结果
                    return {
                        "success": True,
                        "platform": "QQMusic",
                        "content_type": "music",
                        "download_path": result.get('download_path', ''),
                        "album_name": result.get('album_name', ''),
                        "singer_name": result.get('singer_name', ''),
                        "total_songs": result.get('total_songs', 0),
                        "downloaded_songs": result.get('downloaded_songs', 0),
                        "failed_songs": result.get('failed_songs', 0),
                        "downloaded_list": result.get('downloaded_list', []),
                        "failed_list": result.get('failed_list', []),
                        "url": url
                    }
                else:
                    # 单首歌曲下载结果
                    song_info = result.get('song_info', {})
                    
                    # 正确提取歌手信息
                    song_artist = song_info.get('singer', '未知歌手')
                    
                    # 正确提取专辑信息
                    album_name = song_info.get('album', '未知专辑')
                    
                    return {
                        "success": True,
                        "platform": "QQMusic",
                        "content_type": "music",
                        "file_path": result.get('file_path', ''),
                        "song_title": song_info.get('title', '未知歌曲'),
                        "song_artist": song_artist,
                        "album": album_name,
                        "quality": song_info.get('quality', '未知音质'),
                        "format": song_info.get('format', '未知格式'),
                        "duration": song_info.get('interval', 0),
                        "url": url
                    }
            else:
                return {
                    "success": False,
                    "error": result.get('error', 'QQ音乐下载失败'),
                    "platform": "QQMusic",
                    "content_type": "music"
                }

        except Exception as e:
            logger.error(f"QQ音乐下载异常: {str(e)}")
            return {
                "success": False,
                "error": f"下载失败: {str(e)}",
                "platform": "QQMusic",
                "content_type": "music"
            }

    async def _download_youtubemusic_music(self, url: str, download_path: str, message_updater=None, status_message=None, context=None) -> dict:
        """下载YouTube Music"""
        import threading
        try:
            if not self.youtubemusic_downloader:
                # 尝试重新初始化YouTube Music下载器
                try:
                    # 动态导入youtubemusic_downloader模块，避免全局导入失败的影响
                    import youtubemusic_downloader
                    from youtubemusic_downloader import YouTubeMusicDownloader
                    
                    # 直接使用YouTubeMusicDownloader
                    self.youtubemusic_downloader = YouTubeMusicDownloader(bot=self)
                    logger.info(f"🎵 YouTube Music下载器重新初始化成功 (模块: {youtubemusic_downloader.__file__})")
                except Exception as e:
                    logger.warning(f"YouTube Music下载器重新初始化失败: {e}")
                    return {
                        "success": False,
                        "error": "YouTube Music下载器不可用",
                        "platform": "YouTubeMusic",
                        "content_type": "music"
                    }

            # 更新状态消息
            if message_updater:
                try:
                    if asyncio.iscoroutinefunction(message_updater):
                        await message_updater("🎵 正在解析YouTube Music链接...")
                    else:
                        message_updater("🎵 正在解析YouTube Music链接...")
                except Exception as e:
                    logger.warning(f"消息更新失败: {e}")

            # 设置音质
            quality = 'best'  # YouTube Music默认使用最高音质

            # 创建进度回调
            progress_data = {"final_filename": None, "lock": threading.Lock()}

            def youtubemusic_progress_callback(data):
                """
YouTube Music下载进度回调函数"""
                try:
                    # 处理字符串格式的消息（完成消息）
                    if isinstance(data, str):
                        if message_updater:
                            try:
                                if asyncio.iscoroutinefunction(message_updater):
                                    # 异步函数，使用 run_coroutine_threadsafe
                                    try:
                                        loop = asyncio.get_running_loop()
                                        asyncio.run_coroutine_threadsafe(
                                            message_updater(data), loop
                                        )
                                    except Exception as e:
                                        logger.warning(f"异步消息更新失败: {e}")
                                else:
                                    # 同步函数，直接调用
                                    message_updater(data)
                            except Exception as e:
                                logger.warning(f"YouTube Music消息更新失败: {e}")
                    # 处理字典格式的消息（下载进度）
                    elif isinstance(data, dict) and data.get('status') == 'downloading':
                        progress_text = data.get('progress_text', '')
                        if progress_text and message_updater:
                            try:
                                if asyncio.iscoroutinefunction(message_updater):
                                    # 异步函数，使用 run_coroutine_threadsafe
                                    try:
                                        loop = asyncio.get_running_loop()
                                        asyncio.run_coroutine_threadsafe(
                                            message_updater(progress_text), loop
                                        )
                                    except Exception as e:
                                        logger.warning(f"异步消息更新失败: {e}")
                                else:
                                    # 同步函数，直接调用
                                    message_updater(progress_text)
                            except Exception as e:
                                logger.warning(f"YouTube Music进度更新失败: {e}")
                    elif isinstance(data, dict) and data.get('status') == 'finished':
                        if message_updater:
                            finished_text = data.get('progress_text', '✅ YouTube Music下载完成')
                            try:
                                if asyncio.iscoroutinefunction(message_updater):
                                    try:
                                        loop = asyncio.get_running_loop()
                                        asyncio.run_coroutine_threadsafe(
                                            message_updater(finished_text), loop
                                        )
                                    except Exception as e:
                                        logger.warning(f"异步消息更新失败: {e}")
                                else:
                                    message_updater(finished_text)
                            except Exception as e:
                                logger.warning(f"YouTube Music完成消息更新失败: {e}")
                except Exception as e:
                    logger.warning(f"YouTube Music进度回调处理失败: {e}")

            # 使用asyncio.run_in_executor在独立线程中运行同步的下载函数
            import asyncio
            loop = asyncio.get_event_loop()
            
            # 调用download_by_url方法
            result = await loop.run_in_executor(
                None,
                self.youtubemusic_downloader.download_by_url,
                url,
                str(download_path),
                quality,
                youtubemusic_progress_callback
            )

            if result.get('success'):
                # 根据下载类型返回相应的结果
                if 'playlist_name' in result:
                    # 播放列表下载结果
                    return {
                        "success": True,
                        "message": result.get('message', 'YouTube Music 播放列表下载完成'),
                        "platform": "YouTubeMusic",
                        "content_type": "music",
                        "download_path": result.get('download_path', ''),
                        "playlist_name": result.get('playlist_name', ''),
                        "creator": result.get('creator', ''),
                        "total_songs": result.get('total_songs', 0),
                        "downloaded_songs": result.get('downloaded_songs', 0),
                        "failed_songs": result.get('failed_songs', 0),
                        "total_size_mb": result.get('total_size_mb', 0),
                        "songs": result.get('songs', []),
                        "quality": result.get('quality', quality),
                        "url": result.get('url', url)
                    }
                elif 'album_name' in result:
                    # 专辑下载结果
                    return {
                        "success": True,
                        "message": result.get('message', 'YouTube Music 专辑下载完成'),
                        "platform": "YouTubeMusic",
                        "content_type": "music",
                        "download_path": result.get('download_path', ''),
                        "album_name": result.get('album_name', ''),
                        "total_songs": result.get('total_songs', 0),
                        "downloaded_songs": result.get('downloaded_songs', 0),
                        "total_size_mb": result.get('total_size_mb', 0),
                        "songs": result.get('songs', []),
                        "quality": result.get('quality', quality),
                        "url": result.get('url', url)
                    }
                else:
                    # 单曲下载结果
                    return {
                        "success": True,
                        "message": result.get('message', 'YouTube Music 单曲下载完成'),
                        "platform": "YouTubeMusic",
                        "content_type": "music",
                        "download_path": result.get('download_path', ''),
                        "filename": result.get('filename', ''),
                        "file_path": result.get('file_path', ''),
                        "size_mb": result.get('size_mb', 0),
                        "song_title": result.get('song_title', ''),
                        "song_artist": result.get('song_artist', ''),
                        "quality": result.get('quality', quality),
                        "format": result.get('format', 'M4A'),
                        "duration": result.get('duration', 0),
                        "url": result.get('url', url)
                    }
            else:
                return {
                    "success": False,
                    "error": result.get('error', 'YouTube Music下载失败'),
                    "platform": "YouTubeMusic",
                    "content_type": "music"
                }

        except Exception as e:
            logger.error(f"YouTube Music下载异常: {str(e)}")
            return {
                "success": False,
                "error": f"下载失败: {str(e)}",
                "platform": "YouTubeMusic",
                "content_type": "music"
            }


class TelegramBot:
    def __init__(self, token: str, downloader: VideoDownloader):
        self.token = token
        self.downloader = downloader
        # 设置下载器对bot的引用，以便访问设置
        self.downloader.bot = self
        self.application = None
        self.bot_id = None
        self.qbit_client = None
        
        # 初始化消息处理器
        try:
            self.message_handler = TelegramMessageHandler(self)
            logger.info("✅ 消息处理器初始化成功")
        except Exception as e:
            logger.error(f"❌ 消息处理器初始化失败：{e}")
            self.message_handler = None

        # 初始化配置管理器（仅使用数据库）
        try:
            self.config_manager = ConfigManager("/app/db/savextube.db")
            # 从数据库加载配置
            self.config = self.config_manager.get_all_config()
            logger.info("✅ 使用 SQLite 数据库配置")
        except Exception as e:
            logger.error(f"❌ SQLite 数据库配置初始化失败: {e}")
            raise  # 直接抛出异常，不回退到文件配置
        
        # 设置配置项
        self.auto_download_enabled = self.config.get("auto_download_enabled", True)
        self.download_tasks = (
            {}
        )  # 存储下载任务 {task_id: {'task': asyncio.Task, 'cancelled': bool}}
        self.task_lock = asyncio.Lock()  # 用于保护任务字典的锁
        self.user_client: Optional[TelegramClient] = None
        self.main_loop: Optional[asyncio.AbstractEventLoop] = None  # 保存主事件循环

        # 新增：B站自动下载全集配置
        self.bilibili_auto_playlist = self.config.get("bilibili_auto_playlist", False)  # 默认关闭自动下载全集

        # 新增：YouTube音频模式配置
        self.youtube_audio_mode = self.config.get("youtube_audio_mode", False)  # 默认关闭音频模式

        # 新增：YouTube Mix播放列表自动下载配置
        self.youtube_mix_playlist = self.config.get("youtube_mix_playlist", False)  # 默认关闭Mix播放列表下载

        # 新增：YouTube ID标签配置
        self.youtube_id_tags = self.config.get("youtube_id_tags", False)  # 默认关闭ID标签

        # 新增：B站弹幕下载配置
        self.bilibili_danmaku_download = self.config.get("bilibili_danmaku_download", False)  # 默认关闭弹幕下载

        # 新增：B站UGC播放列表自动下载配置
        self.bilibili_ugc_playlist = self.config.get("bilibili_ugc_playlist", False)  # 默认关闭UGC合集下载

        # 新增：网易云歌词合并配置
        self.netease_lyrics_merge = self.config.get("netease_lyrics_merge", False)  # 默认关闭歌词合并

        # 新增：网易云artist下载配置
        self.netease_artist_download = self.config.get("netease_artist_download", True)  # 默认开启artist下载

        # 新增：网易云cover下载配置
        self.netease_cover_download = self.config.get("netease_cover_download", True)  # 默认开启cover下载

        # 新增：YouTube封面下载配置
        self.youtube_thumbnail_download = self.config.get("youtube_thumbnail_download", False)  # 默认关闭封面下载

        # 新增：YouTube字幕下载配置
        self.youtube_subtitle_download = self.config.get("youtube_subtitle_download", False)  # 默认关闭字幕下载

        # 新增：YouTube时间戳命名配置
        self.youtube_timestamp_naming = self.config.get("youtube_timestamp_naming", False)  # 默认关闭时间戳命名

        # 新增：B站封面下载配置
        self.bilibili_thumbnail_download = self.config.get("bilibili_thumbnail_download", False)  # 默认关闭B站封面下载

        # B站收藏夹订阅管理器 - 确保属性始终存在
        self.fav_manager = None  # 先设置默认值
        try:
            self.fav_manager = BilibiliFavSubscriptionManager(
                download_path=self.downloader.download_path,
                proxy_host=self.downloader.proxy_host,
                cookies_path=self.downloader.b_cookies_path
            )
            logger.info("✅ B站收藏夹订阅管理器初始化成功")
        except Exception as e:
            logger.warning(f"⚠️ 初始化 B站收藏夹订阅管理器失败: {e}")
            # self.fav_manager 已经是 None

        # qBittorrent 配置 - 优先从TOML配置文件读取，回退到环境变量
        self.qb_config = {
            "host": None,
            "port": None,
            "username": None,
            "password": None,
            "enabled": False,  # 默认禁用
        }

        # 尝试从TOML配置文件读取qBittorrent配置
        toml_config = None
        if load_toml_config and get_qbittorrent_config:
            try:
                # 尝试多个可能的配置文件路径
                config_paths = [
                    "savextube.toml",
                    "savextube_full.toml",
                    "/app/config/savextube.toml",
                    "config.toml"
                ]
                
                for config_path in config_paths:
                    if os.path.exists(config_path):
                        logger.info(f"📖 尝试从TOML配置文件读取qBittorrent配置: {config_path}")
                        toml_config = load_toml_config(config_path)
                        if toml_config:
                            qb_toml_config = get_qbittorrent_config(toml_config)
                            if qb_toml_config and all(qb_toml_config.values()):
                                self.qb_config.update(qb_toml_config)
                                logger.info(f"✅ 从TOML配置文件成功读取qBittorrent配置: {config_path}")
                                break
            except Exception as e:
                logger.warning(f"⚠️ 从TOML配置文件读取qBittorrent配置失败: {e}")

        # 如果TOML配置不完整，尝试从环境变量读取
        if not all([self.qb_config["host"], self.qb_config["port"], 
                   self.qb_config["username"], self.qb_config["password"]]):
            logger.info("📖 从环境变量读取qBittorrent配置")
            env_config = {
                "host": os.getenv("QB_HOST"),
                "port": os.getenv("QB_PORT"),
                "username": os.getenv("QB_USERNAME"),
                "password": os.getenv("QB_PASSWORD"),
            }
            
            # 只更新未设置的配置项
            for key, value in env_config.items():
                if value and not self.qb_config[key]:
                    self.qb_config[key] = value

        # 检查是否有完整的 qBittorrent 配置
        if all([
            self.qb_config["host"],
            self.qb_config["port"],
            self.qb_config["username"],
            self.qb_config["password"],
        ]):
            try:
                self.qb_config["port"] = int(self.qb_config["port"])
                self.qb_config["enabled"] = True
                logger.info(f"✅ 已配置 qBittorrent: {self.qb_config['host']}:{self.qb_config['port']}")
            except (ValueError, TypeError):
                logger.warning("qBittorrent 端口配置无效，跳过连接")
        else:
            logger.info("❌ 未配置 qBittorrent (缺少必要的配置项)")

        # 新增：权限管理
        self.allowed_user_ids = self._parse_user_ids(os.getenv("TELEGRAM_BOT_ALLOWED_USER_IDS", ""))
        logger.info(f"🔐 允许的用户: {self.allowed_user_ids}")

    async def hot_reload_user_client(self, session_string: str, api_id: Optional[str] = None, api_hash: Optional[str] = None) -> str:
        """在主事件循环中热重载 Telethon user_client"""
        try:
            # 断开旧客户端
            if self.user_client:
                try:
                    await self.user_client.disconnect()
                except Exception:
                    pass
                self.user_client = None

            # 参数兜底
            api_id = api_id or os.getenv("TELEGRAM_BOT_API_ID")
            api_hash = api_hash or os.getenv("TELEGRAM_BOT_API_HASH")
            if not api_id or not api_hash:
                return "missing api_id/api_hash"

            # 构建新客户端
            # 使用64位整数处理大的API ID
            try:
                api_id_int = int(api_id)
                if api_id_int > 2147483647:  # 如果超过32位整数范围
                    logger.info(f"🔍 API ID {api_id_int} 超过32位整数范围，使用64位处理")
            except (ValueError, OverflowError) as e:
                logger.error(f"❌ API ID转换失败: {e}")
                return f"error: invalid api_id format"

            client = TelegramClient(StringSession(session_string), api_id_int, api_hash)

            # 代理配置
            if self.downloader and getattr(self.downloader, "proxy_host", None):
                from urllib.parse import urlparse
                p_url = urlparse(self.downloader.proxy_host)
                proxy_config = (p_url.scheme, p_url.hostname, p_url.port)
                client.set_proxy(proxy_config)

            await client.start()
            self.user_client = client
            logger.info("✅ Telethon 客户端热重载成功")
            return "ok"
        except Exception as e:
            logger.error(f"❌ Telethon 客户端热重载失败: {e}", exc_info=True)
            return f"error: {e}"

    def schedule_hot_reload(self, session_string: str, api_id: Optional[str] = None, api_hash: Optional[str] = None) -> str:
        """跨线程调度热重载，供Flask路由调用"""
        if not self.main_loop:
            return "no main loop"

        fut = asyncio.run_coroutine_threadsafe(
            self.hot_reload_user_client(session_string, api_id, api_hash),
            self.main_loop
        )
        try:
            return fut.result(timeout=30)
        except Exception as e:
            return f"error: {e}"

    def _parse_user_ids(self, user_ids_str: str) -> list:
        """解析用户ID字符串为列表"""
        if not user_ids_str:
            return []

        try:
            # 支持逗号、分号、空格分隔的用户ID
            user_ids = []
            for user_id_str in re.split(r"[,;\s]+", user_ids_str.strip()):
                if user_id_str.strip():
                    user_ids.append(int(user_id_str.strip()))
            return user_ids
        except ValueError as e:
            logger.error(f"解析用户ID失败: {e}")
            return []

    def _check_user_permission(self, user_id: int) -> bool:
        """检查用户是否有权限使用机器人"""
        # 如果没有配置允许的用户，则允许所有用户（向后兼容）
        if not self.allowed_user_ids:
            return True

        # 检查是否在允许的用户列表中
        return user_id in self.allowed_user_ids

    def _save_config_sync(self, config_data=None):
        """同步保存配置到数据库"""
        try:
            if config_data is None:
                config_data = {
                    "auto_download_enabled": self.auto_download_enabled,
                    "bilibili_auto_playlist": self.bilibili_auto_playlist,
                    "youtube_audio_mode": self.youtube_audio_mode,
                    "youtube_id_tags": self.youtube_id_tags,
                    "bilibili_danmaku_download": self.bilibili_danmaku_download,
                    "bilibili_ugc_playlist": self.bilibili_ugc_playlist,
                    "youtube_thumbnail_download": self.youtube_thumbnail_download,
                    "youtube_subtitle_download": self.youtube_subtitle_download,
                    "youtube_timestamp_naming": self.youtube_timestamp_naming,
                    "bilibili_thumbnail_download": self.bilibili_thumbnail_download,
                    "netease_lyrics_merge": self.netease_lyrics_merge,
                    "netease_artist_download": self.netease_artist_download,
                    "netease_cover_download": self.netease_cover_download,
                    "youtube_mix_playlist": self.youtube_mix_playlist
                }

            # 使用数据库保存配置
            if self.config_manager:
                try:
                    for key, value in config_data.items():
                        self.config_manager.set_config(key, value)
                    logger.info("配置已保存到数据库")
                except Exception as e:
                    logger.error(f"❌ 数据库保存失败: {e}")
                    raise  # 直接抛出异常，不回退到文件保存
            else:
                logger.error("❌ 配置管理器未初始化")
                raise Exception("配置管理器未初始化")
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            raise  # 直接抛出异常，不回退到文件保存

    async def _save_config_async(self):
        """异步保存配置到文件或数据库"""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._save_config_sync)



    def _extract_duration_from_filename(self, filename: str) -> str:
        """从文件名中提取时长信息"""
        try:
            # 常见的时长格式：文件名中包含时长信息
            # 例如：歌曲名 (3:45).m4a 或 歌曲名 [3:45].m4a
            import re
            
            # 匹配 (MM:SS) 或 [MM:SS] 格式
            duration_pattern = r'[\(\[\]]([0-9]+):([0-9]{2})[\)\]]'
            match = re.search(duration_pattern, filename)
            
            if match:
                minutes = int(match.group(1))
                seconds = int(match.group(2))
                return f"{minutes}:{seconds:02d}"
            
            # 如果没有找到时长信息，返回默认值
            return "未知"
            
        except Exception:
            return "未知"
    
    def _escape_markdown(self, text: str) -> str:
        """转义Markdown特殊字符"""
        if not text:
            return text

        # 先转义反斜杠，避免重复转义
        escaped_text = text.replace("\\", "\\\\")

        # 需要转义的特殊字符（不包括反斜杠，因为已经处理过了）
        special_chars = [
            "_",
            "*",
            "[",
            "]",
            "(",
            ")",
            "~",
            "`",
            ">",
            "#",
            "+",
            "-",
            "=",
            "|",
            "{",
            "}",
            ".",
            "!",
        ]

        for char in special_chars:
            escaped_text = escaped_text.replace(char, f"\\{char}")

        return escaped_text

    def _get_netease_quality_info(self, quality: str) -> dict:
        """获取网易云音质的详细信息（名称、格式、码率）"""
        # 音质映射表
        quality_map = {
            'standard': '128k',
            'higher': '320k', 
            'exhigh': '320k',
            'lossless': 'flac',
            'hires': 'flac24bit',
            'jyeffect': 'flac24bit',
            'jymaster': 'flac24bit',
            'sky': 'flac24bit',
            # 兼容旧参数
            'high': '320k',
            'master': 'flac24bit',
            'surround': 'flac24bit'
        }
        
        # 详细音质信息
        quality_info_map = {
            '128k': {'name': '标准', 'format': 'MP3', 'bitrate': '16bit/44khz/128kbps'},
            '320k': {'name': '较高', 'format': 'MP3', 'bitrate': '16bit/44khz/320kbps'},
            'flac': {'name': '无损', 'format': 'FLAC', 'bitrate': '16bit/44khz/1058kbps'},
            'flac24bit': {'name': '高解析度无损', 'format': 'FLAC', 'bitrate': '24bit/96khz/2016kbps'}
        }
        
        # 获取质量代码
        quality_code = quality_map.get(quality, quality)
        
        # 返回详细信息
        return quality_info_map.get(quality_code, {
            'name': quality.upper(),
            'format': 'Unknown',
            'bitrate': 'Unknown'
        })
    
    def _get_qqmusic_quality_info(self, quality: str) -> dict:
        """获取QQ音乐音质的详细信息（名称、格式、码率）"""
        # 音质映射表
        quality_map = {
            'best': 'flac',
            'flac': 'flac',
            '320mp3': '320k',
            '128mp3': '128k',
            '96aac': '96k',
            '48aac': '48k',
            # 兼容其他格式
            'high': '320k',
            'standard': '128k',
            'lossless': 'flac'
        }
        
        # 详细音质信息
        quality_info_map = {
            '48k': {'name': 'AAC标准', 'format': 'AAC', 'bitrate': '48kbps'},
            '96k': {'name': 'AAC较高', 'format': 'AAC', 'bitrate': '96kbps'},
            '128k': {'name': 'MP3标准', 'format': 'MP3', 'bitrate': '16bit/44khz/128kbps'},
            '320k': {'name': 'MP3高品质', 'format': 'MP3', 'bitrate': '16bit/44khz/320kbps'},
            'flac': {'name': 'FLAC无损', 'format': 'FLAC', 'bitrate': '16bit/44khz/1058kbps'}
        }
        
        # 获取质量代码
        quality_code = quality_map.get(quality, quality)
        
        # 返回详细信息
        return quality_info_map.get(quality_code, {
            'name': quality.upper(),
            'format': 'Unknown',
            'bitrate': 'Unknown'
        })

    def _extract_artist_from_path(self, download_path: str, album_name: str, songs: list = None) -> str:
        """从下载路径或歌曲列表中提取艺术家信息"""
        try:
            # 首先尝试从歌曲列表中提取艺术家
            if songs and len(songs) > 0:
                artist_counts = {}
                for song in songs[:5]:  # 只检查前5首歌，提高效率
                    song_title = song.get('title', '')
                    if ' - ' in song_title:
                        # 格式：歌曲名 - 艺术家
                        artist = song_title.split(' - ')[1].strip()
                        # 去除合作艺术家标识
                        if ',' in artist:
                            artist = artist.split(',')[0].strip()
                        # 统计艺术家出现次数
                        if artist and artist != '':
                            artist_counts[artist] = artist_counts.get(artist, 0) + 1
                
                # 选择出现次数最多的艺术家
                if artist_counts:
                    most_common_artist = max(artist_counts, key=artist_counts.get)
                    if most_common_artist:
                        return most_common_artist
            
            # 从路径中提取艺术家信息
            # 路径格式通常是：/downloads/Netease/艺术家/专辑名称
            path_parts = download_path.split('/')
            
            # 查找可能的艺术家目录（排除专辑名和系统目录）
            for part in reversed(path_parts):
                if (part and 
                    part != album_name and 
                    not part.startswith('downloads') and
                    not part.startswith('Netease') and
                    not part.startswith('netease') and
                    part != 'v04' and
                    not part.endswith('(2016)') and  # 排除年份信息
                    not part.endswith('(2017)') and
                    not part.endswith('(2018)') and
                    not part.endswith('(2019)') and
                    not part.endswith('(2020)') and
                    not part.endswith('(2021)') and
                    not part.endswith('(2022)') and
                    not part.endswith('(2023)') and
                    not part.endswith('(2024)')):
                    return part
            
            # 如果路径中没有找到艺术家，尝试从专辑名称中提取
            if ' - ' in album_name:
                artist = album_name.split(' - ')[0].strip()
                return artist
            
            # 默认返回未知艺术家
            return "未知艺术家"
                
        except Exception as e:
            logger.warning(f"提取艺术家信息失败: {e}")
            return "未知艺术家"

    async def post_init(self, application: Application):
        """在应用启动后运行的初始化任务, 获取机器人自身 ID"""
        print("🚀 [INIT] post_init 开始执行...")
        bot_info = await application.bot.get_me()
        self.bot_id = bot_info.id
        print(f"🤖 [INIT] 机器人已启动: @{bot_info.username} (ID: {self.bot_id})")
        logger.info(f"机器人已启动，用户名为: @{bot_info.username} (ID: {self.bot_id})")

        # 设置命令菜单
        print("🔧 [INIT] 准备设置命令菜单...")
        await self._setup_bot_commands(application.bot)
        print("✅ [INIT] post_init 执行完成")

    async def _setup_bot_commands(self, bot: Bot):
        """设置Bot命令菜单"""
        try:
            print("🔧 [MENU] 开始设置Telegram Bot命令菜单...")
            logger.info("🔧 开始设置Telegram Bot命令菜单...")

            # 定义命令菜单
            from telegram import BotCommand
            commands = [
                BotCommand("start", "🏁 开始使用"),
                BotCommand("help", "📖 查看帮助"),
                BotCommand("status", "📊 查看下载统计"),
                BotCommand("cancel", "❌ 取消下载任务"),
                BotCommand("version", "🔧 查看版本信息"),
                BotCommand("settings", "⚙️ 功能设置"),
                BotCommand("favsub", "📚 B站收藏夹订阅下载"),
                BotCommand("cleanup", "🧹 清理临时文件"),
                BotCommand("reboot", "🔄 重启容器"),
            ]

            print(f"🔧 [MENU] 准备设置 {len(commands)} 个命令")
            for i, cmd in enumerate(commands, 1):
                print(f"  {i}. /{cmd.command} - {cmd.description}")

            # 设置命令菜单
            print("🔧 [MENU] 正在调用 set_my_commands...")
            await bot.set_my_commands(commands)
            print("✅ [MENU] set_my_commands 调用成功")
            logger.info(f"✅ 已成功设置Telegram Bot命令菜单，共 {len(commands)} 个命令")

            # 验证设置
            print("🔍 [MENU] 验证命令菜单设置...")
            set_commands = await bot.get_my_commands()
            print(f"🔍 [MENU] 获取到 {len(set_commands)} 个已设置的命令")

            if len(set_commands) == len(commands):
                print("🎉 [MENU] 命令菜单设置完全成功！")
                logger.info("🎉 命令菜单设置完全成功！")
                logger.info("📋 可用命令:")
                for cmd in set_commands:
                    print(f"  ✅ /{cmd.command} - {cmd.description}")
                    logger.info(f"  /{cmd.command} - {cmd.description}")
            else:
                print(f"⚠️ [MENU] 命令菜单设置可能有问题，期望 {len(commands)} 个，实际 {len(set_commands)} 个")
                logger.warning(f"⚠️ 命令菜单设置可能有问题，期望 {len(commands)} 个，实际 {len(set_commands)} 个")

        except Exception as e:
            print(f"❌ [MENU] 设置命令菜单失败: {e}")
            logger.error(f"❌ 设置命令菜单失败: {e}")
            import traceback
            print(f"❌ [MENU] 详细错误: {traceback.format_exc()}")
            logger.error(f"详细错误: {traceback.format_exc()}")

    def _connect_qbittorrent(self):
        """连接到 qBittorrent 客户端"""
        try:
            # 检查是否启用了 qBittorrent
            if not self.qb_config["enabled"]:
                return

            logger.info(
                f"正在连接 qBittorrent: {self.qb_config['host']}:{self.qb_config['port']}"
            )

            # 创建客户端
            self.qbit_client = qbittorrentapi.Client(
                host=self.qb_config["host"],
                port=self.qb_config["port"],
                username=self.qb_config["username"],
                password=self.qb_config["password"],
                VERIFY_WEBUI_CERTIFICATE=False,  # 禁用SSL证书验证
                REQUESTS_ARGS={"timeout": 10},  # 设置10秒超时
            )

            # 尝试登录
            self.qbit_client.auth_log_in()

            # 检查连接状态
            if not self.qbit_client.is_logged_in:
                logger.error("qBittorrent 连接失败")
                self.qbit_client = None
                return

            # 获取 qBittorrent 版本信息
            try:
                version_info = self.qbit_client.app.version
                logger.info(f"qBittorrent 连接成功 (版本: {version_info})")
            except Exception as e:
                logger.info("qBittorrent 连接成功")

            # 创建标签
            try:
                self.qbit_client.torrents_create_tags(tags="savextube")
            except Exception:
                pass

        except qbittorrentapi.LoginFailed as e:
            logger.error("qBittorrent 连接失败: 用户名或密码错误")
            self.qbit_client = None
        except qbittorrentapi.APIConnectionError as e:
            logger.error("qBittorrent 连接失败: 无法连接到服务器")
            self.qbit_client = None
        except Exception as e:
            logger.error(f"qBittorrent 连接失败: {e}")
            self.qbit_client = None

    def _is_magnet_link(self, text: str) -> bool:
        magnet_pattern = r"magnet:\?xt=urn:btih:[a-fA-F0-9]{32,40}"
        return bool(re.search(magnet_pattern, text))

    def _extract_magnet_links(self, text: str):
        # 支持多条磁力链接，忽略前后其它文字
        magnet_pattern = r"(magnet:\?xt=urn:btih:[a-fA-F0-9]{32,40}[^\s]*)"
        return re.findall(magnet_pattern, text)

    async def add_magnet_to_qb(self, magnet_link: str) -> bool:
        """添加磁力链接到 qBittorrent"""
        try:
            # 检查 qBittorrent 客户端是否可用
            if not self.qbit_client:
                logger.error("qBittorrent 客户端未连接")
                return False

            # 检查登录状态
            if not self.qbit_client.is_logged_in:
                logger.error("qBittorrent 未登录")
                return False

            # 验证磁力链接格式
            if not self._is_magnet_link(magnet_link):
                logger.error(f"无效的磁力链接格式: {magnet_link}")
                return False

            logger.info(f"正在添加磁力链接到 qBittorrent: {magnet_link[:50]}...")

            # 添加磁力链接
            self.qbit_client.torrents_add(urls=magnet_link, tags="savextube")

            logger.info("✅ 成功添加磁力链接到 qBittorrent")
            return True

        except qbittorrentapi.APIConnectionError as e:
            logger.error(f"qBittorrent API 连接错误: {e}")
            return False
        except qbittorrentapi.LoginFailed as e:
            logger.error(f"qBittorrent 登录失败: {e}")
            return False
        except Exception as e:
            logger.error(f"添加磁力链接失败: {e}")
            logger.error(f"错误类型: {type(e).__name__}")
            return False

    async def add_torrent_file_to_qb(self, torrent_data: bytes, filename: str) -> bool:
        """添加种子文件到 qBittorrent"""
        try:
            # 检查 qBittorrent 客户端是否可用
            if not self.qbit_client:
                logger.error("qBittorrent 客户端未连接")
                return False

            # 检查登录状态
            if not self.qbit_client.is_logged_in:
                logger.error("qBittorrent 未登录")
                return False

            logger.info(f"正在添加种子文件到 qBittorrent: {filename}")

            # 将字节数据写入临时文件
            import tempfile
            import os

            with tempfile.NamedTemporaryFile(delete=False, suffix='.torrent') as temp_file:
                temp_file.write(torrent_data)
                temp_file_path = temp_file.name

            try:
                # 使用临时文件路径添加种子
                self.qbit_client.torrents_add(torrent_files=temp_file_path, tags="savextube")
                logger.info("✅ 成功添加种子文件到 qBittorrent")
                return True
            finally:
                # 清理临时文件
                try:
                    os.unlink(temp_file_path)
                except Exception as e:
                    logger.warning(f"清理临时文件失败: {e}")

        except qbittorrentapi.APIConnectionError as e:
            logger.error(f"qBittorrent API 连接错误: {e}")
            return False
        except qbittorrentapi.LoginFailed as e:
            logger.error(f"qBittorrent 登录失败: {e}")
            return False
        except Exception as e:
            logger.error(f"添加种子文件失败: {e}")
            logger.error(f"错误类型: {type(e).__name__}")
            return False



    def _get_resolution_quality(self, resolution):
        """根据分辨率生成质量标识，如果已有质量标识则不重复添加"""
        if not resolution or resolution == '未知':
            return ''

        # 检查是否已经包含质量标识
        import re
        quality_patterns = [r'\(8K\)', r'\(4K\)', r'\(2K\)', r'\(1080[Pp]\)', r'\(720[Pp]\)', r'\(480[Pp]\)', r'\(360[Pp]\)', r'\(\d+[Pp]\)']
        if any(re.search(pattern, resolution) for pattern in quality_patterns):
            return ''  # 已经有质量标识，不重复添加

        # 提取分辨率数字
        match = re.search(r'(\d+)x(\d+)', resolution)
        if not match:
            # 尝试匹配单个数字（如"1080 (1080p)"）
            height_match = re.search(r'(\d+)', resolution)
            if height_match:
                try:
                    height = int(height_match.group(1))
                    # 根据高度判断质量
                    if height >= 4320:
                        return ' (8K)'
                    elif height >= 2160:
                        return ' (4K)'
                    elif height >= 1440:
                        return ' (2K)'
                    elif height >= 1080:
                        return ' (1080P)'
                    elif height >= 720:
                        return ' (720P)'
                    elif height >= 480:
                        return ' (480P)'
                    elif height >= 360:
                        return ' (360P)'
                    else:
                        return f' ({height}P)'
                except (ValueError, TypeError):
                    return ''
            return ''

        try:
            width = int(match.group(1))
            height = int(match.group(2))
        except (ValueError, TypeError):
            return ''

        # 根据高度判断质量
        if height >= 4320:
            return ' (8K)'
        elif height >= 2160:
            return ' (4K)'
        elif height >= 1440:
            return ' (2K)'
        elif height >= 1080:
            return ' (1080P)'
        elif height >= 720:
            return ' (720P)'
        elif height >= 480:
            return ' (480P)'
        elif height >= 360:
            return ' (360P)'
        else:
            return ' (低画质)'





    def _signal_handler(self, signum, frame):
        """处理系统信号"""
        logger.info(f"收到信号 {signum}，正在优雅关闭...")
        if self.user_client:
            asyncio.create_task(self.user_client.disconnect())
        # 注意：executor 在这个版本中没有使用，所以移除这个调用
        # if hasattr(self, 'executor') and self.executor:
        #     self.executor.shutdown(wait=True)
        sys.exit(0)

    def _setup_handlers(self):
        """设置所有的命令和消息处理器"""
        if not self.application:
            return

        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("version", self.version_command))
        self.application.add_handler(CommandHandler("reboot", self.reboot_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        # self.application.add_handler(CommandHandler("sxt", self.sxt_command))
        # # 已删除：sxt命令处理器
        self.application.add_handler(CommandHandler("settings", self.settings_command))
        self.application.add_handler(CommandHandler("favsub", self.favsub_command))
        self.application.add_handler(CommandHandler("cancel", self.cancel_command))
        self.application.add_handler(CommandHandler("cleanup", self.cleanup_command))
        self.application.add_handler(
            CallbackQueryHandler(self.settings_button_handler, pattern="toggle_autop")
        )
        self.application.add_handler(
            CallbackQueryHandler(self.settings_button_handler, pattern="toggle_id_tags")
        )
        self.application.add_handler(
            CallbackQueryHandler(self.settings_button_handler, pattern="toggle_danmaku")
        )
        self.application.add_handler(
            CallbackQueryHandler(self.settings_button_handler, pattern="toggle_audio_mode")
        )
        self.application.add_handler(
            CallbackQueryHandler(self.settings_button_handler, pattern="toggle_ugc_playlist")
        )
        self.application.add_handler(
            CallbackQueryHandler(self.settings_button_handler, pattern="toggle_thumbnail")
        )
        self.application.add_handler(
            CallbackQueryHandler(self.settings_button_handler, pattern="toggle_subtitle")
        )
        self.application.add_handler(
            CallbackQueryHandler(self.settings_button_handler, pattern="toggle_timestamp")
        )
        self.application.add_handler(
            CallbackQueryHandler(self.settings_button_handler, pattern="toggle_bilibili_thumbnail")
        )
        self.application.add_handler(
            CallbackQueryHandler(self.settings_button_handler, pattern="toggle_lyrics_merge")
        )
        self.application.add_handler(
            CallbackQueryHandler(self.settings_button_handler, pattern="toggle_artist_download")
        )
        self.application.add_handler(
            CallbackQueryHandler(self.settings_button_handler, pattern="toggle_cover_download")
        )
        self.application.add_handler(
            CallbackQueryHandler(self.cancel_task_callback, pattern="cancel:")
        )
        # 统一的媒体处理器，明确指向新函数
        media_filter = (
            filters.AUDIO | filters.VIDEO | filters.Document.ALL
        ) & ~filters.COMMAND
        # self.application.add_handler(MessageHandler(media_filter,
        # self.handle_media)) # 禁用旧的处理器
        self.application.add_handler(
            MessageHandler(media_filter, self.download_user_media)
        )  # 启用新处理器

        # 文本消息处理器 - 保持不变
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )

        # 错误处理器
        self.application.add_error_handler(self.error_handler)
        logger.info("所有处理器已设置。")

    async def run(self):
        """启动机器人和所有客户端"""
        # 0. 保存主事件循环
        self.main_loop = asyncio.get_running_loop()

        # 1. 连接 qBittorrent
        self._connect_qbittorrent()
        # 2. 初始化并连接 Telethon 客户端
        api_id = os.getenv("TELEGRAM_BOT_API_ID")
        api_hash = os.getenv("TELEGRAM_BOT_API_HASH")
        session_string = os.getenv("TELEGRAM_SESSION_STRING")

        # 如果环境变量中没有 session_string，尝试从固定路径加载
        if not session_string:
            # 硬编码session文件路径到/app/cookies目录
            session_file_path = "/app/cookies/telethon_session.txt"

            if os.path.exists(session_file_path):
                try:
                    with open(session_file_path, "r", encoding="utf-8") as f:
                        session_string = f.read().strip()
                    logger.info(f"✅ 从文件加载 Telethon Session: {session_file_path}")
                except Exception as e:
                    logger.warning(f"⚠️ 读取 session 文件失败: {e}")
            else:
                logger.info(
                    f"ℹ️ 未找到 session 文件: {session_file_path}，请先通过 /setup 生成或设置 TELEGRAM_SESSION_STRING"
                )

        logger.info("--- Telethon 配置诊断 ---")
        logger.info(f"读取 TELEGRAM_BOT_API_ID: {'已找到' if api_id else '未找到'}")
        logger.info(
            f"读取 TELEGRAM_BOT_API_HASH: {'已找到' if api_hash else '未找到'}"
        )
        logger.info(
            f"读取 TELEGRAM_SESSION_STRING: {'已找到' if session_string else '未找到'}"
        )
        logger.info("--------------------------")
        if all([api_id, api_hash, session_string]):
            try:
                # 使用64位整数处理大的API ID
                try:
                    api_id_int = int(api_id)
                    if api_id_int > 2147483647:  # 如果超过32位整数范围
                        logger.info(f"🔍 API ID {api_id_int} 超过32位整数范围，使用64位处理")
                except (ValueError, OverflowError) as e:
                    logger.error(f"❌ API ID转换失败: {e}")
                    raise ValueError(f"Invalid API ID format: {api_id}")

                self.user_client = TelegramClient(
                    StringSession(session_string), api_id_int, api_hash
                )
                if self.downloader.proxy_host:
                    p_url = urlparse(self.downloader.proxy_host)
                    proxy_config = (p_url.scheme, p_url.hostname, p_url.port)
                    self.user_client.set_proxy(proxy_config)
                    logger.info(
                        f"Telethon 客户端使用代理: {self.downloader.proxy_host}"
                    )
                logger.info("正在连接 Telethon 客户端...")
                await self.user_client.start()
                logger.info("Telethon 客户端连接成功。")
            except Exception as e:
                logger.error(f"Telethon 客户端启动失败: {e}", exc_info=True)
                self.user_client = None
        else:
            logger.warning("Telethon 未完整配置，媒体转存功能将不可用。")
        # 3. 设置并启动 PTB Application
        # 应用程序将在重试循环中创建

        # 配置Telegram Bot库的日志记录器，使其使用savextube前缀
        import logging
        telegram_loggers = [
            'telegram.ext.Application',
            'telegram.ext.Updater',
            'telegram.ext.JobQueue',
            'telegram.bot'
        ]
        for logger_name in telegram_loggers:
            telegram_logger = logging.getLogger(logger_name)
            telegram_logger.name = 'savextube'

        logger.info("启动 Telegram Bot (PTB)...")

        # 创建应用程序实例
        if self.downloader.proxy_host:
            logger.info(f"Telegram Bot 使用代理: {self.downloader.proxy_host}")
            self.application = (
                Application.builder().token(self.token).proxy(self.downloader.proxy_host).post_init(self.post_init).build()
            )
        else:
            logger.info("Telegram Bot 直接连接")
            self.application = (
                Application.builder().token(self.token).post_init(self.post_init).build()
            )
        self._setup_handlers()

        # 启动应用程序
        try:
            async with self.application:
                await self.application.initialize()
                await self.application.start()

                # 配置更强的网络参数
                await self.application.updater.start_polling(
                    timeout=30,  # 增加超时时间
                    read_timeout=30,
                    write_timeout=30,
                    connect_timeout=30,
                    pool_timeout=30
                )

                logger.info("机器人已成功启动并正在运行。")

                # 健康检查功能已删除，避免事件循环冲突
                asyncio.create_task(self._keep_alive_heartbeat())

                # 启动B站收藏夹订阅检查任务
                if self.fav_manager:
                    try:
                        subscriptions = self.fav_manager.load_subscriptions()
                        if subscriptions:
                            self.fav_manager.ensure_check_task_running()
                            logger.info(f"📚 发现 {len(subscriptions)} 个订阅，已启动定期检查任务")
                    except Exception as e:
                        logger.warning(f"⚠️ 启动B站收藏夹订阅检查任务失败: {e}")
                else:
                    logger.info("📚 B站收藏夹订阅管理器未初始化，跳过订阅检查")

                # 使用可中断的等待
                try:
                    await asyncio.Event().wait()
                except KeyboardInterrupt:
                    logger.info("收到中断信号，正在关闭...")
                except Exception as e:
                    logger.error(f"运行时异常: {e}")
                    raise
        except Exception as e:
            logger.error(f"应用程序启动失败: {e}")
            # 确保应用程序正确关闭
            if self.application and self.application.running:
                try:
                    await self.application.stop()
                except:
                    pass
            raise

    # 健康检查功能已删除，避免事件循环冲突

    async def _restart_bot_connection(self):
        """重启Bot连接"""
        logger.info("🔄 开始重启Bot连接...")

        try:
            # 停止当前的polling
            if self.application.updater.running:
                await self.application.updater.stop()
                logger.info("📴 已停止当前polling")

            # 等待一段时间
            await asyncio.sleep(5)

            # 重新启动polling
            await self.application.updater.start_polling(
                timeout=30,
                read_timeout=30,
                write_timeout=30,
                connect_timeout=30,
                pool_timeout=30
            )
            logger.info("📡 已重新启动polling")

        except Exception as e:
            logger.error(f"❌ 重启Bot连接失败: {e}")
            raise e

    # 网络监控功能已删除，避免事件循环冲突

    async def _keep_alive_heartbeat(self):
        """保持连接活跃的心跳机制"""
        heartbeat_interval = int(os.getenv("HEARTBEAT_INTERVAL", "300"))  # 5分钟发送一次心跳

        while True:
            try:
                await asyncio.sleep(heartbeat_interval)

                # 发送一个轻量级的API调用来保持连接活跃
                try:
                    await self.application.bot.get_me()
                    logger.debug("💓 心跳保持连接活跃")
                except Exception as e:
                    logger.warning(f"💔 心跳失败: {e}")
                    # 心跳失败不需要特殊处理，健康检查会处理

            except Exception as e:
                logger.error(f"❌ 心跳机制异常: {e}")
                await asyncio.sleep(60)  # 异常时等待1分钟

    async def reboot_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /reboot 命令 - 重启容器"""
        user_id = update.message.from_user.id

        # 权限检查
        if not self._check_user_permission(user_id):
            await update.message.reply_text("❌ 您没有权限使用此机器人")
            return

        try:
            # 发送重启确认消息
            await update.message.reply_text("🔄 正在重启 savextube 容器...")
            logger.info(f"👤 用户 {user_id} 请求重启容器")

            import os
            import asyncio

            # 直接使用Docker SDK重启方法
            logger.info("🔄 开始容器重启流程")

            # 检查环境并执行相应的重启命令
            if os.path.exists('/.dockerenv'):
                logger.info("🐳 Docker容器环境")

                # 检查是否映射了Docker socket
                docker_sock_paths = ['/var/run/docker.sock', '/var/run/docker.sock.raw']
                has_docker_sock = any(os.path.exists(path) for path in docker_sock_paths)

                if has_docker_sock:
                        logger.info("🔌 检测到Docker socket映射，使用Docker SDK重启")

                        await update.message.reply_text(
                            "🐳 Docker环境 + Socket映射\n"
                            "🔄 使用Docker SDK自动重启容器...\n"
                            "⏳ 请等待约30秒让服务重新启动"
                        )
                        await asyncio.sleep(2)

                        try:
                            # 使用Docker SDK重启方法
                            await self._restart_via_docker_api()
                            logger.info("✅ 通过Docker SDK重启成功")

                        except Exception as e:
                            # 限制错误消息长度，避免Telegram消息过长
                            error_msg = str(e)
                            if len(error_msg) > 100:
                                error_msg = error_msg[:100] + "..."

                            logger.error(f"❌ Docker SDK重启失败: {error_msg}")
                            await update.message.reply_text(
                                f"❌ SDK重启失败\n\n"
                                "📋 备用方案:\n"
                                "1. 手动重启: `docker restart <容器名>`\n"
                                "2. 或执行优雅退出让容器自动重启"
                            )

                            # 优雅退出作为备用方案
                            await asyncio.sleep(2)
                            await update.message.reply_text("🔄 执行优雅退出...")
                            await asyncio.sleep(1)
                            import sys
                            sys.exit(0)
                else:
                    logger.info("❌ 未检测到Docker socket映射")
                    await update.message.reply_text(
                        "🐳 检测到Docker容器环境\n\n"
                        "⚠️ 未映射Docker socket，无法自动重启\n\n"
                        "📋 请手动重启容器:\n"
                        "• 方法1: `docker restart <容器名>`\n"
                        "• 方法2: `docker-compose restart savextube`\n\n"
                        "💡 要启用自动重启，请映射Docker socket:\n"
                        "`-v /var/run/docker.sock:/var/run/docker.sock`"
                    )

                    # 尝试优雅退出，让容器管理器重启
                    logger.info("🔄 尝试优雅退出进程，期望容器自动重启")
                    await asyncio.sleep(3)

                    try:
                        await update.message.reply_text(
                            "🔄 正在优雅退出进程...\n"
                            "如果容器配置了自动重启，Bot将自动恢复"
                        )
                        await asyncio.sleep(2)
                    except:
                        pass

                    # 优雅退出
                    import sys
                    logger.info("👋 进程即将退出")
                    sys.exit(0)

            elif os.path.exists('docker-compose.yml') or os.path.exists('docker-compose.yaml'):
                logger.info("🐳 docker-compose环境")
                await update.message.reply_text(
                    "🔄 docker-compose环境检测到\n"
                    "⚠️ 无法从容器内重启服务\n\n"
                    "📋 请在宿主机上运行:\n"
                    "`docker-compose restart savextube`\n\n"
                    "💡 或者创建重启脚本来自动化此过程"
                )

            else:
                logger.info("💻 普通进程环境")
                await update.message.reply_text(
                    "🔄 普通进程环境\n"
                    "⚠️ 将尝试重启当前进程\n"
                    "📱 请等待服务重新启动..."
                )
                await asyncio.sleep(2)

                # 重启当前进程
                import sys
                logger.info("🔄 重启进程")
                os.execv(sys.executable, ['python'] + sys.argv)

        except Exception as e:
            error_msg = f"❌ 重启失败: {e}"
            logger.error(error_msg)
            await update.message.reply_text(error_msg)

    async def _restart_via_docker_api(self):
        """通过Docker SDK重启容器"""
        try:
            import docker
            logger.info("📦 使用Docker SDK重启容器")

            # 创建Docker客户端
            client = docker.DockerClient(base_url='unix://var/run/docker.sock')

            # 尝试多种方法获取容器ID
            container_id = None
            container = None

            # 方法1: 通过cpuset获取容器ID
            try:
                container_id = os.popen("basename $(cat /proc/1/cpuset)").read().strip()
                if container_id and len(container_id) >= 12:
                    logger.info(f"📋 通过cpuset获取容器ID: {container_id[:12]}...")
                    container = client.containers.get(container_id)
                else:
                    container_id = None
            except Exception as e:
                logger.warning(f"⚠️ cpuset方法失败: {e}")
                container_id = None

            # 方法2: 通过hostname获取容器ID
            if not container:
                try:
                    hostname_id = os.popen("hostname").read().strip()
                    if hostname_id and len(hostname_id) >= 12:
                        logger.info(f"📋 通过hostname获取容器ID: {hostname_id[:12]}...")
                        container = client.containers.get(hostname_id)
                        container_id = hostname_id
                except Exception as e:
                    logger.warning(f"⚠️ hostname方法失败: {e}")

            # 方法3: 查找名为savextube的容器
            if not container:
                try:
                    logger.info("📋 尝试查找savextube容器...")
                    containers = client.containers.list(filters={"name": "savextube"})
                    if containers:
                        container = containers[0]
                        container_id = container.id
                        logger.info(f"📋 找到savextube容器: {container_id[:12]}...")
                except Exception as e:
                    logger.warning(f"⚠️ 按名称查找失败: {e}")

            # 检查是否找到容器
            if not container:
                raise ValueError("无法找到当前容器，尝试了多种方法都失败")

            # 获取容器信息
            container_name = getattr(container, 'name', 'unknown')
            logger.info(f"🔄 准备重启容器: {container_name}")

            # 执行重启
            container.restart()
            logger.info("✅ Docker SDK重启命令已执行")

        except ImportError:
            logger.error("❌ Docker Python库未安装")
            logger.info("💡 请安装: pip install docker")
            raise ImportError("Docker Python库未安装，无法使用SDK重启")
        except Exception as e:
            # 避免日志过长，只记录关键错误信息
            error_msg = str(e)
            if len(error_msg) > 200:
                error_msg = error_msg[:200] + "..."
            logger.error(f"❌ Docker SDK重启失败: {error_msg}")
            raise e

    async def version_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /version 命令 - 显示版本信息"""
        user_id = update.message.from_user.id

        # 权限检查
        if not self._check_user_permission(user_id):
            await update.message.reply_text("❌ 您没有权限使用此机器人")
            return

        # 心跳更新已删除
        try:
            version_text = (
                f"⚙️ <b>系统版本信息</b>\n\n"
                f"  - <b>机器人</b>: <code>{BOT_VERSION}</code>"
            )
            await update.message.reply_text(version_text, parse_mode="HTML")
        except Exception as e:
            await update.message.reply_text(f"❌ 获取版本信息失败: {e}")

    async def formats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /formats 命令 - 检查视频格式"""
        user_id = update.message.from_user.id

        # 权限检查
        if not self._check_user_permission(user_id):
            await update.message.reply_text("❌ 您没有权限使用此机器人")
            return

        # 心跳更新已删除

        try:
            # 获取用户发送的URL
            if not context.args:
                await update.message.reply_text(
                    """格式检查命令
使用方法：
/formats <视频链接>
示例：
/formats https://www.youtube.com/watch?v=xxx
此命令会显示视频的可用格式，帮助调试下载问题。"""
                )
                return

            url = context.args[0]

            # 验证URL
            if not url.startswith(("http://", "https://")):
                await update.message.reply_text("请提供有效的视频链接")
                return

            check_message = await update.message.reply_text("正在检查视频格式...")

            # 检查格式
            result = self.downloader.check_video_formats(url)

            if result["success"]:
                formats_text = f"""视频格式信息
标题：{result['title']}
可用格式（前10个）：
"""
                for i, fmt in enumerate(result["video_formats"], 1):
                    size_info = ""
                    if fmt["filesize"] and fmt["filesize"] > 0:
                        size_mb = fmt["filesize"] / (1024 * 1024)
                        size_info = f" ({size_mb:.1f}MB)"

                    formats_text += f"{i}. ID: {fmt['id']} | {fmt['ext']} | {fmt['quality']}{size_info}\n"

                formats_text += "\n音频格式（前5个）：\n"
                for i, fmt in enumerate(result["audio_formats"], 1):
                    size_info = ""
                    if fmt["filesize"] and fmt["filesize"] > 0:
                        size_mb = fmt["filesize"] / (1024 * 1024)
                        size_info = f" ({size_mb:.1f}MB)"

                    formats_text += f"{i}. ID: {fmt['id']} | {fmt['ext']} | {fmt['quality']}{size_info}\n"

                formats_text += "\n如果下载失败，可以尝试其他视频或报告此信息。"

                await check_message.edit_text(formats_text)
            else:
                await check_message.edit_text(f"格式检查失败: {result['error']}")

        except Exception as e:
            await update.message.reply_text(f"格式检查出错: {str(e)}")

    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /cancel 命令 - 取消当前下载任务"""
        user_id = update.message.from_user.id

        # 权限检查
        if not self._check_user_permission(user_id):
            await update.message.reply_text("❌ 您没有权限使用此机器人")
            return

        try:
            # 检查是否有正在进行的下载任务
            logger.info(f"🔍 用户 {user_id} 请求取消任务")
            logger.info(f"🔍 当前任务数量: {len(self.download_tasks) if hasattr(self, 'download_tasks') else 0}")

            if hasattr(self, 'download_tasks') and self.download_tasks:
                # 打印所有任务信息用于调试
                for tid, tinfo in self.download_tasks.items():
                    logger.info(f"🔍 任务 {tid}: user_id={tinfo.get('user_id')}, done={tinfo.get('task').done() if tinfo.get('task') else 'None'}")

                cancelled_count = 0
                for task_id, task_info in list(self.download_tasks.items()):
                    task_user_id = task_info.get('user_id')
                    task_done = task_info.get('task').done() if task_info.get('task') else True

                    logger.info(f"🔍 检查任务 {task_id}: user_id={task_user_id}, done={task_done}, 匹配用户={task_user_id == user_id}")

                    if task_user_id == user_id and not task_done:
                        logger.info(f"🚫 取消任务: {task_id}")
                        # 设置取消标志，让 update_progress 检测到
                        task_info['cancelled'] = True
                        task_info['task'].cancel()
                        cancelled_count += 1
                        # 发送取消消息
                        try:
                            status_message = task_info.get('status_message')
                            if status_message:
                                await status_message.edit_text("❌ 下载已被用户取消", parse_mode=None)
                        except Exception as e:
                            logger.debug(f"编辑取消消息失败: {e}")
                            pass  # 忽略编辑消息失败的错误

                if cancelled_count > 0:
                    await update.message.reply_text(f"✅ 已取消 {cancelled_count} 个下载任务")
                else:
                    await update.message.reply_text("ℹ️ 没有找到正在进行的下载任务")
            else:
                await update.message.reply_text("ℹ️ 没有找到正在进行的下载任务")

        except Exception as e:
            logger.error(f"取消下载任务失败: {e}")
            await update.message.reply_text(f"❌ 取消任务失败: {str(e)}")

    async def cleanup_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /cleanup 命令"""
        user_id = update.message.from_user.id

        # 权限检查
        if not self._check_user_permission(user_id):
            await update.message.reply_text("❌ 您没有权限使用此机器人")
            return

        # 心跳更新已删除

        cleanup_message = await update.message.reply_text("开始清理重复文件...")

        try:
            cleaned_count = self.downloader.cleanup_duplicates()
            if cleaned_count > 0:
                completion_text = f"""清理完成!
删除了 {cleaned_count} 个重复文件
释放了存储空间"""
            else:
                completion_text = "清理完成! 未发现重复文件"

            await cleanup_message.edit_text(completion_text)
        except Exception as e:
            await cleanup_message.edit_text(f"清理失败: {str(e)}")

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /status 命令"""
        user_id = update.message.from_user.id

        # 权限检查
        if not self._check_user_permission(user_id):
            await update.message.reply_text("❌ 您没有权限使用此机器人")
            return

        # 心跳更新已删除
        try:
            # 统计文件
            video_extensions = ["*.mp4", "*.mkv", "*.webm", "*.mov", "*.avi"]
            x_files = []
            if self.downloader.x_download_path.exists():
                for ext in video_extensions:
                    x_files.extend(self.downloader.x_download_path.glob(ext))
            youtube_files = []
            if self.downloader.youtube_download_path.exists():
                for ext in video_extensions:
                    youtube_files.extend(
                        self.downloader.youtube_download_path.glob(ext)
                    )
            bilibili_files = []
            if self.downloader.bilibili_download_path.exists():
                for ext in video_extensions:
                    bilibili_files.extend(
                        self.downloader.bilibili_download_path.glob(ext)
                    )
            douyin_files = []
            if self.downloader.douyin_download_path.exists():
                for ext in video_extensions:
                    douyin_files.extend(
                        self.downloader.douyin_download_path.glob(ext)
                    )
            total_files = len(x_files) + len(youtube_files) + len(bilibili_files) + len(douyin_files)
            status_text = (
                f"📊 <b>下载状态</b>\n\n"
                f"  - <b>X (Twitter)</b>: {len(x_files)} 个文件\n"
                f"  - <b>YouTube</b>: {len(youtube_files)} 个文件\n"
                f"  - <b>Bilibili</b>: {len(bilibili_files)} 个文件\n"
                f"  - <b>总计</b>: {total_files} 个文件\n\n"
            )
            # qBittorrent 状态
            if self.qbit_client and self.qbit_client.is_logged_in:
                torrents = self.qbit_client.torrents_info(tag="savextube")
                active_torrents = [
                    t for t in torrents if t.state not in ["completed", "pausedUP"]
                ]
                status_text += f"<b>qBittorrent 任务</b>: {len(torrents)} (活动: {len(active_torrents)})"
            else:
                status_text += "<b>qBittorrent</b>: 未连接"
            await update.message.reply_text(status_text, parse_mode="HTML")
        except Exception as e:
            await update.message.reply_text(f"❌ 获取状态失败: {str(e)}")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理文本消息，支持批量链接（委托给消息处理器）"""
        if hasattr(self, 'message_handler') and self.message_handler:
            await self.message_handler.handle_message(update, context)
        else:
            # 兼容旧版本
            await self._handle_message_legacy(update, context)
    
    async def _handle_message_legacy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """旧版消息处理（兼容）"""
        user_id = update.message.from_user.id
        if not self._check_user_permission(user_id):
            await update.message.reply_text("❌ 您没有权限使用此机器人")
            return

        message = update.message
        url = None

        # 检查搜索命令
        if message.text and message.text.startswith("/search"):
            await self._handle_search_command(message, context)
            return

        # 检查消息类型并提取URL
        if message.text and message.text.startswith("http"):
            # 普通文本链接
            url = message.text
        elif message.text and (message.text.startswith("magnet:") or message.text.endswith(".torrent")):
            # 磁力链接或种子文件 - 新增支持
            url = message.text
        elif message.text and "magnet:" in message.text:
            # 从混合文本中提取磁力链接
            import re
            magnet_match = re.search(r'magnet:\?xt=urn:btih:[a-fA-F0-9]{32,40}[^\s]*', message.text)
            if magnet_match:
                url = magnet_match.group(0)
                logger.info(f"🔧 从混合文本中提取磁力链接: {message.text} -> {url}")
        elif message.text and ".torrent" in message.text:
            # 从混合文本中提取种子文件链接
            import re
            torrent_match = re.search(r'https?://[^\s]*\.torrent[^\s]*', message.text)
            if torrent_match:
                url = torrent_match.group(0)
                logger.info(f"🔧 从混合文本中提取种子文件链接: {message.text} -> {url}")
        elif message.entities:
            # 检查是否有链接实体
            for entity in message.entities:
                if entity.type == "url":
                    url = message.text[entity.offset:entity.offset + entity.length]
                    break
                elif entity.type == "text_link":
                    url = entity.url
                    break
        elif message.text and ("http" in message.text or "tp://" in message.text or "kuaishou.com" in message.text or "douyin.com" in message.text):
            # 尝试从文本中提取URL，包括修复错误的协议和智能提取
            import re

            # 首先使用智能提取方法
            extracted_urls = self.downloader.extract_urls_from_text(message.text)
            if extracted_urls:
                url = extracted_urls[0]  # 使用第一个找到的URL
                logger.info(f"🔧 智能提取URL: {message.text} -> {url}")
            else:
                # 备选方案：修复错误的协议
                fixed_text = message.text.replace("tp://", "http://")
                url_match = re.search(r'https?://[^\s]+', fixed_text)
                if url_match:
                    url = url_match.group(0)
                    logger.info(f"🔧 修复了错误的URL协议: {message.text} -> {url}")

        # 检查转发消息
        if not url and message.forward_from_chat:
            # 处理转发的频道/群组消息
            if message.text and ("http" in message.text or "tp://" in message.text or "magnet:" in message.text):
                import re
                # 首先尝试提取磁力链接
                magnet_match = re.search(r'magnet:\?xt=urn:btih:[a-fA-F0-9]{32,40}[^\s]*', message.text)
                if magnet_match:
                    url = magnet_match.group(0)
                    logger.info(f"🔧 转发消息中提取磁力链接: {message.text} -> {url}")
                else:
                    # 尝试提取种子文件链接
                    torrent_match = re.search(r'https?://[^\s]*\.torrent[^\s]*', message.text)
                    if torrent_match:
                        url = torrent_match.group(0)
                        logger.info(f"🔧 转发消息中提取种子文件链接: {message.text} -> {url}")
                    else:
                        # 修复错误的协议
                        fixed_text = message.text.replace("tp://", "http://")
                        url_match = re.search(r'https?://[^\s]+', fixed_text)
                        if url_match:
                            url = url_match.group(0)
                            logger.info(f"🔧 转发消息中修复了错误的URL协议: {message.text} -> {url}")

        # 检查回复的消息
        if not url and message.reply_to_message:
            reply_msg = message.reply_to_message
            if reply_msg.text and ("http" in reply_msg.text or "tp://" in reply_msg.text or "magnet:" in reply_msg.text):
                import re
                # 首先尝试提取磁力链接
                magnet_match = re.search(r'magnet:\?xt=urn:btih:[a-fA-F0-9]{32,40}[^\s]*', reply_msg.text)
                if magnet_match:
                    url = magnet_match.group(0)
                    logger.info(f"🔧 回复消息中提取磁力链接: {reply_msg.text} -> {url}")
                else:
                    # 尝试提取种子文件链接
                    torrent_match = re.search(r'https?://[^\s]*\.torrent[^\s]*', reply_msg.text)
                    if torrent_match:
                        url = torrent_match.group(0)
                        logger.info(f"🔧 回复消息中提取种子文件链接: {reply_msg.text} -> {url}")
                    else:
                        # 修复错误的协议
                        fixed_text = reply_msg.text.replace("tp://", "http://")
                        url_match = re.search(r'https?://[^\s]+', fixed_text)
                        if url_match:
                            url = url_match.group(0)
                            logger.info(f"🔧 回复消息中修复了错误的URL协议: {reply_msg.text} -> {url}")
            elif reply_msg.entities:
                for entity in reply_msg.entities:
                    if entity.type == "url":
                        url = reply_msg.text[entity.offset:entity.offset + entity.length]
                        break
                    elif entity.type == "text_link":
                        url = entity.url
                        break

        if not url:
            await message.reply_text("🤔 请发送一个有效的链接或包含链接的消息。\n\n💡 提示：\n• 直接发送链接\n• 转发包含链接的消息\n• 回复包含链接的消息")
            return

        # 添加调试日志
        logger.info(f"收到消息: {url}")

        # 立即发送快速响应
        status_message = await message.reply_text("🚀 正在处理您的请求...")

        # 异步处理下载任务，不阻塞响应
        asyncio.create_task(
            self._process_download_async(update, context, url, status_message)
        )

    async def _handle_search_command(self, message, context):
        """处理搜索命令 /search ncm 关键词"""
        try:
            # 解析命令
            parts = message.text.split(' ', 2)  # /search ncm 关键词
            if len(parts) < 3:
                help_text = """
🔍 <b>网易云音乐搜索下载</b>

<b>使用方法：</b>
<code>/search ncm 关键词</code>

<b>示例：</b>
<code>/search ncm 东风破</code>
<code>/search ncm 周杰伦 稻香</code>
<code>/search ncm 王力宏 盖世英雄</code>

<b>说明：</b>
• 支持歌曲名、艺术家名、专辑名搜索
• 自动识别是单曲还是专辑
• 使用配置的目录结构和文件命名格式
                """
                await message.reply_text(help_text, parse_mode="HTML")
                return

            platform = parts[1].lower()
            keyword = parts[2]

            if platform != 'ncm':
                await message.reply_text("❌ 暂只支持网易云音乐搜索，请使用 <code>/search ncm 关键词</code>", parse_mode="HTML")
                return

            # 发送状态消息
            status_message = await message.reply_text(f"🔍 正在搜索: {keyword}")

            try:
                # 调用网易云音乐搜索下载
                result = await self._search_and_download_ncm(keyword, status_message)
                
                if result.get('success'):
                    await status_message.edit_text(f"✅ 搜索下载完成！\n\n🔍 关键词: {keyword}\n📁 保存位置: {result.get('download_path', '未知')}", parse_mode=None)
                else:
                    await status_message.edit_text(f"❌ 搜索下载失败: {result.get('error', '未知错误')}", parse_mode=None)

            except Exception as e:
                logger.error(f"搜索下载失败: {e}")
                await status_message.edit_text(f"❌ 搜索下载时发生错误: {str(e)}", parse_mode=None)

        except Exception as e:
            logger.error(f"处理搜索命令失败: {e}")
            await message.reply_text(f"❌ 命令处理失败: {str(e)}")

    async def _search_and_download_ncm(self, keyword: str, status_message):
        """搜索并下载网易云音乐"""
        try:
            # 创建进度回调
            async def progress_callback(text):
                try:
                    await status_message.edit_text(text, parse_mode=None)
                except Exception as e:
                    logger.warning(f"更新进度消息失败: {e}")

            # 调用网易云音乐下载器的搜索下载方法
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                self.downloader.netease_downloader.download_album,
                keyword,
                str(self.downloader.netease_download_path),
                self.downloader.netease_downloader.get_quality_setting(),
                progress_callback
            )

            return result

        except Exception as e:
            logger.error(f"搜索下载网易云音乐失败: {e}")
            return {'success': False, 'error': str(e)}

    async def favsub_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /favsub 命令 - 订阅B站收藏夹"""
        user_id = update.message.from_user.id

        # 权限检查
        if not self._check_user_permission(user_id):
            await update.message.reply_text("❌ 您没有权限使用此功能")
            return

        try:
            # 获取命令参数
            args = context.args
            if not args:
                help_text = f"""
📚 <b>B站收藏夹订阅功能</b>

<b>使用方法：</b>
<code>/favsub 收藏夹ID</code>

<b>示例：</b>
<code>/favsub 3604284050</code>

<b>说明：</b>
• 收藏夹ID可以从收藏夹URL中获取
• 例如：https://www.bilibili.com/medialist/play/ml3604284050
• 订阅后会每{self.fav_manager.poll_interval}分钟自动检查并下载新视频

<b>管理命令：</b>
<code>/favsub list</code> - 查看已订阅的收藏夹
<code>/favsub remove 收藏夹ID</code> - 取消订阅
<code>/favsub download 收藏夹ID</code> - 手动下载收藏夹
<code>/favsub status</code> - 查看订阅任务状态
                """
                await update.message.reply_text(help_text, parse_mode="HTML")
                return

            command = args[0].lower()

            if command == "status":
                # 查看订阅任务状态
                subscriptions = self.fav_manager.get_subscriptions_list()
                task_running = self.fav_manager.is_check_task_running()

                status_text = f"""
📊 <b>B站收藏夹订阅状态</b>

🔧 <b>配置信息：</b>
• 检查间隔: {self.fav_manager.poll_interval} 分钟
• 下载目录: {self.fav_manager.subscription_download_path}
• 代理设置: {'已配置' if self.fav_manager.proxy_host else '未配置'}
• Cookies: {'已配置' if self.fav_manager.cookies_path else '未配置'}

📚 <b>订阅统计：</b>
• 订阅数量: {len(subscriptions)}
• 后台任务: {'🟢 运行中' if task_running else '🔴 已停止'}

📋 <b>订阅列表：</b>
"""

                if subscriptions:
                    for sub_info in subscriptions[:5]:  # 只显示前5个
                        fav_id = sub_info['fav_id']
                        title = sub_info['title']
                        download_count = sub_info['download_count']
                        status_text += f"• {title} (ID: {fav_id}) - 已下载: {download_count}\n"

                    if len(subscriptions) > 5:
                        status_text += f"... 还有 {len(subscriptions) - 5} 个订阅\n"
                else:
                    status_text += "暂无订阅\n"

                status_text += f"\n💡 使用 <code>/favsub list</code> 查看完整列表"

                await update.message.reply_text(status_text, parse_mode="HTML")

            elif command == "list":
                # 查看订阅列表
                subscriptions = self.fav_manager.get_subscriptions_list()

                if not subscriptions:
                    await update.message.reply_text("📚 暂无订阅的收藏夹")
                    return

                list_text = "📚 <b>已订阅的收藏夹：</b>\n\n"

                for sub_info in subscriptions:
                    fav_id = sub_info['fav_id']
                    title = sub_info['title']
                    video_count = sub_info['video_count']
                    added_time = sub_info['added_time']
                    last_check = sub_info['last_check']
                    download_count = sub_info['download_count']

                    # 格式化时间
                    import time
                    added_str = time.strftime('%Y-%m-%d %H:%M', time.localtime(added_time))
                    if last_check > 0:
                        last_check_str = time.strftime('%Y-%m-%d %H:%M', time.localtime(last_check))
                    else:
                        last_check_str = "未检查"

                    list_text += f"""
🔸 <b>{title}</b>
   • ID: <code>{fav_id}</code>
   • 视频数: {video_count}
   • 已下载: {download_count}
   • 订阅时间: {added_str}
   • 最后检查: {last_check_str}

"""

                list_text += f"\n💡 使用 <code>/favsub remove 收藏夹ID</code> 取消订阅"
                list_text += f"\n💡 使用 <code>/favsub download 收藏夹ID</code> 手动下载"

                await update.message.reply_text(list_text, parse_mode="HTML")

            elif command == "remove" and len(args) > 1:
                # 取消订阅
                fav_id = args[1]
                result = self.fav_manager.remove_subscription(fav_id)

                if result["success"]:
                    success_text = f"""
✅ <b>取消订阅成功！</b>

📚 已取消订阅收藏夹：
• ID: <code>{result['fav_id']}</code>
• 标题: {result['title']}
                    """
                    await update.message.reply_text(success_text, parse_mode="HTML")
                else:
                    await update.message.reply_text(f"❌ {result['error']}")

            elif command == "download" and len(args) > 1:
                # 手动下载
                fav_id = args[1]
                status_msg = await update.message.reply_text("🔄 开始手动下载收藏夹...")

                result = await self.fav_manager.manual_download(fav_id)

                if result["success"]:
                    success_text = f"""
✅ <b>手动下载完成！</b>

📚 <b>收藏夹信息：</b>
• ID: <code>{result['fav_id']}</code>
• 标题: {result['title']}
• 下载路径: {result['download_path']}
• 文件数量: {result['file_count']}
                    """
                    await status_msg.edit_text(success_text, parse_mode="HTML")
                else:
                    await status_msg.edit_text(f"❌ 下载失败: {result['error']}")

            else:
                # 添加订阅
                fav_id = command
                status_msg = await update.message.reply_text("🔍 正在验证收藏夹...")

                # 使用订阅管理器添加订阅
                result = await self.fav_manager.add_subscription(fav_id, update.message.from_user.id)

                if result["success"]:
                    success_text = f"""
✅ <b>订阅成功！</b>

📚 <b>收藏夹信息：</b>
• ID: <code>{result['fav_id']}</code>
• 标题: {result['title']}
• 视频数量: {result['video_count']}
• URL: {result['url']}

⏰ <b>自动下载：</b>
系统将每{self.fav_manager.poll_interval}分钟检查一次新视频并自动下载
                    """
                    await status_msg.edit_text(success_text, parse_mode="HTML")
                else:
                    await status_msg.edit_text(f"❌ {result['error']}")

        except Exception as e:
            logger.error(f"favsub命令处理失败: {e}")
            await update.message.reply_text(f"❌ 命令处理失败: {e}")

    async def handle_qbittorrent_links(self, update: Update, context: ContextTypes.DEFAULT_TYPE, url: str, status_message):
        """专门处理qBittorrent相关的链接（磁力链接和种子文件）"""
        try:
            # 检查是否为磁力链接或种子文件
            if self._is_magnet_link(url) or url.endswith(".torrent"):
                logger.info(f"🔗 检测到磁力链接或种子文件: {url[:50]}...")
                await status_message.edit_text("🔗 正在添加到 qBittorrent...", parse_mode=None)

                # 尝试添加到 qBittorrent
                success = await self.add_magnet_to_qb(url)

                if success:
                    await status_message.edit_text(
                        "✅ **磁力链接/种子文件已成功添加到 qBittorrent！**\n\n"
                        "📝 任务已添加到下载队列\n"
                        "🔍 您可以在 qBittorrent 中查看下载进度\n"
                        "💡 提示：下载完成后文件会保存到配置的下载目录"
                    )
                else:
                    await status_message.edit_text(
                        "❌ **添加磁力链接/种子文件失败**\n\n"
                        "可能的原因：\n"
                        "• qBittorrent 未连接或未配置\n"
                        "• 链接格式无效\n"
                        "• qBittorrent 服务异常\n\n"
                        "请检查 qBittorrent 配置和连接状态"
                    )
                return True  # 表示已处理

            # 检查是否为媒体消息，从媒体消息文本中提取磁力链接
            message = update.message
            if message.photo or message.video or message.document or message.audio:
                if message.caption:
                    caption_text = message.caption
                    logger.info(f"🔍 检测到媒体消息，文本内容: {caption_text}")

                    # 从媒体消息文本中提取磁力链接
                    import re
                    magnet_match = re.search(r'magnet:\?xt=urn:btih:[a-fA-F0-9]{32,40}[^\s]*', caption_text)
                    if magnet_match:
                        magnet_url = magnet_match.group(0)
                        logger.info(f"🔧 从媒体消息文本中提取磁力链接: {caption_text} -> {magnet_url}")
                        await status_message.edit_text("🔗 正在添加到 qBittorrent...", parse_mode=None)

                        # 尝试添加到 qBittorrent
                        success = await self.add_magnet_to_qb(magnet_url)

                        if success:
                            await status_message.edit_text(
                                "✅ **磁力链接已成功添加到 qBittorrent！**\n\n"
                                "📝 任务已添加到下载队列\n"
                                "🔍 您可以在 qBittorrent 中查看下载进度\n"
                                "💡 提示：下载完成后文件会保存到配置的下载目录"
                            )
                        else:
                            await status_message.edit_text(
                                "❌ **添加磁力链接失败**\n\n"
                                "可能的原因：\n"
                                "• qBittorrent 未连接或未配置\n"
                                "• 链接格式无效\n"
                                "• qBittorrent 服务异常\n\n"
                                "请检查 qBittorrent 配置和连接状态"
                            )
                        return True  # 表示已处理

                    # 尝试提取种子文件链接
                    torrent_match = re.search(r'https?://[^\s]*\.torrent[^\s]*', caption_text)
                    if torrent_match:
                        torrent_url = torrent_match.group(0)
                        logger.info(f"🔧 从媒体消息文本中提取种子文件链接: {caption_text} -> {torrent_url}")
                        await status_message.edit_text("🔗 正在添加到 qBittorrent...", parse_mode=None)

                        # 尝试添加到 qBittorrent
                        success = await self.add_magnet_to_qb(torrent_url)

                        if success:
                            await status_message.edit_text(
                                "✅ **种子文件已成功添加到 qBittorrent！**\n\n"
                                "📝 任务已添加到下载队列\n"
                                "🔍 您可以在 qBittorrent 中查看下载进度\n"
                                "💡 提示：下载完成后文件会保存到配置的下载目录"
                            )
                        else:
                            await status_message.edit_text(
                                "❌ **添加种子文件失败**\n\n"
                                "可能的原因：\n"
                                "• qBittorrent 未连接或未配置\n"
                                "• 链接格式无效\n"
                                "• qBittorrent 服务异常\n\n"
                                "请检查 qBittorrent 配置和连接状态"
                            )
                        return True  # 表示已处理

            return False  # 表示未处理，继续其他流程
        except Exception as e:
            logger.error(f"处理qBittorrent链接时发生错误: {e}", exc_info=True)
            await status_message.edit_text(f"❌ 处理qBittorrent链接时发生错误: {str(e)}")
            return True  # 表示已处理（出错也算处理了）

    async def _process_download_async(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        url: str,
        status_message,
    ):
        """异步处理下载任务"""
        import os  # 导入os模块以解决作用域问题

        # 在方法开始时定义chat_id，确保在所有异常处理路径中都可访问
        chat_id = status_message.chat_id

        try:
            # 首先尝试处理qBittorrent相关链接
            if await self.handle_qbittorrent_links(update, context, url, status_message):
                return  # 如果是qB相关链接，处理完就返回

            # 检查是否为B站自定义列表URL
            is_list, uid, list_id = self.downloader.is_bilibili_list_url(url)
            if is_list:
                logger.info(f"🔧 检测到B站用户列表URL: 用户{uid}, 列表{list_id}")
            # 链接有效性检查
            platform_name = self.downloader.get_platform_name(url)
            if platform_name == "未知":
                await status_message.edit_text("🙁 抱歉，暂不支持您发送的网站。", parse_mode=None)
                return

            # 获取平台信息用于后续判断
            platform = platform_name.lower()
        except Exception as e:
            logger.error(f"处理下载时发生意外错误: {e}", exc_info=True)
            await context.bot.edit_message_text(
                text=f"❌ 处理下载时发生内部错误：\n{str(e)}",
                chat_id=chat_id,
                message_id=status_message.message_id,
                parse_mode=None,
            )
            return

        # 缓存上次发送的内容，避免重复发送
        last_progress_text = {"text": None}

        # --- 进度回调 ---
        last_update_time = {"time": time.time()}
        last_progress_percent = {"value": 0}
        progress_state = {"last_stage": None, "last_percent": 0, "finished_shown": False}  # 跟踪上一次的状态和是否已显示完成
        last_progress_text = {"text": ""}  # 跟踪上一次的文本内容

        # 创建增强版的消息更新器函数，支持传递 status_message 和 context 给 single_video_progress_hook
        # 增加对B站多P下载的支持，但保持YouTube功能完全不变
        async def message_updater(text_or_dict, bilibili_progress_data=None):
            try:
                logger.info(f"🔍 message_updater 被调用，参数类型: {type(text_or_dict)}")
                logger.info(f"🔍 message_updater 参数内容: {text_or_dict}")

                # 如果已经显示完成状态，忽略所有后续调用
                if progress_state["finished_shown"]:
                    logger.info("下载已完成，忽略message_updater后续调用")
                    return

                # 处理字符串类型，避免重复发送相同内容
                if isinstance(text_or_dict, str):
                    if text_or_dict == last_progress_text["text"]:
                        logger.info("🔍 跳过重复内容")
                        return  # 跳过重复内容
                    last_progress_text["text"] = text_or_dict
                    await status_message.edit_text(text_or_dict, parse_mode=None)
                    return

                # 检查是否为字典类型（来自progress_hook的进度数据）
                if isinstance(text_or_dict, dict):
                    logger.debug(f"🔍 检测到字典类型，状态: {text_or_dict.get('status')}")

                    # 记录文件名（用于文件查找）
                    if text_or_dict.get("status") == "finished":
                        filename = text_or_dict.get('filename', '')
                        if filename:
                            # 如果提供了bilibili_progress_data，记录B站下载的文件
                            if bilibili_progress_data is not None and isinstance(bilibili_progress_data, dict):
                                if 'downloaded_files' not in bilibili_progress_data:
                                    bilibili_progress_data['downloaded_files'] = []
                                bilibili_progress_data['downloaded_files'].append(filename)
                                logger.info(f"📝 B站文件记录: {filename}")
                            else:
                                # YouTube或其他平台的处理保持不变
                                logger.info(f"📝 检测到finished状态，文件名: {filename}")

                    if text_or_dict.get("status") == "finished":
                        # 对于finished状态，不调用update_progress，避免显示错误的进度信息
                        logger.info("🔍 检测到finished状态，跳过update_progress调用")
                        return
                    elif text_or_dict.get("status") == "downloading":
                        # 这是来自progress_hook的下载进度数据
                        logger.info("🔍 检测到下载进度数据，准备调用 update_progress...")
                        # 调用update_progress函数处理进度数据
                        update_progress(text_or_dict)
                        logger.info("✅ update_progress 调用完成")

                        # 注意：这里不需要再次调用message_updater，因为update_progress已经处理了显示
                        # 如果需要额外的消息显示，应该在update_progress内部处理
                    else:
                        # 其他字典状态，转换为文本
                        logger.info(f"🔍 其他字典状态: {text_or_dict}")
                        dict_text = str(text_or_dict)
                        if dict_text == last_progress_text["text"]:
                            logger.info("🔍 跳过重复字典内容")
                            return  # 跳过重复内容
                        last_progress_text["text"] = dict_text
                        await status_message.edit_text(dict_text, parse_mode=None)
                else:
                    # 普通文本消息
                    logger.info(f"🔍 普通文本消息: {text_or_dict}")
                    text_str = str(text_or_dict)
                    if text_str == last_progress_text["text"]:
                        logger.info("🔍 跳过重复文本内容")
                        return  # 跳过重复内容
                    last_progress_text["text"] = text_str
                    await status_message.edit_text(text_str, parse_mode=None)
            except Exception as e:
                logger.error(f"❌ message_updater 处理错误: {e}")
                logger.error(f"❌ 异常类型: {type(e)}")
                import traceback
                logger.error(f"❌ 异常堆栈: {traceback.format_exc()}")
                if "Message is not modified" not in str(e):
                    logger.warning(f"更新状态消息失败: {e}")

        # 创建增强版的进度回调函数，支持传递 status_message 和 context
        def enhanced_progress_callback(progress_data_dict):
            """增强版进度回调，支持传递 status_message 和 context 给 single_video_progress_hook"""
            # 创建 single_video_progress_hook 的增强版本
            progress_hook = single_video_progress_hook(
                message_updater=None,
                progress_data=progress_data_dict,
                status_message=status_message,
                context=context
            )
            return progress_hook

        # 更新状态消息
        try:
            if message_updater:
                logger.debug(f'message_updater type: {type(message_updater)}, value: {message_updater}')
                if asyncio.iscoroutinefunction(message_updater):
                    await message_updater("🔍 正在分析链接...")
                else:
                    message_updater("🔍 正在分析链接...")
        except Exception as e:
            logger.warning(f"更新状态消息失败: {e}")
        # 直接开始下载，跳过预先获取信息（避免用户等待）
        try:
            if message_updater:
                logger.debug(f'message_updater type: {type(message_updater)}, value: {message_updater}')
                if asyncio.iscoroutinefunction(message_updater):
                    await message_updater("🚀 正在启动下载...")
                else:
                    message_updater("🚀 正在启动下载...")
        except Exception as e:
            logger.warning(f"更新状态消息失败: {e}")
        # 获取当前事件循环
        loop = asyncio.get_running_loop()

        # 生成任务ID
        task_id = f"{update.effective_user.id}_{int(time.time())}"

        # 添加 progress_data 支持（参考 main.v0.3.py）
        progress_data = {
            'filename': '',
            'total_bytes': 0,
            'downloaded_bytes': 0,
            'speed': 0,
            'status': 'downloading',
            'final_filename': '',
            'last_update': 0,
            'progress': 0.0
        }

        # QQ音乐使用自己的详细进度显示，不使用全局进度管理器
        def update_progress(d):
            logger.debug(f"update_progress 被调用: {type(d)}, 内容: {d}")

            # 🎯 关键修复：检查任务是否被取消
            if task_id in self.download_tasks:
                task_info = self.download_tasks[task_id]
                if task_info.get('cancelled', False):
                    logger.info(f"🚫 检测到任务已取消，中断下载: {task_id}")
                    # 抛出异常来中断 yt-dlp 下载
                    raise KeyboardInterrupt("下载已被用户取消")

            # 支持字符串类型，直接发到Telegram
            if isinstance(d, str):
                try:
                    logger.info(f"🔍 [DEBUG] 准备发送字符串到TG: status_message={status_message}, loop={loop}")
                    if status_message is None:
                        logger.warning(f"⚠️ [DEBUG] status_message 是 None，跳过发送")
                        return
                    if loop is None:
                        logger.warning(f"⚠️ [DEBUG] loop 是 None，跳过发送")
                        return

                    logger.info(f"🚀 即将发送消息到TG: {d}")
                    asyncio.run_coroutine_threadsafe(
                        status_message.edit_text(d, parse_mode=None),
                        loop
                    )
                    logger.info(f"✅ [DEBUG] 字符串消息发送成功")
                except Exception as e:
                    logger.warning(f"发送字符串进度到TG失败: {e}")
                return
            # 添加类型检查，确保d是字典类型
            if not isinstance(d, dict):
                logger.warning(f"update_progress接收到非字典类型参数: {type(d)}, 内容: {d}")
                return

            # 更新 progress_data（参考 main.v0.3.py）
            try:
                if d['status'] == 'downloading':
                    raw_filename = d.get('filename', '')
                    display_filename = os.path.basename(raw_filename) if raw_filename else 'video.mp4'
                    progress_data.update({
                        'filename': display_filename,
                        'total_bytes': d.get('total_bytes') or d.get('total_bytes_estimate', 0),
                        'downloaded_bytes': d.get('downloaded_bytes', 0),
                        'speed': d.get('speed', 0),
                        'status': 'downloading',
                        'progress': (d.get('downloaded_bytes', 0) / (d.get('total_bytes') or d.get('total_bytes_estimate', 1))) * 100 if (d.get('total_bytes') or d.get('total_bytes_estimate', 0)) > 0 else 0.0
                    })
                elif d['status'] == 'finished':
                    final_filename = d.get('filename', '')
                    display_filename = os.path.basename(final_filename) if final_filename else 'video.mp4'
                    progress_data.update({
                        'filename': display_filename,
                        'status': 'finished',
                        'final_filename': final_filename,
                        'progress': 100.0
                    })
            except Exception as e:
                logger.error(f"更新 progress_data 错误: {str(e)}")

            now = time.time()
            # 使用 main.v0.3.py 的方式：每1秒更新一次
            if now - last_update_time['time'] < 1.0:
                return
            # 处理B站合集下载进度
            if d.get('status') == 'downloading' and d.get('bv'):
                # B站合集下载进度
                last_update_time['time'] = now
                bv = d.get('bv', '')
                filename = d.get('filename', '')
                template = d.get('template', '')
                index = d.get('index', 0)
                total = d.get('total', 0)

                progress_text = (
                    f"🚀 **正在下载第{index}个**: `{bv}` - `{filename}`\n"
                    f"📝 **文件名模板**: `{template}`\n"
                    f"📊 **进度**: {index}/{total}"
                )

                async def do_update():
                    try:
                        await asyncio.wait_for(
                            context.bot.edit_message_text(
                                text=progress_text,
                                chat_id=status_message.chat_id,
                                message_id=status_message.message_id,
                                parse_mode=None
                            ),
                            timeout=10.0  # 增加到10秒超时，减少超时错误
                        )
                        logger.info(f"B站合集进度更新: 第{index}/{total}个")
                    except asyncio.TimeoutError:
                        logger.warning(f"B站合集进度更新超时: 第{index}/{total}个")
                    except Exception as e:
                        if "Message is not modified" not in str(e):
                            logger.warning(f"更新B站合集进度失败: {e}")

                asyncio.run_coroutine_threadsafe(do_update(), loop)
                return

            # 处理B站合集下载完成/失败
            if d.get('status') in ['finished', 'error'] and d.get('bv'):
                # B站合集下载完成/失败
                last_update_time['time'] = now
                bv = d.get('bv', '')
                filename = d.get('filename', '')
                index = d.get('index', 0)
                total = d.get('total', 0)
                status_emoji = "✅" if d.get('status') == 'finished' else "❌"
                status_text = "下载成功" if d.get('status') == 'finished' else "下载失败"

                progress_text = (
                    f"{status_emoji} **第{index}个{status_text}**: `{filename}`\n"
                    f"📊 **进度**: {index}/{total}"
                )

                async def do_update():
                    try:
                        await asyncio.wait_for(
                            context.bot.edit_message_text(
                                text=progress_text,
                                chat_id=status_message.chat_id,
                                message_id=status_message.message_id,
                                parse_mode=None
                            ),
                            timeout=10.0  # 增加到10秒超时，减少超时错误
                        )
                        logger.info(f"B站合集状态更新: 第{index}个{status_text}")
                    except asyncio.TimeoutError:
                        logger.warning(f"B站合集状态更新超时: 第{index}个{status_text}")
                    except Exception as e:
                        if "Message is not modified" not in str(e):
                            logger.warning(f"更新B站合集状态失败: {e}")

                asyncio.run_coroutine_threadsafe(do_update(), loop)
                return

            # 处理下载完成状态 - 直接显示完成信息并返回（参考 main.v0.3.py）
            elif d.get('status') == 'finished':
                logger.info("yt-dlp下载完成，显示完成信息")

                # 获取进度信息
                if progress_data and isinstance(progress_data, dict):
                    filename = progress_data.get('filename', 'video.mp4')
                    total_bytes = progress_data.get('total_bytes', 0)
                    downloaded_bytes = progress_data.get('downloaded_bytes', 0)
                else:
                    filename = 'video.mp4'
                    total_bytes = 0
                    downloaded_bytes = 0

                # 监控文件合并状态
                actual_filename = d.get('filename', filename)
                if actual_filename.endswith('.part'):
                    logger.warning(f"⚠️ 文件合并可能失败: {actual_filename}")
                else:
                    logger.info(f"✅ 文件下载并合并成功: {actual_filename}")

                # 显示完成信息
                display_filename = _clean_filename_for_display_local(filename)
                progress_bar = _create_progress_bar_local(100.0)
                size_mb = total_bytes / (1024 * 1024) if total_bytes > 0 else downloaded_bytes / (1024 * 1024)

                completion_text = (
                    f"📝 文件：{display_filename}\n"
                    f"💾 大小：{size_mb:.2f}MB\n"
                    f"⚡ 速度：完成\n"
                    f"⏳ 预计剩余：0秒\n"
                    f"📊 进度：{progress_bar} (100.0%)"
                )

                async def do_update():
                    try:
                        await status_message.edit_text(completion_text, parse_mode=None)
                        logger.info("显示下载完成进度信息")
                    except Exception as e:
                        logger.warning(f"显示完成进度信息失败: {e}")

                asyncio.run_coroutine_threadsafe(do_update(), loop)
                return

            if d.get('status') == 'downloading':
                logger.debug(f"收到下载进度回调: {d}")
                last_update_time['time'] = now

                total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                downloaded_bytes = d.get('downloaded_bytes', 0)
                speed_bytes_s = d.get('speed', 0)
                eta_seconds = d.get('eta', 0)
                filename = d.get('filename', '') or "正在下载..."

                # 使用 main.v0.3.py 的简单逻辑
                if total_bytes > 0:
                    progress = (downloaded_bytes / total_bytes) * 100
                    progress_bar = _create_progress_bar_local(progress)
                    size_mb = total_bytes / (1024 * 1024)
                    speed_mb = (speed_bytes_s or 0) / (1024 * 1024)

                    # 计算预计剩余时间
                    eta_text = ""
                    if speed_bytes_s and total_bytes and downloaded_bytes < total_bytes:
                        remaining = total_bytes - downloaded_bytes
                        eta = int(remaining / speed_bytes_s)
                        mins, secs = divmod(eta, 60)
                        if mins > 0:
                            eta_text = f"{mins}分{secs}秒"
                        else:
                            eta_text = f"{secs}秒"
                    elif speed_bytes_s:
                        eta_text = "计算中"
                    else:
                        eta_text = "未知"

                    # 确保文件名不包含路径
                    display_filename = os.path.basename(filename) if filename else 'video.mp4'
                    display_filename = _clean_filename_for_display_local(display_filename)
                    downloaded_mb = downloaded_bytes / (1024 * 1024)
                    progress_text = (
                        f"📥 下载中\n"
                        f"📝 文件名: {display_filename}\n"
                        f"💾 大小: {downloaded_mb:.2f}MB / {size_mb:.2f}MB\n"
                        f"⚡ 速度: {speed_mb:.2f}MB/s\n"
                        f"⏳ 预计剩余: {eta_text}\n"
                        f"📊 进度: {progress_bar} {progress:.1f}%"
                    )

                    async def do_update():
                        try:
                            await status_message.edit_text(progress_text, parse_mode=None)
                        except Exception as e:
                            if "Message is not modified" not in str(e):
                                logger.warning(f"更新进度失败: {e}")

                    asyncio.run_coroutine_threadsafe(do_update(), loop)
                else:
                    # 没有总大小信息时的处理
                    downloaded_mb = downloaded_bytes / (1024 * 1024) if downloaded_bytes > 0 else 0
                    speed_mb = (speed_bytes_s or 0) / (1024 * 1024)
                    # 确保文件名不包含路径
                    display_filename = os.path.basename(filename) if filename else 'video.mp4'
                    display_filename = _clean_filename_for_display_local(display_filename)
                    progress_text = (
                        f"📥 下载中\n"
                        f"📝 文件名: {display_filename}\n"
                        f"💾 大小: {downloaded_mb:.2f}MB\n"
                        f"⚡ 速度: {speed_mb:.2f}MB/s\n"
                        f"⏳ 预计剩余: 未知\n"
                        f"📊 进度: 下载中..."
                    )

                    async def do_update():
                        try:
                            await status_message.edit_text(progress_text, parse_mode=None)
                        except Exception as e:
                            if "Message is not modified" not in str(e):
                                logger.warning(f"更新进度失败: {e}")

                    asyncio.run_coroutine_threadsafe(do_update(), loop)

        # --- 执行下载 ---
        # 检查是否为YouTube Music URL，如果是则使用专门的下载器
        if self.downloader.is_youtube_music_url(url) and YouTubeMusicDownloader:
            logger.info(f"🎵 检测到YouTube Music URL，使用专门的下载器: {url}")
            
            # 创建YouTube Music下载任务
            try:
                youtube_music_downloader = YouTubeMusicDownloader()
                
                # 检查是否为播放列表
                if 'list=' in url:
                    logger.info("🎵 检测到YouTube Music播放列表，开始下载...")
                    download_task = asyncio.create_task(
                        youtube_music_downloader.download_playlist(
                            url, 
                            progress_callback=update_progress
                        )
                    )
                else:
                    logger.info("🎵 检测到YouTube Music单曲，开始下载...")
                    download_task = asyncio.create_task(
                        youtube_music_downloader.download_track(
                            url, 
                            progress_callback=update_progress
                        )
                    )
            except Exception as e:
                logger.error(f"❌ YouTube Music下载器初始化失败: {e}")
                # 回退到通用下载器
                download_task = asyncio.create_task(
                    self.downloader.download_video(
                        url, update_progress, self.bilibili_auto_playlist, status_message, None, context
                    )
                )
        else:
            # 创建普通下载任务，使用增强版的进度回调
            download_task = asyncio.create_task(
                self.downloader.download_video(
                    url, update_progress, self.bilibili_auto_playlist, status_message, None, context
                )
            )

        # 添加到任务管理器
        await self.add_download_task(task_id, download_task, update.effective_user.id, status_message)

        try:
            # 等待下载完成
            result = await download_task
        except asyncio.CancelledError:
            logger.info(f"🚫 下载任务被取消: {task_id}")
            await status_message.edit_text("🚫 下载任务已取消", parse_mode=None)
            return
        except Exception as e:
            logger.error(f"❌ 下载任务执行异常: {e}")
            await status_message.edit_text(f"❌ 下载失败: {str(e)}")
            return
        finally:
            # 从任务管理器中移除任务
            await self.remove_download_task(task_id)
            # 🔥 关键修复：下载完成后立即锁死进度回调，防止后续回调覆盖完成信息
            progress_state["finished_shown"] = True
            logger.info("🔒 下载任务完成，锁死进度回调")

        # 检查result是否为None
        if not result:
            logger.error("❌ 下载任务返回None结果")
            await status_message.edit_text("❌ 下载失败: 未知错误", parse_mode=None)
            return

        # 兼容不同的返回格式：有些返回"success"，有些返回"status"
        if result.get("success") or result.get("status") == "success":
            # 添加调试日志
            logger.info(f"下载完成，结果: {result}")
            logger.info(f"is_playlist: {result.get('is_playlist')}")
            logger.info(f"platform: {result.get('platform')}")
            logger.info(f"video_type: {result.get('video_type')}")

            # 移除UGC合集的特殊跳过逻辑，让所有结果都通过统一的消息处理

            # 检查是否为B站合集下载
            platform_value = result.get("platform", "")
            logger.info(f"Platform值: '{platform_value}'")
            logger.info(f"是否包含Bilibili: {'bilibili' in platform_value.lower()}")

            # 更宽松的B站检测条件
            is_bilibili_playlist = (
                (result.get("is_playlist") and "bilibili" in platform_value.lower()) or
                (result.get("video_type") == "playlist" and "bilibili" in platform_value.lower()) or
                (result.get("video_type") == "user_all_videos" and "bilibili" in platform_value.lower()) or
                (result.get("is_playlist") and platform_value.lower() == "bilibili") or
                (result.get("is_playlist") and "bilibili" in str(result).lower()) or
                (result.get("download_path", "").startswith("/downloads/Bilibili") and result.get("is_playlist"))
            )

            # 检查是否为B站UP主所有视频下载（类似YouTube频道）
            is_bilibili_channel = (
                result.get("is_channel") and "bilibili" in platform_value.lower() and
                result.get("video_type") == "user_all_videos"
            )

            logger.info(f"是否为B站播放列表: {is_bilibili_playlist}")

            if is_bilibili_playlist:
                # 检查是否为UP主所有合集下载
                if result.get("video_type") == "user_all_collections":
                    # UP主所有合集下载完成
                    uid = result.get("uid", "未知")
                    total_collections = result.get("total_collections", 0)
                    downloaded_collections = result.get("downloaded_collections", 0)
                    file_count = result.get("file_count", 0)
                    total_size_mb = result.get("total_size_mb", 0)
                    download_path = result.get("download_path", "")
                    collections = result.get("collections", [])

                    # 构建成功消息
                    success_text = f"""🎬 B站UP主所有合集下载完成

📺 UP主ID: {uid}
📊 合集统计: {downloaded_collections}/{total_collections} 个合集
📁 总文件数: {file_count} 个
💾 总大小: {total_size_mb:.2f}MB
📂 保存位置: {download_path}

已下载的合集:
"""

                    # 添加每个合集的详细信息
                    for i, collection in enumerate(collections, 1):
                        collection_title = collection.get('title', f'合集{i}')
                        collection_type = collection.get('type', 'unknown')
                        collection_files = collection.get('file_count', 0)
                        collection_size = collection.get('size_mb', 0)

                        type_emoji = "📺" if collection_type == "season" else "📝"
                        success_text += f"    {i}. {type_emoji} {collection_title} ({collection_files} 个文件, {collection_size:.1f}MB)\n"

                    try:
                        await status_message.edit_text(
                            success_text,
                            parse_mode=None,
                            timeout=10.0
                        )
                        logger.info("UP主所有合集下载完成消息发送成功")
                    except Exception as e:
                        if "Flood control" in str(e):
                            logger.warning("UP主合集下载完成消息遇到Flood control，等待5秒后重试...")
                            await asyncio.sleep(5)
                            try:
                                await status_message.edit_text(success_text, parse_mode=None)
                            except Exception as retry_error:
                                logger.error(f"重试发送UP主合集完成消息失败: {retry_error}")
                        else:
                            logger.error(f"发送UP主合集完成消息失败: {e}")
                    return

                # B站自定义列表下载完成，直接使用返回的结果，不进行目录遍历
                # 参考 main.mp.py 的逻辑
                file_count = result.get("file_count", 0)
                total_size_mb = result.get("total_size_mb", 0)
                episode_count = result.get("episode_count", 0)
                download_path = result.get("download_path", "")

                # 获取分辨率信息，优先从files中提取
                resolution_display = result.get("resolution", "未知")
                files = result.get("files", [])
                if files and (not resolution_display or resolution_display == "未知" or resolution_display == ""):
                    # 从files中提取分辨率信息
                    resolutions = set()
                    for file_info in files:
                        file_resolution = file_info.get("resolution", "")
                        if file_resolution and file_resolution != "未知":
                            resolutions.add(file_resolution)

                    if resolutions:
                        resolution_display = ', '.join(sorted(resolutions))
                        logger.info(f"✅ 从files中提取到分辨率: {resolution_display}")
                    else:
                        logger.debug("📊 files中没有找到分辨率信息，使用默认值")
                        resolution_display = "未知"  # 确保返回"未知"而不是空字符串

                logger.debug(f"📊 最终使用的分辨率: {resolution_display}")

                # 从result.files中获取文件名列表
                filename_display = ""
                files = result.get("files", [])
                if files:
                    # 构建文件名列表
                    filename_lines = []
                    for i, file_info in enumerate(files, 1):
                        filename = file_info.get("filename", f"文件{i}")
                        filename_lines.append(f"  {i:02d}. {filename}")
                    filename_display = '\n'.join(filename_lines)
                    logger.info(f"✅ 从result.files获取到 {len(files)} 个文件名")
                else:
                    # 回退方案：使用result.filename
                    filename_display = result.get("filename", "")
                    logger.warning("⚠️ result.files为空，使用result.filename")

                title = "🎬 视频下载完成"
                escaped_title = (title)

                # 动态处理文件名显示，最大化利用TG消息空间
                filename_display = self.downloader._optimize_filename_display_for_telegram(
                    filename_display, file_count, total_size_mb, resolution_display, download_path
                )

                # 使用普通文本格式，不需要转义
                escaped_filename = filename_display
                escaped_resolution = resolution_display
                escaped_download_path = download_path

                # 普通格式，不需要转义小数点
                total_size_str = f"{total_size_mb:.2f}"
                episode_count_str = str(episode_count)

                # 获取PART文件统计信息
                success_count = result.get("success_count", file_count)  # 使用file_count作为默认值
                part_count = result.get("part_count", 0)

                # 构建统计信息
                stats_text = f"✅ **成功**: `{success_count} 个`"
                if part_count > 0:
                    stats_text += f"\n⚠️ **未完成**: `{part_count} 个`"
                    stats_text += f"\n💡 **提示**: 发现未完成文件，可能需要重新下载"

                # 添加清晰度标识到分辨率
                def add_quality_label(resolution_str):
                    """根据分辨率添加清晰度标识"""
                    if not resolution_str or resolution_str == "未知":
                        return resolution_str

                    # 解析分辨率
                    try:
                        # 处理多个分辨率的情况（用逗号分隔）
                        resolutions = [r.strip() for r in resolution_str.split(',')]
                        labeled_resolutions = []

                        for res in resolutions:
                            if 'x' in res.lower():
                                # 提取宽度和高度
                                parts = res.lower().split('x')
                                if len(parts) == 2:
                                    try:
                                        # 提取数字部分，忽略括号和其他文本
                                        width_str = parts[0].strip()
                                        height_str = parts[1].strip()

                                        # 使用正则表达式提取数字
                                        import re
                                        width_match = re.search(r'(\d+)', width_str)
                                        height_match = re.search(r'(\d+)', height_str)

                                        if width_match and height_match:
                                            width = int(width_match.group(1))
                                            height = int(height_match.group(1))

                                            # 根据分辨率添加清晰度标识
                                            if width >= 3840 or height >= 2160:
                                                quality = "4K"
                                            elif width >= 2560 or height >= 1440:
                                                quality = "2K"
                                            elif width >= 1920 or height >= 1080:
                                                quality = "1080P"
                                            elif width >= 1280 or height >= 720:
                                                quality = "720P"
                                            elif width >= 854 or height >= 480:
                                                quality = "480P"
                                            else:
                                                quality = "标清"

                                            # 检查是否已经包含质量标识，避免重复添加
                                            quality_patterns = [r'\(8K\)', r'\(4K\)', r'\(2K\)', r'\(1080[Pp]\)', r'\(720[Pp]\)', r'\(480[Pp]\)', r'\(360[Pp]\)', r'\(\d+[Pp]\)', r'\(标清\)']
                                            has_quality = any(re.search(pattern, res) for pattern in quality_patterns)
                                            if not has_quality:
                                                labeled_resolutions.append(f"{res} ({quality})")
                                            else:
                                                labeled_resolutions.append(res)
                                        else:
                                            labeled_resolutions.append(res)
                                    except (ValueError, AttributeError):
                                        # 如果无法解析数字，直接使用原始字符串
                                        labeled_resolutions.append(res)
                                else:
                                    labeled_resolutions.append(res)
                            else:
                                # 检查是否是纯数字分辨率（如"1080", "720"等）
                                try:
                                    import re
                                    height_match = re.search(r'(\d+)', res)
                                    if height_match:
                                        height = int(height_match.group(1))

                                        # 根据高度添加清晰度标识
                                        if height >= 2160:
                                            quality = "4K"
                                        elif height >= 1440:
                                            quality = "2K"
                                        elif height >= 1080:
                                            quality = "1080P"
                                        elif height >= 720:
                                            quality = "720P"
                                        elif height >= 480:
                                            quality = "480P"
                                        else:
                                            quality = "标清"

                                        # 如果原字符串已经包含质量标识，就不重复添加
                                        # 使用正则表达式检查是否已有质量标识
                                        import re
                                        quality_patterns = [
                                            r'\(8K\)', r'\(4K\)', r'\(2K\)', r'\(1080[Pp]\)', r'\(720[Pp]\)', r'\(480[Pp]\)', r'\(360[Pp]\)', r'\(\d+[Pp]\)',
                                            r'8K$', r'4K$', r'2K$', r'1080[Pp]$', r'720[Pp]$', r'480[Pp]$', r'360[Pp]$', r'\d+[Pp]$'
                                        ]
                                        has_quality = any(re.search(pattern, res) for pattern in quality_patterns)
                                        if not has_quality:
                                            labeled_resolutions.append(f"{res} ({quality})")
                                        else:
                                            labeled_resolutions.append(res)
                                    else:
                                        labeled_resolutions.append(res)
                                except (ValueError, AttributeError):
                                    labeled_resolutions.append(res)

                        return ', '.join(labeled_resolutions)
                    except Exception as e:
                        logger.warning(f"解析分辨率时出错: {e}")
                        return resolution_str

                # 添加清晰度标识
                resolution_with_quality = add_quality_label(resolution_display)
                escaped_resolution_with_quality = resolution_with_quality

                success_text = (
                    f"{escaped_title}\n\n"
                    f"📝 **文件名**:\n{escaped_filename}\n\n"
                    f"💾 **文件大小**: `{total_size_str} MB`\n"
                    f"📊 **下载统计**:\n{stats_text}\n"
                    f"🖼️ **分辨率**: `{escaped_resolution_with_quality}`\n"
                    f"📂 **保存位置**: `{escaped_download_path}`"
                )

                try:
                    await status_message.edit_text(
                        text=success_text, parse_mode=None
                    )
                except Exception as e:
                    if "Flood control" in str(e):
                        logger.warning(
                            "B站合集下载完成消息遇到Flood control，等待5秒后重试..."
                        )
                        await asyncio.sleep(5)
                        try:
                            await status_message.edit_text(
                                text=success_text, parse_mode=None
                            )
                        except Exception as retry_error:
                            logger.error(
                                f"重试发送B站合集完成消息失败: {retry_error}"
                            )
                    else:
                        logger.error(f"发送B站合集完成消息失败: {e}")
            # 检查是否为B站UP主频道下载
            elif is_bilibili_channel:
                # B站UP主所有视频下载完成（类似YouTube频道）
                title = "📺 B站UP主所有视频下载完成"
                channel_title = result.get("channel_title", "未知UP主")
                total_videos = result.get("total_videos", 0)
                downloaded_videos = result.get("downloaded_videos", 0)
                failed_videos = result.get("failed_videos", 0)
                success_rate = result.get("success_rate", 0)
                total_size_mb = result.get("total_size_mb", 0)
                download_path = result.get("download_path", "")

                # 格式化总大小显示
                if total_size_mb >= 1024:
                    total_size_str = f"{total_size_mb / 1024:.2f}GB"
                else:
                    total_size_str = f"{total_size_mb:.2f}MB"

                # 获取播放列表信息
                playlists = result.get("playlists_downloaded", [])
                playlist_stats = result.get("playlist_stats", [])

                success_text = f"""📺 **B站UP主播放列表下载完成**

📺 **UP主**: `{(channel_title)}`
📊 **播放列表数量**: `{(str(len(playlists)))}` 个

**已下载的播放列表**:

"""

                # 添加每个播放列表的详细信息
                for i, stat in enumerate(playlist_stats, 1):
                    playlist_title = stat.get("title", f"播放列表{i}")
                    video_count = stat.get("video_count", 0)

                    success_text += f"    {i}. {playlist_title} ({video_count} 集)\n"

                success_text += f"""
📊 下载统计:
总计: {total_videos} 个
✅ 成功: {downloaded_videos} 个
❌ 失败: {failed_videos} 个

💾 文件总大小: {total_size_str}
📂 保存位置: {download_path}"""

                try:
                    await status_message.edit_text(
                        success_text,
                        parse_mode=None,
                        timeout=10.0
                    )
                    logger.info("B站UP主所有视频下载完成消息发送成功")
                except Exception as e:
                    if "Flood control" in str(e):
                        logger.warning("B站UP主下载完成消息遇到Flood control，等待5秒后重试...")
                        await asyncio.sleep(5)
                        try:
                            await status_message.edit_text(success_text, parse_mode=None)
                        except Exception as retry_error:
                            logger.error(f"重试发送B站UP主完成消息失败: {retry_error}")
                    else:
                        logger.error(f"发送B站UP主完成消息失败: {e}")
                return

            # 检查是否为播放列表或频道下载
            elif result.get("is_playlist") or result.get("is_channel") or result.get("downloaded_files"):
                # 播放列表或频道下载完成
                if result.get("is_channel"):
                    title = "📺 YouTube频道播放列表下载完成"
                    channel_title = result.get("channel_title", "未知频道")
                    playlists = result.get("playlists_downloaded", [])
                    playlist_stats = result.get("playlist_stats", [])
                    download_path = result.get("download_path", "")

                    # 计算总文件大小和PART文件统计
                    total_size_mb = sum(stat.get('total_size_mb', 0) for stat in playlist_stats)
                    total_size_gb = total_size_mb / 1024

                    # 计算总的成功和未完成文件数量
                    total_success_count = sum(stat.get('success_count', stat.get('video_count', 0)) for stat in playlist_stats)
                    total_part_count = sum(stat.get('part_count', 0) for stat in playlist_stats)

                    # 计算总计数量和失败数量
                    total_video_count = sum(stat.get('video_count', 0) for stat in playlist_stats)
                    total_failed_count = total_video_count - total_success_count



                    # 格式化总大小显示 - 只显示一个单位
                    if total_size_gb >= 1.0:
                        total_size_str = f"{total_size_gb:.2f}GB"
                    else:
                        total_size_str = f"{total_size_mb:.2f}MB"

                    success_text = (
                        f"{(title)}\n\n"
                        f"📺 频道: {(channel_title)}\n"
                        f"📊 播放列表数量: {(str(len(playlists)))}\n\n"
                        f"已下载的播放列表:\n\n"
                    )

                    # 使用playlist_stats来显示集数信息
                    for i, stat in enumerate(playlist_stats, 1):
                        playlist_title = stat.get("title", f"播放列表{i}")
                        video_count = stat.get("video_count", 0)
                        success_text += f"    {(str(i))}\\. {(playlist_title)} \\({(str(video_count))} 集\\)\n"

                    # 构建下载统计信息（移除成功率，简化格式）
                    stats_text = f"总计: {total_video_count} 个\n✅ 成功: {total_success_count} 个\n❌ 失败: {total_failed_count} 个"

                    if total_part_count > 0:
                        stats_text += f"\n⚠️ 未完成: {total_part_count} 个"

                    # 添加统计信息、总大小和保存位置（在文件总大小前加空行）
                    success_text += (
                        f"\n📊 下载统计:\n{stats_text}\n\n"
                        f"💾 文件总大小: {(total_size_str)}\n"
                        f"📂 保存位置: {(download_path)}"
                    )
                else:
                    # 检查是否为X播放列表
                    platform = result.get("platform", "")
                    if platform == "X" and result.get("is_playlist"):
                        # X播放列表下载完成
                        title = "🎬 X播放列表下载完成"
                        file_count = result.get("file_count", 0)
                        episode_count = result.get("episode_count", 0)
                        total_size_mb = result.get("total_size_mb", 0)
                        resolution = result.get("resolution", "未知")
                        download_path = result.get("download_path", "")
                        filename_display = result.get("filename", "")

                        success_text = (
                            f"{title}\n\n"
                            f"📝 文件名:\n{filename_display}\n\n"
                            f"💾 文件大小: {total_size_mb:.2f} MB\n"
                            f"📊 集数: {episode_count} 集\n"
                            f"🖼️ 分辨率: {resolution}\n"
                            f"📂 保存位置: {download_path}"
                        )
                    else:
                        # YouTube播放列表下载完成
                        # 检查是否有详细的文件信息
                        downloaded_files = result.get("downloaded_files", [])
                        if downloaded_files:
                            # 有详细文件信息，使用增强显示
                            title = "🎬 视频下载完成"
                            playlist_title = result.get("playlist_title", "YouTube播放列表")
                            video_count = result.get("video_count", len(downloaded_files))
                            total_size_mb = result.get("total_size_mb", 0)
                            resolution = result.get("resolution", "未知")
                            download_path = result.get("download_path", "")

                            # 构建文件名显示列表
                            filename_lines = []
                            for i, file_info in enumerate(downloaded_files, 1):
                                filename = file_info.get("filename", f"文件{i}")
                                filename_lines.append(f"  {i:02d}. {filename}")
                            filename_display = '\n'.join(filename_lines)

                            # 动态处理文件名显示，最大化利用TG消息空间
                            filename_display = self.downloader._optimize_filename_display_for_telegram(
                                filename_display, video_count, total_size_mb, resolution, download_path
                            )

                            # 获取PART文件统计信息
                            success_count = result.get("success_count", video_count)
                            part_count = result.get("part_count", 0)

                            # 构建统计信息
                            stats_text = f"✅ **成功**: `{success_count} 个`"
                            if part_count > 0:
                                stats_text += f"\n⚠️ **未完成**: `{part_count} 个`"
                                stats_text += f"\n💡 **提示**: 发现未完成文件，可能需要重新下载"

                            # 使用普通文本格式，不需要转义
                            escaped_title = title
                            escaped_filename = filename_display
                            escaped_resolution = resolution
                            escaped_download_path = download_path
                            size_str = f"{total_size_mb:.2f}"

                            success_text = (
                                f"{escaped_title}\n\n"
                                f"📝 **文件名**:\n{escaped_filename}\n\n"
                                f"💾 **文件大小**: `{size_str} MB`\n"
                                f"📊 **下载统计**:\n{stats_text}\n"
                                f"🖼️ **分辨率**: `{escaped_resolution}`\n"
                                f"📂 **保存位置**: `{escaped_download_path}`"
                            )
                        else:
                            # 没有详细文件信息，使用简单显示
                            title = "📋 YouTube播放列表下载完成"
                            playlist_title = result.get("playlist_title", "未知播放列表")
                            video_count = result.get("video_count", 0)
                            download_path = result.get("download_path", "")

                            # 检查是否已经下载过
                            if result.get("already_downloaded", False):
                                title = "📋 YouTube播放列表已存在"
                                completion_rate = result.get("completion_rate", 100)
                                completion_str = f"{completion_rate:.1f}".replace('.', r'\.')

                                success_text = (
                                    f"{(title)}\n\n"
                                    f"📋 **播放列表**: `{(playlist_title)}`\n"
                                    f"📂 **保存位置**: `{(download_path)}`\n"
                                    f"📊 **视频数量**: `{(str(video_count))}`\n"
                                    f"✅ **完成度**: `{completion_str}%`\n"
                                    f"💡 **状态**: 本地文件已存在，无需重复下载"
                                )
                            else:
                                # 检查是否为零文件情况（所有视频不可用）
                                if video_count == 0:
                                    title = "⚠️ YouTube播放列表无可用视频"
                                    success_text = (
                                        f"{(title)}\n\n"
                                        f"📋 **播放列表**: `{(playlist_title)}`\n"
                                        f"📂 **保存位置**: `{(download_path)}`\n"
                                        f"❌ **状态**: 播放列表中的所有视频都不可用\n"
                                        f"💡 **可能原因**: 视频被删除、账号被终止或地区限制"
                                    )
                                else:
                                    # 尝试从下载目录获取文件名
                                    filename_display = ""
                                    try:
                                        from pathlib import Path
                                        download_dir = Path(download_path)

                                        # 如果有播放列表标题，查找对应的子目录
                                        if playlist_title and playlist_title != "未知播放列表":
                                            playlist_dir = download_dir / playlist_title
                                            if playlist_dir.exists():
                                                # 遍历播放列表目录中的文件
                                                video_files = []
                                                for file_path in playlist_dir.glob("*"):
                                                    if file_path.is_file() and file_path.suffix.lower() in ['.mp4', '.mkv', '.webm', '.avi', '.mov']:
                                                        video_files.append(file_path)

                                                if video_files:
                                                    # 构建文件名列表
                                                    filename_lines = []
                                                    for i, file_path in enumerate(sorted(video_files), 1):
                                                        filename_lines.append(f"  {i:02d}. {file_path.name}")
                                                    filename_display = '\n'.join(filename_lines)
                                                    logger.info(f"✅ 从播放列表目录找到 {len(video_files)} 个文件")
                                        else:
                                            # 如果没有播放列表标题，遍历根目录
                                            video_files = []
                                            for file_path in download_dir.glob("*"):
                                                if file_path.is_file() and file_path.suffix.lower() in ['.mp4', '.mkv', '.webm', '.avi', '.mov']:
                                                    video_files.append(file_path)

                                            if video_files:
                                                # 构建文件名列表
                                                filename_lines = []
                                                for i, file_path in enumerate(sorted(video_files), 1):
                                                    filename_lines.append(f"  {i:02d}. {file_path.name}")
                                                filename_display = '\n'.join(filename_lines)
                                                logger.info(f"✅ 从根目录找到 {len(video_files)} 个文件")

                                        # 如果仍然没有找到文件，尝试递归遍历
                                        if not filename_display:
                                            logger.warning("⚠️ 未找到文件，尝试递归遍历所有子目录")
                                            video_files = []
                                            for file_path in download_dir.rglob("*"):
                                                if file_path.is_file() and file_path.suffix.lower() in ['.mp4', '.mkv', '.webm', '.avi', '.mov']:
                                                    video_files.append(file_path)

                                            if video_files:
                                                # 构建文件名列表
                                                filename_lines = []
                                                for i, file_path in enumerate(sorted(video_files), 1):
                                                    filename_lines.append(f"  {i:02d}. {file_path.name}")
                                                filename_display = '\n'.join(filename_lines)
                                                logger.info(f"✅ 递归找到 {len(video_files)} 个文件")

                                    except Exception as e:
                                        logger.error(f"获取文件名时出错: {e}")

                                    # 构建成功消息
                                    if filename_display:
                                        success_text = (
                                            f"{title}\n\n"
                                            f"📝 文件名:\n{filename_display}\n\n"
                                            f"📋 播放列表: {playlist_title}\n"
                                            f"📂 保存位置: {download_path}\n"
                                            f"📊 视频数量: {video_count}"
                                        )
                                    else:
                                        success_text = (
                                            f"{title}\n\n"
                                            f"📋 播放列表: {playlist_title}\n"
                                            f"📂 保存位置: {download_path}\n"
                                            f"📊 视频数量: {video_count}"
                                        )

                try:
                    await status_message.edit_text(
                        text=success_text, parse_mode=None
                    )
                except Exception as e:
                    if "Flood control" in str(e):
                        logger.warning(
                            "播放列表下载完成消息遇到Flood control，等待5秒后重试..."
                        )
                        await asyncio.sleep(5)
                        try:
                            await status_message.edit_text(
                                text=success_text, parse_mode=None
                            )
                        except Exception as retry_error:
                            logger.error(
                                f"重试发送播放列表完成消息失败: {retry_error}"
                            )
                    else:
                        logger.error(f"发送播放列表完成消息失败: {e}")
            else:
                # 单文件下载，使用原有逻辑
                # 根据结果构建成功消息
                resolution = result.get("resolution", "未知")
                
                # 修复小红书图片下载完成消息显示问题
                # 小红书下载器返回的结果中没有resolution字段，只有content_type字段
                # 只在确实是小红书平台时才执行图片检测逻辑
                if platform.lower() == 'xiaohongshu' or result.get('platform') == 'Xiaohongshu':
                    logger.info(f"🔍 [_process_download_async] 检查小红书图片 - content_type: {result.get('content_type')}, resolution: {resolution}")
                if result.get('content_type') == 'image' and resolution == '未知':
                    resolution = '图片'
                    logger.info(f"✅ [_process_download_async] 小红书图片检测成功，设置resolution为: {resolution}")
                else:
                    logger.info(f"🔍 [_process_download_async] 非小红书平台，跳过图片检测 - platform: {platform}, content_type: {result.get('content_type')}")
                    
                abr = result.get("abr")

                # 根据分辨率判断是视频还是音频
                if resolution and resolution != "未知" and resolution == "图片":
                    # 图片类型
                    title = "🖼️ 图片下载完成"
                    size_str = f"{result['total_size_mb']:.2f}"
                    files_count = result.get("files_count", 1)
                    file_formats = result.get("file_formats", [])
                    format_str = ", ".join(file_formats) if file_formats else "未知格式"

                    # 构建文件名列表
                    files_info = result.get("files", [])
                    filenames_text = ""
                    if files_info:
                        if len(files_info) <= 5:
                            # 文件数量较少，显示所有文件名
                            filenames_text = "\n📝 **文件名**:\n"
                            for i, file_info in enumerate(files_info, 1):
                                # 从path中提取文件名
                                file_path = file_info.get('path', f'图片{i}')
                                filename = os.path.basename(file_path) if file_path else f'图片{i}'
                                filenames_text += f"  `{i}. {filename}`\n"
                        else:
                            # 文件数量较多，只显示前3个和后1个
                            filenames_text = "\n📝 **文件名**:\n"
                            for i in range(min(3, len(files_info))):
                                file_path = files_info[i].get('path', f'图片{i+1}')
                                filename = os.path.basename(file_path) if file_path else f'图片{i+1}'
                                filenames_text += f"  `{i+1}. {filename}`\n"
                            if len(files_info) > 3:
                                filenames_text += f"  `... 等 {len(files_info) - 3} 个文件`\n"
                                if len(files_info) > 4:
                                    last_file = files_info[-1]
                                    last_file_path = last_file.get('path', f'图片{len(files_info)}')
                                    last_filename = os.path.basename(last_file_path) if last_file_path else f'图片{len(files_info)}'
                                    filenames_text += f"  `{len(files_info)}. {last_filename}`\n"
                    elif result.get('filename'):
                        # 如果没有files信息但有单个filename
                        filenames_text = f"\n📝 **文件名**: `{result['filename']}`\n"

                    success_text = (
                        f"{title}\n\n"
                        f"🖼️ **图片数量**: `{files_count} 张`\n"
                        f"💾 **文件大小**: `{size_str} MB`\n"
                        f"📄 **文件格式**: `{format_str}`{filenames_text}"
                        f"📂 **保存位置**: `{result['download_path']}`"
                    )

                    # 发送图片完成消息，替换进度消息
                    logger.info(f"📤 [_process_download_async] 准备发送小红书图片完成消息，消息长度: {len(success_text)}")
                    
                    # 等待一段时间，确保xiaohongshu_downloader的进度消息被处理完毕
                    logger.info("⏳ 等待进度消息处理完成，然后发送汇总信息...")
                    await asyncio.sleep(2.0)  # 等待2秒
                    
                    try:
                        await status_message.edit_text(success_text, parse_mode=None)
                        logger.info("✅ [_process_download_async] 小红书图片下载完成消息发送成功")
                    except Exception as e:
                        if "Flood control" in str(e):
                            logger.warning("⚠️ [_process_download_async] 图片下载完成消息遇到Flood control，等待5秒后重试...")
                            await asyncio.sleep(5)
                            try:
                                await status_message.edit_text(success_text, parse_mode=None)
                                logger.info("✅ [_process_download_async] 重试发送图片下载完成消息成功")
                            except Exception as retry_error:
                                logger.error(f"❌ [_process_download_async] 重试发送图片下载完成消息失败: {retry_error}")
                        else:
                            logger.error(f"❌ [_process_download_async] 发送图片下载完成消息失败: {e}")
                    
                    # 图片下载完成，进度消息已被完成消息替换，直接返回
                    logger.info("🔚 [_process_download_async] 小红书图片下载处理完成，直接返回")
                    return
                elif resolution and resolution != "未知" and "x" in resolution:
                    # 有分辨率信息，说明是视频
                    # 解析分辨率并添加质量标识
                    try:
                        width_str, height_str = resolution.split("x")
                        # 使用正则表达式提取数字部分，忽略括号和其他文本
                        import re
                        width_match = re.search(r'(\d+)', width_str.strip())
                        height_match = re.search(r'(\d+)', height_str.strip())

                        if width_match and height_match:
                            width = int(width_match.group(1))
                            height = int(height_match.group(1))
                        else:
                            # 如果无法提取数字，跳过质量标识
                            raise ValueError("无法提取分辨率数字")

                        # 根据高度判断质量
                        if height >= 4320:
                            quality = "8K"
                        elif height >= 2160:
                            quality = "4K"
                        elif height >= 1440:
                            quality = "2K"
                        elif height >= 1080:
                            quality = "1080p"
                        elif height >= 720:
                            quality = "720p"
                        elif height >= 480:
                            quality = "480p"
                        else:
                            quality = f"{height}p"

                        quality_info = f" ({quality})"
                    except (ValueError, TypeError):
                        quality_info = ""

                    # 构建完整的title，然后一次性转义
                    title = "🎬 视频下载完成"
                    escaped_title = (title)
                    # 将质量标识添加到分辨率后面
                    resolution_with_quality = f"{resolution}{quality_info}"
                    size_str = f"{result['size_mb']:.2f}"
                    success_text = (
                        f"{escaped_title}\n\n"
                        f"📝 文件名: {result['filename']}\n"
                        f"💾 文件大小: {result['size_mb']:.2f} MB\n"
                        f"📺 分辨率: {resolution_with_quality}\n"
                        f"📂 保存位置: {result['download_path']}"
                    )
                    
                    # 发送视频完成消息
                    try:
                        await status_message.edit_text(success_text, parse_mode=None)
                        logger.info("显示视频下载完成信息")
                    except Exception as e:
                        if "Flood control" in str(e):
                            logger.warning("视频下载完成消息遇到Flood control，等待5秒后重试...")
                            await asyncio.sleep(5)
                            try:
                                await status_message.edit_text(success_text, parse_mode=None)
                                logger.info("重试发送视频下载完成消息成功")
                            except Exception as retry_error:
                                logger.error(f"重试发送视频下载完成消息失败: {retry_error}")
                        else:
                            logger.error(f"发送视频下载完成消息失败: {e}")
                    return
                
                # 使用简单格式显示完成信息（只显示一次）
                # 注意：小红书图片下载已在上面的分支中处理并返回，不会执行到这里
                try:
                    # 获取进度信息用于显示
                    display_filename = _clean_filename_for_display_local(result.get('filename', progress_data.get('filename', 'video.mp4') if progress_data and isinstance(progress_data, dict) else 'video.mp4'))
                    resolution = result.get('resolution', '未知')
                    platform = result.get('platform', '未知')
                    size_mb = result.get('size_mb', 0)
                    
                    # 添加调试日志
                    logger.info(f"🔍 [_process_download_async] 进入通用处理逻辑 - content_type: {result.get('content_type')}, resolution: {resolution}, platform: {platform}")

                    # 获取分辨率质量标识（避免重复添加）
                    quality_suffix = self._get_resolution_quality(resolution)
                    # 如果resolution已经包含质量标识，则不添加quality_suffix
                    if quality_suffix and quality_suffix.strip() in resolution:
                        quality_suffix = ""
                    
                    # 构建最终的分辨率显示（避免重复）
                    final_resolution = resolution + quality_suffix

                    # 获取下载路径
                    download_path = result.get('download_path', '未知路径')

                    # 检查是否为网易云音乐下载
                    if platform.lower() == 'netease':
                        # 网易云音乐下载完成
                        if result.get('playlist_name'):
                            # 歌单下载 - 使用普通文本格式
                            title = "🎵 网易云音乐歌单下载完成"
                            
                            playlist_name = result.get('playlist_name', '未知歌单')
                            creator = result.get('creator', '未知创建者')
                            total_songs = result.get('total_songs', 0)
                            downloaded_songs = result.get('downloaded_songs', 0)
                            failed_songs = result.get('failed_songs', 0)
                            total_size = result.get('total_size_mb', 0)
                            download_path = result.get('download_path', '未知路径')
                            quality = result.get('quality', '未知')
                            
                            # 获取音质详细信息
                            quality_info = self._get_netease_quality_info(quality)
                            
                            success_text = (
                                f"{title}\n\n"
                                f"📋 歌单名称: {playlist_name}\n"
                                f"🎵 歌曲数量: {total_songs} 首\n"
                                f"✅ 成功下载: {downloaded_songs} 首\n"
                                f"❌ 失败数量: {failed_songs} 首\n"
                                f"💾 总大小: {total_size:.1f} MB\n"
                                f"📂 保存位置: {download_path}"
                            )
                            
                            # 如果有失败的歌曲，添加失败详情
                            failed_details = result.get('failed_details', [])
                            if failed_details:
                                success_text += "\n\n❌ 下载失败的歌曲:"
                                for i, failed in enumerate(failed_details[:5], 1):  # 只显示前5个失败的
                                    song_name = failed.get('song', {}).get('name', '未知歌曲')
                                    error = failed.get('error', '未知错误')
                                    success_text += f"\n{i}. {song_name}: {error}"
                                if len(failed_details) > 5:
                                    success_text += f"\n... 还有 {len(failed_details) - 5} 首歌曲下载失败"
                            
                        elif result.get('album_name'):
                            # 专辑下载 - 使用新的格式
                            title = "🎵 网易云音乐专辑下载完成"
                            
                            album_name = result.get('album_name', '未知专辑')
                            total_songs = result.get('total_songs', 0)
                            downloaded_songs = result.get('downloaded_songs', 0)
                            total_size = result.get('total_size_mb', 0)
                            download_path = result.get('download_path', '未知路径')
                            quality = result.get('quality', '未知')

                            # 获取音质详细信息（文件格式和码率）
                            quality_info = self._get_netease_quality_info(quality)
                            
                            # 获取歌曲列表用于提取艺术家和文件格式
                            songs = result.get('songs', [])
                            logger.info(f"🔍 获取到的songs列表长度: {len(songs)}")
                            if songs:
                                logger.info(f"🔍 第一首歌曲信息: {songs[0]}")
                            
                            # 尝试从歌曲列表或下载路径提取艺术家信息
                            artist_name = self._extract_artist_from_path(download_path, album_name, songs)
                            
                            # 检测文件格式（从歌曲列表中提取）
                            file_formats = set()
                            for song in songs:
                                song_name = song.get('song_name', '')
                                if song_name.endswith('.mp3'):
                                    file_formats.add('MP3')
                                elif song_name.endswith('.flac'):
                                    file_formats.add('FLAC')
                                elif song_name.endswith('.ape'):
                                    file_formats.add('APE')
                                elif song_name.endswith('.wav'):
                                    file_formats.add('WAV')
                                elif song_name.endswith('.m4a'):
                                    file_formats.add('M4A')
                            
                            # 如果没有检测到格式，使用默认格式
                            if not file_formats:
                                # 不要强制使用音质设置推断的格式，而是使用实际检测到的格式
                                # 如果确实没有检测到任何格式，才使用默认MP3
                                file_formats.add('MP3')
                            
                            format_display = '、'.join(sorted(file_formats))
                            
                            success_text = (
                                f"{title}\n\n"
                                f"📀 专辑名称: {album_name}\n\n"
                                f"🎤 艺术家：{artist_name}\n"
                                f"🎼 曲目数量: {total_songs} 首\n"
                                f"🎚️ 音频质量: {quality_info['name']}\n"
                                f"💾 总大小: {total_size:.2f} MB\n"
                                f"📊 码率: {quality_info['bitrate']}\n"
                                f"📂 保存位置: {download_path}"
                            )

                            # 显示歌曲列表（直接从目录获取实际文件信息）
                            try:
                                import os
                                album_dir = download_path
                                if os.path.exists(album_dir):
                                    files = []
                                    for file in os.listdir(album_dir):
                                        if file.lower().endswith(('.mp3', '.flac', '.ape', '.wav', '.m4a')):
                                            file_path = os.path.join(album_dir, file)
                                            file_size = os.path.getsize(file_path)
                                            files.append({'name': file, 'size': file_size})
                                    
                                    # 按文件名排序
                                    files.sort(key=lambda x: x['name'])
                                    
                                    if files:
                                        success_text += "\n\n🎵 歌曲列表:\n\n"
                                        for i, file_info in enumerate(files, 1):
                                            filename = file_info['name']
                                            file_size_mb = file_info['size'] / (1024 * 1024)
                                            
                                            # 检查文件名是否已经包含序号
                                            import re
                                            has_numbering = re.match(r'^\s*\d+\.\s*', filename)
                                            
                                            if has_numbering:
                                                # 文件名已有序号，直接显示
                                                success_text += f"{filename} ({file_size_mb:.1f}MB)\n"
                                            else:
                                                # 文件名没有序号，添加序号
                                                success_text += f"{i:02d}. {filename} ({file_size_mb:.1f}MB)\n"
                                            
                                            logger.info(f"🔍 实际文件: {filename} - {file_size_mb:.1f}MB")
                                    else:
                                        success_text += "\n\n🎵 歌曲列表: 未找到音频文件\n"
                                else:
                                    # 如果目录不存在，使用原来的songs列表
                                    if songs:
                                        success_text += "\n\n🎵 歌曲列表:\n\n"
                                        for i, song in enumerate(songs, 1):
                                            song_name = song.get('song_name', '未知歌曲')
                                            song_size = song.get('size_mb', 0)
                                            
                                            # 确保文件名包含扩展名（仅用于显示）
                                            if not any(song_name.lower().endswith(ext) for ext in ['.mp3', '.flac', '.ape', '.wav', '.m4a']):
                                                actual_format = song.get('file_format', '').lower()
                                                if actual_format:
                                                    song_name += f'.{actual_format}'
                                                else:
                                                    song_name += '.mp3'
                                            
                                            success_text += f"{i}. {song_name} ({song_size:.1f}MB)\n"
                            except Exception as e:
                                logger.error(f"❌ 获取文件列表失败: {e}")
                                # 使用原来的songs列表作为后备
                                if songs:
                                    success_text += "\n\n🎵 歌曲列表:\n\n"
                                    for i, song in enumerate(songs, 1):
                                        song_name = song.get('song_name', '未知歌曲')
                                        song_size = song.get('size_mb', 0)
                                        success_text += f"{i}. {song_name} ({song_size:.1f}MB)\n"
                        else:
                            # 单曲下载
                            title = "🎵 网易云音乐单曲下载完成"

                            song_title = result.get('song_title', '未知歌曲')
                            song_artist = result.get('song_artist', '未知歌手')
                            filename = result.get('filename', '音乐文件')
                            size_mb = result.get('size_mb', 0)
                            download_path = result.get('download_path', '未知路径')
                            quality_name = result.get('quality_name', '未知')
                            bitrate = result.get('bitrate', '未知')
                            duration = result.get('duration', '未知')
                            file_format = result.get('file_format', 'MP3')

                            # 构建音乐名称
                            music_name = f"{song_title} - {song_artist}" if song_title and song_artist else filename
                            
                            success_text = (
                                f"{title}\n\n"
                                f"🎵 音乐: {music_name}\n"
                                f"💾 大小: {size_mb:.2f}MB\n"
                                f"🖼️ 码率: {bitrate}\n"
                                f"🎚️ 音质: {quality_name}\n"
                                f"⏱️ 时长: {duration}\n"
                                f"📂 保存位置: {download_path}"
                            )
                        
                        # 发送网易云音乐下载完成消息
                        try:
                            await status_message.edit_text(success_text, parse_mode=None)
                            logger.info("网易云音乐下载完成消息发送成功")
                        except Exception as e:
                            logger.error(f"发送网易云音乐完成消息失败: {e}")
                        return

                    # 检查是否为QQ音乐下载
                    elif platform.lower() == 'qqmusic' or result.get('platform') == 'QQMusic':
                        # QQ音乐下载完成
                        if result.get('album_name'):
                            # 专辑下载 - 参考网易云音乐格式
                            title = "🎵 QQ音乐专辑下载完成"
                            
                            album_name = result.get('album_name', '未知专辑')
                            singer_name = result.get('singer_name', '未知歌手')
                            total_songs = result.get('total_songs', 0)
                            downloaded_songs = result.get('downloaded_songs', 0)
                            failed_songs = result.get('failed_songs', 0)
                            download_path = result.get('download_path', '未知路径')
                            
                            # 获取音质信息（从下载的歌曲列表中提取）
                            downloaded_list = result.get('downloaded_list', [])
                            quality_info = {'name': '未知', 'bitrate': '未知'}
                            file_formats = set()
                            
                            if downloaded_list:
                                # 从第一首歌曲获取音质信息
                                first_song = downloaded_list[0]
                                quality = first_song.get('quality', '未知音质')
                                format_type = first_song.get('format', '未知格式')
                                
                                # 设置音质信息
                                if 'flac' in quality.lower() or '无损' in quality:
                                    quality_info = {'name': 'FLAC无损', 'bitrate': '16bit/44khz/1058kbps'}
                                    file_formats.add('FLAC')
                                elif 'ape' in quality.lower():
                                    quality_info = {'name': 'APE无损', 'bitrate': '16bit/44khz/1058kbps'}
                                    file_formats.add('APE')
                                elif '320' in quality:
                                    quality_info = {'name': 'MP3高品质', 'bitrate': '320kbps'}
                                    file_formats.add('MP3')
                                elif '128' in quality:
                                    quality_info = {'name': 'MP3标准', 'bitrate': '128kbps'}
                                    file_formats.add('MP3')
                                else:
                                    quality_info = {'name': quality, 'bitrate': '未知'}
                                    file_formats.add(format_type.upper())
                            
                            # 计算总大小
                            total_size_mb = 0
                            try:
                                import os
                                if os.path.exists(download_path):
                                    for file in os.listdir(download_path):
                                        file_path = os.path.join(download_path, file)
                                        if os.path.isfile(file_path):
                                            total_size_mb += os.path.getsize(file_path) / (1024 * 1024)
                            except Exception as e:
                                logger.warning(f"计算总大小失败: {e}")
                            
                            success_text = (
                                f"{title}\n\n"
                                f"📀 专辑名称: {album_name}\n\n"
                                f"🎤 艺术家：{singer_name}\n"
                                f"🎼 曲目数量: {total_songs} 首\n"
                                f"🎚️ 音频质量: {quality_info['name']}\n"
                                f"💾 总大小: {total_size_mb:.2f} MB\n"
                                f"📊 码率: {quality_info['bitrate']}\n"
                                f"📂 保存位置: {download_path}"
                            )
                            
                            # 显示歌曲列表（从实际文件获取）
                            try:
                                import os
                                album_dir = download_path
                                if os.path.exists(album_dir):
                                    files = []
                                    for file in os.listdir(album_dir):
                                        if file.lower().endswith(('.mp3', '.flac', '.ape', '.wav', '.m4a')):
                                            file_path = os.path.join(album_dir, file)
                                            file_size = os.path.getsize(file_path)
                                            files.append({'name': file, 'size': file_size})
                                    
                                    # 按文件名排序
                                    files.sort(key=lambda x: x['name'])
                                    
                                    if files:
                                        success_text += "\n\n🎵 歌曲列表:\n\n"
                                        for i, file_info in enumerate(files, 1):
                                            filename = file_info['name']
                                            file_size_mb = file_info['size'] / (1024 * 1024)
                                            
                                            # 检查文件名是否已经包含序号
                                            import re
                                            has_numbering = re.match(r'^\s*\d+\.\s*', filename)
                                            
                                            if has_numbering:
                                                # 文件名已有序号，直接显示
                                                success_text += f"{filename} ({file_size_mb:.1f}MB)\n"
                                            else:
                                                # 文件名没有序号，添加序号
                                                success_text += f"{i:02d}. {filename} ({file_size_mb:.1f}MB)\n"
                                    else:
                                        success_text += "\n\n🎵 歌曲列表: 未找到音频文件\n"
                                else:
                                    success_text += "\n\n🎵 歌曲列表: 下载目录不存在\n"
                            except Exception as e:
                                logger.warning(f"获取歌曲列表失败: {e}")
                                success_text += "\n\n🎵 歌曲列表: 获取失败\n"
                            
                        elif result.get('playlist_name'):
                            # 歌单下载 - 参考网易云音乐格式
                            title = "🎵 QQ音乐歌单下载完成"
                            
                            playlist_name = result.get('playlist_name', '未知歌单')
                            total_songs = result.get('total_songs', 0)
                            downloaded_songs = result.get('downloaded_songs', 0)
                            failed_songs = result.get('failed_songs', 0)
                            total_size = result.get('total_size_mb', 0)
                            download_path = result.get('download_path', '未知路径')
                            quality = result.get('quality', '未知')
                            
                            # 获取音质详细信息
                            quality_info = self._get_qqmusic_quality_info(quality)
                            
                            success_text = (
                                f"{title}\n\n"
                                f"📋 歌单名称: {playlist_name}\n"
                                f"🎵 歌曲数量: {total_songs} 首\n"
                                f"✅ 成功下载: {downloaded_songs} 首\n"
                                f"❌ 失败数量: {failed_songs} 首\n"
                                f"💾 总大小: {total_size:.1f} MB\n"
                                f"📂 保存位置: {download_path}"
                            )
                            
                            # 如果有失败的歌曲，添加失败详情
                            failed_list = result.get('failed_list', [])
                            if failed_list:
                                success_text += "\n\n❌ 下载失败的歌曲:"
                                for failed in failed_list[:5]:  # 只显示前5个失败的
                                    song_name = failed.get('song_name', '未知歌曲')
                                    singer_name = failed.get('singer_name', '未知歌手')
                                    error = failed.get('error', '未知错误')
                                    success_text += f"\n• {singer_name} - {song_name}: {error}"
                                
                                if len(failed_list) > 5:
                                    success_text += f"\n• ... 还有 {len(failed_list) - 5} 首歌曲下载失败"
                        
                        else:
                            # 单首歌曲下载
                            title = "🎵 QQ音乐下载完成"
                            
                            song_title = result.get('song_title', '未知歌曲')
                            song_artist = result.get('song_artist', '未知歌手')
                            album = result.get('album', '未知专辑')
                            quality = result.get('quality', '未知音质')
                            format_type = result.get('format', '未知格式')
                            file_path = result.get('file_path', '未知路径')
                            
                            # 计算文件大小（MB）
                            size_text = "未知"
                            try:
                                import os as _os
                                if file_path and _os.path.exists(file_path):
                                    _size_bytes = _os.path.getsize(file_path)
                                    size_text = f"{_size_bytes / (1024 * 1024):.2f} MB"
                            except Exception:
                                pass
                            
                            # 计算时长（优先使用结果中的时长；否则尝试用 mutagen 读取）
                            duration_seconds = result.get('duration') or 0
                            if not duration_seconds or duration_seconds <= 0:
                                try:
                                    from mutagen import File as _MutagenFile
                                    _audio = _MutagenFile(file_path) if file_path else None
                                    if _audio and getattr(_audio, 'info', None) and getattr(_audio.info, 'length', None):
                                        duration_seconds = int(_audio.info.length)
                                except Exception:
                                    pass
                            if duration_seconds and duration_seconds > 0:
                                _mins, _secs = divmod(int(duration_seconds), 60)
                                duration_text = f"{_mins:02d}:{_secs:02d}"
                            else:
                                duration_text = "未知"
                            
                            success_text = (
                                f"{title}\n\n"
                                f"🎵 歌曲: {song_title}\n"
                                f"🎤 艺术家: {song_artist}\n"
                                f"📀 专辑: {album}\n"
                                f"🎚️ 音质: {quality}\n"
                                f"📁 格式: {format_type}\n"
                                f"💾 大小: {size_text}\n"
                                f"⏱️ 时长: {duration_text}\n"
                                f"📂 保存位置: {file_path}"
                            )
                        
                        try:
                            await status_message.edit_text(success_text, parse_mode=None)
                            logger.info("📱 发送QQ音乐下载完成消息")
                        except Exception as e:
                            logger.error(f"发送QQ音乐完成消息失败: {e}")
                        return

                    # 检查是否为 Apple Music 下载
                    elif platform.lower() == 'applemusic' or result.get('platform') == 'AppleMusic':
                        # Apple Music 下载完成
                        # 添加调试日志
                        logger.info(f"🔍 Apple Music下载结果: {result}")
                        logger.info(f"🔍 music_type: {result.get('music_type')}")
                        logger.info(f"🔍 platform: {platform}")
                        logger.info(f"🔍 result platform: {result.get('platform')}")
                        
                        # 🔧 紧急调试：检查result中的total_size_mb
                        logger.info(f"🚨 紧急调试：检查result中的total_size_mb")
                        logger.info(f"  - result包含total_size_mb: {'total_size_mb' in result}")
                        logger.info(f"  - result.get('total_size_mb'): {result.get('total_size_mb')}")
                        logger.info(f"  - result.get('total_size'): {result.get('total_size')}")
                        logger.info(f"  - result的所有字段: {list(result.keys())}")
                        
                        # 修复：直接以URL检测为准，URL检测最准确
                        url = result.get('url', '')
                        is_album = 'album' in url
                        is_song = 'song' in url
                        
                        logger.info(f"🔍 URL检测结果: album={is_album}, song={is_song}")
                        logger.info(f"🔍 原始URL: {url}")
                        
                        if is_album:
                            # 专辑下载
                            title = "🎵 Apple Music专辑下载完成"
                            escaped_title = (title)

                            # 修复：重新统计专辑目录中的文件
                            download_path = result.get('download_path', '/downloads/AppleMusic')
                            amd_downloads_dir = os.path.join(download_path, "AM-DL downloads")
                            
                            # 获取专辑信息 - 从curl脚本获取
                            music_info = result.get('music_info', {})
                            album_name = music_info.get('album', '未知专辑')
                            artist = music_info.get('artist', '未知艺术家')
                            
                            logger.info(f"🔍 curl脚本获取的音乐信息: 艺术家='{artist}', 专辑='{album_name}'")
                            
                            # 如果curl脚本无法获取专辑信息，记录警告
                            if album_name == '未知专辑' or artist == '未知艺术家':
                                logger.warning("⚠️ curl脚本无法获取专辑信息，这不应该发生")
                                logger.warning("⚠️ 请检查curl脚本的HTML解析是否正确")
                            
                            # 只遍历专辑目录，而不是整个下载目录
                            files_info = []
                            total_size = 0
                            
                            if os.path.exists(amd_downloads_dir):
                                # 查找艺术家目录
                                artist_dir = None
                                all_items = os.listdir(amd_downloads_dir)
                                for item in all_items:
                                    item_path = os.path.join(amd_downloads_dir, item)
                                    if os.path.isdir(item_path) and item == artist:
                                        artist_dir = item_path
                                        break
                                
                                if artist_dir:
                                    # 查找专辑目录 - 改为包含匹配，更灵活
                                    album_dir = None
                                    artist_items = os.listdir(artist_dir)
                                    for item in artist_items:
                                        item_path = os.path.join(artist_dir, item)
                                        if os.path.isdir(item_path) and album_name in item:
                                            album_dir = item_path
                                            logger.info(f"✅ 找到专辑目录（包含匹配）: '{item}' 包含 '{album_name}'")
                                            break
                                    
                                    if album_dir:
                                        # 只遍历专辑目录中的文件
                                        album_files = os.listdir(album_dir)
                                        logger.info(f"🔍 遍历专辑目录: {album_dir}，找到 {len(album_files)} 个文件")
                                        
                                        for file in album_files:
                                            if file.lower().endswith(('.m4a', '.flac', '.aac', '.mp3')):
                                                file_path = os.path.join(album_dir, file)
                                                file_size = os.path.getsize(file_path)
                                                total_size += file_size
                                                
                                                files_info.append({
                                                    'name': file,
                                                    'path': file,
                                                    'size': file_size
                                                })
                                        
                                        logger.info(f"✅ 专辑目录中找到 {len(files_info)} 个音频文件")
                                    else:
                                        logger.warning(f"⚠️ 未找到包含专辑名称的目录: '{album_name}'")
                                        logger.info(f"🔍 艺术家目录 '{artist}' 中的子目录: {artist_items}")
                                        # 尝试模糊匹配
                                        for item in artist_items:
                                            item_path = os.path.join(artist_dir, item)
                                            if os.path.isdir(item_path):
                                                logger.info(f"🔍 检查目录: '{item}' vs '{album_name}'")
                                                # 如果专辑名称在目录名中，或者目录名在专辑名称中
                                                if album_name in item or item in album_name:
                                                    album_dir = item_path
                                                    logger.info(f"✅ 模糊匹配成功: '{item}' 与 '{album_name}' 相关")
                                                    break
                                        
                                        if album_dir:
                                            # 模糊匹配成功，继续处理
                                            album_files = os.listdir(album_dir)
                                            logger.info(f"🔍 遍历模糊匹配的专辑目录: {album_dir}")
                                            
                                            for file in album_files:
                                                if file.lower().endswith(('.m4a', '.flac', '.aac', '.mp3')):
                                                    file_path = os.path.join(album_dir, file)
                                                    file_size = os.path.getsize(file_path)
                                                    total_size += file_size
                                                    
                                                    files_info.append({
                                                        'name': file,
                                                        'path': file,
                                                        'size': file_size
                                                    })
                                            
                                            logger.info(f"✅ 模糊匹配目录中找到 {len(files_info)} 个音频文件")
                                        else:
                                            logger.error(f"❌ 无法找到专辑目录，请检查curl脚本的HTML解析是否正确")
                                            return {
                                                'success': False,
                                                'error': f'无法找到专辑目录: {album_name}'
                                            }
                                else:
                                    logger.warning(f"⚠️ 未找到艺术家目录: '{artist}'")
                                    logger.error(f"❌ 无法找到艺术家目录，请检查curl脚本的HTML解析是否正确")
                                    return {
                                        'success': False,
                                        'error': f'无法找到艺术家目录: {artist}'
                                    }
                            
                            # 计算总大小（MB）
                            # 修复：优先使用result中的total_size_mb，避免重复统计
                            if 'result' in locals() and result and result.get('total_size_mb'):
                                total_size_mb = result.get('total_size_mb')
                                logger.info(f"🔧 专辑下载：使用result中的total_size_mb: {total_size_mb:.2f} MB")
                            elif total_size > 0:
                                if total_size > 1000:  # 如果大于1000，可能是bytes，需要转换
                                    total_size_mb = total_size / (1024 * 1024)
                                    logger.info(f"🔧 专辑下载：检测到total_size为bytes，转换为MB: {total_size} bytes -> {total_size_mb:.2f} MB")
                                else:  # 如果小于1000，已经是MB单位
                                    total_size_mb = total_size
                                    logger.info(f"🔧 专辑下载：total_size已经是MB单位: {total_size_mb:.2f} MB")
                            else:
                                total_size_mb = 0
                            files_count = len(files_info)
                            
                            # 计算曲目数量（排除封面和歌词文件）
                            track_count = files_count
                            
                            # 编码判断 - 使用ffprobe准确检测音频编码格式
                            def detect_audio_codec(file_path):
                                """使用ffprobe检测音频文件的编码格式"""
                                try:
                                    import subprocess
                                    import json
                                    
                                    # 使用ffprobe获取音频信息
                                    cmd = [
                                        'ffprobe', '-loglevel', 'quiet', '-print_format', 'json',
                                        '-show_streams', '-select_streams', 'a:0', file_path
                                    ]
                                    
                                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                                    if result.returncode == 0:
                                        data = json.loads(result.stdout)
                                        if 'streams' in data and len(data['streams']) > 0:
                                            stream = data['streams'][0]
                                            
                                            # 获取编码格式
                                            codec_name = stream.get('codec_name', '').upper()
                                            codec_long_name = stream.get('codec_long_name', '')
                                            
                                            # 获取实际码率
                                            bit_rate = stream.get('bit_rate')
                                            if bit_rate:
                                                bit_rate_kbps = int(int(bit_rate) / 1000)
                                            else:
                                                bit_rate_kbps = None
                                            
                                            # 获取采样率
                                            sample_rate = stream.get('sample_rate')
                                            
                                            logger.info(f"🔍 ffprobe检测结果: {codec_name} - {codec_long_name} - {bit_rate_kbps}kbps - {sample_rate}Hz")
                                            
                                            return {
                                                'codec': codec_name,
                                                'long_name': codec_long_name,
                                                'bitrate_kbps': bit_rate_kbps,
                                                'sample_rate': sample_rate
                                            }
                                except Exception as e:
                                    logger.warning(f"⚠️ ffprobe检测失败: {e}")
                                
                                return None
                            
                            # 检测音频文件编码
                            m4a_files = [f for f in files_info if f['name'].lower().endswith('.m4a')]
                            aac_files = [f for f in files_info if f['name'].lower().endswith('.aac')]
                            flac_files = [f for f in files_info if f['name'].lower().endswith('.flac')]
                            mp3_files = [f for f in files_info if f['name'].lower().endswith('.mp3')]
                            
                            # 优先检测M4A文件（Apple Music主要格式，可能是AAC或ALAC）
                            detected_codec = None
                            if m4a_files:
                                # 检测第一个M4A文件的编码
                                first_m4a = m4a_files[0]
                                m4a_path = os.path.join(album_dir, first_m4a['name'])
                                detected_codec = detect_audio_codec(m4a_path)
                                
                                if detected_codec:
                                    if detected_codec['codec'] in ['ALAC', 'AAC']:
                                        audio_quality = detected_codec['codec']
                                    else:
                                        # 如果ffprobe检测到其他编码，根据文件大小推断
                                        if first_m4a['size'] > 8 * 1024 * 1024:  # 大于8MB
                                            audio_quality = "ALAC"
                                        else:
                                            audio_quality = "AAC"
                                else:
                                    # ffprobe检测失败，使用文件大小推断
                                    if first_m4a['size'] > 8 * 1024 * 1024:
                                        audio_quality = "ALAC"
                                    else:
                                        audio_quality = "AAC"
                            # 其他格式作为备选（主要是兼容其他平台）
                            elif aac_files:
                                audio_quality = "AAC"
                            elif mp3_files:
                                audio_quality = "MP3"
                            elif flac_files:
                                audio_quality = "FLAC"
                            else:
                                audio_quality = "未知"
                            
                            # 码率信息 - 使用ffprobe检测的实际码率，或使用默认值（不重复显示编码格式）
                            if detected_codec and detected_codec['bitrate_kbps']:
                                # 使用ffprobe检测的实际码率
                                bitrate = f"{detected_codec['bitrate_kbps']}kbps"
                            else:
                                # 使用默认码率
                                if audio_quality == "ALAC":
                                    bitrate = "2304kbps"  # Apple Music ALAC标准码率
                                elif audio_quality == "AAC":
                                    bitrate = "256kbps"  # Apple Music AAC标准码率
                                elif audio_quality == "FLAC":
                                    bitrate = "无损"  # FLAC格式
                                elif audio_quality == "MP3":
                                    bitrate = "320kbps"  # 标准MP3码率
                                else:
                                    bitrate = "未知"
                            
                            # 文件格式显示
                            formats = set()
                            for f in files_info:
                                if f['name'].lower().endswith('.flac'):
                                    formats.add('FLAC')
                                elif f['name'].lower().endswith('.m4a'):
                                    formats.add('M4A')
                                elif f['name'].lower().endswith('.aac'):
                                    formats.add('AAC')
                                elif f['name'].lower().endswith('.mp3'):
                                    formats.add('MP3')
                            format_display = ", ".join(formats) if formats else "未知"

                            # 确保total_size_mb有值，并添加调试信息
                            logger.info(f"🔍 专辑下载统计: total_size={total_size}, files_count={len(files_info)}")

                            size_str = f"{total_size_mb:.2f}"
                            logger.info(f"🔍 构建size_str: {total_size_mb:.2f} -> {size_str}")
                            
                            # 构建歌曲列表 - 从专辑目录中获取实际文件信息
                            song_list = ""
                            if files_info:
                                song_list = "\n🎵 **歌曲列表**:\n\n"
                                for i, file_info in enumerate(files_info, 1):
                                    if file_info['name'].lower().endswith(('.m4a', '.flac', '.aac', '.mp3')):
                                        # 保持原始文件名，包含正确的扩展名
                                        filename = file_info['name']
                                        size_mb = file_info['size'] / (1024 * 1024)
                                        size_mb_str = f"{size_mb:.1f}".replace('.', r'\.')
                                        song_list += f"{i:02d}. {filename} ({size_mb_str}MB)\n"
                                        
                                        logger.info(f"🔍 歌曲 {i}: {filename} - {size_mb:.1f}MB -> {size_mb_str}MB")
                            
                            # 使用普通文本格式，不需要转义
                            escaped_album_name = album_name
                            escaped_artist = artist
                            escaped_country = music_info.get('country', 'CN')
                            escaped_track_count = str(track_count)
                            escaped_audio_quality = audio_quality
                            escaped_format_display = format_display
                            escaped_bitrate = bitrate
                            escaped_download_path = download_path
                            
                            # 修改为普通文本格式，与网易云音乐保持一致
                            success_text = (
                                f"🎵 **Apple Music专辑下载完成**\n\n"
                                f"📀 专辑名称: {album_name}\n\n"
                                f"🎤 艺术家: {artist}\n"
                                f"🌍 地区: {music_info.get('country', 'CN')}\n"
                                f"🎼 曲目数量: {track_count} 首\n"
                                f"🎚️ 编码: {audio_quality}\n"
                                f"💾 总大小: {total_size_mb:.2f} MB\n"
                                f"🎼 文件格式: {format_display}\n"
                                f"🖼️ 码率: {bitrate}\n"
                                f"🎛️ 采样率: 44.1 kHz\n"
                                f"📂 保存位置: {download_path}"
                            )
                            
                            # 构建歌曲列表（普通文本格式）
                            if files_info:
                                success_text += "\n\n🎵 歌曲列表:\n\n"
                                for i, file_info in enumerate(files_info, 1):
                                    if file_info['name'].lower().endswith(('.m4a', '.flac', '.aac', '.mp3')):
                                        # 保持原始文件名，包含正确的扩展名
                                        filename = file_info['name']
                                        size_mb = file_info['size'] / (1024 * 1024)
                                        success_text += f"{i}. {filename} ({size_mb:.1f}MB)\n"

                        elif is_song:
                            # 单曲下载 - 修复：重新统计文件并修复消息格式
                            logger.info(f"🔍 进入Apple Music单曲下载分支")
                            title = "🎵 Apple Music 单曲下载完成"
                            
                            # 修复：重新统计下载目录中的文件
                            download_path = result.get('download_path', '/downloads/AppleMusic')
                            amd_downloads_dir = os.path.join(download_path, "AM-DL downloads")
                            
                            files_info = []
                            total_size = 0
                            
                            # 修复：优先从music_info中获取专辑和艺术家信息，用于构建正确的目录路径
                            music_info = result.get('music_info', {})
                            artist_name = music_info.get('artist', '未知艺术家')
                            album_name = music_info.get('album', '未知专辑')
                            
                            # 构建专辑目录路径 - 改为包含匹配，更灵活
                            album_dir = os.path.join(amd_downloads_dir, artist_name, album_name)
                            
                            if os.path.exists(album_dir):
                                # 只遍历专辑目录，而不是整个AM-DL downloads目录
                                logger.info(f"🔍 遍历专辑目录: {album_dir}")
                                for root, dirs, files in os.walk(album_dir):
                                    for file in files:
                                        if file.lower().endswith(('.m4a', '.flac', '.aac', '.mp3')):
                                            file_path = os.path.join(root, file)
                                            file_size = os.path.getsize(file_path)
                                            total_size += file_size
                                            
                                            # 从文件路径提取音乐信息
                                            relative_path = os.path.relpath(file_path, album_dir)
                                            files_info.append({
                                                'name': file,
                                                'path': relative_path,
                                                'size': file_size
                                            })
                            else:
                                # 如果专辑目录不存在，尝试包含匹配
                                logger.warning(f"⚠️ 专辑目录不存在: {album_dir}，尝试包含匹配")
                                
                                # 先尝试在艺术家目录中查找包含专辑名称的目录
                                artist_dir = os.path.join(amd_downloads_dir, artist_name)
                                if os.path.exists(artist_dir):
                                    artist_items = os.listdir(artist_dir)
                                    logger.info(f"🔍 艺术家目录 '{artist_name}' 中的子目录: {artist_items}")
                                    
                                    # 查找包含专辑名称的目录
                                    for item in artist_items:
                                        item_path = os.path.join(artist_dir, item)
                                        if os.path.isdir(item_path) and album_name in item:
                                            album_dir = item_path
                                            logger.info(f"✅ 找到包含匹配的专辑目录: '{item}' 包含 '{album_name}'")
                                            break
                                    
                                    if album_dir:
                                        # 遍历包含匹配的专辑目录
                                        logger.info(f"🔍 遍历包含匹配的专辑目录: {album_dir}")
                                        for root, dirs, files in os.walk(album_dir):
                                            for file in files:
                                                if file.lower().endswith(('.m4a', '.flac', '.aac', '.mp3')):
                                                    file_path = os.path.join(root, file)
                                                    file_size = os.path.getsize(file_path)
                                                    total_size += file_size
                                                    
                                                    # 从文件路径提取音乐信息
                                                    relative_path = os.path.relpath(file_path, album_dir)
                                                    files_info.append({
                                                        'name': file,
                                                        'path': relative_path,
                                                        'size': file_size
                                                    })
                                        
                                        logger.info(f"✅ 包含匹配目录中找到 {len(files_info)} 个音频文件")
                                
                                # 如果仍然没有找到，回退到整个AM-DL downloads目录
                                if not files_info:
                                    logger.warning(f"⚠️ 包含匹配也失败，回退到整个目录遍历")
                                    if os.path.exists(amd_downloads_dir):
                                        for root, dirs, files in os.walk(amd_downloads_dir):
                                            for file in files:
                                                if file.lower().endswith(('.m4a', '.flac', '.aac', '.mp3')):
                                                    file_path = os.path.join(root, file)
                                                    file_size = os.path.getsize(file_path)
                                                    total_size += file_size
                                                    
                                                    # 从文件路径提取音乐信息
                                                    relative_path = os.path.relpath(file_path, amd_downloads_dir)
                                                    files_info.append({
                                                        'name': file,
                                                        'path': relative_path,
                                                        'size': file_size
                                                    })
                            
                            # 计算总大小（MB）
                            # 修复：优先使用result中的total_size_mb，避免重复统计
                            if 'result' in locals() and result and result.get('total_size_mb'):
                                total_size_mb = result.get('total_size_mb')
                                logger.info(f"🔧 单曲下载：使用result中的total_size_mb: {total_size_mb:.2f} MB")
                            elif total_size > 0:
                                total_size_mb = total_size / (1024 * 1024)
                                logger.info(f"🔧 单曲下载：重新统计total_size={total_size} bytes -> {total_size_mb:.2f} MB")
                            else:
                                total_size_mb = 0
                                logger.warning(f"⚠️ 单曲下载：total_size为0，可能没有找到音频文件")
                            
                            # 修复：获取音频时长
                            def get_audio_duration(file_path):
                                """使用ffprobe获取音频文件时长"""
                                try:
                                    import subprocess
                                    result = subprocess.run([
                                        'ffprobe', '-loglevel', 'quiet', '-show_entries', 'format=duration',
                                        '-of', 'csv=p=0', file_path
                                    ], capture_output=True, text=True, timeout=10)
                                    
                                    if result.returncode == 0 and result.stdout.strip():
                                        duration_seconds = float(result.stdout.strip())
                                        minutes = int(duration_seconds // 60)
                                        seconds = int(duration_seconds % 60)
                                        return f"{minutes}:{seconds:02d}"
                                    else:
                                        return "未知"
                                except Exception as e:
                                    logger.warning(f"⚠️ 获取音频时长失败: {e}")
                                    return "未知"
                            
                            # 获取第一个音频文件的时长
                            duration = "未知"
                            if files_info:
                                # 修复：构建正确的文件路径
                                first_file = files_info[0]
                                
                                # 尝试多种路径构建方式
                                possible_paths = []
                                
                                # 方式1：使用当前album_dir（如果存在）
                                if 'album_dir' in locals() and album_dir and os.path.exists(album_dir):
                                    possible_paths.append(os.path.join(album_dir, first_file['name']))
                                
                                # 方式2：使用标准路径
                                standard_album_dir = os.path.join(amd_downloads_dir, artist_name, album_name)
                                if os.path.exists(standard_album_dir):
                                    possible_paths.append(os.path.join(standard_album_dir, first_file['name']))
                                
                                # 方式3：根据files_info中的path信息构建
                                if first_file.get('path'):
                                    if os.path.isabs(first_file['path']):
                                        # 如果path是绝对路径
                                        possible_paths.append(first_file['path'])
                                    else:
                                        # 如果path是相对路径
                                        possible_paths.append(os.path.join(amd_downloads_dir, first_file['path']))
                                
                                # 方式4：直接在amd_downloads_dir中查找
                                for root, dirs, files in os.walk(amd_downloads_dir):
                                    if first_file['name'] in files:
                                        possible_paths.append(os.path.join(root, first_file['name']))
                                        break
                                
                                # 尝试每种路径，找到第一个存在的文件
                                first_file_path = None
                                for path in possible_paths:
                                    if os.path.exists(path):
                                        first_file_path = path
                                        logger.info(f"✅ 找到音频文件: {first_file_path}")
                                        break
                                
                                if first_file_path:
                                    duration = get_audio_duration(first_file_path)
                                    logger.info(f"🔍 获取音频时长: {duration}")
                                else:
                                    logger.warning(f"⚠️ 无法找到音频文件: {first_file['name']}")
                                    logger.warning(f"⚠️ 尝试的路径: {possible_paths}")
                            
                            # 音质判断
                            if any(f['name'].lower().endswith('.flac') for f in files_info):
                                audio_quality = "无损"
                            elif any(f['name'].lower().endswith('.m4a') for f in files_info):
                                audio_quality = "无损" if total_size_mb > 20 else "高质量"
                            else:
                                audio_quality = "高质量"
                            
                            # 文件格式显示
                            formats = set()
                            for f in files_info:
                                if f['name'].lower().endswith('.flac'):
                                    formats.add('FLAC')
                                elif f['name'].lower().endswith('.m4a'):
                                    formats.add('M4A')
                                elif f['name'].lower().endswith('.aac'):
                                    formats.add('AAC')
                                elif f['name'].lower().endswith('.mp3'):
                                    formats.add('MP3')
                            
                            format_display = ", ".join(formats) if formats else "未知"
                            
                            # 构建成功消息 - 使用MarkdownV2格式，与网易云音乐保持一致
                            # 优先从curl脚本获取音乐信息，如果没有则从文件名提取
                            music_info = result.get('music_info', {})
                            if music_info and music_info.get('title') != '未知标题':
                                # 使用curl脚本获取的信息
                                music_title = music_info.get('title', '未知标题')
                                artist = music_info.get('artist', '未知艺术家')
                                album = music_info.get('album', '未知专辑')
                            else:
                                # 从文件名提取音乐信息
                                first_file = files_info[0]
                                file_name = first_file['name']
                                # 移除文件扩展名
                                music_title = file_name.replace('.m4a', '').replace('.flac', '').replace('.aac', '').replace('.mp3', '')
                                artist = '未知艺术家'
                                album = '未知专辑'
                            
                            # 音质判断 - 修复：显示正确的Apple Music音质（不重复显示编码格式）
                            if any(f['name'].lower().endswith('.flac') for f in files_info):
                                audio_quality = "FLAC"
                                bitrate = "无损"
                            elif any(f['name'].lower().endswith('.m4a') for f in files_info):
                                audio_quality = "ALAC"  # Apple Music使用ALAC格式
                                bitrate = "2304kbps"  # Apple Music ALAC标准码率
                            elif any(f['name'].lower().endswith('.aac') for f in files_info):
                                audio_quality = "AAC"
                                bitrate = "256kbps"  # Apple Music AAC标准码率
                            else:
                                audio_quality = "MP3"
                                bitrate = "320kbps"  # 标准MP3码率
                            
                            # 修改为普通文本格式，与专辑下载保持一致
                            success_text = (
                                f"🎵 **Apple Music 单曲下载完成**\n\n"
                                f"🎵 音乐: {music_title}\n"
                                f"🎤 艺术家: {artist}\n"
                                f"📀 专辑: {album}\n"
                                f"💾 大小: {total_size_mb:.2f}MB\n"
                                f"🖼️ 码率: {bitrate}\n"
                                f"🎚️ 编码: {audio_quality}\n"
                                f"🎛️ 采样率: 44.1 kHz\n"
                                f"⏱️ 时长: {duration}\n"
                                f"📂 保存位置: {download_path}"
                            )
                        
                        else:
                            # 其他情况（未知类型）
                            logger.warning(f"⚠️ Apple Music下载类型未知: URL={url}, music_type={result.get('music_type')}")
                            title = "🎵 Apple Music 下载完成"
                            escaped_title = (title)
                            
                            # 构建通用成功消息
                            success_text = (
                                f"{escaped_title}\n\n"
                                f"🔗 **链接**: `{(url)}`\n"
                                f"📂 **保存位置**: `{(download_path)}`"
                            )

                        try:
                            # 使用普通文本格式，与网易云音乐保持一致
                            await status_message.edit_text(success_text, parse_mode=None)
                            logger.info("Apple Music 下载完成消息发送成功")
                        except Exception as e:
                            logger.error(f"发送 Apple Music 完成消息失败: {e}")
                            logger.error(f"错误详情: {type(e).__name__}: {str(e)}")
                            
                            # 回退消息
                            if is_album:
                                fallback_text = (
                                    f"✅ Apple Music专辑下载完成\n\n"
                                    f"📀 专辑: {album_name}\n"
                                    f"🎤 艺术家: {artist}\n"
                                    f"🎼 曲目数量: {track_count} 首\n"
                                    f"💾 总大小: {total_size_mb:.2f} MB\n"
                                    f"📁 下载完成，共 {len(files_info)} 个文件\n"
                                    f"📂 保存位置: {download_path}"
                                )
                            elif is_song:
                                fallback_text = (
                                    f"✅ Apple Music单曲下载完成\n\n"
                                    f"🎵 音乐: {music_info.get('title', '未知标题')}\n"
                                    f"🎤 艺术家: {artist}\n"
                                    f"📀 专辑: {album_name}\n"
                                    f"💾 大小: {total_size_mb:.2f} MB\n"
                                    f"📁 下载完成，共 {len(files_info)} 个文件\n"
                                    f"📂 保存位置: {download_path}"
                                )
                            else:
                                fallback_text = f"✅ Apple Music下载完成\n📁 下载完成，共 {len(files_info)} 个文件"
                            
                            await status_message.edit_text(fallback_text, parse_mode=None)
                        return

                    # 检查是否为YouTube Music下载
                    elif platform.lower() == 'youtubemusic' or result.get('platform') == 'YouTubeMusic':
                        # YouTube Music下载完成
                        if result.get('album_name'):
                            # 专辑下载 - 参考网易云音乐格式
                            title = "🎵 YouTube Music专辑下载完成"
                            
                            album_name = result.get('album_name', '未知专辑')
                            creator = result.get('creator', '未知艺术家')
                            total_songs = result.get('total_songs', 0)
                            downloaded_songs = result.get('downloaded_songs', 0)
                            failed_songs = result.get('failed_songs', 0)
                            total_size = result.get('total_size_mb', 0)
                            download_path = result.get('download_path', '未知路径')
                            quality = result.get('quality', 'best')
                            
                            # 获取音质信息
                            if quality == 'best':
                                quality_info = {'name': 'M4A无损', 'bitrate': 'AAC/256kbps'}
                            else:
                                quality_info = {'name': f'M4A {quality}', 'bitrate': 'Variable'}
                            
                            # 获取歌曲列表
                            songs = result.get('songs', [])
                            
                            success_text = (
                                f"{title}\n\n"
                                f"📀 专辑名称: {album_name}\n\n"
                                f"🎤 艺术家：{creator}\n"
                                f"🎼 曲目数量: {downloaded_songs} 首\n"
                                f"🎚️ 音频质量: {quality_info['name']}\n"
                                f"💾 总大小: {total_size:.2f} MB\n"
                                f"📊 码率: {quality_info['bitrate']}\n"
                                f"📂 保存位置: {download_path}"
                            )
                            
                            # 显示歌曲列表（限制显示数量以避免消息过长）
                            if songs:
                                success_text += "\n\n🎵 歌曲列表:\n"
                                for i, song in enumerate(songs[:10], 1):  # 只显示前10首
                                    song_title = song.get('title', '未知歌曲')
                                    file_size_mb = round(song.get('file_size', 0) / (1024 * 1024), 2)
                                    success_text += f"{i:02d}. {song_title}.m4a ({file_size_mb}MB)\n"
                                
                                if len(songs) > 10:
                                    success_text += f"... 还有 {len(songs) - 10} 首歌曲"
                            
                            # 如果有失败的歌曲，添加失败信息
                            if failed_songs > 0:
                                success_text += f"\n\n❌ 下载失败: {failed_songs} 首"
                            
                        elif result.get('playlist_name'):
                            # 播放列表下载 - 参考网易云音乐格式
                            title = "🎵 YouTube Music播放列表下载完成"
                            
                            playlist_name = result.get('playlist_name', '未知播放列表')
                            creator = result.get('creator', '未知创建者')
                            total_songs = result.get('total_songs', 0)
                            downloaded_songs = result.get('downloaded_songs', 0)
                            failed_songs = result.get('failed_songs', 0)
                            total_size = result.get('total_size_mb', 0)
                            download_path = result.get('download_path', '未知路径')
                            quality = result.get('quality', 'best')
                            
                            # 获取音质信息
                            if quality == 'best':
                                quality_info = {'name': 'M4A无损', 'bitrate': 'AAC/256kbps'}
                            else:
                                quality_info = {'name': f'M4A {quality}', 'bitrate': 'Variable'}
                            
                            # 获取歌曲列表
                            songs = result.get('songs', [])
                            
                            success_text = (
                                f"{title}\n\n"
                                f"📋 播放列表名称: {playlist_name}\n"
                                f"🎵 歌曲数量: {total_songs} 首\n"
                                f"✅ 成功下载: {downloaded_songs} 首\n"
                                f"❌ 失败数量: {failed_songs} 首\n"
                                f"💾 总大小: {total_size:.1f} MB\n"
                                f"📂 保存位置: {download_path}"
                            )
                            
                            # 显示歌曲列表（限制显示数量以避免消息过长）
                            if songs:
                                success_text += "\n\n🎵 歌曲列表:\n"
                                for i, song in enumerate(songs[:10], 1):  # 只显示前10首
                                    song_title = song.get('title', '未知歌曲')
                                    file_size_mb = round(song.get('file_size', 0) / (1024 * 1024), 2)
                                    success_text += f"{i:02d}. {song_title}.m4a ({file_size_mb}MB)\n"
                                
                                if len(songs) > 10:
                                    success_text += f"... 还有 {len(songs) - 10} 首歌曲"
                            
                        else:
                            # 单曲下载
                            title = "🎵 YouTube Music单曲下载完成"
                            
                            song_title = result.get('song_title', '未知歌曲')
                            song_artist = result.get('song_artist', '未知艺术家')
                            filename = result.get('filename', '未知文件')
                            size_mb = result.get('size_mb', 0)
                            download_path = result.get('download_path', '未知路径')
                            quality = result.get('quality', 'best')
                            format_type = result.get('format', 'M4A')
                            duration = result.get('duration', 0)
                            
                            # 获取音质信息
                            if quality == 'best':
                                quality_info = {'name': f'{format_type}无损', 'bitrate': 'AAC/256kbps'}
                            else:
                                quality_info = {'name': f'{format_type} {quality}', 'bitrate': 'Variable'}
                            
                            # 格式化时长
                            duration_str = "未知"
                            if duration > 0:
                                minutes = int(duration // 60)
                                seconds = int(duration % 60)
                                duration_str = f"{minutes:02d}:{seconds:02d}"
                            
                            success_text = (
                                f"{title}\n\n"
                                f"🎵 歌曲: {song_title}\n"
                                f"🎤 艺术家: {song_artist}\n"
                                f"🎚️ 音质: {quality_info['name']}\n"
                                f"⏱️ 时长: {duration_str}\n"
                                f"💾 大小: {size_mb:.2f} MB\n"
                                f"📂 保存位置: {download_path}"
                            )
                        
                        # 发送完成消息
                        try:
                            await status_message.edit_text(success_text, parse_mode=None)
                            logger.info("YouTube Music 下载完成消息发送成功")
                        except Exception as e:
                            logger.error(f"发送 YouTube Music 完成消息失败: {e}")
                        return

                    # 检查是否为B站合集下载
                    video_type = result.get('video_type', '')
                    count = result.get('count', 0)
                    playlist_title = result.get('playlist_title', '')

                    if video_type == 'playlist' and count > 1 and 'Bilibili' in platform:
                        # B站合集下载完成，使用特殊格式
                        # 使用result中的文件信息，而不是遍历目录
                        import os

                        try:
                            # 检查result中是否有文件信息
                            if result.get('is_playlist') and result.get('files'):
                                # 使用yt-dlp记录的文件信息
                                file_info_list = result['files']

                                # 构建文件名列表
                                file_list = []
                                for i, file_info in enumerate(file_info_list, 1):
                                    filename = file_info['filename']
                                    file_list.append(f"  {i:02d}. {filename}")

                                # 使用已计算的总文件大小
                                total_size = result.get('total_size_mb', 0)
                            else:
                                # 回退方案：如果result中没有文件信息，使用目录遍历
                                logger.warning("⚠️ result中没有文件信息，使用目录遍历回退方案")

                                def get_files_from_current_playlist(download_path, result, file_extensions=None):
                                    """只从本次下载的播放列表目录中获取文件"""
                                    if file_extensions is None:
                                        file_extensions = ['.mp4', '.mkv', '.webm', '.avi', '.mov']

                                    download_dir = Path(download_path)
                                    video_files = []

                                    # 检查是否为播放列表下载
                                    playlist_title = result.get('playlist_title')
                                    logger.info(f"🔍 检查播放列表标题: {playlist_title}")

                                    if playlist_title:
                                        # 如果是播放列表，只遍历对应的子目录
                                        playlist_dir = download_dir / playlist_title
                                        logger.info(f"🎯 只遍历本次下载的播放列表目录: {playlist_dir}")

                                        if playlist_dir.exists():
                                            # 只遍历播放列表目录中的文件
                                            for file_path in playlist_dir.glob("*"):
                                                if file_path.is_file() and file_path.suffix.lower() in file_extensions:
                                                    video_files.append(file_path)
                                                    logger.info(f"✅ 找到文件: {file_path}")
                                        else:
                                            logger.warning(f"⚠️ 播放列表目录不存在: {playlist_dir}")
                                            # 回退方案：尝试遍历根目录
                                            logger.info(f"🔄 回退到根目录遍历: {download_dir}")
                                            for file_path in download_dir.glob("*"):
                                                if file_path.is_file() and file_path.suffix.lower() in file_extensions:
                                                    video_files.append(file_path)
                                                    logger.info(f"✅ 在根目录找到文件: {file_path}")
                                    else:
                                        # 如果不是播放列表，只遍历根目录
                                        logger.info(f"🎯 单视频下载，只遍历根目录: {download_dir}")
                                        for file_path in download_dir.glob("*"):
                                            if file_path.is_file() and file_path.suffix.lower() in file_extensions:
                                                video_files.append(file_path)
                                                logger.info(f"✅ 找到文件: {file_path}")

                                    # 如果仍然没有找到文件，尝试递归遍历
                                    if not video_files:
                                        logger.warning("⚠️ 未找到文件，尝试递归遍历所有子目录")
                                        for file_path in download_dir.rglob("*"):
                                            if file_path.is_file() and file_path.suffix.lower() in file_extensions:
                                                video_files.append(file_path)
                                                logger.info(f"✅ 递归找到文件: {file_path}")

                                    # 按文件名排序
                                    video_files.sort(key=lambda x: x.name)
                                    logger.info(f"📊 总共找到 {len(video_files)} 个文件")

                                    return video_files

                                video_files = get_files_from_current_playlist(download_path, result)

                                # 构建文件名列表
                                file_list = []
                                for i, file_path in enumerate(video_files, 1):
                                    filename = file_path.name
                                    file_list.append(f"  {i:02d}. {filename}")

                                # 计算总文件大小
                                total_size = sum(f.stat().st_size for f in video_files) / (1024 * 1024)

                            # 获取分辨率信息
                            if result.get('is_playlist') and result.get('files'):
                                # 使用result中的分辨率信息
                                resolutions = set()
                                for file_info in file_info_list:
                                    resolution = file_info.get('resolution', '未知')
                                    if resolution != '未知':
                                        resolutions.add(resolution)
                                resolution_str = ', '.join(sorted(resolutions)) if resolutions else '未知'
                            else:
                                # 回退方案：使用ffprobe检测分辨率
                                resolutions = set()
                                for file_path in video_files[:3]:  # 只检查前3个文件
                                    try:
                                        import subprocess
                                        result_cmd = subprocess.run([
                                            'ffprobe', '-loglevel', 'quiet', '-select_streams', 'v:0',
                                            '-show_entries', 'stream=width,height', '-of', 'csv=p=0',
                                            str(file_path)
                                        ], capture_output=True, text=True)
                                        if result_cmd.returncode == 0:
                                            width, height = result_cmd.stdout.strip().split(',')
                                            resolutions.add(f"{width}x{height}")
                                    except:
                                        pass
                                resolution_str = ', '.join(sorted(resolutions)) if resolutions else '未知'

                            # 检查是否有文件列表，如果没有则尝试其他方式获取文件名
                            if not file_list:
                                logger.warning("⚠️ 文件列表为空，尝试其他方式获取文件名")
                                # 尝试从result中获取文件名信息
                                if result.get('filename'):
                                    file_list = [f"  {result['filename']}"]
                                elif result.get('files'):
                                    # 从result.files中获取文件名
                                    for i, file_info in enumerate(result['files'], 1):
                                        filename = file_info.get('filename', f'文件{i}')
                                        file_list.append(f"  {i:02d}. {filename}")
                                else:
                                    # 最后的回退方案：使用display_filename
                                    if display_filename:
                                        file_list = [f"  {display_filename}"]

                            # 构建完成消息
                            if file_list:
                                completion_text = f"""🎬 视频下载完成

📝 文件名:
{chr(10).join(file_list)}

💾 文件大小: {total_size:.2f} MB
📊 集数: {count} 集
📂 保存位置: {download_path}"""
                            else:
                                # 如果仍然没有文件名，使用简化格式
                                completion_text = f"""🎬 视频下载完成

💾 文件大小: {total_size:.2f} MB
📊 集数: {count} 集
📂 保存位置: {download_path}"""

                        except Exception as e:
                            logger.error(f"构建B站合集完成信息时出错: {e}")
                            # 如果出错，使用默认格式
                            completion_text = f"""🎬 视频下载完成

📝 文件名: {display_filename}
💾 文件大小: {size_mb:.2f} MB
📊 集数: {count} 集
📂 保存位置: {download_path}"""
                    else:
                        # 单视频下载完成，显示完整信息包括分辨率
                        completion_text = f"""🎬 视频下载完成

📝 文件名: {display_filename}
💾 文件大小: {size_mb:.2f} MB
🖼️ 分辨率: {final_resolution}
📂 保存位置: {download_path}"""

                    await status_message.edit_text(completion_text, parse_mode=None)
                    logger.info("显示下载完成信息")
                except Exception as e:
                    if "Flood control" in str(e):
                        logger.warning(
                            "下载完成消息遇到Flood control，等待5秒后重试..."
                        )
                        await asyncio.sleep(5)
                        try:
                            await status_message.edit_text(completion_text, parse_mode=None)
                        except Exception as retry_error:
                            logger.error(
                                f"重试发送下载完成消息失败: {retry_error}"
                            )
                    else:
                        logger.error(f"发送下载完成消息失败: {e}")
        else:
            # 确保result不为None
            if result:
                error_msg = result.get("error", "未知错误")
            else:
                error_msg = "下载任务返回空结果"

            try:
                await status_message.edit_text(
                    f"❌ 下载失败: `{(error_msg)}`",
                    parse_mode=None,
                )
            except Exception as retry_error:
                logger.error(f"重试发送下载失败消息失败: {retry_error}")
            return


    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /start 命令 - 显示帮助信息"""
        user_id = update.message.from_user.id

        # 权限检查
        if not self._check_user_permission(user_id):
            await update.message.reply_text("❌ 您没有权限使用此机器人")
            return

        welcome_message = (
            "🤖 <b>欢迎使用SaveXTube下载机器人！</b>\n\n"
            "你可以发送链接或使用命令操作。\n"
            "输入 /help 查看完整功能。"
        )
        await update.message.reply_text(welcome_message, parse_mode="HTML")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /help 命令 - 显示详细帮助信息"""
        user_id = update.message.from_user.id

        # 权限检查
        if not self._check_user_permission(user_id):
            await update.message.reply_text("❌ 您没有权限使用此机器人")
            return

        help_message = (
            "🤖 <b>SaveXTube 机器人帮助</b>\n\n"

            "📺 <b>支持的平台：</b>\n"
            "• 🐦 X (Twitter)\n"
            "• 🎬 YouTube（视频/播放列表/频道）\n"
            "• 📺 Bilibili（视频/多P/合集/收藏夹）\n"
            "• 🔞 Xvideos / Pornhub\n"
            "• 📸 Instagram / TikTok\n"
            "• 🎵 抖音 / 快手\n"
            "• 📖 小红书 / 微博\n"
            "• 📰 Telegraph / Facebook\n"
            "• 🎵 网易云音乐（歌曲/专辑/歌单）\n\n"

            "🚀 <b>使用方法：</b>\n"
            "1. 直接发送视频链接即可开始下载\n"
            "2. 支持批量链接（一次发送多个链接）\n"
            "3. 支持播放列表下载\n"
            "4. 支持媒体文件转发和处理\n\n"

            "⚙️ <b>可用命令：</b>\n"
            "• <b>/start</b> - 🏁 显示欢迎信息\n"
            "• <b>/help</b> - 📖 显示此帮助信息\n"
            "• <b>/status</b> - 📊 查看下载统计和系统状态\n"
            "• <b>/version</b> - 🔧 查看版本信息\n"
            "• <b>/settings</b> - 🛠 功能设置面板\n"
            "• <b>/favsub</b> - 📚 B站收藏夹订阅管理\n"
            "• <b>/cancel</b> - ❌ 取消当前下载任务\n"
            "• <b>/cleanup</b> - 🧹 清理重复文件\n"
            "• <b>/reboot</b> - 🔄 重启机器人（管理员）\n\n"

            "✨ <b>核心特性：</b>\n"
            "• 🔄 实时下载进度显示\n"
            "• 🎯 智能格式选择和多重备用方案\n"
            "• 🔧 自动格式转换（webm → mp4）\n"
            "• 📁 按平台智能分类存储\n"
            "• 🔒 支持 NSFW 内容下载\n"
            "• 🆔 唯一文件名，避免覆盖\n"
            "• 📋 批量下载（播放列表/频道/合集）\n"
            "• 🎵 YouTube音频模式（MP3提取）\n"
            "• 💬 B站弹幕下载\n"
            "• 🔄 B站收藏夹自动订阅更新\n"
            "• 📱 自动压缩大文件适配Telegram\n"
            "• 💾 断点续传和错误重试\n\n"

            "🛠 <b>设置选项：</b>\n"
            "• 自动播放列表下载\n"
            "• YouTube视频ID标签\n"
            "• B站弹幕下载\n"
            "• YouTube音频模式\n"
            "• UGC播放列表处理\n"
            "• 缩略图下载\n"
            "• 字幕下载\n\n"

            "💡 <b>使用技巧：</b>\n"
            "• 发送播放列表链接可批量下载\n"
            "• 使用 /settings 调整下载偏好\n"
            "• 大文件会自动分割发送\n"
            "• 支持多种视频质量选择\n"
            "• 可以转发其他聊天中的媒体文件\n\n"

            "❓ <b>遇到问题？</b>\n"
            "• 检查链接是否有效\n"
            "• 使用 /status 查看系统状态\n"
            "• 某些地区内容可能受限\n"
            "• 大文件下载需要更多时间"
        )

        await update.message.reply_text(help_message, parse_mode="HTML")

    async def settings_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """/settings 命令，显示功能设置按钮"""
        user_id = update.message.from_user.id

        # 权限检查
        if not self._check_user_permission(user_id):
            await update.message.reply_text("❌ 您没有权限使用此机器人")
            return

        # B站多P自动下载按钮
        auto_playlist_current = self.bilibili_auto_playlist
        auto_playlist_text = "✅ B站多P自动下载：开启" if auto_playlist_current else "❌ B站多P自动下载：关闭"
        auto_playlist_button = InlineKeyboardButton(auto_playlist_text, callback_data="toggle_autop")

        # 油管自动添加标签按钮
        id_tags_current = self.youtube_id_tags
        id_tags_text = "✅ 油管自动添加标签：开启" if id_tags_current else "❌ 油管自动添加标签：关闭"
        id_tags_button = InlineKeyboardButton(id_tags_text, callback_data="toggle_id_tags")

        # YouTube音频模式按钮
        audio_mode_current = self.youtube_audio_mode
        audio_mode_text = "✅ 油管音频模式：开启" if audio_mode_current else "❌ 油管音频模式：关闭"
        audio_mode_button = InlineKeyboardButton(audio_mode_text, callback_data="toggle_audio_mode")

        # B站UGC播放列表自动下载按钮
        ugc_playlist_current = self.bilibili_ugc_playlist
        ugc_playlist_text = "✅ B站UGC下载：开启" if ugc_playlist_current else "❌ B站UGC下载：关闭"
        ugc_playlist_button = InlineKeyboardButton(ugc_playlist_text, callback_data="toggle_ugc_playlist")

        # B站弹幕下载按钮
        danmaku_current = self.bilibili_danmaku_download
        danmaku_text = "✅ B站弹幕下载：开启" if danmaku_current else "❌ B站弹幕下载：关闭"
        danmaku_button = InlineKeyboardButton(danmaku_text, callback_data="toggle_danmaku")

        # YouTube封面下载按钮
        thumbnail_current = self.youtube_thumbnail_download
        thumbnail_text = "✅ 油管封面下载：开启" if thumbnail_current else "❌ 油管封面下载：关闭"
        thumbnail_button = InlineKeyboardButton(thumbnail_text, callback_data="toggle_thumbnail")

        # YouTube字幕下载按钮
        subtitle_current = self.youtube_subtitle_download
        subtitle_text = "✅ 油管字幕下载：开启" if subtitle_current else "❌ 油管字幕下载：关闭"
        subtitle_button = InlineKeyboardButton(subtitle_text, callback_data="toggle_subtitle")

        # YouTube时间戳命名按钮
        timestamp_current = self.youtube_timestamp_naming
        timestamp_text = "✅ 油管时间戳命名：开启" if timestamp_current else "❌ 油管时间戳命名：关闭"
        timestamp_button = InlineKeyboardButton(timestamp_text, callback_data="toggle_timestamp")

        # B站封面下载按钮
        bilibili_thumbnail_current = self.bilibili_thumbnail_download
        bilibili_thumbnail_text = "✅ B站封面下载：开启" if bilibili_thumbnail_current else "❌ B站封面下载：关闭"
        bilibili_thumbnail_button = InlineKeyboardButton(bilibili_thumbnail_text, callback_data="toggle_bilibili_thumbnail")

        # 网易云歌词合并按钮
        lyrics_merge_current = self.netease_lyrics_merge
        lyrics_merge_text = "✅ 网易云歌词合并：开启" if lyrics_merge_current else "❌ 网易云歌词合并：关闭"
        lyrics_merge_button = InlineKeyboardButton(lyrics_merge_text, callback_data="toggle_lyrics_merge")

        # 网易云artist下载按钮
        artist_download_current = self.netease_artist_download
        artist_download_text = "✅ 网易云artist下载：开启" if artist_download_current else "❌ 网易云artist下载：关闭"
        artist_download_button = InlineKeyboardButton(artist_download_text, callback_data="toggle_artist_download")

        # 网易云cover下载按钮
        cover_download_current = self.netease_cover_download
        cover_download_text = "✅ 网易云cover下载：开启" if cover_download_current else "❌ 网易云cover下载：关闭"
        cover_download_button = InlineKeyboardButton(cover_download_text, callback_data="toggle_cover_download")

        reply_markup = InlineKeyboardMarkup([
            [auto_playlist_button],
            [id_tags_button],
            [audio_mode_button],
            [ugc_playlist_button],
            [danmaku_button],
            [thumbnail_button],
            [subtitle_button],
            [timestamp_button],
            [bilibili_thumbnail_button],
            [lyrics_merge_button],
            [artist_download_button],
            [cover_download_button]
        ])
        await update.message.reply_text("🛠 功能设置", reply_markup=reply_markup)

    async def settings_button_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        query = update.callback_query
        user_id = query.from_user.id

        # 权限检查
        if not self._check_user_permission(user_id):
            await query.answer("❌ 您没有权限使用此机器人")
            return

        callback_data = query.data

        if callback_data == "toggle_autop":
            # 切换多P自动下载
            current = self.bilibili_auto_playlist
            self.bilibili_auto_playlist = not current
            await self._save_config_async()

            # 重新生成四个按钮
            auto_playlist_text = "✅ B站多P自动下载：开启" if not current else "❌ B站多P自动下载：关闭"
            auto_playlist_button = InlineKeyboardButton(auto_playlist_text, callback_data="toggle_autop")

            id_tags_text = "✅ 油管自动添加标签：开启" if self.youtube_id_tags else "❌ 油管自动添加标签：关闭"
            id_tags_button = InlineKeyboardButton(id_tags_text, callback_data="toggle_id_tags")

            audio_mode_text = "✅ 油管音频模式：开启" if self.youtube_audio_mode else "❌ 油管音频模式：关闭"
            audio_mode_button = InlineKeyboardButton(audio_mode_text, callback_data="toggle_audio_mode")

            ugc_playlist_text = "✅ B站UGC下载：开启" if self.bilibili_ugc_playlist else "❌ B站UGC下载：关闭"
            ugc_playlist_button = InlineKeyboardButton(ugc_playlist_text, callback_data="toggle_ugc_playlist")

            danmaku_text = "✅ B站弹幕下载：开启" if self.bilibili_danmaku_download else "❌ B站弹幕下载：关闭"
            danmaku_button = InlineKeyboardButton(danmaku_text, callback_data="toggle_danmaku")

            thumbnail_text = "✅ 油管封面下载：开启" if self.youtube_thumbnail_download else "❌ 油管封面下载：关闭"
            thumbnail_button = InlineKeyboardButton(thumbnail_text, callback_data="toggle_thumbnail")

            subtitle_text = "✅ 油管字幕下载：开启" if self.youtube_subtitle_download else "❌ 油管字幕下载：关闭"
            subtitle_button = InlineKeyboardButton(subtitle_text, callback_data="toggle_subtitle")

            timestamp_text = "✅ 油管时间戳命名：开启" if self.youtube_timestamp_naming else "❌ 油管时间戳命名：关闭"
            timestamp_button = InlineKeyboardButton(timestamp_text, callback_data="toggle_timestamp")

            bilibili_thumbnail_text = "✅ B站封面下载：开启" if self.bilibili_thumbnail_download else "❌ B站封面下载：关闭"
            bilibili_thumbnail_button = InlineKeyboardButton(bilibili_thumbnail_text, callback_data="toggle_bilibili_thumbnail")

            lyrics_merge_text = "✅ 网易云歌词合并：开启" if self.netease_lyrics_merge else "❌ 网易云歌词合并：关闭"
            lyrics_merge_button = InlineKeyboardButton(lyrics_merge_text, callback_data="toggle_lyrics_merge")

            # 网易云artist下载按钮
            artist_download_text = "✅ 网易云artist下载：开启" if self.netease_artist_download else "❌ 网易云artist下载：关闭"
            artist_download_button = InlineKeyboardButton(artist_download_text, callback_data="toggle_artist_download")

            # 网易云cover下载按钮
            cover_download_text = "✅ 网易云cover下载：开启" if self.netease_cover_download else "❌ 网易云cover下载：关闭"
            cover_download_button = InlineKeyboardButton(cover_download_text, callback_data="toggle_cover_download")

            reply_markup = InlineKeyboardMarkup([
                [auto_playlist_button],
                [id_tags_button],
                [audio_mode_button],
                [ugc_playlist_button],
                [danmaku_button],
                [thumbnail_button],
                [subtitle_button],
                [timestamp_button],
                [bilibili_thumbnail_button],
                [lyrics_merge_button],
                [artist_download_button],
                [cover_download_button]
            ])
            await query.edit_message_reply_markup(reply_markup=reply_markup)
            await query.answer("已切换B站多P自动下载状态")

        elif callback_data == "toggle_id_tags":
            # 切换ID标签
            current = self.youtube_id_tags
            self.youtube_id_tags = not current
            await self._save_config_async()

            # 重新生成四个按钮
            auto_playlist_text = "✅ B站多P自动下载：开启" if self.bilibili_auto_playlist else "❌ B站多P自动下载：关闭"
            auto_playlist_button = InlineKeyboardButton(auto_playlist_text, callback_data="toggle_autop")

            id_tags_text = "✅ 油管自动添加标签：开启" if self.youtube_id_tags else "❌ 油管自动添加标签：关闭"
            id_tags_button = InlineKeyboardButton(id_tags_text, callback_data="toggle_id_tags")

            audio_mode_text = "✅ 油管音频模式：开启" if self.youtube_audio_mode else "❌ 油管音频模式：关闭"
            audio_mode_button = InlineKeyboardButton(audio_mode_text, callback_data="toggle_audio_mode")

            ugc_playlist_text = "✅ B站UGC下载：开启" if self.bilibili_ugc_playlist else "❌ B站UGC下载：关闭"
            ugc_playlist_button = InlineKeyboardButton(ugc_playlist_text, callback_data="toggle_ugc_playlist")

            danmaku_text = "✅ B站弹幕下载：开启" if self.bilibili_danmaku_download else "❌ B站弹幕下载：关闭"
            danmaku_button = InlineKeyboardButton(danmaku_text, callback_data="toggle_danmaku")

            thumbnail_text = "✅ 油管封面下载：开启" if self.youtube_thumbnail_download else "❌ 油管封面下载：关闭"
            thumbnail_button = InlineKeyboardButton(thumbnail_text, callback_data="toggle_thumbnail")

            subtitle_text = "✅ 油管字幕下载：开启" if self.youtube_subtitle_download else "❌ 油管字幕下载：关闭"
            subtitle_button = InlineKeyboardButton(subtitle_text, callback_data="toggle_subtitle")

            timestamp_text = "✅ 油管时间戳命名：开启" if self.youtube_timestamp_naming else "❌ 油管时间戳命名：关闭"
            timestamp_button = InlineKeyboardButton(timestamp_text, callback_data="toggle_timestamp")

            bilibili_thumbnail_text = "✅ B站封面下载：开启" if self.bilibili_thumbnail_download else "❌ B站封面下载：关闭"
            bilibili_thumbnail_button = InlineKeyboardButton(bilibili_thumbnail_text, callback_data="toggle_bilibili_thumbnail")

            lyrics_merge_text = "✅ 网易云歌词合并：开启" if self.netease_lyrics_merge else "❌ 网易云歌词合并：关闭"
            lyrics_merge_button = InlineKeyboardButton(lyrics_merge_text, callback_data="toggle_lyrics_merge")

            # 网易云artist下载按钮
            artist_download_text = "✅ 网易云artist下载：开启" if self.netease_artist_download else "❌ 网易云artist下载：关闭"
            artist_download_button = InlineKeyboardButton(artist_download_text, callback_data="toggle_artist_download")

            # 网易云cover下载按钮
            cover_download_text = "✅ 网易云cover下载：开启" if self.netease_cover_download else "❌ 网易云cover下载：关闭"
            cover_download_button = InlineKeyboardButton(cover_download_text, callback_data="toggle_cover_download")

            reply_markup = InlineKeyboardMarkup([
                [auto_playlist_button],
                [id_tags_button],
                [audio_mode_button],
                [ugc_playlist_button],
                [danmaku_button],
                [thumbnail_button],
                [subtitle_button],
                [timestamp_button],
                [bilibili_thumbnail_button],
                [lyrics_merge_button],
                [artist_download_button],
                [cover_download_button]
            ])
            await query.edit_message_reply_markup(reply_markup=reply_markup)
            await query.answer("已切换油管自动添加标签状态")

        elif callback_data == "toggle_danmaku":
            # 切换B站弹幕下载
            current = self.bilibili_danmaku_download
            self.bilibili_danmaku_download = not current
            await self._save_config_async()

            # 重新生成四个按钮
            auto_playlist_text = "✅ B站多P自动下载：开启" if self.bilibili_auto_playlist else "❌ B站多P自动下载：关闭"
            auto_playlist_button = InlineKeyboardButton(auto_playlist_text, callback_data="toggle_autop")

            id_tags_text = "✅ 油管自动添加标签：开启" if self.youtube_id_tags else "❌ 油管自动添加标签：关闭"
            id_tags_button = InlineKeyboardButton(id_tags_text, callback_data="toggle_id_tags")

            audio_mode_text = "✅ 油管音频模式：开启" if self.youtube_audio_mode else "❌ 油管音频模式：关闭"
            audio_mode_button = InlineKeyboardButton(audio_mode_text, callback_data="toggle_audio_mode")

            ugc_playlist_text = "✅ B站UGC下载：开启" if self.bilibili_ugc_playlist else "❌ B站UGC下载：关闭"
            ugc_playlist_button = InlineKeyboardButton(ugc_playlist_text, callback_data="toggle_ugc_playlist")

            danmaku_text = "✅ B站弹幕下载：开启" if self.bilibili_danmaku_download else "❌ B站弹幕下载：关闭"
            danmaku_button = InlineKeyboardButton(danmaku_text, callback_data="toggle_danmaku")

            thumbnail_text = "✅ 油管封面下载：开启" if self.youtube_thumbnail_download else "❌ 油管封面下载：关闭"
            thumbnail_button = InlineKeyboardButton(thumbnail_text, callback_data="toggle_thumbnail")

            subtitle_text = "✅ 油管字幕下载：开启" if self.youtube_subtitle_download else "❌ 油管字幕下载：关闭"
            subtitle_button = InlineKeyboardButton(subtitle_text, callback_data="toggle_subtitle")

            timestamp_text = "✅ 油管时间戳命名：开启" if self.youtube_timestamp_naming else "❌ 油管时间戳命名：关闭"
            timestamp_button = InlineKeyboardButton(timestamp_text, callback_data="toggle_timestamp")

            bilibili_thumbnail_text = "✅ B站封面下载：开启" if self.bilibili_thumbnail_download else "❌ B站封面下载：关闭"
            bilibili_thumbnail_button = InlineKeyboardButton(bilibili_thumbnail_text, callback_data="toggle_bilibili_thumbnail")

            # 网易云歌词合并按钮
            lyrics_merge_text = "✅ 网易云歌词合并：开启" if self.netease_lyrics_merge else "❌ 网易云歌词合并：关闭"
            lyrics_merge_button = InlineKeyboardButton(lyrics_merge_text, callback_data="toggle_lyrics_merge")

            # 网易云artist下载按钮
            artist_download_text = "✅ 网易云artist下载：开启" if self.netease_artist_download else "❌ 网易云artist下载：关闭"
            artist_download_button = InlineKeyboardButton(artist_download_text, callback_data="toggle_artist_download")

            # 网易云cover下载按钮
            cover_download_text = "✅ 网易云cover下载：开启" if self.netease_cover_download else "❌ 网易云cover下载：关闭"
            cover_download_button = InlineKeyboardButton(cover_download_text, callback_data="toggle_cover_download")

            reply_markup = InlineKeyboardMarkup([
                [auto_playlist_button],
                [id_tags_button],
                [audio_mode_button],
                [ugc_playlist_button],
                [danmaku_button],
                [thumbnail_button],
                [subtitle_button],
                [timestamp_button],
                [bilibili_thumbnail_button],
                [lyrics_merge_button],
                [artist_download_button],
                [cover_download_button]
            ])
            await query.edit_message_reply_markup(reply_markup=reply_markup)
            await query.answer("已切换B站弹幕下载状态")

        elif callback_data == "toggle_audio_mode":
            # 切换YouTube音频模式
            current = self.youtube_audio_mode
            self.youtube_audio_mode = not current
            await self._save_config_async()

            # 重新生成四个按钮
            auto_playlist_text = "✅ B站多P自动下载：开启" if self.bilibili_auto_playlist else "❌ B站多P自动下载：关闭"
            auto_playlist_button = InlineKeyboardButton(auto_playlist_text, callback_data="toggle_autop")

            id_tags_text = "✅ 油管自动添加标签：开启" if self.youtube_id_tags else "❌ 油管自动添加标签：关闭"
            id_tags_button = InlineKeyboardButton(id_tags_text, callback_data="toggle_id_tags")

            audio_mode_text = "✅ 油管音频模式：开启" if self.youtube_audio_mode else "❌ 油管音频模式：关闭"
            audio_mode_button = InlineKeyboardButton(audio_mode_text, callback_data="toggle_audio_mode")

            ugc_playlist_text = "✅ B站UGC下载：开启" if self.bilibili_ugc_playlist else "❌ B站UGC下载：关闭"
            ugc_playlist_button = InlineKeyboardButton(ugc_playlist_text, callback_data="toggle_ugc_playlist")

            danmaku_text = "✅ B站弹幕下载：开启" if self.bilibili_danmaku_download else "❌ B站弹幕下载：关闭"
            danmaku_button = InlineKeyboardButton(danmaku_text, callback_data="toggle_danmaku")

            thumbnail_text = "✅ 油管封面下载：开启" if self.youtube_thumbnail_download else "❌ 油管封面下载：关闭"
            thumbnail_button = InlineKeyboardButton(thumbnail_text, callback_data="toggle_thumbnail")

            subtitle_text = "✅ 油管字幕下载：开启" if self.youtube_subtitle_download else "❌ 油管字幕下载：关闭"
            subtitle_button = InlineKeyboardButton(subtitle_text, callback_data="toggle_subtitle")

            timestamp_text = "✅ 油管时间戳命名：开启" if self.youtube_timestamp_naming else "❌ 油管时间戳命名：关闭"
            timestamp_button = InlineKeyboardButton(timestamp_text, callback_data="toggle_timestamp")

            bilibili_thumbnail_text = "✅ B站封面下载：开启" if self.bilibili_thumbnail_download else "❌ B站封面下载：关闭"
            bilibili_thumbnail_button = InlineKeyboardButton(bilibili_thumbnail_text, callback_data="toggle_bilibili_thumbnail")

            # 网易云歌词合并按钮
            lyrics_merge_text = "✅ 网易云歌词合并：开启" if self.netease_lyrics_merge else "❌ 网易云歌词合并：关闭"
            lyrics_merge_button = InlineKeyboardButton(lyrics_merge_text, callback_data="toggle_lyrics_merge")

            # 网易云artist下载按钮
            artist_download_text = "✅ 网易云artist下载：开启" if self.netease_artist_download else "❌ 网易云artist下载：关闭"
            artist_download_button = InlineKeyboardButton(artist_download_text, callback_data="toggle_artist_download")

            # 网易云cover下载按钮
            cover_download_text = "✅ 网易云cover下载：开启" if self.netease_cover_download else "❌ 网易云cover下载：关闭"
            cover_download_button = InlineKeyboardButton(cover_download_text, callback_data="toggle_cover_download")

            reply_markup = InlineKeyboardMarkup([
                [auto_playlist_button],
                [id_tags_button],
                [audio_mode_button],
                [ugc_playlist_button],
                [danmaku_button],
                [thumbnail_button],
                [subtitle_button],
                [timestamp_button],
                [bilibili_thumbnail_button],
                [lyrics_merge_button],
                [artist_download_button],
                [cover_download_button]
            ])
            await query.edit_message_reply_markup(reply_markup=reply_markup)
            await query.answer("已切换油管音频模式状态")
            await query.edit_message_reply_markup(reply_markup=reply_markup)
            await query.answer("已切换网易云歌词合并状态")

        elif callback_data == "toggle_ugc_playlist":
            # 切换B站UGC播放列表自动下载
            current = self.bilibili_ugc_playlist
            self.bilibili_ugc_playlist = not current
            await self._save_config_async()

            # 重新生成五个按钮
            auto_playlist_text = "✅ B站多P自动下载：开启" if self.bilibili_auto_playlist else "❌ B站多P自动下载：关闭"
            auto_playlist_button = InlineKeyboardButton(auto_playlist_text, callback_data="toggle_autop")

            id_tags_text = "✅ 油管自动添加标签：开启" if self.youtube_id_tags else "❌ 油管自动添加标签：关闭"
            id_tags_button = InlineKeyboardButton(id_tags_text, callback_data="toggle_id_tags")

            audio_mode_text = "✅ 油管音频模式：开启" if self.youtube_audio_mode else "❌ 油管音频模式：关闭"
            audio_mode_button = InlineKeyboardButton(audio_mode_text, callback_data="toggle_audio_mode")

            ugc_playlist_text = "✅ B站UGC下载：开启" if self.bilibili_ugc_playlist else "❌ B站UGC下载：关闭"
            ugc_playlist_button = InlineKeyboardButton(ugc_playlist_text, callback_data="toggle_ugc_playlist")

            danmaku_text = "✅ B站弹幕下载：开启" if self.bilibili_danmaku_download else "❌ B站弹幕下载：关闭"
            danmaku_button = InlineKeyboardButton(danmaku_text, callback_data="toggle_danmaku")

            thumbnail_text = "✅ 油管封面下载：开启" if self.youtube_thumbnail_download else "❌ 油管封面下载：关闭"
            thumbnail_button = InlineKeyboardButton(thumbnail_text, callback_data="toggle_thumbnail")

            subtitle_text = "✅ 油管字幕下载：开启" if self.youtube_subtitle_download else "❌ 油管字幕下载：关闭"
            subtitle_button = InlineKeyboardButton(subtitle_text, callback_data="toggle_subtitle")

            timestamp_text = "✅ 油管时间戳命名：开启" if self.youtube_timestamp_naming else "❌ 油管时间戳命名：关闭"
            timestamp_button = InlineKeyboardButton(timestamp_text, callback_data="toggle_timestamp")

            bilibili_thumbnail_text = "✅ B站封面下载：开启" if self.bilibili_thumbnail_download else "❌ B站封面下载：关闭"
            bilibili_thumbnail_button = InlineKeyboardButton(bilibili_thumbnail_text, callback_data="toggle_bilibili_thumbnail")

            reply_markup = InlineKeyboardMarkup([
                [auto_playlist_button],
                [id_tags_button],
                [audio_mode_button],
                [ugc_playlist_button],
                [danmaku_button],
                [thumbnail_button],
                [subtitle_button],
                [timestamp_button],
                [bilibili_thumbnail_button]
            ])
            await query.edit_message_reply_markup(reply_markup=reply_markup)
            await query.answer("已切换B站UGC下载状态")

            lyrics_merge_text = "✅ 网易云歌词合并：开启" if self.netease_lyrics_merge else "❌ 网易云歌词合并：关闭"
            lyrics_merge_button = InlineKeyboardButton(lyrics_merge_text, callback_data="toggle_lyrics_merge")

            reply_markup = InlineKeyboardMarkup([
                [auto_playlist_button],
                [id_tags_button],
                [audio_mode_button],
                [ugc_playlist_button],
                [danmaku_button],
                [thumbnail_button],
                [subtitle_button],
                [timestamp_button],
                [bilibili_thumbnail_button],
                [lyrics_merge_button]
            ])
            # 网易云artist下载按钮
            artist_download_text = "✅ 网易云artist下载：开启" if self.netease_artist_download else "❌ 网易云artist下载：关闭"
            artist_download_button = InlineKeyboardButton(artist_download_text, callback_data="toggle_artist_download")

            # 网易云cover下载按钮
            cover_download_text = "✅ 网易云cover下载：开启" if self.netease_cover_download else "❌ 网易云cover下载：关闭"
            cover_download_button = InlineKeyboardButton(cover_download_text, callback_data="toggle_cover_download")

            reply_markup = InlineKeyboardMarkup([
                [auto_playlist_button],
                [id_tags_button],
                [audio_mode_button],
                [ugc_playlist_button],
                [danmaku_button],
                [thumbnail_button],
                [subtitle_button],
                [timestamp_button],
                [bilibili_thumbnail_button],
                [lyrics_merge_button],
                [artist_download_button],
                [cover_download_button]
            ])
            await query.edit_message_reply_markup(reply_markup=reply_markup)
            await query.answer("已切换网易云歌词合并状态")

        elif callback_data == "toggle_thumbnail":
            # 切换YouTube封面下载
            current = self.youtube_thumbnail_download
            self.youtube_thumbnail_download = not current
            await self._save_config_async()

            # 重新生成所有按钮
            auto_playlist_text = "✅ B站多P自动下载：开启" if self.bilibili_auto_playlist else "❌ B站多P自动下载：关闭"
            auto_playlist_button = InlineKeyboardButton(auto_playlist_text, callback_data="toggle_autop")

            id_tags_text = "✅ 油管自动添加标签：开启" if self.youtube_id_tags else "❌ 油管自动添加标签：关闭"
            id_tags_button = InlineKeyboardButton(id_tags_text, callback_data="toggle_id_tags")

            audio_mode_text = "✅ 油管音频模式：开启" if self.youtube_audio_mode else "❌ 油管音频模式：关闭"
            audio_mode_button = InlineKeyboardButton(audio_mode_text, callback_data="toggle_audio_mode")

            ugc_playlist_text = "✅ B站UGC下载：开启" if self.bilibili_ugc_playlist else "❌ B站UGC下载：关闭"
            ugc_playlist_button = InlineKeyboardButton(ugc_playlist_text, callback_data="toggle_ugc_playlist")

            danmaku_text = "✅ B站弹幕下载：开启" if self.bilibili_danmaku_download else "❌ B站弹幕下载：关闭"
            danmaku_button = InlineKeyboardButton(danmaku_text, callback_data="toggle_danmaku")

            thumbnail_text = "✅ 油管封面下载：开启" if self.youtube_thumbnail_download else "❌ 油管封面下载：关闭"
            thumbnail_button = InlineKeyboardButton(thumbnail_text, callback_data="toggle_thumbnail")

            reply_markup = InlineKeyboardMarkup([
                [auto_playlist_button],
                [id_tags_button],
                [audio_mode_button],
                [ugc_playlist_button],
                [danmaku_button],
                [thumbnail_button]
            ])
            await query.edit_message_reply_markup(reply_markup=reply_markup)
            await query.answer("已切换油管封面下载状态")

        elif callback_data == "toggle_subtitle":
            # 切换YouTube字幕下载
            current = self.youtube_subtitle_download
            self.youtube_subtitle_download = not current
            await self._save_config_async()

            # 重新生成所有按钮
            auto_playlist_text = "✅ B站多P自动下载：开启" if self.bilibili_auto_playlist else "❌ B站多P自动下载：关闭"
            auto_playlist_button = InlineKeyboardButton(auto_playlist_text, callback_data="toggle_autop")

            id_tags_text = "✅ 油管自动添加标签：开启" if self.youtube_id_tags else "❌ 油管自动添加标签：关闭"
            id_tags_button = InlineKeyboardButton(id_tags_text, callback_data="toggle_id_tags")

            audio_mode_text = "✅ 油管音频模式：开启" if self.youtube_audio_mode else "❌ 油管音频模式：关闭"
            audio_mode_button = InlineKeyboardButton(audio_mode_text, callback_data="toggle_audio_mode")

            ugc_playlist_text = "✅ B站UGC下载：开启" if self.bilibili_ugc_playlist else "❌ B站UGC下载：关闭"
            ugc_playlist_button = InlineKeyboardButton(ugc_playlist_text, callback_data="toggle_ugc_playlist")

            danmaku_text = "✅ B站弹幕下载：开启" if self.bilibili_danmaku_download else "❌ B站弹幕下载：关闭"
            danmaku_button = InlineKeyboardButton(danmaku_text, callback_data="toggle_danmaku")

            thumbnail_text = "✅ 油管封面下载：开启" if self.youtube_thumbnail_download else "❌ 油管封面下载：关闭"
            thumbnail_button = InlineKeyboardButton(thumbnail_text, callback_data="toggle_thumbnail")

            subtitle_text = "✅ 油管字幕下载：开启" if self.youtube_subtitle_download else "❌ 油管字幕下载：关闭"
            subtitle_button = InlineKeyboardButton(subtitle_text, callback_data="toggle_subtitle")

            timestamp_text = "✅ 油管时间戳命名：开启" if self.youtube_timestamp_naming else "❌ 油管时间戳命名：关闭"
            timestamp_button = InlineKeyboardButton(timestamp_text, callback_data="toggle_timestamp")

            bilibili_thumbnail_text = "✅ B站封面下载：开启" if self.bilibili_thumbnail_download else "❌ B站封面下载：关闭"
            bilibili_thumbnail_button = InlineKeyboardButton(bilibili_thumbnail_text, callback_data="toggle_bilibili_thumbnail")

            reply_markup = InlineKeyboardMarkup([
                [auto_playlist_button],
                [id_tags_button],
                [audio_mode_button],
                [ugc_playlist_button],
                [danmaku_button],
                [thumbnail_button],
                [subtitle_button],
                [timestamp_button],
                [bilibili_thumbnail_button]
            ])
            await query.edit_message_reply_markup(reply_markup=reply_markup)
            await query.answer("已切换油管字幕下载状态")

            lyrics_merge_text = "✅ 网易云歌词合并：开启" if self.netease_lyrics_merge else "❌ 网易云歌词合并：关闭"
            lyrics_merge_button = InlineKeyboardButton(lyrics_merge_text, callback_data="toggle_lyrics_merge")

            reply_markup = InlineKeyboardMarkup([
                [auto_playlist_button],
                [id_tags_button],
                [audio_mode_button],
                [ugc_playlist_button],
                [danmaku_button],
                [thumbnail_button],
                [subtitle_button],
                [timestamp_button],
                [bilibili_thumbnail_button],
                [lyrics_merge_button]
            ])
            # 网易云artist下载按钮
            artist_download_text = "✅ 网易云artist下载：开启" if self.netease_artist_download else "❌ 网易云artist下载：关闭"
            artist_download_button = InlineKeyboardButton(artist_download_text, callback_data="toggle_artist_download")

            # 网易云cover下载按钮
            cover_download_text = "✅ 网易云cover下载：开启" if self.netease_cover_download else "❌ 网易云cover下载：关闭"
            cover_download_button = InlineKeyboardButton(cover_download_text, callback_data="toggle_cover_download")

            reply_markup = InlineKeyboardMarkup([
                [auto_playlist_button],
                [id_tags_button],
                [audio_mode_button],
                [ugc_playlist_button],
                [danmaku_button],
                [thumbnail_button],
                [subtitle_button],
                [timestamp_button],
                [bilibili_thumbnail_button],
                [lyrics_merge_button],
                [artist_download_button],
                [cover_download_button]
            ])
            await query.edit_message_reply_markup(reply_markup=reply_markup)
            await query.answer("已切换网易云歌词合并状态")

        elif callback_data == "toggle_timestamp":
            # 切换YouTube时间戳命名
            current = self.youtube_timestamp_naming
            self.youtube_timestamp_naming = not current
            await self._save_config_async()

            # 重新生成所有按钮
            auto_playlist_text = "✅ B站多P自动下载：开启" if self.bilibili_auto_playlist else "❌ B站多P自动下载：关闭"
            auto_playlist_button = InlineKeyboardButton(auto_playlist_text, callback_data="toggle_autop")

            id_tags_text = "✅ 油管自动添加标签：开启" if self.youtube_id_tags else "❌ 油管自动添加标签：关闭"
            id_tags_button = InlineKeyboardButton(id_tags_text, callback_data="toggle_id_tags")

            audio_mode_text = "✅ 油管音频模式：开启" if self.youtube_audio_mode else "❌ 油管音频模式：关闭"
            audio_mode_button = InlineKeyboardButton(audio_mode_text, callback_data="toggle_audio_mode")

            ugc_playlist_text = "✅ B站UGC下载：开启" if self.bilibili_ugc_playlist else "❌ B站UGC下载：关闭"
            ugc_playlist_button = InlineKeyboardButton(ugc_playlist_text, callback_data="toggle_ugc_playlist")

            danmaku_text = "✅ B站弹幕下载：开启" if self.bilibili_danmaku_download else "❌ B站弹幕下载：关闭"
            danmaku_button = InlineKeyboardButton(danmaku_text, callback_data="toggle_danmaku")

            thumbnail_text = "✅ 油管封面下载：开启" if self.youtube_thumbnail_download else "❌ 油管封面下载：关闭"
            thumbnail_button = InlineKeyboardButton(thumbnail_text, callback_data="toggle_thumbnail")

            subtitle_text = "✅ 油管字幕下载：开启" if self.youtube_subtitle_download else "❌ 油管字幕下载：关闭"
            subtitle_button = InlineKeyboardButton(subtitle_text, callback_data="toggle_subtitle")

            timestamp_text = "✅ 油管时间戳命名：开启" if self.youtube_timestamp_naming else "❌ 油管时间戳命名：关闭"
            timestamp_button = InlineKeyboardButton(timestamp_text, callback_data="toggle_timestamp")

            bilibili_thumbnail_text = "✅ B站封面下载：开启" if self.bilibili_thumbnail_download else "❌ B站封面下载：关闭"
            bilibili_thumbnail_button = InlineKeyboardButton(bilibili_thumbnail_text, callback_data="toggle_bilibili_thumbnail")

            reply_markup = InlineKeyboardMarkup([
                [auto_playlist_button],
                [id_tags_button],
                [audio_mode_button],
                [ugc_playlist_button],
                [danmaku_button],
                [thumbnail_button],
                [subtitle_button],
                [timestamp_button],
                [bilibili_thumbnail_button]
            ])
            await query.edit_message_reply_markup(reply_markup=reply_markup)
            await query.answer("已切换油管时间戳命名状态")

            lyrics_merge_text = "✅ 网易云歌词合并：开启" if self.netease_lyrics_merge else "❌ 网易云歌词合并：关闭"
            lyrics_merge_button = InlineKeyboardButton(lyrics_merge_text, callback_data="toggle_lyrics_merge")

            reply_markup = InlineKeyboardMarkup([
                [auto_playlist_button],
                [id_tags_button],
                [audio_mode_button],
                [ugc_playlist_button],
                [danmaku_button],
                [thumbnail_button],
                [subtitle_button],
                [timestamp_button],
                [bilibili_thumbnail_button],
                [lyrics_merge_button]
            ])
            # 网易云artist下载按钮
            artist_download_text = "✅ 网易云artist下载：开启" if self.netease_artist_download else "❌ 网易云artist下载：关闭"
            artist_download_button = InlineKeyboardButton(artist_download_text, callback_data="toggle_artist_download")

            # 网易云cover下载按钮
            cover_download_text = "✅ 网易云cover下载：开启" if self.netease_cover_download else "❌ 网易云cover下载：关闭"
            cover_download_button = InlineKeyboardButton(cover_download_text, callback_data="toggle_cover_download")

            reply_markup = InlineKeyboardMarkup([
                [auto_playlist_button],
                [id_tags_button],
                [audio_mode_button],
                [ugc_playlist_button],
                [danmaku_button],
                [thumbnail_button],
                [subtitle_button],
                [timestamp_button],
                [bilibili_thumbnail_button],
                [lyrics_merge_button],
                [artist_download_button],
                [cover_download_button]
            ])
            await query.edit_message_reply_markup(reply_markup=reply_markup)
            await query.answer("已切换网易云歌词合并状态")

        elif callback_data == "toggle_bilibili_thumbnail":
            # 切换B站封面下载
            current = self.bilibili_thumbnail_download
            self.bilibili_thumbnail_download = not current
            await self._save_config_async()

            # 重新生成所有按钮
            auto_playlist_text = "✅ B站多P自动下载：开启" if self.bilibili_auto_playlist else "❌ B站多P自动下载：关闭"
            auto_playlist_button = InlineKeyboardButton(auto_playlist_text, callback_data="toggle_autop")

            id_tags_text = "✅ 油管自动添加标签：开启" if self.youtube_id_tags else "❌ 油管自动添加标签：关闭"
            id_tags_button = InlineKeyboardButton(id_tags_text, callback_data="toggle_id_tags")

            audio_mode_text = "✅ 油管音频模式：开启" if self.youtube_audio_mode else "❌ 油管音频模式：关闭"
            audio_mode_button = InlineKeyboardButton(audio_mode_text, callback_data="toggle_audio_mode")

            ugc_playlist_text = "✅ B站UGC下载：开启" if self.bilibili_ugc_playlist else "❌ B站UGC下载：关闭"
            ugc_playlist_button = InlineKeyboardButton(ugc_playlist_text, callback_data="toggle_ugc_playlist")

            danmaku_text = "✅ B站弹幕下载：开启" if self.bilibili_danmaku_download else "❌ B站弹幕下载：关闭"
            danmaku_button = InlineKeyboardButton(danmaku_text, callback_data="toggle_danmaku")

            thumbnail_text = "✅ 油管封面下载：开启" if self.youtube_thumbnail_download else "❌ 油管封面下载：关闭"
            thumbnail_button = InlineKeyboardButton(thumbnail_text, callback_data="toggle_thumbnail")

            subtitle_text = "✅ 油管字幕下载：开启" if self.youtube_subtitle_download else "❌ 油管字幕下载：关闭"
            subtitle_button = InlineKeyboardButton(subtitle_text, callback_data="toggle_subtitle")

            timestamp_text = "✅ 油管时间戳命名：开启" if self.youtube_timestamp_naming else "❌ 油管时间戳命名：关闭"
            timestamp_button = InlineKeyboardButton(timestamp_text, callback_data="toggle_timestamp")

            bilibili_thumbnail_text = "✅ B站封面下载：开启" if self.bilibili_thumbnail_download else "❌ B站封面下载：关闭"
            bilibili_thumbnail_button = InlineKeyboardButton(bilibili_thumbnail_text, callback_data="toggle_bilibili_thumbnail")

            # 网易云歌词合并按钮
            lyrics_merge_text = "✅ 网易云歌词合并：开启" if self.netease_lyrics_merge else "❌ 网易云歌词合并：关闭"
            lyrics_merge_button = InlineKeyboardButton(lyrics_merge_text, callback_data="toggle_lyrics_merge")

            # 网易云artist下载按钮
            artist_download_text = "✅ 网易云artist下载：开启" if self.netease_artist_download else "❌ 网易云artist下载：关闭"
            artist_download_button = InlineKeyboardButton(artist_download_text, callback_data="toggle_artist_download")

            # 网易云cover下载按钮
            cover_download_text = "✅ 网易云cover下载：开启" if self.netease_cover_download else "❌ 网易云cover下载：关闭"
            cover_download_button = InlineKeyboardButton(cover_download_text, callback_data="toggle_cover_download")

            reply_markup = InlineKeyboardMarkup([
                [auto_playlist_button],
                [id_tags_button],
                [audio_mode_button],
                [ugc_playlist_button],
                [danmaku_button],
                [thumbnail_button],
                [subtitle_button],
                [timestamp_button],
                [bilibili_thumbnail_button],
                [lyrics_merge_button],
                [artist_download_button],
                [cover_download_button]
            ])
            await query.edit_message_reply_markup(reply_markup=reply_markup)
            await query.answer("已切换B站封面下载状态")

        elif callback_data == "toggle_lyrics_merge":
            # 切换网易云歌词合并
            current = self.netease_lyrics_merge
            self.netease_lyrics_merge = not current
            await self._save_config_async()

            # 重新生成所有按钮
            auto_playlist_text = "✅ B站多P自动下载：开启" if self.bilibili_auto_playlist else "❌ B站多P自动下载：关闭"
            auto_playlist_button = InlineKeyboardButton(auto_playlist_text, callback_data="toggle_autop")

            id_tags_text = "✅ 油管自动添加标签：开启" if self.youtube_id_tags else "❌ 油管自动添加标签：关闭"
            id_tags_button = InlineKeyboardButton(id_tags_text, callback_data="toggle_id_tags")

            audio_mode_text = "✅ 油管音频模式：开启" if self.youtube_audio_mode else "❌ 油管音频模式：关闭"
            audio_mode_button = InlineKeyboardButton(audio_mode_text, callback_data="toggle_audio_mode")

            ugc_playlist_text = "✅ B站UGC下载：开启" if self.bilibili_ugc_playlist else "❌ B站UGC下载：关闭"
            ugc_playlist_button = InlineKeyboardButton(ugc_playlist_text, callback_data="toggle_ugc_playlist")

            danmaku_text = "✅ B站弹幕下载：开启" if self.bilibili_danmaku_download else "❌ B站弹幕下载：关闭"
            danmaku_button = InlineKeyboardButton(danmaku_text, callback_data="toggle_danmaku")

            thumbnail_text = "✅ 油管封面下载：开启" if self.youtube_thumbnail_download else "❌ 油管封面下载：关闭"
            thumbnail_button = InlineKeyboardButton(thumbnail_text, callback_data="toggle_thumbnail")

            subtitle_text = "✅ 油管字幕下载：开启" if self.youtube_subtitle_download else "❌ 油管字幕下载：关闭"
            subtitle_button = InlineKeyboardButton(subtitle_text, callback_data="toggle_subtitle")

            timestamp_text = "✅ 油管时间戳命名：开启" if self.youtube_timestamp_naming else "❌ 油管时间戳命名：关闭"
            timestamp_button = InlineKeyboardButton(timestamp_text, callback_data="toggle_timestamp")

            bilibili_thumbnail_text = "✅ B站封面下载：开启" if self.bilibili_thumbnail_download else "❌ B站封面下载：关闭"
            bilibili_thumbnail_button = InlineKeyboardButton(bilibili_thumbnail_text, callback_data="toggle_bilibili_thumbnail")

            lyrics_merge_text = "✅ 网易云歌词合并：开启" if self.netease_lyrics_merge else "❌ 网易云歌词合并：关闭"
            lyrics_merge_button = InlineKeyboardButton(lyrics_merge_text, callback_data="toggle_lyrics_merge")

            # 网易云artist下载按钮
            artist_download_text = "✅ 网易云artist下载：开启" if self.netease_artist_download else "❌ 网易云artist下载：关闭"
            artist_download_button = InlineKeyboardButton(artist_download_text, callback_data="toggle_artist_download")

            # 网易云cover下载按钮
            cover_download_text = "✅ 网易云cover下载：开启" if self.netease_cover_download else "❌ 网易云cover下载：关闭"
            cover_download_button = InlineKeyboardButton(cover_download_text, callback_data="toggle_cover_download")

            reply_markup = InlineKeyboardMarkup([
                [auto_playlist_button],
                [id_tags_button],
                [audio_mode_button],
                [ugc_playlist_button],
                [danmaku_button],
                [thumbnail_button],
                [subtitle_button],
                [timestamp_button],
                [bilibili_thumbnail_button],
                [lyrics_merge_button],
                [artist_download_button],
                [cover_download_button]
            ])
            await query.edit_message_reply_markup(reply_markup=reply_markup)
            await query.answer("已切换网易云歌词合并状态")

        elif callback_data == "toggle_artist_download":
            # 切换网易云artist下载
            current = self.netease_artist_download
            self.netease_artist_download = not current
            await self._save_config_async()

            # 重新生成所有按钮
            auto_playlist_text = "✅ B站多P自动下载：开启" if self.bilibili_auto_playlist else "❌ B站多P自动下载：关闭"
            auto_playlist_button = InlineKeyboardButton(auto_playlist_text, callback_data="toggle_autop")

            id_tags_text = "✅ 油管自动添加标签：开启" if self.youtube_id_tags else "❌ 油管自动添加标签：关闭"
            id_tags_button = InlineKeyboardButton(id_tags_text, callback_data="toggle_id_tags")

            audio_mode_text = "✅ 油管音频模式：开启" if self.youtube_audio_mode else "❌ 油管音频模式：关闭"
            audio_mode_button = InlineKeyboardButton(audio_mode_text, callback_data="toggle_audio_mode")

            ugc_playlist_text = "✅ B站UGC下载：开启" if self.bilibili_ugc_playlist else "❌ B站UGC下载：关闭"
            ugc_playlist_button = InlineKeyboardButton(ugc_playlist_text, callback_data="toggle_ugc_playlist")

            danmaku_text = "✅ B站弹幕下载：开启" if self.bilibili_danmaku_download else "❌ B站弹幕下载：关闭"
            danmaku_button = InlineKeyboardButton(danmaku_text, callback_data="toggle_danmaku")

            thumbnail_text = "✅ 油管封面下载：开启" if self.youtube_thumbnail_download else "❌ 油管封面下载：关闭"
            thumbnail_button = InlineKeyboardButton(thumbnail_text, callback_data="toggle_thumbnail")

            subtitle_text = "✅ 油管字幕下载：开启" if self.youtube_subtitle_download else "❌ 油管字幕下载：关闭"
            subtitle_button = InlineKeyboardButton(subtitle_text, callback_data="toggle_subtitle")

            timestamp_text = "✅ 油管时间戳命名：开启" if self.youtube_timestamp_naming else "❌ 油管时间戳命名：关闭"
            timestamp_button = InlineKeyboardButton(timestamp_text, callback_data="toggle_timestamp")

            bilibili_thumbnail_text = "✅ B站封面下载：开启" if self.bilibili_thumbnail_download else "❌ B站封面下载：关闭"
            bilibili_thumbnail_button = InlineKeyboardButton(bilibili_thumbnail_text, callback_data="toggle_bilibili_thumbnail")

            lyrics_merge_text = "✅ 网易云歌词合并：开启" if self.netease_lyrics_merge else "❌ 网易云歌词合并：关闭"
            lyrics_merge_button = InlineKeyboardButton(lyrics_merge_text, callback_data="toggle_lyrics_merge")

            # 网易云artist下载按钮
            artist_download_text = "✅ 网易云artist下载：开启" if self.netease_artist_download else "❌ 网易云artist下载：关闭"
            artist_download_button = InlineKeyboardButton(artist_download_text, callback_data="toggle_artist_download")

            # 网易云cover下载按钮
            cover_download_text = "✅ 网易云cover下载：开启" if self.netease_cover_download else "❌ 网易云cover下载：关闭"
            cover_download_button = InlineKeyboardButton(cover_download_text, callback_data="toggle_cover_download")

            reply_markup = InlineKeyboardMarkup([
                [auto_playlist_button],
                [id_tags_button],
                [audio_mode_button],
                [ugc_playlist_button],
                [danmaku_button],
                [thumbnail_button],
                [subtitle_button],
                [timestamp_button],
                [bilibili_thumbnail_button],
                [lyrics_merge_button],
                [artist_download_button],
                [cover_download_button]
            ])
            await query.edit_message_reply_markup(reply_markup=reply_markup)
            await query.answer("已切换网易云artist下载状态")

        elif callback_data == "toggle_cover_download":
            # 切换网易云cover下载
            current = self.netease_cover_download
            self.netease_cover_download = not current
            await self._save_config_async()

            # 重新生成所有按钮
            auto_playlist_text = "✅ B站多P自动下载：开启" if self.bilibili_auto_playlist else "❌ B站多P自动下载：关闭"
            auto_playlist_button = InlineKeyboardButton(auto_playlist_text, callback_data="toggle_autop")

            id_tags_text = "✅ 油管自动添加标签：开启" if self.youtube_id_tags else "❌ 油管自动添加标签：关闭"
            id_tags_button = InlineKeyboardButton(id_tags_text, callback_data="toggle_id_tags")

            audio_mode_text = "✅ 油管音频模式：开启" if self.youtube_audio_mode else "❌ 油管音频模式：关闭"
            audio_mode_button = InlineKeyboardButton(audio_mode_text, callback_data="toggle_audio_mode")

            ugc_playlist_text = "✅ B站UGC下载：开启" if self.bilibili_ugc_playlist else "❌ B站UGC下载：关闭"
            ugc_playlist_button = InlineKeyboardButton(ugc_playlist_text, callback_data="toggle_ugc_playlist")

            danmaku_text = "✅ B站弹幕下载：开启" if self.bilibili_danmaku_download else "❌ B站弹幕下载：关闭"
            danmaku_button = InlineKeyboardButton(danmaku_text, callback_data="toggle_danmaku")

            thumbnail_text = "✅ 油管封面下载：开启" if self.youtube_thumbnail_download else "❌ 油管封面下载：关闭"
            thumbnail_button = InlineKeyboardButton(thumbnail_text, callback_data="toggle_thumbnail")

            subtitle_text = "✅ 油管字幕下载：开启" if self.youtube_subtitle_download else "❌ 油管字幕下载：关闭"
            subtitle_button = InlineKeyboardButton(subtitle_text, callback_data="toggle_subtitle")

            timestamp_text = "✅ 油管时间戳命名：开启" if self.youtube_timestamp_naming else "❌ 油管时间戳命名：关闭"
            timestamp_button = InlineKeyboardButton(timestamp_text, callback_data="toggle_timestamp")

            bilibili_thumbnail_text = "✅ B站封面下载：开启" if self.bilibili_thumbnail_download else "❌ B站封面下载：关闭"
            bilibili_thumbnail_button = InlineKeyboardButton(bilibili_thumbnail_text, callback_data="toggle_bilibili_thumbnail")

            lyrics_merge_text = "✅ 网易云歌词合并：开启" if self.netease_lyrics_merge else "❌ 网易云歌词合并：关闭"
            lyrics_merge_button = InlineKeyboardButton(lyrics_merge_text, callback_data="toggle_lyrics_merge")

            # 网易云artist下载按钮
            artist_download_text = "✅ 网易云artist下载：开启" if self.netease_artist_download else "❌ 网易云artist下载：关闭"
            artist_download_button = InlineKeyboardButton(artist_download_text, callback_data="toggle_artist_download")

            # 网易云cover下载按钮
            cover_download_text = "✅ 网易云cover下载：开启" if self.netease_cover_download else "❌ 网易云cover下载：关闭"
            cover_download_button = InlineKeyboardButton(cover_download_text, callback_data="toggle_cover_download")

            reply_markup = InlineKeyboardMarkup([
                [auto_playlist_button],
                [id_tags_button],
                [audio_mode_button],
                [ugc_playlist_button],
                [danmaku_button],
                [thumbnail_button],
                [subtitle_button],
                [timestamp_button],
                [bilibili_thumbnail_button],
                [lyrics_merge_button],
                [artist_download_button],
                [cover_download_button]
            ])
            await query.edit_message_reply_markup(reply_markup=reply_markup)
            await query.answer("已切换网易云cover下载状态")

    async def cancel_task_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """处理取消下载任务的按钮点击"""
        query = update.callback_query
        user_id = query.from_user.id

        # 权限检查
        if not self._check_user_permission(user_id):
            await query.answer("❌ 您没有权限使用此机器人")
            return

        await query.answer()

        # 获取任务 ID
        task_id = query.data.split(":")[1]

        # 取消对应的下载任务
        cancelled = await self.cancel_download_task(task_id)

        if cancelled:
            # 编辑原消息为已取消
            await query.edit_message_text(f"🚫 下载任务已取消（ID: {task_id}）")
        else:
            # 任务不存在或已经被取消
            await query.edit_message_text(f"⚠️ 任务不存在或已被取消（ID: {task_id}）")

    async def add_download_task(self, task_id: str, task: asyncio.Task, user_id: int = None, status_message=None):
        """添加下载任务到管理器中"""
        async with self.task_lock:
            self.download_tasks[task_id] = {
                "task": task,
                "cancelled": False,
                "start_time": time.time(),
                "user_id": user_id,
                "status_message": status_message,
                "chat_id": status_message.chat_id if status_message else None,
                "message_id": status_message.message_id if status_message else None,
            }
            logger.info(f"📝 添加下载任务: {task_id} (用户: {user_id})")

    async def cancel_download_task(self, task_id: str) -> bool:
        """取消指定的下载任务"""
        async with self.task_lock:
            if task_id in self.download_tasks:
                task_info = self.download_tasks[task_id]
                if not task_info["cancelled"]:
                    task_info["cancelled"] = True
                    task_info["task"].cancel()
                    logger.info(f"🚫 取消下载任务: {task_id}")
                    return True
                else:
                    logger.warning(f"⚠️ 任务 {task_id} 已经被取消")
                    return False
            else:
                logger.warning(f"⚠️ 未找到任务: {task_id}")
                return False

    async def remove_download_task(self, task_id: str):
        """从管理器中移除下载任务"""
        async with self.task_lock:
            if task_id in self.download_tasks:
                del self.download_tasks[task_id]
                logger.info(f"🗑️ 移除下载任务: {task_id}")

    def is_task_cancelled(self, task_id: str) -> bool:
        """检查任务是否已被取消"""
        if task_id in self.download_tasks:
            return self.download_tasks[task_id]["cancelled"]
        return False

    async def download_user_media(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        通过 Telethon 处理用户发送或转发的媒体文件，以支持大文件下载。
        """
        import re
        user_id = update.message.from_user.id

        # 权限检查
        if not self._check_user_permission(user_id):
            await update.message.reply_text("❌ 您没有权限使用此机器人")
            return

        message = update.message
        chat_id = message.chat_id

        if not self.user_client:
            await message.reply_text("❌ 媒体下载功能未启用（Telethon 未配置），请联系管理员。")
            return

        # --- 紧急修复: 确保 self.bot_id 已设置 ---
        if not self.bot_id:
            try:
                logger.warning("self.bot_id 未设置，正在尝试获取...")
                bot_info = await context.bot.get_me()
                self.bot_id = bot_info.id
                logger.info(f"成功获取到 bot_id: {self.bot_id}")
            except Exception as e:
                logger.error(f"紧急获取 bot_id 失败: {e}", exc_info=True)
                await message.reply_text(f"❌ 内部初始化错误：无法获取机器人自身ID。请稍后重试。")
                return
        # 提取媒体信息
        attachment = message.effective_attachment
        if not attachment:
            await message.reply_text("❓ 请发送或转发一个媒体文件。")
            return

        file_name = getattr(attachment, 'file_name', 'unknown_file')
        # 优先处理.torrent文件
        if file_name and file_name.lower().endswith('.torrent'):
            logger.info(f"🔗 检测到种子文件: {file_name}")
            status_message = await message.reply_text("🔗 正在处理种子文件...")
            try:
                file_path = await context.bot.get_file(attachment.file_id)
                torrent_data = await file_path.download_as_bytearray()
                success = await self.add_torrent_file_to_qb(torrent_data, file_name)
                if success:
                    await status_message.edit_text("✅ **磁力链接/种子文件已成功添加到 qBittorrent！**\n\n📝 任务已添加到下载队列\n🔍 您可以在 qBittorrent 中查看下载进度\n💡 提示：下载完成后文件会保存到配置的下载目录", parse_mode=None)
                else:
                    await status_message.edit_text("❌ 添加到qBittorrent失败！", parse_mode=None)
            except Exception as e:
                logger.exception(f"添加种子文件到qBittorrent出错: {e}")
                await status_message.edit_text(f"❌ 添加种子文件出错: {e}", parse_mode=None)
            return
        # 如果 Bot API 没有文件名，尝试从消息文本中提取
        if not file_name or file_name == 'unknown_file':
            logger.info(f"Bot API 消息文本: '{message.text}'")
            if message.text and message.text.strip():
                file_name = message.text.strip()
                logger.info(f"从消息文本中提取文件名: {file_name}")
            else:
                logger.info("Bot API 消息文本为空或只包含空白字符")

        # 文件名处理：首行去#，空格变_；正文空格变_；末行全#标签则去#拼接，所有部分用_拼接
        if file_name and file_name != 'unknown_file':
            lines = file_name.splitlines()
            parts = []
            # 处理首行
            if lines:
                first = lines[0].lstrip('#').strip().replace(' ', '_')
                if first:
                    parts.append(first)
            # 处理正文
            for l in lines[1:-1]:
                l = l.strip().replace(' ', '_')
                if l:
                    parts.append(l)
            # 处理末行（全是#标签）
            if len(lines) > 1 and all(x.startswith('#') for x in lines[-1].split()):
                tags = [x.lstrip('#').strip().replace(' ', '_') for x in lines[-1].split() if x.lstrip('#').strip()]
                if tags:
                    parts.extend(tags)
            else:
                # 末行不是全#标签，也当正文处理
                if len(lines) > 1:
                    last = lines[-1].strip().replace(' ', '_')
                    if last:
                        parts.append(last)
            file_name = '_'.join(parts)
        if not file_name:
            file_name = 'unknown_file'
        file_size = getattr(attachment, 'file_size', 0)
        file_unique_id = getattr(attachment, 'file_unique_id', 'unknown_id')
        total_mb = file_size / (1024 * 1024) if file_size else 0

        # 记录 bot 端收到的消息信息
        bot_message_timestamp = message.date
        logger.info(
            f"Bot API 收到媒体: name='{file_name}', size={file_size}, "
            f"time={bot_message_timestamp.isoformat()}, unique_id='{file_unique_id}'"
        )
        status_message = await message.reply_text("正在分析消息，请稍候...")
        try:
            # 在用户客户端（user_client）中查找匹配的消息
            telethon_message = None
            audio_bitrate = None
            audio_duration = None
            video_width = None
            video_height = None
            video_duration = None
            time_window_seconds = 5 # 允许5秒的时间误差

            # 目标是与机器人的私聊
            try:
                # 首先尝试使用bot_id获取实体
                target_entity = await self.user_client.get_entity(self.bot_id)
            except ValueError as e:
                logger.warning(f"无法通过bot_id获取实体: {e}")
                try:
                    # 备用方案1: 尝试使用bot用户名
                    bot_info = await context.bot.get_me()
                    bot_username = bot_info.username
                    if bot_username:
                        logger.info(f"尝试使用bot用户名获取实体: @{bot_username}")
                        target_entity = await self.user_client.get_entity(bot_username)
                    else:
                        raise ValueError("Bot没有用户名")
                except Exception as e2:
                    logger.warning(f"无法通过用户名获取实体: {e2}")
                    try:
                        # 备用方案2: 使用 "me" 获取与自己的对话
                        logger.info("尝试使用 'me' 获取对话")
                        target_entity = await self.user_client.get_entity("me")
                    except Exception as e3:
                        logger.error(f"所有获取实体的方法都失败了: {e3}")
                        await status_message.edit_text(
                            "❌ 无法访问消息历史，可能是Telethon会话问题。请联系管理员。"
                        )
                        return

            async for msg in self.user_client.iter_messages(target_entity, limit=20):
                # 兼容两种媒体类型: document (视频/文件) 和 audio (作为音频发送)
                media_to_check = msg.media.document if hasattr(msg.media, 'document') else msg.media

                if media_to_check and hasattr(media_to_check, 'size') and media_to_check.size == file_size:
                    if abs((msg.date - bot_message_timestamp).total_seconds()) < time_window_seconds:
                        telethon_message = msg
                        logger.info(f"找到匹配消息，开始提取媒体属性...")
                        logger.info(f"Telethon 消息完整信息: {telethon_message}")
                        logger.info(f"Telethon 消息文本属性: '{telethon_message.text}'")
                        logger.info(f"Telethon 消息原始文本: '{telethon_message.raw_text}'")

                        # 检查是否为音频并提取元数据
                        if hasattr(media_to_check, 'attributes'):
                            logger.info(f"媒体属性列表: {[type(attr).__name__ for attr in media_to_check.attributes]}")

                            for attr in media_to_check.attributes:
                                logger.info(f"检查属性: {type(attr).__name__} - {attr}")

                                # 音频属性
                                if isinstance(attr, types.DocumentAttributeAudio):
                                    if hasattr(attr, 'bitrate'):
                                        audio_bitrate = attr.bitrate
                                    if hasattr(attr, 'duration'):
                                        audio_duration = attr.duration
                                    logger.info(f"提取到音频元数据: 码率={audio_bitrate}, 时长={audio_duration}")

                                # 视频属性
                                elif isinstance(attr, types.DocumentAttributeVideo):
                                    if hasattr(attr, 'w') and hasattr(attr, 'h'):
                                        video_width = attr.w
                                        video_height = attr.h
                                        logger.info(f"提取到视频元数据: 分辨率={video_width}x{video_height}")

                                    if hasattr(attr, 'duration'):
                                        video_duration = attr.duration
                                        logger.info(f"提取到视频时长: {video_duration}秒")

                                # 文档属性（可能包含文件名等信息）
                                elif isinstance(attr, types.DocumentAttributeFilename):
                                    logger.info(f"提取到文件名: {attr.file_name}")
                                    # 使用从 Telethon 提取的文件名，如果之前没有获取到文件名
                                    if not file_name or file_name == 'unknown_file':
                                        file_name = attr.file_name
                                        logger.info(f"使用 Telethon 文件名: {file_name}")

                                # 音频属性
                                if isinstance(attr, types.DocumentAttributeAudio):
                                    if hasattr(attr, 'bitrate'):
                                        audio_bitrate = attr.bitrate
                                    if hasattr(attr, 'duration'):
                                        audio_duration = attr.duration
                                    logger.info(f"提取到音频元数据: 码率={audio_bitrate}, 时长={audio_duration}")

                                # 视频属性
                                elif isinstance(attr, types.DocumentAttributeVideo):
                                    if hasattr(attr, 'w') and hasattr(attr, 'h'):
                                        video_width = attr.w
                                        video_height = attr.h
                                        logger.info(f"提取到视频元数据: 分辨率={video_width}x{video_height}")

                                    if hasattr(attr, 'duration'):
                                        video_duration = attr.duration
                                        logger.info(f"提取到视频时长: {video_duration}秒")

                        break # 找到匹配项，跳出循环

            # 如果还没有文件名，尝试从 Telethon 消息文本中提取
            if (not file_name or file_name == 'unknown_file') and telethon_message:
                logger.info(f"Telethon 消息文本: '{telethon_message.text}'")
                if telethon_message.text and telethon_message.text.strip():
                    raw_text = telethon_message.text.strip()
                    logger.info(f"从 Telethon 消息文本中提取原始文本: {raw_text}")
                    
                    # 清理消息文本，提取可能的标题
                    # 移除常见的标签和符号
                    clean_text = re.sub(r'[#@]\w+', '', raw_text).strip()
                    # 移除多余的空格和换行
                    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
                    # 限制长度
                    if len(clean_text) > 50:
                        clean_text = clean_text[:50]
                    
                    if clean_text:
                        # 使用清理后的文本作为文件名
                        file_name = clean_text
                        logger.info(f"使用清理后的文本作为文件名: {file_name}")
                    else:
                        # 如果清理后为空，使用原始文本的第一行
                        first_line = raw_text.splitlines()[0].strip()
                        if first_line:
                            # 移除#号但保留其他内容
                            first_line = re.sub(r'^#+\s*', '', first_line).strip()
                            if first_line:
                                file_name = first_line
                                logger.info(f"使用第一行作为文件名: {file_name}")
                            else:
                                file_name = 'unknown_file'
                        else:
                            file_name = 'unknown_file'
                    
                    if file_name == 'unknown_file':
                        logger.info("无法从消息文本中提取有效文件名")
                    else:
                        logger.info(f"最终提取的文件名: {file_name}")
                else:
                    logger.info("Telethon 消息文本为空或只包含空白字符")

            # 兜底机制：如果还是没有文件名，使用文档ID生成文件名
            if not file_name or file_name == 'unknown_file':
                if telethon_message and hasattr(telethon_message.media, 'document'):
                    doc_id = telethon_message.media.document.id
                    logger.info(f"兜底机制触发 - 文件大小: {file_size} bytes, 视频分辨率: {video_width}x{video_height}, 音频时长: {audio_duration}")
                    
                    # 根据检测到的文件类型生成文件名
                    if video_width is not None and video_height is not None:
                        # 回退到使用文档ID，但添加分辨率信息
                        file_name = f"video_{video_width}x{video_height}_{doc_id}.mp4"
                        logger.info(f"使用分辨率+ID作为视频文件名: {file_name}")
                    elif audio_duration is not None and audio_bitrate is not None:
                        # 回退到使用文档ID，但添加时长信息
                        duration_min = int(audio_duration // 60)
                        duration_sec = int(audio_duration % 60)
                        file_name = f"audio_{duration_min:02d}_{duration_sec:02d}_{doc_id}.mp3"
                        logger.info(f"使用时长+ID作为音频文件名: {file_name}")
                    else:
                        # 如果无法确定类型，但文件大小较大，很可能是视频文件
                        if file_size > 1024 * 1024:  # 大于1MB
                            file_name = f"video_{doc_id}.mp4"
                            logger.info(f"文件大小较大({file_size} bytes)，推测为视频文件，使用 .mp4 扩展名")
                        else:
                            file_name = f"file_{doc_id}.bin"
                            logger.info(f"文件大小较小({file_size} bytes)，使用 .bin 扩展名")
                    logger.info(f"最终生成的文件名: {file_name}")

            # 根据媒体类型确定下载路径
            # 改进音频检测：不仅检查DocumentAttributeAudio，也检查文件扩展名
            is_audio_file = False
            if audio_duration is not None and audio_bitrate is not None:
                is_audio_file = True
            elif file_name and any(file_name.lower().endswith(ext) for ext in ['.mp3', '.m4a', '.flac', '.wav', '.ogg', '.aac', '.wma', '.opus']):
                is_audio_file = True
                logger.info(f"通过文件扩展名检测到音频文件: {file_name}")

            # 改进视频检测：不仅检查DocumentAttributeVideo，也检查文件扩展名
            is_video_file = False
            if video_width is not None and video_height is not None:
                is_video_file = True
            elif file_name and any(file_name.lower().endswith(ext) for ext in ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.3gp', '.ts']):
                is_video_file = True
                logger.info(f"通过文件扩展名检测到视频文件: {file_name}")

            if is_audio_file:
                # 音频文件放在telegram/music文件夹
                download_path = os.path.join(self.downloader.download_path, "telegram", "music")
                logger.info(f"检测到音频文件，下载路径: {download_path}")
            elif is_video_file:
                # 视频文件放在telegram/videos文件夹
                download_path = os.path.join(self.downloader.download_path, "telegram", "videos")
                logger.info(f"检测到视频文件，下载路径: {download_path}")
            else:
                # 其他文件放在telegram文件夹
                download_path = os.path.join(self.downloader.download_path, "telegram")
                logger.info(f"检测到其他媒体文件，下载路径: {download_path}")

            os.makedirs(download_path, exist_ok=True)
            if telethon_message:
                logger.info(f"找到匹配的Telethon消息: {telethon_message.id}，开始下载...")

                # 添加详细的调试信息
                logger.info(f"消息类型: {type(telethon_message)}")
                logger.info(f"消息媒体: {type(telethon_message.media) if telethon_message.media else 'None'}")
                if telethon_message.media:
                    logger.info(f"媒体属性: {dir(telethon_message.media)}")
                    if hasattr(telethon_message.media, 'document'):
                        logger.info(f"Document: {telethon_message.media.document}")
                    else:
                        logger.info(f"直接媒体: {telethon_message.media}")

                # --- 下载回调 (统一为详细样式) ---
                last_update_time = time.time()
                last_downloaded = 0
                async def progress(current, total):
                    nonlocal last_update_time, last_downloaded
                    now = time.time()

                    if now - last_update_time < 5 and current != total:
                        return

                    diff_time = now - last_update_time
                    diff_bytes = current - last_downloaded
                    last_update_time = now
                    last_downloaded = current

                    speed_bytes_s = diff_bytes / diff_time if diff_time > 0 else 0
                    speed_mb_s = speed_bytes_s / (1024 * 1024)
                    eta_str = "未知"
                    if speed_bytes_s > 0:
                        remaining_bytes = total - current
                        try:
                            eta_seconds = remaining_bytes / speed_bytes_s
                            minutes, seconds = divmod(int(eta_seconds), 60)
                            eta_str = f"{minutes:02d}:{seconds:02d}"
                        except (OverflowError, ValueError):
                            eta_str = "未知"

                    downloaded_mb = current / (1024 * 1024)
                    total_mb = total / (1024 * 1024)
                    # 修复：检查file_name是否为None
                    display_filename = file_name if file_name else "未知文件"
                    percent = current * 100 / total if total > 0 else 0
                    bar = self._make_progress_bar(percent)
                    
                    progress_text = (
                        f"📝 文件：{display_filename}\n"
                        f"💾 大小：{downloaded_mb:.2f}MB / {total_mb:.2f}MB\n"
                        f"⚡ 速度：{speed_mb_s:.2f}MB/s\n"
                        f"⏳ 预计剩余：{eta_str}\n"
                        f"📊 进度：{bar}"
                    )
                    try:
                        if current != total:
                            await context.bot.edit_message_text(
                                text=progress_text,
                                chat_id=chat_id,
                                message_id=status_message.message_id,
                                parse_mode=None
                            )
                    except Exception as e:
                        if "Message is not modified" not in str(e):
                            logger.warning(f"更新TG下载进度时出错: {e}")

                try:
                    # 生成唯一文件名，防止覆盖
                    def get_unique_filename(base_path, filename):
                        name, ext = os.path.splitext(filename)
                        counter = 1
                        unique_filename = filename
                        while os.path.exists(os.path.join(base_path, unique_filename)):
                            unique_filename = f"{name}_{counter}{ext}"
                            counter += 1
                        return unique_filename

                    unique_file_name = get_unique_filename(download_path, file_name)
                    downloaded_file = await self.user_client.download_media(
                        telethon_message,
                        file=os.path.join(download_path, unique_file_name),
                        progress_callback=progress
                    )
                    if downloaded_file:
                        # 下载成功，获取文件信息
                        file_size_mb = os.path.getsize(downloaded_file) / (1024 * 1024)

                        # 检查是否为音频文件
                        file_extension = os.path.splitext(downloaded_file)[1].lower()
                        is_audio_file = file_extension in ['.mp3', '.flac', '.wav', '.aac', '.ogg', '.m4a', '.wma']

                        logger.info(f"🎵 音频文件检测: 文件扩展名={file_extension}, 是否为音频文件={is_audio_file}")
                        logger.info(f"🎵 Telegram元数据: 码率={audio_bitrate}, 时长={audio_duration}")

                        # 对于音频文件，强制尝试获取音频信息
                        if is_audio_file:
                            try:
                                logger.info(f"🎵 开始提取音频文件信息: {downloaded_file}")
                                media_info = self.downloader.get_media_info(downloaded_file)
                                logger.info(f"🎵 get_media_info返回: {media_info}")

                                # 如果没有码率信息，从文件中提取
                                if not audio_bitrate and media_info.get('bit_rate'):
                                    # 从字符串中提取数字，如 "320 kbps" -> 320
                                    bit_rate_str = str(media_info.get('bit_rate', ''))
                                    import re
                                    match = re.search(r'(\d+)', bit_rate_str)
                                    if match:
                                        audio_bitrate = int(match.group(1))
                                        logger.info(f"✅ 从文件提取到音频码率: {audio_bitrate}kbps")
                                    else:
                                        logger.warning(f"⚠️ 无法从码率字符串提取数字: {bit_rate_str}")

                                # 如果没有时长信息，从文件中提取
                                if not audio_duration and media_info.get('duration'):
                                    duration_from_file = media_info.get('duration')
                                    # 检查是否为格式化的时间字符串（如 "03:47"）
                                    if isinstance(duration_from_file, str) and ':' in duration_from_file:
                                        # 解析时间字符串为秒数
                                        try:
                                            time_parts = duration_from_file.split(':')
                                            if len(time_parts) == 2:  # MM:SS
                                                minutes, seconds = map(int, time_parts)
                                                audio_duration = minutes * 60 + seconds
                                            elif len(time_parts) == 3:  # HH:MM:SS
                                                hours, minutes, seconds = map(int, time_parts)
                                                audio_duration = hours * 3600 + minutes * 60 + seconds
                                            else:
                                                audio_duration = float(duration_from_file)
                                        except ValueError:
                                            logger.warning(f"⚠️ 无法解析时长字符串: {duration_from_file}")
                                    else:
                                        # 直接使用数字时长
                                        audio_duration = float(duration_from_file)
                                    logger.info(f"✅ 从文件提取到音频时长: {audio_duration}秒")

                                # 如果仍然没有获取到信息，尝试使用ffprobe
                                if not audio_bitrate or not audio_duration:
                                    logger.info(f"🔍 尝试使用ffprobe获取音频信息")
                                    try:
                                        import subprocess
                                        import json

                                        cmd = [
                                            'ffprobe', '-loglevel', 'quiet', '-print_format', 'json',
                                            '-show_format', '-show_streams', downloaded_file
                                        ]
                                        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

                                        if result.returncode == 0:
                                            probe_data = json.loads(result.stdout)
                                            logger.info(f"🔍 ffprobe返回数据: {probe_data}")

                                            # 从streams中获取音频信息
                                            for stream in probe_data.get('streams', []):
                                                if stream.get('codec_type') == 'audio':
                                                    if not audio_bitrate and 'bit_rate' in stream:
                                                        audio_bitrate = int(int(stream['bit_rate']) / 1000)  # 转换为kbps
                                                        logger.info(f"✅ ffprobe从streams获取到码率: {audio_bitrate}kbps")
                                                    break

                                            # 从format中获取码率和时长信息
                                            if 'format' in probe_data:
                                                format_info = probe_data['format']

                                                # 如果streams中没有码率信息，尝试从format中获取
                                                if not audio_bitrate and 'bit_rate' in format_info:
                                                    audio_bitrate = int(int(format_info['bit_rate']) / 1000)  # 转换为kbps
                                                    logger.info(f"✅ ffprobe从format获取到码率: {audio_bitrate}kbps")

                                                # 获取时长信息
                                                if (not audio_duration or not isinstance(audio_duration, (int, float))) and 'duration' in format_info:
                                                    audio_duration = float(format_info['duration'])
                                                    logger.info(f"✅ ffprobe获取到时长: {audio_duration}秒")
                                        else:
                                            logger.warning(f"⚠️ ffprobe执行失败: {result.stderr}")
                                    except Exception as ffprobe_error:
                                        logger.warning(f"⚠️ ffprobe执行异常: {ffprobe_error}")

                            except Exception as e:
                                logger.warning(f"❌ 无法从文件提取音频信息: {e}")

                        # 确保 audio_duration 是数字类型
                        if audio_duration and isinstance(audio_duration, str) and ':' in audio_duration:
                            # 如果是时间字符串格式，解析为秒数
                            try:
                                time_parts = audio_duration.split(':')
                                if len(time_parts) == 2:  # MM:SS
                                    minutes, seconds = map(int, time_parts)
                                    audio_duration = minutes * 60 + seconds
                                elif len(time_parts) == 3:  # HH:MM:SS
                                    hours, minutes, seconds = map(int, time_parts)
                                    audio_duration = hours * 3600 + minutes * 60 + seconds
                                logger.info(f"🔧 解析时长字符串 '{':'.join(time_parts)}' 为 {audio_duration} 秒")
                            except ValueError as e:
                                logger.warning(f"⚠️ 无法解析时长字符串 '{audio_duration}': {e}")

                        logger.info(f"🎵 最终音频信息: 码率={audio_bitrate}, 时长={audio_duration}")

                        # 构建成功消息
                        success_text = f"✅ 文件下载完成\n\n"
                        success_text += f"📝 文件名: {file_name}\n"
                        success_text += f"💾 文件大小: {file_size_mb:.2f}MB\n"

                        # 如果有视频分辨率信息，显示在文件大小下面
                        if video_width and video_height:
                            # 判断分辨率等级
                            resolution_label = ""
                            max_dimension = max(video_width, video_height)
                            if max_dimension >= 3840:  # 4K
                                resolution_label = " (4K)"
                            elif max_dimension >= 2560:  # 2K
                                resolution_label = " (2K)"
                            elif max_dimension >= 1920:  # 1080p
                                resolution_label = " (1080p)"
                            elif max_dimension >= 1280:  # 720p
                                resolution_label = " (720p)"
                            elif max_dimension >= 854:   # 480p
                                resolution_label = " (480p)"

                            success_text += f"🎥 分辨率: {video_width}x{video_height}{resolution_label}\n"

                        # 如果是音频文件，显示码率信息
                        if is_audio_file and audio_bitrate:
                            success_text += f"🎵 码率: {audio_bitrate}kbps\n"

                        # 显示时长信息（音频或视频）
                        duration_to_show = audio_duration if is_audio_file else video_duration
                        if duration_to_show:
                            minutes, seconds = divmod(int(duration_to_show), 60)
                            duration_str = f"{minutes:02d}:{seconds:02d}"
                            success_text += f"⏱️ 时长: {duration_str}\n"

                        success_text += f"📁 保存路径: {os.path.dirname(downloaded_file)}"

                        await context.bot.edit_message_text(
                            text=success_text,
                            chat_id=chat_id,
                            message_id=status_message.message_id,
                                parse_mode=None
                        )
                        logger.info(f"✅ 媒体文件下载完成: {downloaded_file}")
                    else:
                        await context.bot.edit_message_text(
                            text="❌ 下载失败：无法获取文件",
                            chat_id=chat_id,
                            message_id=status_message.message_id
                        )
                        logger.error("❌ 媒体文件下载失败：无法获取文件")

                except Exception as e:
                    logger.error(f"❌ 媒体文件下载失败: {e}", exc_info=True)
                    await context.bot.edit_message_text(
                        text=f"❌ 下载失败: {str(e)}",
                        chat_id=chat_id,
                        message_id=status_message.message_id
                    )
            else:
                await context.bot.edit_message_text(
                    text="❌ 无法找到匹配的媒体消息，请重试",
                    chat_id=chat_id,
                    message_id=status_message.message_id
                )
                logger.error("❌ 无法找到匹配的Telethon消息")

        except Exception as e:
            logger.error(f"❌ 处理媒体消息时出错: {e}", exc_info=True)
            await context.bot.edit_message_text(
                text=f"❌ 处理失败: {str(e)}",
                chat_id=chat_id,
                message_id=status_message.message_id
            )

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """记录所有 PTB 抛出的错误并处理网络错误"""
        error = context.error
        error_msg = str(error)
        error_type = type(error).__name__

        # 检查是否为网络相关错误
        is_network_error = any(keyword in error_msg.lower() for keyword in [
            'connection', 'timeout', 'network', 'remote', 'protocol',
            'httpx', 'telegram', 'api', 'server', 'unavailable',
            'connecterror', 'timeoutexception', 'httperror', 'ssl',
            'dns', 'resolve', 'unreachable', 'refused', 'reset',
            'broken pipe', 'connection reset', 'connection aborted',
            'read timeout', 'write timeout', 'connect timeout',
            'pool timeout', 'proxy', 'gateway', 'service unavailable'
        ])

        if is_network_error:
            logger.warning(f"🌐 检测到网络错误: {error_type}: {error_msg}")
            logger.info("🔄 网络错误将由健康检查机制自动处理")
        else:
            logger.error(f"❌ PTB 错误: {error_type}: {error_msg}", exc_info=error)

        # 对于严重的网络错误，触发立即健康检查
        if is_network_error and any(critical in error_msg.lower() for critical in [
            'connection reset', 'connection aborted', 'broken pipe', 'ssl'
        ]):
            logger.warning("🚨 检测到严重网络错误，触发立即健康检查")
            # 这里可以触发立即的健康检查，但要避免递归调用

    def _make_progress_bar(self, percent: float) -> str:
        """生成进度条"""
        bar_length = 20
        filled_length = int(bar_length * percent / 100)
        bar = "█" * filled_length + "░" * (bar_length - filled_length)
        return f"[{bar}] {percent:.1f}%"


class GlobalProgressManager:
    """全局进度管理器，统一管理所有下载任务的进度更新"""

    def __init__(self):
        self.last_update_time = time.time()
        self.update_interval = 15  # 全局更新间隔15秒
        self.active_downloads = {}  # 存储活跃下载任务
        self.lock = asyncio.Lock()

    async def update_progress(
        self, task_id: str, progress_data: dict, context, status_message
    ):
        """更新单个任务的进度"""
        async with self.lock:
            self.active_downloads[task_id] = progress_data

            now = time.time()
            if now - self.last_update_time < self.update_interval:
                return  # 未到更新时间

            # 构建汇总进度消息
            await self._send_summary_progress(context, status_message)
            self.last_update_time = now

    async def _send_summary_progress(self, context, status_message):
        """发送汇总进度消息"""
        if not self.active_downloads:
            return

        total_tasks = len(self.active_downloads)
        completed_tasks = sum(
            1
            for data in self.active_downloads.values()
            if data.get("status") == "finished"
        )

        # 构建进度消息
        progress_lines = []
        progress_lines.append(f"📦 **批量下载进度** ({completed_tasks}/{total_tasks})")

        # 显示前3个活跃任务
        active_tasks = [
            data
            for data in self.active_downloads.values()
            if data.get("status") == "downloading"
        ][:3]

        for i, data in enumerate(active_tasks, 1):
            filename = os.path.basename(data.get("filename", "未知文件"))
            progress = data.get("progress", 0)
            speed = data.get("speed", 0)

            if speed and speed > 0:
                speed_mb = speed / (1024 * 1024)
                speed_str = f"{speed_mb:.1f}MB/s"
            else:
                speed_str = "未知"

            progress_lines.append(f"{i}. `{filename}` - {progress:.1f}% ({speed_str})")

        if len(active_tasks) < total_tasks - completed_tasks:
            remaining = total_tasks - completed_tasks - len(active_tasks)
            progress_lines.append(f"... 还有 {remaining} 个任务进行中")

        progress_text = "\n".join(progress_lines)

        try:
            await context.bot.edit_message_text(
                text=progress_text,
                chat_id=status_message.chat_id,
                message_id=status_message.message_id,
                                parse_mode=None,
            )
        except Exception as e:
            if "Message is not modified" not in str(e) and "Flood control" not in str(
                e
            ):
                logger.warning(f"更新汇总进度失败: {e}")

    def remove_task(self, task_id: str):
        """移除完成的任务"""
        if task_id in self.active_downloads:
            del self.active_downloads[task_id]


# 全局进度管理器实例
global_progress_manager = GlobalProgressManager()


async def test_network_connectivity():
    """测试网络连接性"""
    import httpx
    test_urls = [
        "https://api.telegram.org",
        "https://www.google.com",
        "https://1.1.1.1"
    ]

    for url in test_urls:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    logger.debug(f"🟢 网络连接测试成功: {url}")
                    return True
        except Exception as e:
            logger.warning(f"🟡 网络连接测试失败: {url} - {e}")
            continue

    logger.error(f"🔴 所有网络连接测试都失败")
    return False

async def main():
    """主函数 (异步)"""
    # 启动时环境检查
    logger.info("🔍 开始启动前环境检查...")

    # 读取 TOML 配置文件
    toml_config = {}
    if load_toml_config:
        toml_config = load_toml_config()
        if toml_config:
            logger.info("✅ 成功读取 TOML 配置文件")
            print_config_summary(toml_config)
        else:
            logger.warning("⚠️ TOML 配置文件不存在或读取失败，将使用环境变量")
    else:
        logger.warning("⚠️ 配置读取器不可用，将使用环境变量")

    # 获取 Telegram 配置
    if toml_config and load_toml_config:
        telegram_config = get_telegram_config(toml_config)
        proxy_config = get_proxy_config(toml_config)
        
        # 从 TOML 配置获取 Telegram 参数
        bot_token = telegram_config.get('bot_token', '') or os.getenv("TELEGRAM_BOT_TOKEN", "")
        allowed_user_ids = telegram_config.get('allowed_user_ids', '') or os.getenv("TELEGRAM_BOT_ALLOWED_USER_IDS", "")
        api_id = telegram_config.get('api_id', '') or os.getenv("TELEGRAM_BOT_API_ID", "")
        api_hash = telegram_config.get('api_hash', '') or os.getenv("TELEGRAM_BOT_API_HASH", "")
        proxy_host = proxy_config.get('proxy_host', '') or os.getenv("PROXY_HOST", "")
        
        # 设置为环境变量以保持其他代码的兼容性
        if proxy_host:
            os.environ['PROXY_HOST'] = proxy_host
            logger.info(f"🌐 从 TOML 配置设置代理: {proxy_host}")
        if api_id:
            os.environ['TELEGRAM_BOT_API_ID'] = str(api_id)
            logger.info(f"🔑 从 TOML 配置设置 API ID: {api_id}")
        if api_hash:
            os.environ['TELEGRAM_BOT_API_HASH'] = api_hash
            logger.info(f"🔐 从 TOML 配置设置 API Hash: {api_hash[:10]}...")
        if allowed_user_ids:
            os.environ['TELEGRAM_BOT_ALLOWED_USER_IDS'] = str(allowed_user_ids)
            logger.info(f"👥 从 TOML 配置设置允许的用户ID: {allowed_user_ids}")
    else:
        # 回退到环境变量
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        logger.info("🔧 使用环境变量配置")

    # 检查关键配置
    if not bot_token:
        logger.error("❌ 请在 TOML 配置文件或环境变量中设置 TELEGRAM_BOT_TOKEN")
        sys.exit(1)

    # 网络连接测试和健康检查
    logger.info("🔍 开始网络连接测试...")
    if not await test_network_connectivity(proxy_config.get("proxy_host")):
        logger.warning("⚠️ 网络连接测试失败，但将继续尝试启动")
        # 不要直接退出，继续尝试启动，可能是测试URL的问题

    # 健康检查功能已删除，避免事件循环冲突
    logger.info("健康检查功能已禁用，避免事件循环冲突")
    # 硬编码下载路径为 /downloads
    download_path = "/downloads"
    
    # 统一cookies目录配置
    cookies_base_dir = "/app/cookies"
    x_cookies_path = os.getenv("X_COOKIES") or f"{cookies_base_dir}/x_cookies.txt"
    b_cookies_path = os.getenv("BILIBILI_COOKIES") or os.getenv("B_COOKIES") or f"{cookies_base_dir}/bilibili_cookies.txt"
    youtube_cookies_path = os.getenv("YOUTUBE_COOKIES") or f"{cookies_base_dir}/youtube_cookies.txt"
    douyin_cookies_path = os.getenv("DOUYIN_COOKIES") or f"{cookies_base_dir}/douyin_cookies.txt"
    kuaishou_cookies_path = os.getenv("KUAISHOU_COOKIES") or f"{cookies_base_dir}/kuaishou_cookies.txt"
    instagram_cookies_path = os.getenv("INSTAGRAM_COOKIES") or f"{cookies_base_dir}/instagram_cookies.txt"

    logger.info(f"📁 下载路径: {download_path}")
    if x_cookies_path:
        logger.info(f"X Cookies 路径: {x_cookies_path}")
    if b_cookies_path:
        logger.info(f"Bilibili Cookies 路径: {b_cookies_path}")
    if youtube_cookies_path:
        logger.info(f"🍪 使用YouTube cookies: {youtube_cookies_path}")
    if douyin_cookies_path:
        logger.info(f"🎬 使用抖音 cookies: {douyin_cookies_path}")
        # 检查文件是否存在
        if os.path.exists(douyin_cookies_path):
            file_size = os.path.getsize(douyin_cookies_path)
            logger.info(f"✅ 抖音 cookies 文件存在，大小: {file_size} 字节")

            # 读取并显示前几行内容
            try:
                with open(douyin_cookies_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    logger.info(f"📄 抖音 cookies 文件包含 {len(lines)} 行")
                    if lines:
                        logger.info(f"📝 第一行内容: {lines[0].strip()}")
                        if len(lines) > 1:
                            logger.info(f"📝 第二行内容: {lines[1].strip()}")
            except Exception as e:
                logger.error(f"❌ 读取抖音 cookies 文件失败: {e}")
        else:
            logger.warning(f"⚠️ 抖音 cookies 文件不存在: {douyin_cookies_path}")
    else:
        logger.warning("⚠️ 未设置 DOUYIN_COOKIES 环境变量")

    # 检查快手cookies
    if kuaishou_cookies_path:
        logger.info(f"⚡ 使用快手 cookies: {kuaishou_cookies_path}")
        # 检查文件是否存在
        if os.path.exists(kuaishou_cookies_path):
            file_size = os.path.getsize(kuaishou_cookies_path)
            logger.info(f"✅ 快手 cookies 文件存在，大小: {file_size} 字节")

            # 读取并显示前几行内容
            try:
                with open(kuaishou_cookies_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    logger.info(f"📄 快手 cookies 文件包含 {len(lines)} 行")
                    if lines:
                        logger.info(f"📝 第一行内容: {lines[0].strip()}")
                        if len(lines) > 1:
                            logger.info(f"📝 第二行内容: {lines[1].strip()}")
            except Exception as e:
                logger.error(f"❌ 读取快手 cookies 文件失败: {e}")
        else:
            logger.warning(f"⚠️ 快手 cookies 文件不存在: {kuaishou_cookies_path}")
    else:
        logger.warning("⚠️ 未设置 KUAISHOU_COOKIES 环境变量")

    # 确保下载目录存在
    download_path_obj = Path(download_path)
    download_path_obj.mkdir(parents=True, exist_ok=True)
    
    # 确保cookies目录存在
    cookies_dir = Path(cookies_base_dir)
    cookies_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"📁 确保cookies目录存在: {cookies_base_dir}")
    
    # 确保 AppleMusic 子目录存在
    apple_music_path = download_path_obj / "AppleMusic"
    apple_music_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"📁 确保下载目录存在: {download_path}")
    logger.info(f"📁 确保 AppleMusic 子目录存在: {apple_music_path}")
    
    # 创建下载器和机器人
    downloader = VideoDownloader(
        download_path, x_cookies_path, b_cookies_path, youtube_cookies_path, douyin_cookies_path, kuaishou_cookies_path, None, instagram_cookies_path
    )
    bot = TelegramBot(bot_token, downloader)

    # 将 bot 实例注册到 Flask 应用，供 Web 接口使用
    app._bot_instance = bot

    # 在后台线程中启动 Flask 应用（仅用于 Telegram 会话生成）
    def run_flask():
        try:
            # 硬编码端口为8530
            web_port = 8530

            logger.info(f"🌐 启动内置Flask服务（仅用于 Telegram 会话生成）")
            logger.info(f"   🔍 Web端口: {web_port} (包含 /setup)")

            app.run(host="0.0.0.0", port=web_port, debug=False, use_reloader=False)
        except Exception as e:
            logger.error(f"❌ Flask启动失败: {e}")

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("✅ Flask Telegram 会话生成服务已启动")

    # 直接启动机器人
    logger.info("🚀 启动Telegram Bot...")
    await bot.run()
    logger.info("✅ Telegram Bot启动成功！")

    # ==================== B站收藏夹订阅功能 ====================




if __name__ == "__main__":
    try:
        # 心跳更新已删除  # 初始化心跳
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("机器人已停止。")





























