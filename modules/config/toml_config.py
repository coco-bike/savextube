#!/usr/bin/env python3
"""
TOML 配置文件读取器
支持从 /app/config/savextube.toml 读取配置
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

def load_toml_config(config_path: str = "/app/config/savextube.toml") -> Dict[str, Any]:
    """
    从 TOML 配置文件中加载配置
    
    Args:
        config_path: 配置文件路径，默认为 /app/config/savextube.toml
        
    Returns:
        配置字典
    """
    try:
        # 尝试导入 TOML 解析库，优先级：tomllib > tomli > toml
        try:
            import tomllib  # Python 3.11+
            def load_toml(f):
                return tomllib.load(f)
        except ImportError:
            try:
                import tomli as tomllib  # Python <=3.10，需要 pip install tomli
                def load_toml(f):
                    return tomllib.load(f)
            except ImportError:
                try:
                    import toml  # 需要 pip install toml
                    def load_toml(f):
                        return toml.load(f)
                except ImportError:
                    logger.error("❌ 无法导入 TOML 解析库，请安装 tomli 或 toml")
                    return {}

        config_file = Path(config_path)
        
        # 检查配置文件是否存在
        if not config_file.exists():
            logger.warning(f"⚠️ 配置文件不存在: {config_path}")
            return {}
            
        # 读取并解析 TOML 配置文件
        logger.info(f"📖 正在读取配置文件: {config_path}")
        
        with open(config_file, 'rb') as f:
            config = load_toml(f)
            
        logger.info(f"✅ 成功读取配置文件，包含 {len(config)} 个配置段")
        
        # 打印读取到的配置段名称（用于调试）
        for section_name in config.keys():
            logger.info(f"   📁 配置段: {section_name}")
            
        return config
        
    except Exception as e:
        logger.error(f"❌ 读取配置文件失败: {e}")
        return {}

def get_telegram_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    从配置中提取 Telegram 相关配置
    
    Args:
        config: 完整的配置字典
        
    Returns:
        Telegram 配置字典
    """
    telegram_config = config.get('telegram', {})
    
    # 提取所有 Telegram 相关配置
    telegram_settings = {
        'bot_token': telegram_config.get('telegram_bot_token', ''),
        'api_id': telegram_config.get('telegram_bot_api_id', ''),
        'api_hash': telegram_config.get('telegram_bot_api_hash', ''),
        'allowed_user_ids': telegram_config.get('telegram_bot_allowed_user_ids', ''),
        'config_path': telegram_config.get('telegram_bot_config_path', '/config/settings.json'),
        'session_file': telegram_config.get('telegram_session_file', '/app/cookies/'),
    }
    
    # 处理 bot_token 的特殊格式（移除可能的等号）
    if '=' in telegram_settings['bot_token']:
        # 处理类似 "8174810484=AAEF1iD2xIrf0QKsfRYx4th9fstnlEhoHo8" 的格式
        # 应该是 "8174810484:AAEF1iD2xIrf0QKsfRYx4th9fstnlEhoHo8"
        telegram_settings['bot_token'] = telegram_settings['bot_token'].replace('=', ':')
    
    return telegram_settings

def get_proxy_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    从配置中提取代理相关配置
    
    Args:
        config: 完整的配置字典
        
    Returns:
        代理配置字典
    """
    proxy_config = config.get('proxy', {})
    
    return {
        'proxy_host': proxy_config.get('proxy_host', ''),
    }

def get_netease_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    从配置中提取网易云音乐相关配置
    
    Args:
        config: 完整的配置字典
        
    Returns:
        网易云音乐配置字典
    """
    netease_config = config.get('netease', {})
    
    return {
        'quality_level': netease_config.get('ncm_quality_level', '无损'),
        'download_lyrics': netease_config.get('ncm_download_lyrics', True),
        'dir_format': netease_config.get('ncm_dir_format', '{ArtistName}/{AlbumName}'),
        'album_folder_format': netease_config.get('ncm_album_folder_format', '{AlbumName}({ReleaseDate})'),
        'song_file_format': netease_config.get('ncm_song_file_format', '{SongName}'),
    }

