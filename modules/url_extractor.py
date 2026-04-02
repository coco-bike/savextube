# -*- coding: utf-8 -*-
"""
URL 提取工具模块
支持从文本中提取各种链接（HTTP、磁力、Torrent 等）
"""

import re
import unicodedata
from typing import List


class URLExtractor:
    """URL 提取器"""

    @staticmethod
    def _normalize_url(url: str) -> str:
        """清理复制链接时混入的不可见字符和尾部标点。"""
        if not isinstance(url, str):
            return url

        cleaned = unicodedata.normalize("NFKC", url).strip()
        cleaned = "".join(
            ch for ch in cleaned if unicodedata.category(ch) not in {"Cf", "Cc"}
        )
        cleaned = cleaned.rstrip('.,;!?，。；！？)]}>"\'')
        return cleaned

    @classmethod
    def _normalize_urls(cls, urls: List[str]) -> List[str]:
        return [cls._normalize_url(u) for u in urls if u]

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

        urls = URLExtractor._normalize_urls(urls)

        # 去重并保持顺序
        return list(dict.fromkeys(urls))

    @staticmethod
    def extract_http_urls(text: str) -> List[str]:
        """提取 HTTP/HTTPS 链接"""
        urls = re.findall(r'https?://[^\s]+', text)
        return URLExtractor._normalize_urls(urls)

    @staticmethod
    def extract_magnet_links(text: str) -> List[str]:
        """提取磁力链接"""
        urls = re.findall(r'magnet:\?xt=urn:btih:[a-fA-F0-9]{32,40}[^\s]*', text)
        return URLExtractor._normalize_urls(urls)

    @staticmethod
    def extract_torrent_links(text: str) -> List[str]:
        """提取 Torrent 链接"""
        urls = re.findall(r'https?://[^\s]*\.torrent[^\s]*', text)
        return URLExtractor._normalize_urls(urls)

    @staticmethod
    def is_valid_url(url: str) -> bool:
        """检查是否为有效的 URL"""
        normalized = URLExtractor._normalize_url(url)
        patterns = [
            r'^https?://[^\s]+$',
            r'^magnet:\?xt=urn:btih:[a-fA-F0-9]{32,40}[^\s]*$',
            r'^https?://[^\s]*\.torrent[^\s]*$'
        ]
        return any(re.match(pattern, normalized) for pattern in patterns)

    @staticmethod
    def is_youtube_url(url: str) -> bool:
        """检查是否为 YouTube URL"""
        normalized = URLExtractor._normalize_url(url)
        return 'youtube.com' in normalized or 'youtu.be' in normalized

    @staticmethod
    def is_bilibili_url(url: str) -> bool:
        """检查是否为 Bilibili URL"""
        normalized = URLExtractor._normalize_url(url)
        return 'bilibili.com' in normalized or 'b23.tv' in normalized

    @staticmethod
    def is_music_url(url: str) -> bool:
        """检查是否为音乐平台 URL"""
        normalized = URLExtractor._normalize_url(url)
        music_domains = [
            'music.163.com',  # 网易云
            'y.qq.com',       # QQ 音乐
            'youtube.com',    # YouTube Music
            'music.apple.com' # Apple Music
        ]
        return any(domain in normalized for domain in music_domains)

    @staticmethod
    def extract_xiaohongshu_url(text: str) -> str:
        """从文本中提取小红书链接，兼容非标准协议。"""
        # 先尝试提取标准 http/https 链接
        urls = re.findall(r'http[s]?://[^\s]+', text)
        for url in urls:
            normalized = URLExtractor._normalize_url(url)
            if 'xhslink.com' in normalized or 'xiaohongshu.com' in normalized:
                return normalized

        # 兼容 p://、tp://、ttp:// 等协议
        non_http_urls = re.findall(r'(p|tp|ttp)://([^\s]+)', text)
        for _, url in non_http_urls:
            normalized = URLExtractor._normalize_url(url)
            if 'xhslink.com' in normalized or 'xiaohongshu.com' in normalized:
                return f"https://{normalized}"

        # 匹配没有协议的小红书域名
        domain_urls = re.findall(r'(xhslink\.com/[^\s]+|xiaohongshu\.com/[^\s]+)', text)
        for url in domain_urls:
            normalized = URLExtractor._normalize_url(url)
            return f"https://{normalized}"

        return None
