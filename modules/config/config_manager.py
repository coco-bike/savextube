#!/usr/bin/env python3
"""
SQLite 配置管理器
用于管理 Telegram 机器人的配置开关状态
"""

import sqlite3
import json
import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ConfigManager:
    def __init__(self, db_path: str = "/app/db/savextube.db"):
        """
        初始化配置管理器
        
        Args:
            db_path: SQLite 数据库文件路径
        """
        self.db_path = Path(db_path)
        self.default_config = {
            "auto_download_enabled": True,  # 默认启用自动下载
            "bilibili_auto_playlist": False,  # 默认不启用B站自动下载全集
            "youtube_audio_mode": False,  # 默认不启用YouTube音频模式
            "youtube_id_tags": False,  # 默认不启用YouTube ID标签
            "bilibili_danmaku_download": False,  # 默认不启用B站弹幕下载
            "bilibili_ugc_playlist": True,  # 默认启用B站UGC播放列表自动下载
            "youtube_thumbnail_download": False,  # 默认不启用YouTube封面下载
            "youtube_subtitle_download": False,  # 默认不启用YouTube字幕下载
            "youtube_timestamp_naming": False,  # 默认不启用YouTube时间戳命名
            "bilibili_thumbnail_download": False,  # 默认不启用B站封面下载
            "netease_lyrics_merge": False,  # 默认不启用网易云歌词合并
            "netease_artist_download": True,  # 网易云artist下载默认启用
            "netease_cover_download": True,  # 网易云cover下载默认启用
            "youtube_mix_playlist": False  # 默认不启用YouTube Mix播放列表自动下载
        }
        
        # 确保数据库目录存在
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error(f"无法创建数据库目录 {self.db_path.parent}: {e}")
            raise  # 直接抛出异常，不回退到本地目录
        
        # 初始化数据库
        self._init_database()
    
    def _init_database(self):
        """初始化数据库表"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 创建 tg_config 表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS tg_config (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        key TEXT UNIQUE NOT NULL,
                        value TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # 创建更新时间触发器
                cursor.execute('''
                    CREATE TRIGGER IF NOT EXISTS update_tg_config_timestamp 
                    AFTER UPDATE ON tg_config
                    BEGIN
                        UPDATE tg_config SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
                    END
                ''')
                
                conn.commit()
                logger.info(f"✅ 配置数据库初始化成功: {self.db_path}")
                
                # 如果表为空，插入默认配置
                cursor.execute("SELECT COUNT(*) FROM tg_config")
                count = cursor.fetchone()[0]
                if count == 0:
                    self._insert_default_config(cursor)
                    conn.commit()
                    logger.info("✅ 默认配置已插入数据库")
                    
        except Exception as e:
            logger.error(f"❌ 数据库初始化失败: {e}")
            raise  # 直接抛出异常，不回退到其他方式
    
    def _insert_default_config(self, cursor):
        """插入默认配置到数据库"""
        for key, value in self.default_config.items():
            cursor.execute(
                "INSERT INTO tg_config (key, value) VALUES (?, ?)",
                (key, json.dumps(value))
            )
    
    def get_config(self, key: str, default=None) -> Any:
        """
        获取配置项的值
        
        Args:
            key: 配置项键名
            default: 默认值
            
        Returns:
            配置项的值
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT value FROM tg_config WHERE key = ?",
                    (key,)
                )
                result = cursor.fetchone()
                
                if result:
                    return json.loads(result[0])
                else:
                    # 如果键不存在，返回默认值并插入到数据库
                    if key in self.default_config:
                        default_value = self.default_config[key]
                        self.set_config(key, default_value)
                        return default_value
                    return default
                    
        except Exception as e:
            logger.error(f"❌ 获取配置失败 ({key}): {e}")
            raise  # 直接抛出异常，不回退到其他方式
    
    def get_all_config(self) -> Dict[str, Any]:
        """
        获取所有配置项
        
        Returns:
            包含所有配置项的字典
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT key, value FROM tg_config")
                results = cursor.fetchall()
                
                config = {}
                for key, value in results:
                    config[key] = json.loads(value)
                
                # 确保所有默认配置项都存在
                for key, default_value in self.default_config.items():
                    if key not in config:
                        config[key] = default_value
                        # 插入缺失的配置项
                        self.set_config(key, default_value)
                
                return config
                
        except Exception as e:
            logger.error(f"❌ 获取所有配置失败: {e}")
            raise  # 直接抛出异常，不回退到其他方式
    
    def set_config(self, key: str, value: Any) -> bool:
        """
        设置配置项的值
        
        Args:
            key: 配置项键名
            value: 配置项值
            
        Returns:
            是否设置成功
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 尝试更新现有配置
                cursor.execute(
                    "UPDATE tg_config SET value = ? WHERE key = ?",
                    (json.dumps(value), key)
                )
                
                # 如果没有更新任何行，插入新配置
                if cursor.rowcount == 0:
                    cursor.execute(
                        "INSERT INTO tg_config (key, value) VALUES (?, ?)",
                        (key, json.dumps(value))
                    )
                
                conn.commit()
                logger.info(f"✅ 配置已更新: {key} = {value}")
                return True
                
        except Exception as e:
            logger.error(f"❌ 设置配置失败 ({key}={value}): {e}")
            raise  # 直接抛出异常，不回退到其他方式
    
    def reset_to_default(self) -> bool:
        """
        重置所有配置为默认值
        
        Returns:
            是否重置成功
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 删除所有现有配置
                cursor.execute("DELETE FROM tg_config")
                
                # 插入默认配置
                self._insert_default_config(cursor)
                
                conn.commit()
                logger.info("✅ 配置已重置为默认值")
                return True
                
        except Exception as e:
            logger.error(f"❌ 重置配置失败: {e}")
            raise  # 直接抛出异常，不回退到其他方式