def get_apple_music_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    从配置中提取 Apple Music 相关配置
    
    Args:
        config: 完整的配置字典
        
    Returns:
        Apple Music 配置字典
    """
    apple_music_config = config.get('apple_music', {})
    
    return {
        'amdp': apple_music_config.get('amdp', True),
        'amd_wrapper_decrypt': apple_music_config.get('amd_wraper_decrypt', '192.168.2.134:10020'),
        'amd_wrapper_get': apple_music_config.get('amd_wraper_get', '192.168.2.134:20020'),
        'amd_region': apple_music_config.get('amd_region', 'cn'),
    }

def get_bilibili_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    从配置中提取 Bilibili 相关配置
    
    Args:
        config: 完整的配置字典
        
    Returns:
        Bilibili 配置字典
    """
    bilibili_config = config.get('bilibili', {})
    
    return {
        'poll_interval': bilibili_config.get('bilibili_poll_interval', 1),
    }

def get_paths_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    从配置中提取路径相关配置
    
    Args:
        config: 完整的配置字典
        
    Returns:
        路径配置字典
    """
    paths_config = config.get('paths', {})
    
    return {
        'config_path': paths_config.get('config_path', '/config/settings.json'),
        'pic_download_path': paths_config.get('pic_download_path', '/downloads/gallery'),
    }

def get_qbittorrent_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    从配置中提取 qBittorrent 相关配置
    
    Args:
        config: 完整的配置字典
        
    Returns:
        qBittorrent 配置字典
    """
    qb_config = config.get('qbittorrent', {})
    
    return {
        'host': qb_config.get('qb_host', '192.168.2.134'),
        'port': qb_config.get('qb_port', 8988),
        'username': qb_config.get('qb_username', 'admin'),
        'password': qb_config.get('qb_password', 'Lixing/87'),
    }

def get_logging_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    从配置中提取日志相关配置
    
    Args:
        config: 完整的配置字典
        
    Returns:
        日志配置字典
    """
    logging_config = config.get('logging', {})
    
    return {
        'log_level': logging_config.get('log_level', 'INFO'),
        'log_dir': logging_config.get('log_dir', '/app/logs'),
        'log_max_size': logging_config.get('log_max_size', 10),
        'log_backup_count': logging_config.get('log_backup_count', 5),
        'log_to_console': logging_config.get('log_to_console', True),
        'log_to_file': logging_config.get('log_to_file', True),
    }

def get_youtube_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    从配置中提取 YouTube 相关配置
    
    Args:
        config: 完整的配置字典
        
    Returns:
        YouTube 配置字典
    """
    youtube_config = config.get('youtube', {})
    
    return {
        'convert_to_mp4': youtube_config.get('youtube_convert_to_mp4', True),
    }

def get_config_with_fallback(toml_config: Dict[str, Any], env_var: str, toml_key: str, default: str = "") -> str:
    """
    获取配置值，支持 TOML 配置和环境变量回退
    
    Args:
        toml_config: TOML 配置字典
        env_var: 环境变量名
        toml_key: TOML 配置键名
        default: 默认值
        
    Returns:
        配置值
    """
    # 优先使用 TOML 配置
    toml_value = toml_config.get(toml_key, '')
    if toml_value:
        logger.info(f"📋 使用 TOML 配置: {toml_key} = {toml_value[:20]}...")
        return str(toml_value)
    
    # 回退到环境变量
    env_value = os.getenv(env_var, default)
    if env_value:
        logger.info(f"🔧 使用环境变量: {env_var} = {env_value[:20]}...")
        return env_value
    
    # 使用默认值
    if default:
        logger.info(f"⚙️ 使用默认值: {toml_key} = {default}")
    else:
        logger.warning(f"⚠️ 配置项未设置: {toml_key} / {env_var}")
    
    return default

def validate_telegram_config(telegram_config: Dict[str, Any]) -> bool:
    """
    验证 Telegram 配置的有效性
    
    Args:
        telegram_config: Telegram 配置字典
        
    Returns:
        配置是否有效
    """
    required_fields = ['bot_token']
    missing_fields = []
    
    for field in required_fields:
        if not telegram_config.get(field):
            missing_fields.append(field)
    
    if missing_fields:
        logger.error(f"❌ Telegram 配置缺少必需字段: {missing_fields}")
        return False
    
    # 验证 bot_token 格式
    bot_token = telegram_config['bot_token']
    if ':' not in bot_token or len(bot_token.split(':')) != 2:
        logger.error(f"❌ Telegram Bot Token 格式不正确: {bot_token[:20]}...")
        return False
    
    logger.info("✅ Telegram 配置验证通过")
    return True

