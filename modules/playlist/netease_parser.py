# -*- coding: utf-8 -*-
"""
网易云音乐歌单解析器
"""

import logging
import requests
import re
from typing import List, Dict, Optional

logger = logging.getLogger('savextube.playlist.netease')


class NeteasePlaylistParser:
    """网易云音乐歌单解析器"""
    
    def __init__(self, proxy_host: Optional[str] = None):
        """
        初始化解析器
        
        Args:
            proxy_host: 代理服务器地址（可选）
        """
        self.proxy_host = proxy_host
        self.proxies = None
        if proxy_host:
            self.proxies = {
                'http': proxy_host,
                'https': proxy_host
            }
        
        # 使用公开的网易云 API
        self.api_base = "https://music.163.com/api"
    
    def extract_playlist_id(self, url: str) -> Optional[str]:
        """
        从链接中提取歌单 ID
        
        Args:
            url: 网易云音乐歌单链接
            
        Returns:
            歌单 ID，失败返回 None
        """
        # 支持多种链接格式
        patterns = [
            r'playlist\?id=(\d+)',
            r'/playlist/(\d+)',
            r'#/playlist/(\d+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        return None
    
    def get_playlist_info(self, playlist_id: str) -> Optional[Dict]:
        """
        获取歌单信息
        
        Args:
            playlist_id: 歌单 ID
            
        Returns:
            歌单信息字典，失败返回 None
        """
        try:
            # 使用网易云网页版 API
            url = f"https://music.163.com/api/playlist/detail?id={playlist_id}"
            
            headers = {
                'Referer': 'https://music.163.com/',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(url, headers=headers, proxies=self.proxies, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('code') == 200:
                playlist = data.get('playlist', {})
                return {
                    'id': playlist_id,
                    'name': playlist.get('name', '未知歌单'),
                    'creator': playlist.get('creator', {}).get('nickname', '未知'),
                    'count': playlist.get('trackCount', 0),
                    'play_count': playlist.get('playCount', 0),
                    'cover_url': playlist.get('coverImgUrl', ''),
                    'description': playlist.get('description', '')
                }
            
            logger.warning(f"获取歌单信息失败：{data}")
            return None
            
        except Exception as e:
            logger.error(f"获取歌单信息异常：{e}")
            return None
    
    def get_playlist_tracks(self, playlist_id: str) -> List[Dict]:
        """
        获取歌单中的所有歌曲
        
        Args:
            playlist_id: 歌单 ID
            
        Returns:
            歌曲列表
        """
        try:
            # 使用网易云网页版 API
            url = f"https://music.163.com/api/playlist/detail?id={playlist_id}"
            
            headers = {
                'Referer': 'https://music.163.com/',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(url, headers=headers, proxies=self.proxies, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('code') != 200:
                logger.warning(f"获取歌曲列表失败：{data}")
                return []
            
            playlist = data.get('playlist', {})
            tracks = playlist.get('tracks', [])
            
            result = []
            for track in tracks:
                song_info = {
                    'id': track.get('id'),
                    'name': track.get('name', '未知曲目'),
                    'artists': [artist.get('name') for artist in track.get('artists', [])],
                    'artist': ' / '.join([artist.get('name') for artist in track.get('artists', [])]),
                    'album': track.get('album', {}).get('name', '未知专辑'),
                    'duration': track.get('duration', 0) // 1000,  # 转换为秒
                    'quality': 'lossless'  # 默认标记为无损
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
            url: 网易云音乐歌单链接
            
        Returns:
            包含歌单信息和歌曲列表的字典，失败返回 None
        """
        playlist_id = self.extract_playlist_id(url)
        if not playlist_id:
            logger.error(f"无法从链接中提取歌单 ID: {url}")
            return None
        
        logger.info(f"解析网易云歌单：{playlist_id}")
        
        # 获取歌单信息
        playlist_info = self.get_playlist_info(playlist_id)
        if not playlist_info:
            return None
        
        # 获取歌曲列表
        tracks = self.get_playlist_tracks(playlist_id)
        
        result = {
            'platform': 'netease',
            'playlist': playlist_info,
            'tracks': tracks,
            'total': len(tracks)
        }
        
        logger.info(f"网易云歌单解析完成：{playlist_info['name']} - {len(tracks)} 首歌曲")
        return result


# 测试代码
if __name__ == '__main__':
    parser = NeteasePlaylistParser()
    
    # 测试链接（示例）
    test_url = "https://music.163.com/#/playlist?id=12345678"
    result = parser.parse(test_url)
    
    if result:
        print(f"歌单名称：{result['playlist']['name']}")
        print(f"歌曲数量：{result['total']}")
        print("前 5 首歌曲:")
        for i, track in enumerate(result['tracks'][:5], 1):
            print(f"  {i}. {track['name']} - {track['artist']}")
