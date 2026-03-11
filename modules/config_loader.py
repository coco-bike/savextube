# -*- coding: utf-8 -*-
"""
配置文件读取器
读取歌单、频道等配置
"""

import logging
import toml
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger('savextube.config_loader')


class ConfigLoader:
    """配置文件读取器"""
    
    def __init__(self, config_dir: str = '/app/config'):
        """
        初始化配置读取器
        
        Args:
            config_dir: 配置文件目录
        """
        self.config_dir = Path(config_dir)
    
    def load_playlists(self) -> List[Dict]:
        """
        加载歌单配置
        
        Returns:
            歌单配置列表
        """
        config_file = self.config_dir / 'playlists.toml'
        
        if not config_file.exists():
            logger.warning(f"歌单配置文件不存在：{config_file}")
            return []
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = toml.load(f)
            
            playlists = config.get('playlists', [])
            logger.info(f"加载 {len(playlists)} 个歌单配置")
            return playlists
            
        except Exception as e:
            logger.error(f"加载歌单配置失败：{e}")
            return []
    
    def load_channels(self) -> List[Dict]:
        """
        加载 TG 频道配置
        
        Returns:
            频道配置列表
        """
        config_file = self.config_dir / 'tg_channels.toml'
        
        if not config_file.exists():
            logger.warning(f"频道配置文件不存在：{config_file}")
            return []
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = toml.load(f)
            
            channels = config.get('channels', [])
            logger.info(f"加载 {len(channels)} 个频道配置")
            return channels
            
        except Exception as e:
            logger.error(f"加载频道配置失败：{e}")
            return []
    
    def load_storage_config(self) -> Dict:
        """
        加载存储配置
        
        Returns:
            存储配置字典
        """
        config_file = self.config_dir / 'storage.toml'
        
        if not config_file.exists():
            # 返回默认配置
            return {
                'download_path': '/vol2/1000/media/music',
                '分类方式': 'style',
                'file_naming': '{artist} - {title}'
            }
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = toml.load(f)
            
            return config.get('storage', {})
            
        except Exception as e:
            logger.error(f"加载存储配置失败：{e}")
            return {}


# 使用示例
if __name__ == '__main__':
    loader = ConfigLoader()
    
    playlists = loader.load_playlists()
    print(f"歌单配置：{len(playlists)} 个")
    
    channels = loader.load_channels()
    print(f"频道配置：{len(channels)} 个")
