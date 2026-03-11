# -*- coding: utf-8 -*-
"""
QQ 音乐歌单解析器
"""

import logging
import requests
import re
import json
from typing import List, Dict, Optional

logger = logging.getLogger('savextube.playlist.qq')


class QQMusicPlaylistParser:
    """QQ 音乐歌单解析器"""
    
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
    
    def extract_playlist_id(self, url: str) -> Optional[str]:
        """
        从链接中提取歌单 ID
        
        Args:
            url: QQ 音乐歌单链接
            
        Returns:
            歌单 ID，失败返回 None
        """
        # 支持多种链接格式
        patterns = [
            r'playlist/(\d+)',
            r'id=(\d+)',
            r'/playDetail/(\d+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        return None
    
    def get_playlist_info(self, playlist_id: str) -> Optional[Dict]:
        """
        获取歌单信息（通过第三方 API）
        
        Args:
            playlist_id: 歌单 ID
            
        Returns:
            歌单信息字典，失败返回 None
        """
        try:
            # 使用第三方 API（参考 music_jx 项目）
            # 这里使用公开的 QQ 音乐 API
            url = f"https://c.y.qq.com/qzone/fcg-bin/fcg_ucc_getcdinfo_byids_cp.fcg?type=1&utf8=1&disstid={playlist_id}&loginUin=0"
            
            headers = {
                'Referer': 'https://y.qq.com/n/ryqq/playlist',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(url, headers=headers, proxies=self.proxies, timeout=10)
            response.raise_for_status()
            
            # QQ 音乐 API 返回的是 JSONP，需要去除回调函数
            content = response.text
            if content.startswith('callback('):
                content = content[9:-1]  # 去除 "callback(" 和 ")"
            
            data = json.loads(content)
            
            if data.get('code') == 0:
                cdlist = data.get('cdlist', [])
                if cdlist:
                    playlist = cdlist[0]
                    return {
                        'id': playlist_id,
                        'name': playlist.get('dissname', '未知歌单'),
                        'creator': playlist.get('nickname', '未知'),
                        'count': playlist.get('song_count', 0),
                        'play_count': playlist.get('listennum', 0),
                        'cover_url': playlist.get('logo', ''),
                        'description': playlist.get('desc', '')
                    }
            
            logger.warning(f"获取歌单信息失败：{data.get('message', 'Unknown error')}")
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
            url = f"https://c.y.qq.com/qzone/fcg-bin/fcg_ucc_getcdinfo_byids_cp.fcg?type=1&utf8=1&disstid={playlist_id}&loginUin=0"
            
            headers = {
                'Referer': 'https://y.qq.com/n/ryqq/playlist',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(url, headers=headers, proxies=self.proxies, timeout=10)
            response.raise_for_status()
            
            # 处理 JSONP
            content = response.text
            if content.startswith('callback('):
                content = content[9:-1]
            
            data = json.loads(content)
            
            if data.get('code') != 0:
                logger.warning(f"获取歌曲列表失败：{data.get('message', 'Unknown error')}")
                return []
            
            cdlist = data.get('cdlist', [])
            if not cdlist:
                return []
            
            songs = cdlist[0].get('songlist', [])
            
            result = []
            for song in songs:
                song_info = {
                    'id': song.get('songid'),
                    'name': song.get('songname', '未知曲目'),
                    'artist': song.get('singer', [{}])[0].get('name', '未知歌手'),
                    'artists': [singer.get('name') for singer in song.get('singer', [])],
                    'album': song.get('albumname', '未知专辑'),
                    'duration': song.get('interval', 0),
                    'quality': 'lossless'
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
            url: QQ 音乐歌单链接
            
        Returns:
            包含歌单信息和歌曲列表的字典，失败返回 None
        """
        playlist_id = self.extract_playlist_id(url)
        if not playlist_id:
            logger.error(f"无法从链接中提取歌单 ID: {url}")
            return None
        
        logger.info(f"解析 QQ 音乐歌单：{playlist_id}")
        
        # 获取歌单信息
        playlist_info = self.get_playlist_info(playlist_id)
        if not playlist_info:
            return None
        
        # 获取歌曲列表
        tracks = self.get_playlist_tracks(playlist_id)
        
        result = {
            'platform': 'qq',
            'playlist': playlist_info,
            'tracks': tracks,
            'total': len(tracks)
        }
        
        logger.info(f"QQ 音乐歌单解析完成：{playlist_info['name']} - {len(tracks)} 首歌曲")
        return result


# 测试代码
if __name__ == '__main__':
    parser = QQMusicPlaylistParser()
    
    # 测试链接（示例）
    test_url = "https://y.qq.com/n/ryqq/playlist/1234567890"
    result = parser.parse(test_url)
    
    if result:
        print(f"歌单名称：{result['playlist']['name']}")
        print(f"歌曲数量：{result['total']}")
        print("前 5 首歌曲:")
        for i, track in enumerate(result['tracks'][:5], 1):
            print(f"  {i}. {track['name']} - {track['artist']}")
