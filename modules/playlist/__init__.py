# -*- coding: utf-8 -*-
"""
歌单解析模块
支持网易云音乐、QQ 音乐、汽水音乐等平台
"""

from .netease_parser import NeteasePlaylistParser
from .qq_parser import QQMusicPlaylistParser
from .qishui_parser import QishuiPlaylistParser

__all__ = [
    'NeteasePlaylistParser',
    'QQMusicPlaylistParser',
    'QishuiPlaylistParser',
]
