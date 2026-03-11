# -*- coding: utf-8 -*-
"""
汽水音乐歌单解析器
参考 music_jx 项目实现
"""

import logging
import requests
import re
from typing import List, Dict, Optional

logger = logging.getLogger('savextube.playlist.qishui')


class QishuiPlaylistParser:
    """汽水音乐歌单解析器"""
    
    def __init__(self, proxy_host: Optional[str] = None, api_url: Optional[str] = None):
        """
        初始化解析器
        
        Args:
            proxy_host: 代理服务器地址（可选）
            api_url: 第三方 API 地址（可选，默认使用演示 API）
        """
        self.proxy_host = proxy_host
        self.proxies = None
        if proxy_host:
            self.proxies = {
                'http': proxy_host,
                'https': proxy_host
            }
        
        # 使用第三方 API（参考 music_jx 项目）
        # 备用 API 列表
        self.api_urls = [
            api_url,
            "https://api.bugpk.com/api/qishui",
            "https://music-api.example.com/qishui",  # 备用
        ]
        self.api_urls = [url for url in self.api_urls if url]  # 移除 None
    
    def extract_playlist_id(self, url: str) -> Optional[str]:
        """
        从链接中提取歌单 ID
        
        Args:
            url: 汽水音乐歌单链接
            
        Returns:
            歌单 ID，失败返回 None
        """
        # 支持格式：https://qishui.douyin.com/s/i9wXxJGq/
        patterns = [
            r'qishui\.douyin\.com/s/([^/]+)/',
            r'qishui\.douyin\.com/([^/]+)/',
            r'/s/([^/\?]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        return None
    
    def get_playlist_info_from_api(self, url: str) -> Optional[Dict]:
        """
        通过第三方 API 获取歌单信息（支持多个 API）
        
        Args:
            url: 汽水音乐歌单链接
            
        Returns:
            歌单信息字典，失败返回 None
        """
        for api_base in self.api_urls:
            try:
                logger.info(f"尝试 API: {api_base}")
                
                # 调用第三方 API
                api_url = f"{api_base}?url={url}"
                response = requests.get(api_url, proxies=self.proxies, timeout=15)
                response.raise_for_status()
                
                data = response.json()
                
                if data.get('code') == 200:
                    playlist_data = data.get('data', {})
                    return {
                        'id': self.extract_playlist_id(url) or 'unknown',
                        'name': playlist_data.get('title', '未知歌单'),
                        'creator': playlist_data.get('author', '未知'),
                        'count': playlist_data.get('song_count', 0),
                        'cover_url': playlist_data.get('cover', ''),
                        'description': playlist_data.get('desc', '')
                    }
                
                logger.warning(f"API 返回错误：{data.get('message', 'Unknown error')}")
                
            except Exception as e:
                logger.warning(f"API {api_base} 失败：{e}")
                continue
        
        logger.error("所有 API 都失败了")
        return None
    
    def get_playlist_tracks(self, url: str) -> List[Dict]:
        """
        获取歌单中的所有歌曲
        
        Args:
            url: 汽水音乐歌单链接
            
        Returns:
            歌曲列表
        """
        try:
            # 调用第三方 API
            api_url = f"{self.api_url}?url={url}"
            response = requests.get(api_url, proxies=self.proxies, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('code') != 200:
                logger.warning(f"获取歌曲列表失败：{data.get('message', 'Unknown error')}")
                return []
            
            # 解析返回数据
            playlist_data = data.get('data', {})
            songs = playlist_data.get('songs', [])
            
            if not songs:
                # 尝试另一种格式
                songs = playlist_data.get('song_list', [])
            
            result = []
            for song in songs:
                song_info = {
                    'id': song.get('id') or song.get('song_id'),
                    'name': song.get('title') or song.get('name', '未知曲目'),
                    'artist': song.get('author') or song.get('artist', '未知歌手'),
                    'artists': [song.get('author', '未知歌手')],
                    'album': song.get('album', '未知专辑'),
                    'duration': song.get('duration', 0),
                    'quality': 'lossless',
                    'play_url': song.get('play_url') or song.get('music_url')  # 播放链接
                }
                result.append(song_info)
            
            logger.info(f"成功获取歌单歌曲：{len(result)} 首")
            return result
            
        except Exception as e:
            logger.error(f"获取歌曲列表异常：{e}")
            return []
    
    def parse(self, url: str) -> Optional[Dict]:
        """
        解析歌单链接
        
        Args:
            url: 汽水音乐歌单链接
            
        Returns:
            包含歌单信息和歌曲列表的字典，失败返回 None
        """
        playlist_id = self.extract_playlist_id(url)
        if not playlist_id:
            logger.error(f"无法从链接中提取歌单 ID: {url}")
            return None
        
        logger.info(f"解析汽水音乐歌单：{playlist_id}")
        
        # 获取歌单信息
        playlist_info = self.get_playlist_info_from_api(url)
        if not playlist_info:
            return None
        
        # 获取歌曲列表
        tracks = self.get_playlist_tracks(url)
        
        result = {
            'platform': 'qishui',
            'playlist': playlist_info,
            'tracks': tracks,
            'total': len(tracks)
        }
        
        logger.info(f"汽水音乐歌单解析完成：{playlist_info['name']} - {len(tracks)} 首歌曲")
        return result


# 测试代码
if __name__ == '__main__':
    parser = QishuiPlaylistParser()
    
    # 测试链接（示例）
    test_url = "https://qishui.douyin.com/s/i9wXxJGq/"
    result = parser.parse(test_url)
    
    if result:
        print(f"歌单名称：{result['playlist']['name']}")
        print(f"歌曲数量：{result['total']}")
        print("前 5 首歌曲:")
        for i, track in enumerate(result['tracks'][:5], 1):
            print(f"  {i}. {track['name']} - {track['artist']}")
    else:
        print("解析失败")