def print_config_summary(config: Dict[str, Any]):
    """
    打印配置文件摘要信息
    
    Args:
        config: 完整的配置字典
    """
    logger.info("📊 配置文件摘要:")
    
    # Telegram 配置
    telegram_config = get_telegram_config(config)
    if telegram_config['bot_token']:
        logger.info(f"   🤖 Telegram Bot Token: {telegram_config['bot_token'][:20]}...")
    if telegram_config['api_id']:
        logger.info(f"   🔑 Telegram API ID: {telegram_config['api_id']}")
    if telegram_config['api_hash']:
        logger.info(f"   🔐 Telegram API Hash: {telegram_config['api_hash'][:20]}...")
    if telegram_config['allowed_user_ids']:
        logger.info(f"   👥 允许的用户ID: {telegram_config['allowed_user_ids']}")
    
    # 代理配置
    proxy_config = get_proxy_config(config)
    if proxy_config['proxy_host']:
        logger.info(f"   🌐 代理服务器: {proxy_config['proxy_host']}")
    
    # 网易云音乐配置
    netease_config = get_netease_config(config)
    logger.info(f"   🎵 网易云音乐音质: {netease_config['quality_level']}")
    logger.info(f"   🎤 网易云音乐歌词下载: {netease_config['download_lyrics']}")
    
    # Apple Music 配置
    apple_music_config = get_apple_music_config(config)
    logger.info(f"   🍎 Apple Music AMDP: {apple_music_config['amdp']}")
    logger.info(f"   🌐 Apple Music 解密端口: {apple_music_config['amd_wrapper_decrypt']}")
    
    # Bilibili 配置
    bilibili_config = get_bilibili_config(config)
    logger.info(f"   📺 Bilibili 轮询间隔: {bilibili_config['poll_interval']}")
    
    # 路径配置
    paths_config = get_paths_config(config)
    logger.info(f"   📁 配置文件路径: {paths_config['config_path']}")
    logger.info(f"   📷 图片下载路径: {paths_config['pic_download_path']}")
    
    # qBittorrent 配置
    qb_config = get_qbittorrent_config(config)
    logger.info(f"   ⚡ qBittorrent 地址: {qb_config['host']}:{qb_config['port']}")
    
    # 日志配置
    logging_config = get_logging_config(config)
    logger.info(f"   📝 日志级别: {logging_config['log_level']}")
    logger.info(f"   📁 日志目录: {logging_config['log_dir']}")
    
    # YouTube 配置
    youtube_config = get_youtube_config(config)
    logger.info(f"   ▶️ YouTube 转换为 MP4: {youtube_config['convert_to_mp4']}")
    
    logger.info("📊 配置摘要完成")

if __name__ == "__main__":
    # 测试配置读取
    print("🧪 测试 TOML 配置读取器")
    
    config = load_toml_config()
    if config:
        print_config_summary(config)
        
        telegram_config = get_telegram_config(config)
        print(f"\nTelegram 配置: {telegram_config}")
        
        proxy_config = get_proxy_config(config)
        print(f"代理配置: {proxy_config}")
        
        netease_config = get_netease_config(config)
        print(f"网易云音乐配置: {netease_config}")
        
        apple_music_config = get_apple_music_config(config)
        print(f"Apple Music 配置: {apple_music_config}")
        
        bilibili_config = get_bilibili_config(config)
        print(f"Bilibili 配置: {bilibili_config}")
        
        paths_config = get_paths_config(config)
        print(f"路径配置: {paths_config}")
        
        qb_config = get_qbittorrent_config(config)
        print(f"qBittorrent 配置: {qb_config}")
        
        logging_config = get_logging_config(config)
        print(f"日志配置: {logging_config}")
        
        youtube_config = get_youtube_config(config)
        print(f"YouTube 配置: {youtube_config}")
        
        is_valid = validate_telegram_config(telegram_config)
        print(f"配置有效性: {is_valid}")
    else:
        print("❌ 无法读取配置文件")
