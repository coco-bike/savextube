# -*- coding: utf-8 -*-
"""
文件处理工具
文件名清理、路径处理、文件查找等
"""

import os
import re
from pathlib import Path
from typing import Optional, Set


def clean_filename(filename: str, max_length: int = 100) -> str:
    """
    清理文件名，移除非法字符
    
    Args:
        filename: 原始文件名
        max_length: 最大长度
        
    Returns:
        清理后的文件名
    """
    # 移除非法字符
    illegal_chars = r'[<>:"/\\|？*]'
    cleaned = re.sub(illegal_chars, '', filename)
    
    # 替换多个空格为单个空格
    cleaned = re.sub(r'\s+', ' ', cleaned)
    
    # 截断到最大长度
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length]
    
    return cleaned.strip()


def sanitize_for_filename(text: str) -> str:
    """
    将文本转换为适合文件名的格式
    
    Args:
        text: 输入文本
        
    Returns:
        适合文件名的文本
    """
    # 移除或替换特殊字符
    text = re.sub(r'[\\/:*?"<>|]', '_', text)
    
    # 移除控制字符
    text = ''.join(char for char in text if ord(char) >= 32)
    
    return text.strip()


def find_downloaded_file(
    download_path: Path,
    title: str,
    extensions: Optional[Set[str]] = None,
    time_threshold: int = 300
) -> Optional[str]:
    """
    在下载目录中查找刚下载的文件
    
    Args:
        download_path: 下载目录
        title: 文件标题
        extensions: 文件扩展名集合
        time_threshold: 时间阈值（秒）
        
    Returns:
        文件路径，未找到返回 None
    """
    import time
    
    if extensions is None:
        extensions = {'.mp4', '.mkv', '.webm', '.avi', '.mov', '.m4a', '.mp3', '.flac'}
    
    current_time = time.time()
    safe_title = sanitize_for_filename(title)
    
    # 1. 尝试精确匹配标题
    for ext in extensions:
        expected_file = download_path / f"{safe_title}{ext}"
        if expected_file.exists():
            return str(expected_file)
    
    # 2. 尝试模糊匹配（包含标题）
    for file_path in download_path.rglob('*'):
        if file_path.is_file() and file_path.suffix.lower() in extensions:
            if safe_title.lower() in file_path.name.lower():
                # 检查文件修改时间
                mtime = file_path.stat().st_mtime
                if current_time - mtime <= time_threshold:
                    return str(file_path)
    
    # 3. 查找最新的视频文件
    all_files = []
    for file_path in download_path.rglob('*'):
        if file_path.is_file() and file_path.suffix.lower() in extensions:
            mtime = file_path.stat().st_mtime
            all_files.append((file_path, mtime))
    
    if all_files:
        all_files.sort(key=lambda x: x[1], reverse=True)
        return str(all_files[0][0])
    
    return None


def format_file_size(size_bytes: int) -> str:
    """
    格式化文件大小显示
    
    Args:
        size_bytes: 字节数
        
    Returns:
        格式化后的大小字符串
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def format_speed(speed_bps: float) -> str:
    """
    格式化速度显示
    
    Args:
        speed_bps: 字节/秒
        
    Returns:
        格式化后的速度字符串
    """
    if speed_bps is None or speed_bps == 0:
        return "0 B/s"
    
    for unit in ['B/s', 'KB/s', 'MB/s', 'GB/s']:
        if speed_bps < 1024.0:
            return f"{speed_bps:.2f} {unit}"
        speed_bps /= 1024.0
    return f"{speed_bps:.2f} TB/s"


def create_progress_bar(percent: float, length: int = 20) -> str:
    """
    创建进度条
    
    Args:
        percent: 百分比（0-100）
        length: 进度条长度
        
    Returns:
        进度条字符串
    """
    filled_length = int(length * percent / 100)
    bar = '█' * filled_length + '░' * (length - filled_length)
    return bar


def ensure_dir_exists(path: Path) -> None:
    """
    确保目录存在，不存在则创建
    
    Args:
        path: 目录路径
    """
    path.mkdir(parents=True, exist_ok=True)


def get_download_path_by_platform(base_path: Path, platform: str) -> Path:
    """
    根据平台获取下载路径
    
    Args:
        base_path: 基础下载目录
        platform: 平台名称
        
    Returns:
        平台对应的下载目录
    """
    platform_dirs = {
        'youtube': 'YouTube',
        'bilibili': 'Bilibili',
        'instagram': 'Instagram',
        'tiktok': 'TikTok',
        'twitter': 'X',
        'x': 'X',
        'douyin': 'Douyin',
        'kuaishou': 'Kuaishou',
        'netease': 'NeteaseCloudMusic',
        'qqmusic': 'QQMusic',
        'applemusic': 'AppleMusic',
        'youtubemusic': 'YouTubeMusic',
    }
    
    subdir = platform_dirs.get(platform.lower(), platform.capitalize())
    return base_path / subdir
