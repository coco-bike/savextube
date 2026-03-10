# -*- coding: utf-8 -*-
"""
URL 提取工具模块
支持从文本中提取各种链接（HTTP、磁力、Torrent 等）
"""

import re
from typing import List


class URLExtractor:
    """URL 提取器"""
    
    @staticmethod
    def extract_all_urls(text: str) -> List[str]:
        """
        从文本中提取所有 URL 链接
        
        Args:
            text: 输入文本
            
        Returns:
            URL 列表（已去重）
        """
        urls = []
        
        # HTTP/HTTPS 链接
        urls.extend(re.findall(r'https?://[^\s]+', text))
        
        # 磁力链接
        urls.extend(re.findall(r'magnet:\?xt=urn:btih:[a-fA-F0-9]{32,40}[^\s]*', text))
        
        # Torrent 链接
        urls.extend(re.findall(r'https?://[^\s]*\.torrent[^\s]*', text))
        
        # 去重并保持顺序
        return list(dict.fromkeys(urls))
    
    @staticmethod
    def extract_http_urls(text: str) -> List[str]:
        """提取 HTTP/HTTPS 链接"""
        return re.findall(r'https?://[^\s]+', text)
    
    @staticmethod
    def extract_magnet_links(text: str) -> List[str]:
        """提取磁力链接"""
        return re.findall(r'magnet:\?xt=urn:btih:[a-fA-F0-9]{32,40}[^\s]*', text)
    
    @staticmethod
    def extract_torrent_links(text: str) -> List[str]:
        """提取 Torrent 链接"""
        return re.findall(r'https?://[^\s]*\.torrent[^\s]*', text)
    
    @staticmethod
    def is_valid_url(url: str) -> bool:
        """检查是否为有效的 URL"""
        patterns = [
            r'^https?://[^\s]+$',
            r'^magnet:\?xt=urn:btih:[a-fA-F0-9]{32,40}[^\s]*$',
            r'^https?://[^\s]*\.torrent[^\s]*$'
        ]
        return any(re.match(pattern, url) for pattern in patterns)
    
    @staticmethod
    def is_youtube_url(url: str) -> bool:
        """检查是否为 YouTube URL"""
        return 'youtube.com' in url or 'youtu.be' in url
    
    @staticmethod
    def is_bilibili_url(url: str) -> bool:
        """检查是否为 Bilibili URL"""
        return 'bilibili.com' in url or 'b23.tv' in url
    
    @staticmethod
    def is_music_url(url: str) -> bool:
        """检查是否为音乐平台 URL"""
        music_domains = [
            'music.163.com',  # 网易云
            'y.qq.com',       # QQ 音乐
            'youtube.com',    # YouTube Music
            'music.apple.com' # Apple Music
        ]
        return any(domain in url for domain in music_domains)
