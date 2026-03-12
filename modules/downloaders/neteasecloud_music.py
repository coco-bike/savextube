#!/usr/bin/env python3

import os
import re
import json
import time
import logging
import requests
import urllib.parse
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any
from hashlib import md5
# from cryptography.hazmat.primitives import padding
# from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('netease_downloader')

# 导入音乐元数据处理模块
try:
    from music_metadata import MusicMetadataManager
    METADATA_AVAILABLE = True
    logger.info("✅ 成功导入音乐元数据模块")
except ImportError as e:
    METADATA_AVAILABLE = False
    logger.warning(f"⚠️ 音乐元数据模块不可用，将跳过元数据处理: {e}")
except Exception as e:
    METADATA_AVAILABLE = False
    logger.error(f"❌ 导入音乐元数据模块时出错: {e}")

# 常量定义 - 基于musicapi.txt
class APIConstants:
    """API相关常量"""
    AES_KEY = b"e82ckenh8dichen8"
    USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Safari/537.36 Chrome/91.0.4472.164 NeteaseMusicDesktop/2.10.2.200154'
    REFERER = 'https://music.163.com/'
    
    # API URLs
    SONG_URL_V1 = "https://interface3.music.163.com/eapi/song/enhance/player/url/v1"
    SONG_DETAIL_V3 = "https://interface3.music.163.com/api/v3/song/detail"
    PLAYLIST_DETAIL_API = 'https://music.163.com/api/v6/playlist/detail'
    
    # 默认配置
    DEFAULT_CONFIG = {
        "os": "pc",
        "appver": "",
        "osver": "",
        "deviceId": "pyncm!"
    }

class CryptoUtils:
    """加密工具类 - 基于musicapi.txt"""
    
    @staticmethod
    def hex_digest(data: bytes) -> str:
        """将字节数据转换为十六进制字符串"""
        return "".join([hex(d)[2:].zfill(2) for d in data])
    
    @staticmethod
    def hash_digest(text: str) -> bytes:
        """计算MD5哈希值"""
        return md5(text.encode("utf-8")).digest()
    
    @staticmethod
    def hash_hex_digest(text: str) -> str:
        """计算MD5哈希值并转换为十六进制字符串"""
        return CryptoUtils.hex_digest(CryptoUtils.hash_digest(text))
    
    @staticmethod
    def encrypt_params(url: str, payload: Dict[str, Any]) -> str:
        """加密请求参数（简化版本，不使用cryptography）"""
        url_path = urllib.parse.urlparse(url).path.replace("/eapi/", "/api/")
        digest = CryptoUtils.hash_hex_digest(f"nobody{url_path}use{json.dumps(payload)}md5forencrypt")
        params = f"{url_path}-36cd479b6b5-{json.dumps(payload)}-36cd479b6b5-{digest}"
        
        # 简化版本：直接返回MD5哈希，不使用AES加密
        return CryptoUtils.hex_digest(params.encode())

class NeteaseDownloader:
    def __init__(self, bot=None):
        self.session = requests.Session()
        self.crypto_utils = CryptoUtils()
        self.bot = bot  # 保存bot引用，用于访问配置

        # 网易云音乐官方API配置
        self.api_url = "https://music.163.com"

        # 设置请求头
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://music.163.com/',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Connection': 'keep-alive',
        })

        # 设置cookies - 从环境变量或配置文件加载
        self._load_cookies()
        
        # 初始化音乐元数据管理器
        logger.info(f"🔧 元数据初始化: METADATA_AVAILABLE = {METADATA_AVAILABLE}")
        if METADATA_AVAILABLE:
            try:
                self.metadata_manager = MusicMetadataManager()
                logger.info("✅ 音乐元数据管理器初始化成功")
                logger.info(f"🔧 可用的音频标签库: {', '.join(self.metadata_manager.available_libraries) if self.metadata_manager.available_libraries else '无'}")
            except Exception as e:
                logger.error(f"❌ 音乐元数据管理器初始化失败: {e}")
                self.metadata_manager = None
        else:
            self.metadata_manager = None
            logger.warning("⚠️ 音乐元数据管理器不可用")
        
        # 歌词下载配置
        self.enable_lyrics_download = os.getenv('NCM_DOWNLOAD_LYRICS', 'true').lower() in ['true', '1', 'yes', 'on']
        if self.enable_lyrics_download:
            logger.info("🎤 歌词下载功能已启用")
        else:
            logger.info("📝 歌词下载功能已禁用")
        
        # 网易云音乐目录结构和文件命名配置
        self.dir_format = os.getenv('NCM_DIR_FORMAT', '{AlbumName}')
        self.album_folder_format = os.getenv('NCM_ALBUM_FOLDER_FORMAT', '{AlbumName}')
        self.song_file_format = os.getenv('NCM_SONG_FILE_FORMAT', '{SongName}')
        
        logger.info(f"🔧 网易云音乐配置:")
        logger.info(f"  - 目录结构格式: {self.dir_format}")
        logger.info(f"  - 专辑文件夹格式: {self.album_folder_format}")
        logger.info(f"  - 歌曲文件名格式: {self.song_file_format}")
        logger.info("支持的占位符:")
        logger.info("  - 目录结构: {ArtistName}, {AlbumName}")
        logger.info("  - 专辑文件夹: {AlbumName}, {ReleaseDate}")
        logger.info("  - 歌曲文件名: {SongNumber}, {ArtistName}, {SongName}")
        

        
        # 音质配置 - 对应网易云专业音质等级
        self.quality_map = {
            'standard': '128k',       # 标准
            'higher': '320k',         # 较高  
            'exhigh': '320k',         # 极高（修正：极高是320k，不是flac）
            'lossless': 'flac',       # 无损
            'hires': 'flac24bit',     # 高解析度无损
            'jyeffect': 'flac24bit',  # 高清臻音
            'jymaster': 'flac24bit',  # 超清母带
            'sky': 'flac24bit',       # 沉浸环绕声
            # 兼容旧参数
            'high': '320k',           # 兼容：较高
            'master': 'flac24bit',    # 兼容：超清母带
            'surround': 'flac24bit',  # 兼容：沉浸环绕声
        }

        # 音质等级名称映射（支持中文名称）
        self.quality_names = {
            '128k': '标准',
            '320k': '较高', 
            'flac': '极高',
            'flac24bit': '无损'
        }
        
        # 中文音质名称到英文的映射
        self.chinese_quality_map = {
            '标准': 'standard',
            '较高': 'higher',
            '极高': 'exhigh',
            '无损': 'lossless',
            '高解析度无损': 'hires',
            '高清臻音': 'jyeffect',
            '超清母带': 'jymaster',
            '沉浸环绕声': 'sky',
            # 兼容别名
            '高音质': 'higher',
            '高品质': 'higher'
        }
        
        # 音质降级顺序（从高到低）
        self.quality_fallback = [
            'jymaster',   # 超清母带
            'sky',        # 沉浸环绕声  
            'jyeffect',   # 高清臻音
            'hires',      # 高解析度无损
            'lossless',   # 无损
            'exhigh',     # 极高
            'higher',     # 较高
            'standard'    # 标准
        ]
        
        self.cache_dir = Path("./cache")
        self.cache_dir.mkdir(exist_ok=True)

        # 下载统计
        self.download_stats = {
            'total_files': 0,
            'downloaded_files': 0,
            'total_size': 0,
            'downloaded_songs': []
        }
        
    def _load_cookies(self):
        """从环境变量或配置文件加载网易云cookies"""
        import os
        
        # 第一优先级：环境变量NCM_COOKIES
        cookies_env = os.getenv('NCM_COOKIES')
        if cookies_env:
            logger.info("✅ 从环境变量NCM_COOKIES加载网易云cookies")
            cookies_loaded = 0
            for cookie in cookies_env.split(';'):
                if '=' in cookie:
                    name, value = cookie.strip().split('=', 1)
                    self.session.cookies.set(name.strip(), value.strip(), domain='.music.163.com')
                    cookies_loaded += 1
            
            logger.info(f"📝 已加载环境变量cookies: {cookies_loaded} 个")
            return
        
        # 第二优先级：从环境变量获取cookies文件路径
        cookie_file = os.getenv('NCM_COOKIE_FILE', '/app/cookies/ncm_cookies.txt')
        
        # 如果指定的路径不存在，尝试一些常见路径
        if not os.path.exists(cookie_file):
            possible_paths = [
                '/app/cookies/ncm_cookies.txt',
                './ncm_cookies.txt',
                './cookies/ncm_cookies.txt',
                './config/ncm_cookies.txt',
                '/app/ncm_cookies.txt',
                '/ncm/ncm_cookies.txt'
            ]
            
            cookie_file = None
            for path in possible_paths:
                if os.path.exists(path):
                    cookie_file = path
                    break
        
        if cookie_file and os.path.exists(cookie_file):
            try:
                with open(cookie_file, 'r', encoding='utf-8') as f:
                    cookies_content = f.read().strip()
                
                logger.info(f"✅ 从文件加载网易云cookies: {cookie_file}")
                
                # 支持多种格式
                if cookies_content.startswith('{'):
                    # JSON格式
                    import json
                    cookies_dict = json.loads(cookies_content)
                    for name, value in cookies_dict.items():
                        self.session.cookies.set(name, value, domain='.music.163.com')
                    logger.info(f"📝 已加载JSON格式cookies: {len(cookies_dict)} 个")
                    
                elif cookies_content.startswith('# Netscape HTTP Cookie File'):
                    # Netscape格式cookie文件
                    logger.info("📝 检测到Netscape格式cookie文件")
                    cookies_loaded = 0
                    for line in cookies_content.split('\n'):
                        line = line.strip()
                        if line and not line.startswith('#') and '\t' in line:
                            try:
                                # Netscape格式: domain, flag, path, secure, expiry, name, value
                                parts = line.split('\t')
                                if len(parts) >= 7:
                                    domain, _, path, secure, expiry, name, value = parts[:7]
                                    # 只处理网易云音乐相关的cookies
                                    if '.music.163.com' in domain or 'music.163.com' in domain:
                                        self.session.cookies.set(name, value, domain=domain, path=path)
                                        cookies_loaded += 1
                            except Exception as e:
                                logger.debug(f"⚠️ 解析cookie行失败: {line[:50]}... - {e}")
                    logger.info(f"📝 已加载Netscape格式cookies: {cookies_loaded} 个")
                    
                else:
                    # 字符串格式 (name=value; name2=value2)
                    cookies_loaded = 0
                    for cookie in cookies_content.split(';'):
                        if '=' in cookie:
                            name, value = cookie.strip().split('=', 1)
                            self.session.cookies.set(name.strip(), value.strip(), domain='.music.163.com')
                            cookies_loaded += 1
                    logger.info(f"📝 已加载字符串格式cookies: {cookies_loaded} 个")
                
                logger.info(f"📝 总共加载 {len(self.session.cookies)} 个cookies")
                return
                
            except Exception as e:
                logger.warning(f"⚠️ 读取cookies文件失败 {cookie_file}: {e}")
        

        
        # 如果都没有找到，给出警告
        logger.warning("⚠️ 未找到网易云cookies配置")
        logger.warning("💡 请设置环境变量:")
        logger.warning("   NCM_COOKIE_FILE=/path/to/ncm_cookies.txt")
        logger.warning("   或 NCM_COOKIES='MUSIC_U=xxx; __csrf=xxx'")
        logger.warning("📝 将使用游客模式，可能无法下载受版权保护的音乐")
        
    def resolve_netease_short_url(self, short_url: str) -> Optional[Dict]:
        """
        解析网易云音乐短链接，转换为实际的音乐链接
        
        Args:
            short_url: 短链接，如 https://163cn.tv/I8JPL0o
            
        Returns:
            Dict: 包含解析结果的字典
            {
                'success': bool,
                'type': 'song' | 'album' | 'playlist',
                'id': str,
                'url': str,
                'error': str (如果失败)
            }
        """
        logger.info(f"🔗 开始解析网易云音乐短链接: {short_url}")
        
        try:
            # 检查是否是支持的短链接格式
            if not any(domain in short_url for domain in ['163cn.tv', 'music.163.com']):
                logger.warning(f"⚠️ 不支持的链接格式: {short_url}")
                return {
                    'success': False,
                    'error': f'不支持的链接格式: {short_url}'
                }
            
            # 发送请求获取重定向后的URL
            response = self.session.get(short_url, allow_redirects=True, timeout=10)
            
            if response.status_code != 200:
                logger.error(f"❌ 请求短链接失败，状态码: {response.status_code}")
                return {
                    'success': False,
                    'error': f'请求短链接失败，状态码: {response.status_code}'
                }
            
            # 获取最终URL
            final_url = response.url
            logger.info(f"🔗 短链接重定向到: {final_url}")
            
            # 解析URL，提取音乐类型和ID
            if 'music.163.com' in final_url:
                # 单曲链接 - 支持多种格式
                song_match = re.search(r'(?:#/song\?id=|/song\?.*?id=)(\d+)', final_url)
                if song_match:
                    song_id = song_match.group(1)
                    logger.info(f"🎵 检测到单曲，ID: {song_id}")
                    return {
                        'success': True,
                        'type': 'song',
                        'id': song_id,
                        'url': f'https://music.163.com/#/song?id={song_id}',
                        'original_url': short_url
                    }
                
                # 专辑链接 - 支持多种格式
                album_match = re.search(r'(?:#/album\?id=|/album\?.*?id=)(\d+)', final_url)
                if album_match:
                    album_id = album_match.group(1)
                    logger.info(f"📀 检测到专辑，ID: {album_id}")
                    return {
                        'success': True,
                        'type': 'album',
                        'id': album_id,
                        'url': f'https://music.163.com/#/album?id={album_id}',
                        'original_url': short_url
                    }
                
                # 歌单链接 - 支持多种格式
                playlist_match = re.search(r'(?:#/playlist\?id=|#/my/m/music/playlist\?id=|/playlist\?.*?id=)(\d+)', final_url)
                if playlist_match:
                    playlist_id = playlist_match.group(1)
                    logger.info(f"📋 检测到歌单，ID: {playlist_id}")
                    return {
                        'success': True,
                        'type': 'playlist',
                        'id': playlist_id,
                        'url': f'https://music.163.com/#/playlist?id={playlist_id}',
                        'original_url': short_url
                    }
                
                # 艺术家链接 - 支持多种格式
                artist_match = re.search(r'(?:#/artist\?id=|/artist\?.*?id=)(\d+)', final_url)
                if artist_match:
                    artist_id = artist_match.group(1)
                    logger.info(f"🎤 检测到艺术家，ID: {artist_id}")
                    return {
                        'success': True,
                        'type': 'artist',
                        'id': artist_id,
                        'url': f'https://music.163.com/#/artist?id={artist_id}',
                        'original_url': short_url
                    }
            
            logger.warning(f"⚠️ 无法识别链接类型: {final_url}")
            return {
                'success': False,
                'error': f'无法识别链接类型: {final_url}'
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ 请求短链接时发生网络错误: {e}")
            return {
                'success': False,
                'error': f'网络错误: {e}'
            }
        except Exception as e:
            logger.error(f"❌ 解析短链接时发生未知错误: {e}")
            return {
                'success': False,
                'error': f'未知错误: {e}'
            }
    
    def download_by_url(self, url: str, download_dir: str = "./downloads/netease", quality: str = '128k', progress_callback=None) -> Dict:
        """
        通过URL下载音乐，自动识别链接类型并调用相应的下载方法
        
        Args:
            url: 音乐链接（支持短链接和官方链接）
            download_dir: 下载目录
            quality: 音质
            progress_callback: 进度回调函数
            
        Returns:
            Dict: 下载结果
        """
        logger.info(f"🔗 开始通过URL下载: {url}")
        
        # 首先检查是否是标准格式的网易云音乐链接 (带#)
        if 'music.163.com' in url:
            # 单曲链接 - 标准格式 (带#)
            song_match = re.search(r'#/song\?id=(\d+)', url)
            if song_match:
                song_id = song_match.group(1)
                logger.info(f"🎵 检测到标准单曲链接，ID: {song_id}")
                return self.download_song_by_id(song_id, download_dir, quality, progress_callback)
            
            # 专辑链接 - 标准格式 (带#)
            album_match = re.search(r'#/album\?id=(\d+)', url)
            if album_match:
                album_id = album_match.group(1)
                logger.info(f"📀 检测到标准专辑链接，ID: {album_id}")
                return self.download_album_by_id(album_id, download_dir, quality, progress_callback)
            
            # 歌单链接 - 标准格式 (带#)
            playlist_match = re.search(r'#/playlist\?id=(\d+)', url)
            if playlist_match:
                playlist_id = playlist_match.group(1)
                logger.info(f"📋 检测到标准歌单链接，ID: {playlist_id}")
                return self.download_playlist_by_id(playlist_id, download_dir, quality, progress_callback)
            
            # 歌单链接 - 我的音乐歌单格式
            my_playlist_match = re.search(r'#/my/m/music/playlist\?id=(\d+)', url)
            if my_playlist_match:
                playlist_id = my_playlist_match.group(1)
                logger.info(f"📋 检测到我的音乐歌单链接，ID: {playlist_id}")
                return self.download_playlist_by_id(playlist_id, download_dir, quality, progress_callback)
            
            # 艺术家链接 - 标准格式 (带#)
            artist_match = re.search(r'#/artist\?id=(\d+)', url)
            if artist_match:
                artist_id = artist_match.group(1)
                logger.info(f"🎤 检测到标准艺术家链接，ID: {artist_id}")
                # TODO: 实现艺术家下载
                logger.warning("⚠️ 艺术家下载功能暂未实现")
                return {
                    'success': False,
                    'error': '艺术家下载功能暂未实现'
                }
            
            # 如果不是标准格式，尝试转换为标准格式
            logger.info(f"🔄 检测到非标准格式链接，尝试转换为标准格式: {url}")
            
            # 重定向后的链接格式 (不带#，但有其他参数)
            # 单曲链接 - 重定向格式
            song_redirect_match = re.search(r'(?:/song\?|song\?)(?:.*?&)?id=(\d+)', url)
            if song_redirect_match:
                song_id = song_redirect_match.group(1)
                standard_url = f"https://music.163.com/#/song?id={song_id}"
                logger.info(f"🎵 重定向单曲链接转换为标准格式: {standard_url}")
                # 递归调用自身，使用标准格式
                return self.download_by_url(standard_url, download_dir, quality, progress_callback)
            
            # 专辑链接 - 重定向格式
            album_redirect_match = re.search(r'(?:/album\?|album\?)(?:.*?&)?id=(\d+)', url)
            if album_redirect_match:
                album_id = album_redirect_match.group(1)
                standard_url = f"https://music.163.com/#/album?id={album_id}"
                logger.info(f"📀 重定向专辑链接转换为标准格式: {standard_url}")
                # 递归调用自身，使用标准格式
                return self.download_by_url(standard_url, download_dir, quality, progress_callback)
            
            # 歌单链接 - 重定向格式
            playlist_redirect_match = re.search(r'(?:/playlist\?|playlist\?)(?:.*?&)?id=(\d+)', url)
            if playlist_redirect_match:
                playlist_id = playlist_redirect_match.group(1)
                standard_url = f"https://music.163.com/#/playlist?id={playlist_id}"
                logger.info(f"📋 重定向歌单链接转换为标准格式: {standard_url}")
                # 递归调用自身，使用标准格式
                return self.download_by_url(standard_url, download_dir, quality, progress_callback)
            
            # 艺术家链接 - 重定向格式
            artist_redirect_match = re.search(r'(?:/artist\?|artist\?)(?:.*?&)?id=(\d+)', url)
            if artist_redirect_match:
                artist_id = artist_redirect_match.group(1)
                standard_url = f"https://music.163.com/#/artist?id={artist_id}"
                logger.info(f"🎤 重定向艺术家链接转换为标准格式: {standard_url}")
                # TODO: 实现艺术家下载
                logger.warning("⚠️ 艺术家下载功能暂未实现")
                return {
                    'success': False,
                    'error': '艺术家下载功能暂未实现'
                }
        
        # 如果是短链接，先解析
        if any(domain in url for domain in ['163cn.tv']):
            logger.info(f"🔗 检测到短链接，开始解析: {url}")
            # 尝试解析短链接
            resolved = self.resolve_netease_short_url(url)
            if resolved and resolved['success']:
                url_type = resolved['type']
                music_id = resolved['id']
                
                logger.info(f"✅ 成功解析短链接: 类型={url_type}, ID={music_id}")
                
                # 根据类型调用相应的下载方法
                if url_type == 'song':
                    return self.download_song_by_id(music_id, download_dir, quality, progress_callback)
                elif url_type == 'album':
                    return self.download_album_by_id(music_id, download_dir, quality, progress_callback)
                elif url_type == 'playlist':
                    return self.download_playlist_by_id(music_id, download_dir, quality, progress_callback)
                elif url_type == 'artist':
                    # TODO: 实现艺术家下载
                    logger.warning("⚠️ 艺术家下载功能暂未实现")
                    return {
                        'success': False,
                        'error': '艺术家下载功能暂未实现'
                    }
            else:
                logger.error(f"❌ 解析短链接失败: {resolved.get('error', '未知错误')}")
                return {
                    'success': False,
                    'error': f'解析短链接失败: {resolved.get("error", "未知错误")}'
                }
        
        logger.error(f"❌ 无法识别的链接格式: {url}")
        return {
            'success': False,
            'error': f'无法识别的链接格式: {url}'
        }
        
    def get_quality_setting(self) -> str:
        """获取音质设置，支持多种环境变量和降级逻辑"""
        import os
        
        # 优先检查 NCM_QUALITY_LEVEL（你使用的环境变量）
        quality_level = os.getenv('NCM_QUALITY_LEVEL')
        if quality_level:
            # 支持中文音质名称
            if quality_level in self.chinese_quality_map:
                quality = self.chinese_quality_map[quality_level]
                logger.info(f"🎚️ 从NCM_QUALITY_LEVEL获取音质: {quality_level} -> {quality}")
                return quality
            # 支持英文音质名称
            elif quality_level.lower() in self.quality_map:
                quality = quality_level.lower()
                logger.info(f"🎚️ 从NCM_QUALITY_LEVEL获取音质: {quality}")
                return quality
        
        # 兼容 NCM_QUALITY 环境变量
        ncm_quality = os.getenv('NCM_QUALITY')
        if ncm_quality:
            if ncm_quality.lower() in self.quality_map:
                quality = ncm_quality.lower()
                logger.info(f"🎚️ 从NCM_QUALITY获取音质: {quality}")
                return quality
        
        # 默认使用高音质
        default_quality = 'high'
        logger.info(f"🎚️ 使用默认音质: {default_quality}")
        return default_quality
    
    def _detect_available_formats(self, song_id: str) -> dict:
        """
        检测歌曲所有可用的格式
        返回: {quality: format_type}
        """
        available_formats = {}
        
        for quality in self.quality_fallback:
            quality_code = self.quality_map[quality]
            result = self.get_music_url(song_id, quality_code)
            if result and result['url']:
                format_type = result['format']
                available_formats[quality] = format_type
                logger.debug(f"🔍 {quality} -> {format_type}")
        
        return available_formats

    def get_music_url_with_fallback(self, song_id: str, preferred_quality: str = None) -> tuple:
        """
        获取音乐下载链接，保持原文件格式
        返回: (url, actual_quality, file_format)
        """
        if not preferred_quality:
            preferred_quality = self.get_quality_setting()
        
        # 检测歌曲所有可用的格式
        available_formats = self._detect_available_formats(song_id)
        logger.info(f"🔍 歌曲 {song_id} 可用格式: {available_formats}")
        
        # 从首选音质开始，按降级顺序尝试
        start_index = 0
        if preferred_quality in self.quality_fallback:
            start_index = self.quality_fallback.index(preferred_quality)
        
        # 记录已尝试的格式，避免重复
        tried_formats = set()
        
        # 优先尝试用户指定的音质
        for i in range(start_index, len(self.quality_fallback)):
            quality = self.quality_fallback[i]
            quality_code = self.quality_map[quality]
            
            logger.info(f"🔗 尝试获取音质 {quality} ({quality_code}) 的下载链接: {song_id}")
            result = self.get_music_url(song_id, quality_code)
            
            if result and result['url']:
                file_format = result['format']
                logger.info(f"✅ 获取到 {quality} ({quality_code}) 音质链接，格式: {file_format}")
                
                # 如果这个格式还没尝试过，直接返回
                if file_format not in tried_formats:
                    tried_formats.add(file_format)
                    logger.info(f"🎯 选择格式: {file_format} (音质: {quality})")
                    return result['url'], quality, file_format
                else:
                    logger.info(f"⚠️ 格式 {file_format} 已尝试过，跳过")
        
        # 如果所有音质都尝试过了，返回最后一个可用的
        if result and result['url']:
            logger.warning(f"❌ 所有音质都尝试过，使用最后可用的: {quality} -> {file_format}")
            return result['url'], quality, file_format
        
        logger.error(f"❌ 所有音质都不可用: {song_id}")
        return None, None, None
    

        
    def clean_filename(self, filename: str) -> str:
        """清理文件名中的非法字符"""
        illegal_chars = r'[<>:"/\\|?*]'
        filename = re.sub(illegal_chars, '_', filename)
        filename = filename.strip(' .')
        if len(filename) > 200:
            filename = filename[:200]
        return filename
    
    def _extract_primary_album_artist(self, album_info: Dict) -> str:
        """
        智能提取专辑的主要艺术家
        对于多艺术家合作的专辑，优先使用第一个（主要）艺术家作为专辑艺术家
        """
        try:
            # 首先尝试从 artists 字段获取
            album_artists = album_info.get('artists') or []
            if isinstance(album_artists, list) and album_artists:
                # 只取第一个艺术家作为专辑艺术家（通常是主要艺术家）
                primary_artist = album_artists[0].get('name', '').strip()
                if primary_artist:
                    logger.debug(f"🎤 专辑主要艺术家: {primary_artist}")
                    return primary_artist
            
            # 如果 artists 字段不可用，尝试 artist 字段
            if 'artist' in album_info and album_info['artist']:
                artist_info = album_info['artist']
                if isinstance(artist_info, dict):
                    artist_name = artist_info.get('name', '').strip()
                    if artist_name:
                        logger.debug(f"🎤 专辑艺术家(单一): {artist_name}")
                        return artist_name
                elif isinstance(artist_info, str):
                    # 有时候可能直接是字符串
                    artist_name = artist_info.strip()
                    if artist_name:
                        logger.debug(f"🎤 专辑艺术家(字符串): {artist_name}")
                        return artist_name
            
            # 最后的备选方案：尝试从第一首歌获取主要艺术家
            songs = album_info.get('songs', [])
            if songs and len(songs) > 0:
                first_song = songs[0]
                song_artists = first_song.get('artists', [])
                if song_artists and len(song_artists) > 0:
                    primary_from_song = song_artists[0].get('name', '').strip()
                    if primary_from_song:
                        logger.debug(f"🎤 专辑艺术家(从首歌提取): {primary_from_song}")
                        return primary_from_song
            
            logger.warning("⚠️ 无法确定专辑主要艺术家，使用默认值")
            return 'Various Artists'
            
        except Exception as e:
            logger.warning(f"⚠️ 提取专辑艺术家时出错: {e}")
            return 'Unknown Artist'
    
    def _extract_primary_artist_from_string(self, artist_string: str) -> str:
        """
        从包含多个艺术家的字符串中提取第一个（主要）艺术家
        处理格式如："王力宏, Rain, 林贞熙" -> "王力宏"
        """
        if not artist_string:
            return ''
        
        try:
            # 常见的艺术家分隔符
            separators = [', ', '、', '/', ' feat. ', ' ft. ', ' & ', ' and ']
            
            # 尝试各种分隔符
            for separator in separators:
                if separator in artist_string:
                    primary_artist = artist_string.split(separator)[0].strip()
                    if primary_artist:
                        logger.debug(f"🎤 提取主要艺术家: '{primary_artist}' (从 '{artist_string}')")
                        return primary_artist
            
            # 如果没有找到分隔符，返回原字符串（可能就是单一艺术家）
            return artist_string.strip()
            
        except Exception as e:
            logger.warning(f"⚠️ 提取主要艺术家时出错: {e}")
            return artist_string
    
    def search_netease_music(self, keyword: str, limit: int = 20) -> Optional[List[Dict]]:
        """搜索网易云音乐"""
        try:
            # 使用网易云音乐搜索API
            url = f"{self.api_url}/api/search/get/web"
            params = {
                'csrf_token': '',
                's': keyword,
                'type': '1',  # 1表示搜索歌曲
                'offset': '0',
                'total': 'true',
                'limit': str(limit)
            }

            logger.info(f"🔍 搜索歌曲: {keyword}")

            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()

            data = response.json()

            if data.get('code') == 200 and data.get('result'):
                songs = data['result'].get('songs', [])

                processed_songs = []
                for song in songs:
                    song_info = {
                        'id': str(song.get('id')),
                        'name': song.get('name', 'Unknown'),
                        'artist': ', '.join([artist.get('name', '') for artist in song.get('artists', [])]),
                        'album': song.get('album', {}).get('name', 'Unknown'),
                        'duration': song.get('duration', 0) // 1000  # 转换为秒
                    }
                    processed_songs.append(song_info)

                logger.info(f"✅ 搜索到 {len(processed_songs)} 首歌曲")
                return processed_songs
            else:
                logger.error(f"❌ 搜索失败: {data.get('msg', '未知错误')}")

        except Exception as e:
            logger.error(f"❌ 搜索时出错: {e}")

        return None

    def search_netease_album(self, keyword: str, limit: int = 20) -> Optional[List[Dict]]:
        """搜索网易云音乐专辑"""
        try:
            # 使用网易云音乐专辑搜索API
            url = f"{self.api_url}/api/search/get/web"
            params = {
                'csrf_token': '',
                's': keyword,
                'type': '10',  # 10表示搜索专辑
                'offset': '0',
                'total': 'true',
                'limit': str(limit)
            }

            logger.info(f"🔍 搜索专辑: {keyword}")

            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()

            data = response.json()

            if data.get('code') == 200 and data.get('result'):
                albums = data['result'].get('albums', [])

                processed_albums = []
                for album in albums:
                    album_info = {
                        'id': str(album.get('id')),
                        'name': album.get('name', 'Unknown'),
                        'artist': album.get('artist', {}).get('name', 'Unknown'),
                        'size': album.get('size', 0),  # 专辑歌曲数量
                        'publishTime': album.get('publishTime', 0)
                    }
                    processed_albums.append(album_info)

                logger.info(f"✅ 搜索到 {len(processed_albums)} 个专辑")
                return processed_albums
            else:
                logger.error(f"❌ 专辑搜索失败: {data.get('msg', '未知错误')}")

        except Exception as e:
            logger.error(f"❌ 专辑搜索时出错: {e}")

        return None

    def get_album_songs(self, album_id: str) -> Optional[List[Dict]]:
        """获取专辑中的所有歌曲"""
        try:
            url = f"https://music.163.com/api/album/{album_id}"

            response = self.session.get(url, timeout=15)
            response.raise_for_status()

            data = response.json()

            if data.get('code') == 200 and data.get('album'):
                album_info = data['album']
                songs = album_info.get('songs', [])
                # 从专辑信息提取公用字段（封面、发行时间、专辑艺术家）
                album_pic_url = album_info.get('picUrl', '')
                # 专辑艺术家处理：优先使用主要艺术家，避免多艺术家列表
                album_artist_name = self._extract_primary_album_artist(album_info)
                album_publish_time = album_info.get('publishTime', 0)

                processed_songs = []
                for song in songs:
                    # 确保只使用第一个艺术家，避免多艺术家显示
                    artists = song.get('artists', [])
                    if artists:
                        primary_artist = artists[0].get('name', '')
                    else:
                        primary_artist = 'Unknown'
                    
                    song_info = {
                        'id': song.get('id'),
                        'name': song.get('name', 'Unknown'),
                        'artist': primary_artist,
                        'album': album_info.get('name', 'Unknown'),
                        'duration': song.get('duration', 0) // 1000,  # 转换为秒
                        'track_number': song.get('no', 0),  # 曲目编号
                        # 新增：为后续元数据写入提供专辑级信息
                        'pic_url': album_pic_url,
                        'publish_time': album_publish_time,
                        'album_artist': album_artist_name
                    }
                    processed_songs.append(song_info)

                logger.info(f"✅ 获取到专辑 {album_info.get('name')} 中的 {len(processed_songs)} 首歌曲")
                return processed_songs
            else:
                logger.error(f"❌ 获取专辑歌曲失败: {data.get('msg', '未知错误')}")
                logger.error(f"❌ API响应: {data}")

        except Exception as e:
            logger.error(f"❌ 获取专辑歌曲时出错: {e}")

        return None

    def get_song_info(self, song_id: str) -> Optional[Dict]:
        """通过歌曲ID获取歌曲详细信息"""
        try:
            # 使用网易云音乐的歌曲详情API
            url = f"https://music.163.com/api/song/detail/?id={song_id}&ids=[{song_id}]"

            response = self.session.get(url, timeout=15)
            response.raise_for_status()

            data = response.json()

            if data.get('code') == 200 and data.get('songs'):
                song = data['songs'][0]

                # 提取歌曲信息
                # 确保只使用第一个艺术家，避免多艺术家显示
                artists = song.get('artists', [])
                if artists:
                    primary_artist = artists[0].get('name', 'Unknown')
                else:
                    primary_artist = 'Unknown'
                
                song_info = {
                    'id': song.get('id'),
                    'name': song.get('name', 'Unknown'),
                    'artist': primary_artist,
                    'album': song.get('album', {}).get('name', 'Unknown'),
                    'duration': song.get('duration', 0),
                    'pic_url': song.get('album', {}).get('picUrl', ''),
                    'publish_time': song.get('album', {}).get('publishTime', 0)
                }

                logger.info(f"✅ 获取歌曲信息成功: {song_info['name']} - {song_info['artist']}")
                return song_info
            else:
                logger.warning(f"⚠️ 歌曲详情API返回异常: {data}")
                return None

        except Exception as e:
            logger.error(f"❌ 获取歌曲信息时出错: {e}")
            return None

    def get_music_url(self, song_id: str, quality: str = '128k') -> Optional[Dict]:
        """
        获取网易云音乐下载链接和格式信息
        返回: {'url': str, 'format': str} 或 None
        """
        try:
            # 使用网易云音乐的歌曲URL获取API
            url = f"{self.api_url}/api/song/enhance/player/url"

            # 音质映射 - 网易云API参数
            quality_map = {
                '128k': 128000,        # 标准音质
                '320k': 320000,        # 较高音质
                'flac': 999000,        # 极高/无损
                'flac24bit': 1999000,  # Hi-Res 24bit及以上
                # 兼容旧参数
                'high': 320000,        # 兼容：较高
                'lossless': 999000,    # 兼容：无损
                'hires': 1999000,      # 兼容：高解析度无损
                'master': 1999000,     # 兼容：超清母带
                'surround': 1999000    # 兼容：沉浸环绕声
            }

            br = quality_map.get(quality, 128000)

            params = {
                'ids': f'[{song_id}]',
                'br': br,
                # 移除强制的encodeType参数，让API返回原始格式
                # 'encodeType': 'flac' if br >= 999000 else 'mp3'  # 指定编码类型
            }

            logger.info(f"🔗 请求音乐链接: {song_id} (音质: {quality}, API参数: {br})")

            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()

            data = response.json()

            if data.get('code') == 200:
                song_data = data.get('data', [])
                if song_data and len(song_data) > 0:
                    song_info = song_data[0]
                    music_url = song_info.get('url')

                    if music_url:
                        # 从URL中推断文件格式
                        file_format = self._extract_format_from_url(music_url)
                        logger.info(f"✅ 获取音乐链接成功: {song_id}, 格式: {file_format}")
                        return {
                            'url': music_url,
                            'format': file_format
                        }
                    else:
                        logger.warning(f"⚠️ 音乐链接为空，可能需要VIP或版权限制: {song_id}")
                        return None
                else:
                    logger.warning(f"⚠️ 未获取到歌曲数据: {song_id}")
                    return None
            else:
                logger.error(f"❌ 获取音乐链接失败: {data.get('message', '未知错误')}")

        except Exception as e:
            logger.error(f"❌ 获取音乐链接时出错: {e}")

        return None
    
    def _extract_format_from_url(self, url: str) -> str:
        """
        从下载URL中推断文件格式
        """
        try:
            import urllib.parse
            parsed_url = urllib.parse.urlparse(url)
            path = parsed_url.path.lower()
            query = parsed_url.query.lower()
            
            # 从URL路径和查询参数中提取文件扩展名
            full_url_lower = url.lower()
            
            if '.flac' in full_url_lower:
                return 'flac'
            elif '.mp3' in full_url_lower:
                return 'mp3'
            elif '.ape' in full_url_lower:
                return 'ape'
            elif '.wav' in full_url_lower:
                return 'wav'
            elif '.m4a' in full_url_lower:
                return 'm4a'
            else:
                # 如果URL中没有明确的格式，默认为mp3
                logger.warning(f"⚠️ 无法从URL推断格式，使用默认mp3: {url[:100]}...")
                return 'mp3'
        except Exception as e:
            logger.error(f"❌ 推断文件格式时出错: {e}")
            return 'mp3'
    
    def get_file_size(self, url: str) -> int:
        """获取文件大小（字节）"""
        try:
            response = requests.head(url, timeout=10)
            if response.status_code == 200:
                content_length = response.headers.get('content-length')
                if content_length:
                    return int(content_length)
        except Exception as e:
            logger.warning(f"⚠️ 获取文件大小失败: {e}")
        return 0

    def format_file_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        if size_bytes == 0:
            return "0B"

        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                if unit == 'B':
                    return f"{int(size_bytes)}{unit}"
                else:
                    return f"{size_bytes:.1f}{unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f}TB"

    def download_file(self, url: str, filepath: str, song_name: str = "", retries: int = 3, progress_callback=None) -> bool:
        """下载文件并记录统计信息，支持进度回调"""
        # 获取文件大小
        file_size = self.get_file_size(url)
        filename = Path(filepath).name

        for attempt in range(retries):
            try:
                logger.info(f"⬇️ 正在下载: {filename}")
                response = requests.get(url, timeout=30, stream=True)
                response.raise_for_status()

                # 确保目录存在
                os.makedirs(os.path.dirname(filepath), exist_ok=True)

                # 获取实际文件大小
                total_size = int(response.headers.get('content-length', file_size or 0))
                downloaded_size = 0

                # 发送开始下载的进度信息
                if progress_callback:
                    progress_callback({
                        'status': 'downloading',
                        'filename': filename,
                        'total_bytes': total_size,
                        'downloaded_bytes': 0,
                        'speed': 0,
                        'eta': 0
                    })


                start_time = time.time()
                last_update_time = start_time

                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded_size += len(chunk)

                            current_time = time.time()

                            # 每0.5秒更新一次进度
                            if current_time - last_update_time >= 0.5 or downloaded_size == total_size:
                                # 计算下载速度
                                elapsed_time = current_time - start_time
                                speed = downloaded_size / elapsed_time if elapsed_time > 0 else 0

                                # 计算预计剩余时间
                                eta = 0
                                if speed > 0 and total_size > downloaded_size:
                                    eta = (total_size - downloaded_size) / speed

                                # 发送进度更新
                                if progress_callback:
                                    progress_callback({
                                        'status': 'downloading',
                                        'filename': filename,
                                        'total_bytes': total_size,
                                        'downloaded_bytes': downloaded_size,
                                        'speed': speed,
                                        'eta': eta
                                    })

                                last_update_time = current_time

                # 获取实际文件大小
                actual_size = os.path.getsize(filepath)

                # 发送完成信息（仅在单曲下载时发送，专辑下载时由上层统一处理）
                if progress_callback:
                    # 检查是否是单曲下载（通过检查是否有专辑上下文来判断）
                    is_single_song = not hasattr(self, '_in_album_download') or not self._in_album_download
                    if is_single_song:
                        progress_callback({
                            'status': 'finished',
                            'filename': filename,
                            'total_bytes': actual_size,
                            'downloaded_bytes': actual_size,
                            'speed': 0,
                            'eta': 0
                        })

                # 统计信息的更新由上层调用方（专辑/单曲下载函数）统一处理，避免重复统计

                logger.info(f"✅ 下载成功: {filename} ({self.format_file_size(actual_size)})")
                return True

            except Exception as e:
                logger.warning(f"⚠️ 下载失败 (尝试 {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(2)

        return False
    
    def get_song_lyrics(self, song_id: str) -> Optional[Dict[str, str]]:
        """
        获取歌曲歌词
        
        Args:
            song_id: 歌曲ID
            
        Returns:
            Dict包含歌词信息: {'lrc': '同步歌词', 'tlyric': '翻译歌词', 'romalrc': '罗马音歌词'}
            如果获取失败返回None
        """
        try:
            logger.info(f"🎤 获取歌词: {song_id}")
            
            # 网易云音乐歌词API
            url = f"{self.api_url}/api/song/lyric"
            params = {
                'id': song_id,
                'lv': 1,  # 原版歌词
                'tv': 1,  # 翻译歌词
                'rv': 1   # 罗马音歌词
            }
            
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('code') == 200:
                lyrics_data = {}
                
                # 获取原版歌词 (LRC格式)
                if 'lrc' in data and data['lrc'].get('lyric'):
                    lyrics_data['lrc'] = data['lrc']['lyric']
                    logger.debug(f"✅ 获取到原版歌词")
                
                # 获取翻译歌词
                if 'tlyric' in data and data['tlyric'].get('lyric'):
                    lyrics_data['tlyric'] = data['tlyric']['lyric']
                    logger.debug(f"✅ 获取到翻译歌词")
                
                # 获取罗马音歌词
                if 'romalrc' in data and data['romalrc'].get('lyric'):
                    lyrics_data['romalrc'] = data['romalrc']['lyric']
                    logger.debug(f"✅ 获取到罗马音歌词")
                
                if lyrics_data:
                    logger.info(f"✅ 成功获取歌词: {song_id}")
                    return lyrics_data
                else:
                    logger.warning(f"⚠️ 歌曲无歌词或歌词为空: {song_id}")
                    return None
            else:
                logger.warning(f"⚠️ 获取歌词失败: {data.get('msg', '未知错误')}")
                return None
                
        except Exception as e:
            logger.error(f"❌ 获取歌词时出错: {e}")
            return None
    
    def save_lyrics_file(
        self, 
        lyrics_data: Dict[str, str], 
        music_file_path: str, 
        song_info: Dict
    ) -> bool:
        """
        保存歌词文件
        
        Args:
            lyrics_data: 歌词数据字典
            music_file_path: 音乐文件路径
            song_info: 歌曲信息
            
        Returns:
            bool: 是否成功保存歌词文件
        """
        try:
            music_path = Path(music_file_path)
            base_name = music_path.stem  # 不包含扩展名的文件名
            lyrics_dir = music_path.parent  # 直接使用音乐文件所在目录
            
            # 添加调试信息
            logger.info(f"🔍 歌词保存路径调试:")
            logger.info(f"   - 音乐文件路径: {music_file_path}")
            logger.info(f"   - 音乐文件目录: {music_path.parent}")
            logger.info(f"   - 歌词保存目录: {lyrics_dir}")
            logger.info(f"   - 歌词保存目录绝对路径: {lyrics_dir.absolute()}")
            
            song_name = song_info.get('name', 'Unknown')
            artist = song_info.get('artist', 'Unknown')
            
            saved_files = []
            
            # 检查是否启用歌词合并（动态读取配置）
            lyrics_merge_enabled = False
            try:
                # 优先从bot配置获取歌词合并设置
                if hasattr(self, 'bot') and hasattr(self.bot, 'netease_lyrics_merge'):
                    lyrics_merge_enabled = self.bot.netease_lyrics_merge
                    logger.info(f"🎤 从bot配置获取歌词合并设置: {'启用' if lyrics_merge_enabled else '禁用'}")
                else:
                    # 如果bot配置不可用，尝试从配置文件直接读取
                    try:
                        # 尝试多个可能的配置文件路径
                        possible_paths = [
                            Path("config/settings.json"),
                            Path("./config/settings.json"),
                            Path("../config/settings.json"),
                            Path("settings.json")
                        ]
                        
                        config_found = False
                        for config_path in possible_paths:
                            logger.info(f"🔍 尝试配置文件路径: {config_path.absolute()}")
                            if config_path.exists():
                                with open(config_path, 'r', encoding='utf-8') as f:
                                    config_data = json.load(f)
                                    lyrics_merge_enabled = config_data.get("netease_lyrics_merge", False)
                                    logger.info(f"🎤 从配置文件 {config_path} 获取歌词合并设置: {'启用' if lyrics_merge_enabled else '禁用'}")
                                    config_found = True
                                    break
                        
                        if not config_found:
                            logger.warning("⚠️ 所有可能的配置文件路径都不存在")
                            logger.info(f"🔍 当前工作目录: {os.getcwd()}")
                            logger.info(f"🔍 当前目录内容: {list(os.listdir('.'))}")
                    except Exception as e:
                        logger.warning(f"⚠️ 读取配置文件失败: {e}")
                        lyrics_merge_enabled = False
            except Exception as e:
                logger.warning(f"⚠️ 获取歌词合并设置失败，使用默认值: {e}")
            
            if lyrics_merge_enabled:
                # 启用歌词合并模式：创建合并歌词文件
                logger.info("🎤 启用歌词合并模式，创建合并歌词文件")
                
                # 合并所有可用的歌词类型
                merged_lyrics = None
                merge_description = ""
                
                # 检查有哪些歌词类型可用
                has_lrc = 'lrc' in lyrics_data and lyrics_data['lrc'].strip()
                has_tlyric = 'tlyric' in lyrics_data and lyrics_data['tlyric'].strip()
                has_romalrc = 'romalrc' in lyrics_data and lyrics_data['romalrc'].strip()
                
                if has_lrc and has_romalrc and has_tlyric:
                    # 三种歌词都有：原文+中文翻译+罗马音
                    logger.info("🎤 检测到三种歌词，进行完整合并")
                    
                    # 直接合并三种歌词，按原文+中文+罗马音的顺序
                    merged_lyrics = self._merge_three_lyrics(
                        lyrics_data['lrc'],
                        lyrics_data['tlyric'], 
                        lyrics_data['romalrc']
                    )
                    merge_description = "原文+中文翻译+罗马音"
                
                elif has_lrc and has_tlyric:
                    # 只有原文+翻译
                    logger.info("🎤 检测到原文+翻译歌词，进行合并")
                    merged_lyrics = self._merge_lyrics(
                        lyrics_data['lrc'], 
                        lyrics_data['tlyric'], 
                        "原版+翻译"
                    )
                    merge_description = "原文+翻译"
                
                elif has_lrc and has_romalrc:
                    # 只有原文+罗马音
                    logger.info("🎤 检测到原文+罗马音歌词，进行合并")
                    merged_lyrics = self._merge_lyrics(
                        lyrics_data['lrc'], 
                        lyrics_data['romalrc'], 
                        "原版+罗马音"
                    )
                    merge_description = "原文+罗马音"
                
                elif has_lrc and has_tlyric and not has_romalrc:
                    # 只有原文+中文
                    logger.info("🎤 检测到原文+中文歌词，进行合并")
                    merged_lyrics = self._merge_lyrics(
                        lyrics_data['lrc'], 
                        lyrics_data['tlyric'], 
                        "原版+中文"
                    )
                    merge_description = "原文+中文"
                
                elif has_lrc and has_romalrc and not has_tlyric:
                    # 只有原文+罗马音
                    logger.info("🎤 检测到原文+罗马音歌词，进行合并")
                    merged_lyrics = self._merge_lyrics(
                        lyrics_data['lrc'], 
                        lyrics_data['romalrc'], 
                        "原版+罗马音"
                    )
                    merge_description = "原文+罗马音"
                elif has_lrc:
                    # 只有原文歌词，直接使用原文
                    logger.info("🎤 只有原文歌词，直接使用原文")
                    merged_lyrics = lyrics_data['lrc']
                    merge_description = "原文"
                
                # 保存合并后的歌词
                if merged_lyrics:
                    merged_path = lyrics_dir / f"{base_name}.lrc"
                    merged_content = self._format_lrc_content(
                        merged_lyrics,
                        f"{song_name} ({merge_description})",
                        artist,
                        song_info.get('album', ''),
                        song_info.get('track_number', '')
                    )
                    with open(merged_path, 'w', encoding='utf-8') as f:
                        f.write(merged_content)
                    saved_files.append(str(merged_path))
                    logger.info(f"✅ 保存合并歌词: {merged_path.name} ({merge_description})")
                else:
                    logger.warning("⚠️ 没有可用的歌词内容进行合并")
                
            else:
                # 默认模式：保存3个独立的歌词文件
                logger.info("🎤 使用默认模式，保存独立歌词文件")
                
                # 保存原版LRC歌词
                if 'lrc' in lyrics_data and lyrics_data['lrc'].strip():
                    lrc_path = lyrics_dir / f"{base_name}.lrc"
                    
                    # 添加歌词文件头信息
                    lrc_content = self._format_lrc_content(
                        lyrics_data['lrc'], 
                        song_name, 
                        artist,
                        song_info.get('album', ''),
                        song_info.get('track_number', '')
                    )
                    
                    with open(lrc_path, 'w', encoding='utf-8') as f:
                        f.write(lrc_content)
                    
                    saved_files.append(str(lrc_path))
                    logger.info(f"✅ 保存LRC歌词: {lrc_path.name}")
                
                # 保存中文歌词（如果有）
                if 'tlyric' in lyrics_data and lyrics_data['tlyric'].strip():
                    tlyric_path = lyrics_dir / f"{base_name}.中文.lrc"
                    
                    tlyric_content = self._format_lrc_content(
                        lyrics_data['tlyric'],
                        f"{song_name} (中文)",
                        artist,
                        song_info.get('album', ''),
                        song_info.get('track_number', '')
                    )
                    
                    with open(tlyric_path, 'w', encoding='utf-8') as f:
                        f.write(tlyric_content)
                    
                    saved_files.append(str(tlyric_path))
                    logger.info(f"✅ 保存中文歌词: {tlyric_path.name}")
                
                # 保存罗马音歌词（如果有）
                if 'romalrc' in lyrics_data and lyrics_data['romalrc'].strip():
                    romalrc_path = lyrics_dir / f"{base_name}.罗马音.lrc"
                    
                    romalrc_content = self._format_lrc_content(
                        lyrics_data['romalrc'],
                        f"{song_name} (罗马音)",
                        artist,
                        song_info.get('album', ''),
                        song_info.get('track_number', '')
                    )
                    
                    with open(romalrc_path, 'w', encoding='utf-8') as f:
                        f.write(romalrc_content)
                    
                    saved_files.append(str(romalrc_path))
                    logger.info(f"✅ 保存罗马音歌词: {romalrc_path.name}")
            
            if saved_files:
                logger.info(f"🎤 成功保存 {len(saved_files)} 个歌词文件")
                return True
            else:
                logger.warning(f"⚠️ 没有有效的歌词内容可保存")
                return False
                
        except Exception as e:
            logger.error(f"❌ 保存歌词文件时出错: {e}")
            return False
    
    def _format_lrc_content(
        self, 
        raw_lyrics: str, 
        title: str, 
        artist: str, 
        album: str = '',
        track: str = ''
    ) -> str:
        """
        格式化LRC歌词内容，添加标准的LRC文件头
        
        Args:
            raw_lyrics: 原始歌词内容
            title: 歌曲标题
            artist: 艺术家
            album: 专辑名称
            track: 曲目编号
            
        Returns:
            str: 格式化后的LRC内容
        """
        try:
            from datetime import datetime
            
            # LRC标准文件头
            header_lines = [
                f"[ti:{title}]",
                f"[ar:{artist}]"
            ]
            
            if album:
                header_lines.append(f"[al:{album}]")
            
            if track:
                header_lines.append(f"[offset:0]")
            
            # 只添加空行分隔，保持简洁格式
            header_lines.append("")
            
            # 组合完整内容
            formatted_content = "\n".join(header_lines) + raw_lyrics
            
            return formatted_content
            
        except Exception as e:
            logger.warning(f"⚠️ 格式化歌词时出错，使用原始内容: {e}")
            return raw_lyrics
    
    def _merge_three_lyrics(self, lyrics1: str, lyrics2: str, lyrics3: str) -> str:
        """
        合并三种歌词，按时间轴垂直对齐，顺序为：原文、中文、罗马音
        
        Args:
            lyrics1: 原文歌词
            lyrics2: 中文翻译歌词
            lyrics3: 罗马音歌词
            
        Returns:
            str: 合并后的歌词内容
        """
        try:
            import re
            
            # 解析三种歌词的时间轴和内容
            lyrics1_lines = self._parse_lyrics_with_timestamps(lyrics1)
            lyrics2_lines = self._parse_lyrics_with_timestamps(lyrics2)
            lyrics3_lines = self._parse_lyrics_with_timestamps(lyrics3)
            
            if not lyrics1_lines:
                logger.warning(f"⚠️ 原文歌词解析失败，无法合并")
                return lyrics1
            
            # 创建合并后的歌词
            merged_lines = []
            
            # 遍历原文歌词的每一行
            for timestamp, content1 in lyrics1_lines:
                # 查找相同时间轴的中文翻译
                content2 = ""
                for ts2, content2_temp in lyrics2_lines:
                    if ts2 == timestamp:
                        content2 = content2_temp
                        break
                
                # 查找相同时间轴的罗马音
                content3 = ""
                for ts3, content3_temp in lyrics3_lines:
                    if ts3 == timestamp:
                        content3 = content3_temp
                        break
                
                # 按顺序添加：原文、中文、罗马音
                merged_lines.append(f"[{timestamp}]{content1}")
                if content2:
                    merged_lines.append(f"[{timestamp}]{content2}")
                if content3:
                    merged_lines.append(f"[{timestamp}]{content3}")
            
            # 组合最终结果
            merged_lyrics = "\n".join(merged_lines)
            
            logger.info(f"✅ 成功合并三种歌词: 原文+中文+罗马音, 共 {len(merged_lines)} 行")
            return merged_lyrics
            
        except Exception as e:
            logger.error(f"❌ 合并三种歌词时出错: {e}")
            # 如果合并失败，返回原文歌词
            return lyrics1

    def _merge_lyrics(self, lyrics1: str, lyrics2: str, merge_type: str) -> str:
        """
        合并两种歌词，按时间轴垂直对齐
        
        Args:
            lyrics1: 第一种歌词（通常是原版）
            lyrics2: 第二种歌词（翻译或罗马音）
            merge_type: 合并类型标识
            
        Returns:
            str: 合并后的歌词内容
        """
        try:
            import re
            
            # 解析第一种歌词的时间轴和内容
            lyrics1_lines = self._parse_lyrics_with_timestamps(lyrics1)
            
            # 解析第二种歌词的时间轴和内容
            lyrics2_lines = self._parse_lyrics_with_timestamps(lyrics2)
            
            if not lyrics1_lines:
                logger.warning(f"⚠️ 第一种歌词解析失败，无法合并")
                return lyrics1
            
            # 创建合并后的歌词
            merged_lines = []
            
            # 遍历第一种歌词的每一行
            for timestamp, content1 in lyrics1_lines:
                # 查找相同时间轴的第二种歌词
                content2 = ""
                for ts2, content2_temp in lyrics2_lines:
                    if ts2 == timestamp:
                        content2 = content2_temp
                        break
                
                # 垂直合并内容：先显示第一种，再显示第二种
                if content2:
                    # 两种语言都有内容，垂直显示
                    merged_lines.append(f"[{timestamp}]{content1}")
                    merged_lines.append(f"[{timestamp}]{content2}")
                else:
                    # 只有第一种语言有内容
                    merged_lines.append(f"[{timestamp}]{content1}")
            
            # 组合最终结果
            merged_lyrics = "\n".join(merged_lines)
            
            logger.info(f"✅ 成功合并歌词: {merge_type}, 共 {len(merged_lines)} 行")
            return merged_lyrics
            
        except Exception as e:
            logger.error(f"❌ 合并歌词时出错: {e}")
            # 如果合并失败，返回第一种歌词
            return lyrics1
    
    def _parse_lyrics_with_timestamps(self, lyrics: str) -> list:
        """
        解析歌词，提取时间轴和内容
        
        Args:
            lyrics: 原始歌词内容
            
        Returns:
            list: [(timestamp, content), ...] 格式的列表
        """
        try:
            import re
            
            # 匹配时间轴格式 [mm:ss.fff] 或 [mm:ss.ff] 或 [mm:ss] 或 [mm:ss.f]
            timestamp_pattern = r'\[(\d{2}:\d{2}(?:\.\d{1,3})?)\](.*)'
            
            lines = []
            for line in lyrics.split('\n'):
                line = line.strip()
                if not line:
                    continue
                    
                match = re.match(timestamp_pattern, line)
                if match:
                    timestamp = match.group(1)
                    content = match.group(2).strip()
                    if content:  # 只添加有内容的行
                        lines.append((timestamp, content))
            
            return lines
            
        except Exception as e:
            logger.error(f"❌ 解析歌词时间轴时出错: {e}")
            return []
    
    def download_song_lyrics(self, song_id: str, music_file_path: str, song_info: Dict) -> bool:
        """
        下载并保存歌曲歌词
        
        Args:
            song_id: 歌曲ID
            music_file_path: 音乐文件路径
            song_info: 歌曲信息
            
        Returns:
            bool: 是否成功下载歌词
        """
        try:
            logger.info(f"🔧 调试: 开始下载歌词 - song_id={song_id}, file={Path(music_file_path).name}")
            logger.info(f"🔧 调试: enable_lyrics_download = {self.enable_lyrics_download}")
            
            # 检查是否启用歌词下载
            if not self.enable_lyrics_download:
                logger.warning("📝 歌词下载功能已禁用，跳过")
                return False
            
            # 获取歌词
            lyrics_data = self.get_song_lyrics(song_id)
            
            if not lyrics_data:
                logger.info(f"📝 歌曲无歌词: {song_info.get('name', 'Unknown')}")
                return False
            
            # 保存歌词文件
            success = self.save_lyrics_file(lyrics_data, music_file_path, song_info)
            
            if success:
                logger.info(f"🎤 歌词下载完成: {Path(music_file_path).stem}")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ 下载歌词时出错: {e}")
            return False

    def add_metadata_to_music_file(
        self, 
        file_path: str, 
        song_info: Dict, 
        album_info: Optional[Dict] = None
    ) -> bool:
        """为下载的音乐文件添加元数据"""
        logger.info(f"🔧 调试: 开始处理元数据 - {Path(file_path).name}")
        logger.info(f"🔧 调试: metadata_manager = {self.metadata_manager}")
        logger.info(f"🔧 调试: METADATA_AVAILABLE = {METADATA_AVAILABLE}")
        
        if not self.metadata_manager:
            # 不直接返回，尝试本地回退方案（使用mutagen直接写入）
            logger.warning("⚠️ 元数据管理器不可用，尝试使用内置回退方式写入元数据")
        
        try:
            # 安全提取发布时间（分别提取年份和完整日期）
            def _extract_year(publish_time_value) -> str:
                """提取年份"""
                if not publish_time_value:
                    return ''
                try:
                    if isinstance(publish_time_value, int):
                        from datetime import datetime
                        dt = datetime.fromtimestamp(publish_time_value / 1000)
                        return str(dt.year)
                    s = str(publish_time_value)
                    return s[:4] if len(s) >= 4 else s
                except Exception:
                    return ''
            
            def _extract_release_date(publish_time_value) -> str:
                """提取完整发布日期"""
                if not publish_time_value:
                    return ''
                try:
                    if isinstance(publish_time_value, int):
                        from datetime import datetime
                        dt = datetime.fromtimestamp(publish_time_value / 1000)
                        return dt.strftime('%Y-%m-%d')
                    # 如果是字符串且长度足够，尝试解析
                    s = str(publish_time_value)
                    if len(s) >= 8:  # 可能是日期字符串
                        return s
                    return ''  # 太短的字符串不能作为完整日期
                except Exception:
                    return ''

            # 智能处理发布时间：优先使用完整日期，否则使用年份
            song_release_date = _extract_release_date(song_info.get('publish_time'))
            song_publish_year = _extract_year(song_info.get('publish_time'))

            # 准备元数据
            # 智能处理专辑艺术家：对于多艺术家的歌曲，优先使用第一个艺术家作为专辑艺术家
            song_album_artist = song_info.get('album_artist', '')
            if not song_album_artist:
                # 如果没有明确的专辑艺术家，从歌曲艺术家中提取第一个
                song_album_artist = self._extract_primary_artist_from_string(song_info.get('artist', ''))
            
            metadata = {
                'title': song_info.get('name', ''),
                'artist': song_info.get('artist', ''),
                'album': song_info.get('album', ''),
                'album_artist': song_album_artist,
                'track_number': str(song_info.get('track_number', '')),
                'disc_number': '1',  # 固定写入碟片编号为 1
                'genre': '流行'  # 默认流派
            }
            
            # 智能处理时间字段：有完整日期时同时写入年份和完整日期，否则只写年份
            if song_release_date and len(song_release_date) > 4:  # 有完整日期
                metadata['date'] = song_publish_year  # 年份 → DATE
                metadata['releasetime'] = song_release_date  # 完整日期 → RELEASETIME
                logger.debug(f"🗓️ 同时写入年份: {song_publish_year} 和完整发布时间: {song_release_date}")
            elif song_publish_year:  # 只有年份
                metadata['date'] = song_publish_year  # 年份 → DATE  
                logger.debug(f"📅 只写入发布年份: {song_publish_year}")
            
            # 如果有专辑信息，优先使用专辑信息
            if album_info:
                metadata['album'] = album_info.get('name', metadata['album'])
                metadata['album_artist'] = album_info.get('artist', metadata['album_artist'])
                album_release_date = _extract_release_date(album_info.get('publish_time'))
                album_publish_year = _extract_year(album_info.get('publish_time'))
                
                # 智能处理专辑时间字段
                if album_release_date and len(album_release_date) > 4:  # 专辑有完整日期
                    metadata['date'] = album_publish_year or metadata.get('date', '')  # 年份 → DATE
                    metadata['releasetime'] = album_release_date  # 完整日期 → RELEASETIME
                    logger.debug(f"🗓️ 专辑同时写入年份: {metadata['date']} 和完整发布时间: {album_release_date}")
                elif album_publish_year:  # 专辑只有年份
                    metadata['date'] = album_publish_year  # 年份 → DATE
                    # 移除可能的完整日期字段，因为我们只有年份
                    metadata.pop('releasetime', None)
                    logger.debug(f"📅 专辑只写入发布年份: {album_publish_year}")
            
            # 获取专辑封面URL
            cover_url = song_info.get('pic_url') or (album_info.get('pic_url') if album_info else None)
            
            logger.info(f"🏷️ 为音乐文件添加元数据: {Path(file_path).name}")
            logger.debug(f"  标题: {metadata['title']}")
            logger.debug(f"  艺术家: {metadata['artist']}")
            logger.debug(f"  专辑: {metadata['album']}")
            
            # 如果有外部管理器，优先使用
            if self.metadata_manager:
                success = self.metadata_manager.add_metadata_to_file(
                    file_path=file_path,
                    metadata=metadata,
                    cover_url=cover_url
                )
            else:
                # 使用回退方案写入元数据
                success = self._embed_metadata_fallback(file_path, metadata, cover_url)
            
            if success:
                logger.info(f"✅ 成功添加元数据: {Path(file_path).name}")
            else:
                logger.warning(f"⚠️ 添加元数据失败: {Path(file_path).name}")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ 添加元数据时出错: {e}")
            return False

    def _embed_metadata_fallback(self, file_path: str, metadata: Dict, cover_url: Optional[str]) -> bool:
        """当外部元数据管理器不可用时，使用mutagen直接写入元数据。
        仅依赖 mutagen，可选使用 requests 下载封面。
        """
        try:
            from mutagen import File
            from mutagen.id3 import (
                ID3,
                ID3NoHeaderError,
                TIT2,
                TPE1,
                TALB,
                TPE2,
                TRCK,
                TCON,
                APIC,
                TDRC,
                TYER,
            )
            from mutagen.flac import FLAC, Picture
        except Exception as e:
            logger.warning(f"⚠️ 回退元数据写入不可用（缺少mutagen）: {e}")
            return False

        try:
            path_obj = Path(file_path)
            suffix = path_obj.suffix.lower()

            title = metadata.get('title', '')
            artist = metadata.get('artist', '')
            album = metadata.get('album', '')
            album_artist = metadata.get('album_artist', artist)
            track_number = str(metadata.get('track_number', '') or '')
            disc_number = str(metadata.get('disc_number', '1') or '1')
            genre = metadata.get('genre', '流行')

            cover_data: Optional[bytes] = None
            cover_mime = 'image/jpeg'
            if cover_url:
                try:
                    import requests as _req
                    resp = _req.get(cover_url, timeout=15)
                    resp.raise_for_status()
                    cover_data = resp.content
                    ctype = resp.headers.get('content-type', '').lower()
                    if 'png' in ctype:
                        cover_mime = 'image/png'
                except Exception as ce:
                    logger.warning(f"⚠️ 下载专辑封面失败，跳过封面: {ce}")

            if suffix == '.mp3':
                try:
                    try:
                        tags = ID3(file_path)
                    except ID3NoHeaderError:
                        tags = ID3()

                    tags.add(TIT2(encoding=3, text=title))
                    tags.add(TPE1(encoding=3, text=artist))
                    tags.add(TALB(encoding=3, text=album))
                    tags.add(TPE2(encoding=3, text=album_artist))
                    if track_number:
                        tags.add(TRCK(encoding=3, text=track_number))
                    tags.add(TCON(encoding=3, text=genre))
                    
                    # 处理时间字段：支持同时写入年份和完整日期
                    if metadata.get('date'):
                        # 写入年份
                        try:
                            tags.add(TYER(encoding=3, text=metadata['date']))
                        except:
                            # 如果TYER不可用，使用TDRC写入年份
                            tags.add(TDRC(encoding=3, text=metadata['date']))
                    
                    if metadata.get('releasetime'):
                        # 写入完整发布时间 (录音时间)
                        tags.add(TDRC(encoding=3, text=metadata['releasetime']))
                    # 碟片编号（TPOS）
                    try:
                        from mutagen.id3 import TPOS
                        # 为兼容更多播放器，写入 1/1 形式
                        tpos_value = f"{disc_number}/1" if disc_number else "1/1"
                        tags.add(TPOS(encoding=3, text=tpos_value))
                    except Exception:
                        pass

                    if cover_data:
                        tags.add(APIC(encoding=3, mime=cover_mime, type=3, desc='Cover', data=cover_data))

                    tags.save(file_path)
                    logger.info(f"✅ 回退方式为MP3写入元数据成功: {path_obj.name}")
                    return True
                except Exception as e:
                    logger.error(f"❌ 回退方式写入MP3元数据失败: {e}")
                    return False

            elif suffix == '.flac':
                try:
                    audio = FLAC(file_path)
                    audio['TITLE'] = title
                    audio['ARTIST'] = artist
                    audio['ALBUM'] = album
                    audio['ALBUMARTIST'] = album_artist
                    if track_number:
                        audio['TRACKNUMBER'] = track_number
                    
                    # 处理时间字段：支持同时写入年份和完整日期
                    if metadata.get('date'):
                        # 写入年份
                        audio['DATE'] = metadata['date']
                    
                    if metadata.get('releasetime'):
                        # 写入完整发布时间 (录音时间)
                        audio['RELEASETIME'] = metadata['releasetime']
                        # 兼容字段
                        audio['RELEASEDATE'] = metadata['releasetime']
                    # 碟片编号与总碟数（为兼容不同播放器，同时写多个key）
                    audio['DISCNUMBER'] = disc_number
                    audio['DISCTOTAL'] = '1'
                    audio['TOTALDISCS'] = '1'
                    # 额外兼容字段
                    audio['DISC'] = disc_number
                    audio['PART'] = disc_number
                    audio['PARTOFSET'] = '1/1'
                    audio['PART_OF_SET'] = '1/1'
                    audio['GENRE'] = genre

                    if cover_data:
                        pic = Picture()
                        pic.data = cover_data
                        pic.type = 3
                        pic.mime = cover_mime
                        pic.desc = 'Cover'
                        audio.clear_pictures()
                        audio.add_picture(pic)

                    audio.save()
                    logger.info(f"✅ 回退方式为FLAC写入元数据成功: {path_obj.name}")
                    return True
                except Exception as e:
                    logger.error(f"❌ 回退方式写入FLAC元数据失败: {e}")
                    return False

            else:
                # 其他格式暂不支持写入，返回False
                logger.warning(f"⚠️ 暂不支持的音频格式，无法写入元数据: {suffix}")
                return False

        except Exception as e:
            logger.error(f"❌ 回退方式写入元数据异常: {e}")
            return False
    
    def download_song_by_search(self, song_name: str, artist: str, download_dir: str, quality: str = '128k', progress_callback=None) -> Dict:
        """通过搜索下载歌曲，返回详细信息"""
        # 重置统计信息
        self.download_stats = {
            'total_files': 1,
            'downloaded_files': 0,
            'total_size': 0,
            'downloaded_songs': []
        }

        # 构建搜索关键词
        keyword = f"{artist} {song_name}".strip()

        # 搜索歌曲
        search_results = self.search_netease_music(keyword)
        if not search_results:
            logger.error(f"❌ 搜索不到歌曲: {keyword}")
            return {
                'success': False,
                'error': f'搜索不到歌曲: {keyword}',
                'filename': '',
                'size_mb': 0,
                'download_path': download_dir
            }

        # 选择最匹配的结果
        best_match = None
        for song in search_results:
            # 简单的匹配逻辑：歌曲名和歌手名都包含关键词
            if (song_name.lower() in song['name'].lower() and
                artist.lower() in song['artist'].lower()):
                best_match = song
                break

        if not best_match:
            # 如果没有完全匹配的，使用第一个结果
            best_match = search_results[0]
            logger.warning(f"⚠️ 没有完全匹配的结果，使用: {best_match['name']} - {best_match['artist']}")

        song_id = str(best_match['id'])
        song_title = best_match['name']
        song_artist = best_match['artist']

        logger.info(f"🎵 选择歌曲: {song_title} - {song_artist}")

        # 获取下载链接（支持音质降级）
        download_url, actual_quality, file_format = self.get_music_url_with_fallback(song_id, quality)
        if not download_url:
            logger.error(f"❌ 无法获取下载链接: {song_title}")
            return {
                'success': False,
                'error': f'无法获取下载链接: {song_title}',
                'filename': '',
                'size_mb': 0,
                'download_path': download_dir
            }

        # 生成文件名
        safe_title = self.clean_filename(song_title)
        safe_artist = self.clean_filename(song_artist)

        # 使用从URL推断的实际文件格式
        ext = file_format

        if safe_artist and safe_artist != 'Unknown':
            filename = f"{safe_artist} - {safe_title}.{ext}"
        else:
            filename = f"{safe_title}.{ext}"

        filepath = Path(download_dir) / filename

        # 检查文件是否已存在
        if filepath.exists():
            logger.info(f"📁 文件已存在，跳过: {filename}")
            file_size = filepath.stat().st_size
            return {
                'success': True,
                'message': '文件已存在',
                'filename': filename,
                'size_mb': file_size / (1024 * 1024),
                'download_path': download_dir,
                'song_title': song_title,
                'song_artist': song_artist,
                'quality': quality
            }

        # 下载文件
        download_success = self.download_file(download_url, str(filepath), f"{song_title} - {song_artist}", progress_callback=progress_callback)

        if download_success and filepath.exists():
            file_size = filepath.stat().st_size
            
            # 为下载的音乐文件添加元数据
            song_info = {
                'name': song_title,
                'artist': song_artist,
                'album': best_match.get('album', ''),
                'pic_url': best_match.get('pic_url', ''),
                'publish_time': best_match.get('publish_time', ''),
                'track_number': 1
            }
            self.add_metadata_to_music_file(str(filepath), song_info)
            
            # 下载歌词文件
            self.download_song_lyrics(song_id, str(filepath), song_info)
            
            # 检查是否启用cover下载（动态读取配置）
            cover_download_enabled = True
            try:
                # 优先从bot配置获取cover下载设置
                if hasattr(self, 'bot') and hasattr(self.bot, 'netease_cover_download'):
                    cover_download_enabled = self.bot.netease_cover_download
                    logger.info(f"🖼️ 从bot配置获取cover下载设置: {'启用' if cover_download_enabled else '禁用'}")
                else:
                    # 如果bot配置不可用，尝试从配置文件直接读取
                    try:
                        # 尝试多个可能的配置文件路径
                        possible_paths = [
                            Path("config/settings.json"),
                            Path("./config/settings.json"),
                            Path("../config/settings.json"),
                            Path("settings.json")
                        ]
                        
                        config_found = False
                        for config_path in possible_paths:
                            logger.info(f"🔍 尝试配置文件路径: {config_path.absolute()}")
                            if config_path.exists():
                                with open(config_path, 'r', encoding='utf-8') as f:
                                    config_data = json.load(f)
                                    cover_download_enabled = config_data.get("netease_cover_download", True)
                                    logger.info(f"🖼️ 从配置文件 {config_path} 获取cover下载设置: {'启用' if cover_download_enabled else '禁用'}")
                                    config_found = True
                                    break
                        
                        if not config_found:
                            logger.warning("⚠️ 所有可能的配置文件路径都不存在")
                            logger.info(f"🔍 当前工作目录: {os.getcwd()}")
                            logger.info(f"🔍 当前目录内容: {list(os.listdir('.'))}")
                    except Exception as e:
                        logger.warning(f"⚠️ 读取配置文件失败: {e}")
                        cover_download_enabled = True
            except Exception as e:
                logger.warning(f"⚠️ 获取cover下载设置失败，使用默认值: {e}")
            
            # 下载单曲封面到音乐文件同目录（如果启用）
            if best_match.get('pic_url') and cover_download_enabled:
                cover_url = best_match['pic_url']
                logger.info(f"🖼️ 开始下载单曲封面: {cover_url}")
                cover_success = self.download_cover_image(cover_url, download_dir, "cover.jpg")
                if cover_success:
                    logger.info(f"✅ 单曲封面下载成功: {download_dir}/cover.jpg")
                else:
                    logger.warning(f"⚠️ 单曲封面下载失败")
            elif best_match.get('pic_url') and not cover_download_enabled:
                logger.info(f"🖼️ cover下载已禁用，跳过单曲封面下载")
            else:
                logger.warning(f"⚠️ 未找到单曲封面URL")
            
            return {
                'success': True,
                'message': '下载成功',
                'filename': filename,
                'size_mb': file_size / (1024 * 1024),
                'download_path': download_dir,
                'song_title': song_title,
                'song_artist': song_artist,
                'quality': quality
            }
        else:
            return {
                'success': False,
                'error': '下载失败',
                'filename': filename,
                'size_mb': 0,
                'download_path': download_dir
            }

    def download_album(self, album_name: str, download_dir: str = "./downloads/netease", quality: str = '128k', progress_callback=None) -> Dict:
        """下载专辑"""
        # 重置统计信息
        self.download_stats = {
            'total_files': 0,
            'downloaded_files': 0,
            'total_size': 0,
            'downloaded_songs': []
        }
        
        # 设置专辑下载标志，避免单个文件下载完成时发送finished回调
        self._in_album_download = True

        print(f"🔍 搜索专辑: {album_name}")

        # 搜索专辑
        albums = self.search_netease_album(album_name, 10)
        if not albums:
            print("❌ 搜索不到专辑")
            return {
                'success': False,
                'error': f'搜索不到专辑: {album_name}',
                'album_name': album_name,
                'total_songs': 0,
                'downloaded_songs': 0,
                'total_size_mb': 0,
                'download_path': download_dir,
                'songs': []
            }

        # 显示搜索结果并让用户选择
        print(f"\n📋 找到 {len(albums)} 个专辑:")
        for i, album in enumerate(albums, 1):
            print(f"  {i}. {album['name']} - {album['artist']} ({album['size']}首)")

        # 选择第一个专辑（可以扩展为用户选择）
        selected_album = albums[0]
        album_id = str(selected_album['id'])
        album_title = selected_album['name']
        # 确保只使用第一个艺术家，避免多艺术家目录
        album_artist = selected_album['artist']
        if ',' in album_artist:
            album_artist = album_artist.split(',')[0].strip()
        elif '、' in album_artist:
            album_artist = album_artist.split('、')[0].strip()
        elif ' feat. ' in album_artist:
            album_artist = album_artist.split(' feat. ')[0].strip()
        elif ' ft. ' in album_artist:
            album_artist = album_artist.split(' ft. ')[0].strip()
        elif ' & ' in album_artist:
            album_artist = album_artist.split(' & ')[0].strip()

        print(f"\n✅ 选择专辑: {album_title} - {album_artist}")

        # 获取专辑中的歌曲
        songs = self.get_album_songs(album_id)
        if not songs:
            print("⚠️ 无法通过专辑API获取歌曲列表，尝试通过搜索获取...")
            # 尝试通过搜索专辑名称获取相关歌曲
            search_results = self.search_netease_music(f"{album_title} {album_artist}", 20)
            if search_results:
                # 过滤出可能属于该专辑的歌曲（歌手名匹配）
                songs = []
                for song in search_results:
                    if album_artist.lower() in song.get('artist', '').lower():
                        songs.append(song)

                if songs:
                    print(f"✅ 通过搜索找到 {len(songs)} 首可能的专辑歌曲")
                else:
                    print("❌ 搜索也无法找到相关歌曲")
                    return {
                        'success': False,
                        'error': '无法获取专辑歌曲',
                        'album_name': album_title,
                        'total_songs': 0,
                        'downloaded_songs': 0,
                        'total_size_mb': 0,
                        'download_path': download_dir,
                        'songs': []
                    }
            else:
                print("❌ 搜索也无法找到相关歌曲")
                return {
                    'success': False,
                    'error': '无法获取专辑歌曲',
                    'album_name': album_title,
                    'total_songs': 0,
                    'downloaded_songs': 0,
                    'total_size_mb': 0,
                    'download_path': download_dir,
                    'songs': []
                }

        # 使用配置的目录结构格式
        # 构建专辑文件夹名称（使用NCM_ALBUM_FOLDER_FORMAT）
        if '{AlbumName}' in self.album_folder_format:
            # 替换专辑名称占位符
            album_folder_name = self.album_folder_format.replace('{AlbumName}', album_title)
            
            # 如果有发布日期占位符，尝试获取发布日期
            if '{ReleaseDate}' in album_folder_name:
                try:
                    # 尝试从歌曲信息中获取发布日期
                    release_date = songs[0].get('publish_time', '') if songs else ''
                    if release_date and release_date != 0:
                        # 转换时间戳为年份
                        try:
                            # 处理不同格式的时间戳
                            if isinstance(release_date, str) and release_date.isdigit():
                                release_date = int(release_date)
                            
                            if isinstance(release_date, (int, float)) and release_date > 0:
                                # 判断时间戳是秒还是毫秒
                                # 使用更合理的阈值：大于9999999999认为是毫秒级
                                timestamp_seconds = release_date / 1000 if release_date > 9999999999 else release_date
                                year = time.strftime('%Y', time.localtime(timestamp_seconds))
                                album_folder_name = album_folder_name.replace('{ReleaseDate}', year)
                                logger.info(f"✅ 成功获取发布日期: {year}")
                            else:
                                logger.warning(f"⚠️ 发布日期无效: {release_date}")
                                album_folder_name = album_folder_name.replace('{ReleaseDate}', '')
                        except Exception as e:
                            logger.warning(f"⚠️ 转换发布日期失败: {e}")
                            album_folder_name = album_folder_name.replace('{ReleaseDate}', '')
                    else:
                        logger.warning(f"⚠️ 无法获取发布日期，移除占位符")
                        album_folder_name = album_folder_name.replace('{ReleaseDate}', '')
                except Exception as e:
                    logger.warning(f"⚠️ 处理发布日期时出错: {e}")
                    album_folder_name = album_folder_name.replace('{ReleaseDate}', '')
            
            # 清理文件名中的非法字符
            safe_album_folder_name = self.clean_filename(album_folder_name)
        else:
            # 如果没有占位符，使用默认格式
            safe_album_folder_name = self.clean_filename(f"{album_artist} - {album_title}")
        
        # 构建完整的目录路径（使用NCM_DIR_FORMAT）
        if '{ArtistName}' in self.dir_format and '{AlbumName}' in self.dir_format:
            # 格式：{ArtistName}/{AlbumName} - 艺术家/专辑
            safe_artist_name = self.clean_filename(album_artist)
            album_dir = Path(download_dir) / safe_artist_name / safe_album_folder_name
            logger.info(f"🔍 使用艺术家/专辑目录结构: {safe_artist_name}/{safe_album_folder_name}")
        elif '{AlbumName}' in self.dir_format:
            # 格式：{AlbumName} - 直接以专辑命名
            album_dir = Path(download_dir) / safe_album_folder_name
            logger.info(f"🔍 使用专辑目录结构: {safe_album_folder_name}")
        else:
            # 默认格式：直接以专辑命名
            album_dir = Path(download_dir) / safe_album_folder_name
            logger.info(f"🔍 使用默认专辑目录结构: {safe_album_folder_name}")
        
        album_dir.mkdir(parents=True, exist_ok=True)

        # 更新统计信息
        self.download_stats['total_files'] = len(songs)

        print(f"\n📁 专辑目录: {album_dir}")
        print(f"🎵 开始下载专辑: {album_title}")
        print(f"🎚️ 音质: {quality}")
        print(f"📊 歌曲数量: {len(songs)}")
        print()

        # 下载每首歌曲
        for i, song in enumerate(songs, 1):
            song_name = song['name']
            artist = song['artist']
            track_number = song.get('track_number', i)

            print(f"[{i}/{len(songs)}] {song_name} - {artist}")

            # 获取下载链接（支持音质降级）
            song_id = str(song['id'])
            download_url, actual_quality, file_format = self.get_music_url_with_fallback(song_id, quality)

            if download_url:
                # 使用配置的歌曲文件名格式
                safe_title = self.clean_filename(song_name)
                safe_artist = self.clean_filename(artist)

                # 使用从URL推断的实际文件格式
                ext = file_format

                # 构建自定义文件名（使用NCM_SONG_FILE_FORMAT）
                if '{SongNumber}' in self.song_file_format or '{SongName}' in self.song_file_format or '{ArtistName}' in self.song_file_format:
                    # 替换占位符
                    custom_filename = self.song_file_format
                    
                    # 替换歌曲编号
                    if '{SongNumber}' in custom_filename:
                        custom_filename = custom_filename.replace('{SongNumber}', f"{track_number:02d}")
                    
                    # 替换歌曲名称
                    if '{SongName}' in custom_filename:
                        custom_filename = custom_filename.replace('{SongName}', safe_title)
                    
                    # 替换艺术家名称
                    if '{ArtistName}' in custom_filename:
                        custom_filename = custom_filename.replace('{ArtistName}', safe_artist)
                    
                    # 添加文件扩展名
                    filename = f"{custom_filename}.{ext}"
                else:
                    # 如果没有占位符，使用默认格式
                    filename = f"{track_number:02d}. {safe_artist} - {safe_title}.{ext}"
                
                filepath = album_dir / filename

                # 检查文件是否已存在
                if filepath.exists():
                    print(f"  📁 文件已存在，跳过")
                    # 仍然需要更新统计信息
                    file_size = filepath.stat().st_size
                    self.download_stats['downloaded_files'] += 1
                    self.download_stats['total_size'] += file_size
                    self.download_stats['downloaded_songs'].append({
                        'name': f"{song_name} - {artist}",
                        'song_name': song_name,  # 添加原始歌曲名称
                        'size': file_size,
                        'filepath': str(filepath),
                        'file_format': ext  # 添加文件格式信息
                    })
                else:
                    # 下载文件
                    download_success = self.download_file(download_url, str(filepath), f"{song_name} - {artist}", progress_callback=progress_callback)
                    if download_success:
                        # 下载成功，更新统计信息
                        file_size = filepath.stat().st_size if filepath.exists() else 0
                        self.download_stats['downloaded_files'] += 1
                        self.download_stats['total_size'] += file_size
                        self.download_stats['downloaded_songs'].append({
                            'name': f"{song_name} - {artist}",
                            'song_name': song_name,  # 添加原始歌曲名称
                            'size': file_size,
                            'filepath': str(filepath),
                            'file_format': ext  # 添加文件格式信息
                        })
                        
                        # 为下载的音乐文件添加元数据
                        song_info = {
                            'name': song_name,
                            'artist': artist,
                            'album': album_title,
                            'album_artist': album_artist,
                            'pic_url': song.get('pic_url', ''),
                            'publish_time': song.get('publish_time', ''),
                            'track_number': track_number
                        }
                        album_info = {
                            'name': album_title,
                            'artist': album_artist,
                            'pic_url': songs[0].get('pic_url', '') if songs else '',
                            'publish_time': songs[0].get('publish_time', '') if songs else ''
                        }
                        self.add_metadata_to_music_file(str(filepath), song_info, album_info)
                        
                        # 下载歌词文件
                        self.download_song_lyrics(str(song['id']), str(filepath), song_info)
                        
                        print(f"  ✅ 下载成功: {song_name} - {artist} ({self.format_file_size(file_size)})")
                    else:
                        print(f"  ❌ 下载失败: {song_name} - {artist}")
                        # 记录失败的歌曲
                        self.download_stats['downloaded_songs'].append({
                            'name': f"{song_name} - {artist}",
                            'song_name': song_name,  # 添加原始歌曲名称
                            'size': 0,
                            'filepath': str(filepath),
                            'file_format': ext,  # 添加文件格式信息
                            'status': 'failed'
                        })
            else:
                print(f"  ❌ 无法获取下载链接")

            # 避免请求过快
            time.sleep(1)

        # 显示下载完成统计
        self.show_download_summary(album_title, str(album_dir), quality)
        
        # 发送专辑下载完成的进度回调
        if progress_callback:
            progress_callback({
                'status': 'finished',
                'filename': f"{album_title} (专辑)",
                'total_bytes': self.download_stats['total_size'],
                'downloaded_bytes': self.download_stats['total_size'],
                'speed': 0,
                'eta': 0
            })
        
        # 清除专辑下载标志
        self._in_album_download = False

        # 检查是否启用cover下载（动态读取配置）
        cover_download_enabled = True
        try:
            # 优先从bot配置获取cover下载设置
            if hasattr(self, 'bot') and hasattr(self.bot, 'netease_cover_download'):
                cover_download_enabled = self.bot.netease_cover_download
                logger.info(f"🖼️ 从bot配置获取cover下载设置: {'启用' if cover_download_enabled else '禁用'}")
            else:
                # 如果bot配置不可用，尝试从配置文件直接读取
                try:
                    # 尝试多个可能的配置文件路径
                    possible_paths = [
                        Path("config/settings.json"),
                        Path("./config/settings.json"),
                        Path("../config/settings.json"),
                        Path("settings.json")
                    ]
                    
                    config_found = False
                    for config_path in possible_paths:
                        logger.info(f"🔍 尝试配置文件路径: {config_path.absolute()}")
                        if config_path.exists():
                            with open(config_path, 'r', encoding='utf-8') as f:
                                config_data = json.load(f)
                                cover_download_enabled = config_data.get("netease_cover_download", True)
                                logger.info(f"🖼️ 从配置文件 {config_path} 获取cover下载设置: {'启用' if cover_download_enabled else '禁用'}")
                                config_found = True
                                break
                    
                    if not config_found:
                        logger.warning("⚠️ 所有可能的配置文件路径都不存在")
                        logger.info(f"🔍 当前工作目录: {os.getcwd()}")
                        logger.info(f"🔍 当前目录内容: {list(os.listdir('.'))}")
                except Exception as e:
                    logger.warning(f"⚠️ 读取配置文件失败: {e}")
                    cover_download_enabled = True
        except Exception as e:
            logger.warning(f"⚠️ 获取cover下载设置失败，使用默认值: {e}")
        
        # 下载专辑封面到音乐文件同目录（如果启用）
        if songs and songs[0].get('pic_url') and cover_download_enabled:
            cover_url = songs[0]['pic_url']
            logger.info(f"🖼️ 开始下载专辑封面: {cover_url}")
            cover_success = self.download_cover_image(cover_url, str(album_dir), "cover.jpg")
            if cover_success:
                logger.info(f"✅ 专辑封面下载成功: {album_dir}/cover.jpg")
            else:
                logger.warning(f"⚠️ 专辑封面下载失败")
        elif songs and songs[0].get('pic_url') and not cover_download_enabled:
            logger.info(f"🖼️ cover下载已禁用，跳过专辑封面下载")
        else:
            logger.warning(f"⚠️ 未找到专辑封面URL")

        # 检查是否启用artist下载（动态读取配置）
        artist_download_enabled = True
        try:
            # 优先从bot配置获取artist下载设置
            if hasattr(self, 'bot') and hasattr(self.bot, 'netease_artist_download'):
                artist_download_enabled = self.bot.netease_artist_download
                logger.info(f"🎨 从bot配置获取artist下载设置: {'启用' if artist_download_enabled else '禁用'}")
            else:
                # 如果bot配置不可用，尝试从配置文件直接读取
                try:
                    # 尝试多个可能的配置文件路径
                    possible_paths = [
                        Path("config/settings.json"),
                        Path("./config/settings.json"),
                        Path("../config/settings.json"),
                        Path("settings.json")
                    ]
                    
                    config_found = False
                    for config_path in possible_paths:
                        logger.info(f"🔍 尝试配置文件路径: {config_path.absolute()}")
                        if config_path.exists():
                            with open(config_path, 'r', encoding='utf-8') as f:
                                config_data = json.load(f)
                                artist_download_enabled = config_data.get("netease_artist_download", True)
                                logger.info(f"🎨 从配置文件 {config_path} 获取artist下载设置: {'启用' if artist_download_enabled else '禁用'}")
                                config_found = True
                                break
                    
                    if not config_found:
                        logger.warning("⚠️ 所有可能的配置文件路径都不存在")
                        logger.info(f"🔍 当前工作目录: {os.getcwd()}")
                        logger.info(f"🔍 当前目录内容: {list(os.listdir('.'))}")
                except Exception as e:
                    logger.warning(f"⚠️ 读取配置文件失败: {e}")
                    artist_download_enabled = True
        except Exception as e:
            logger.warning(f"⚠️ 获取artist下载设置失败，使用默认值: {e}")
        
        # 下载艺术家头像到艺术家目录（如果启用）
        if album_artist and artist_download_enabled:
            logger.info(f"🎨 开始下载艺术家头像: {album_artist}")
            # 根据目录结构确定艺术家头像保存位置
            if '{ArtistName}' in self.dir_format:
                # 格式：{ArtistName}/{AlbumName} - 保存到艺术家目录
                safe_artist_name = self.clean_filename(album_artist)
                artist_dir = Path(download_dir) / safe_artist_name
                artist_success = self.download_artist_image(album_artist, str(artist_dir), "artist.jpg")
                if artist_success:
                    logger.info(f"✅ 艺术家头像下载成功: {artist_dir}/artist.jpg")
                else:
                    logger.warning(f"⚠️ 艺术家头像下载失败")
            else:
                # 格式：{AlbumName} - 保存到专辑目录
                artist_success = self.download_artist_image(album_artist, str(album_dir), "artist.jpg")
                if artist_success:
                    logger.info(f"✅ 艺术家头像下载成功: {album_dir}/artist.jpg")
                else:
                    logger.warning(f"⚠️ 艺术家头像下载失败")
        elif album_artist and not artist_download_enabled:
            logger.info(f"🎨 artist下载已禁用，跳过艺术家头像下载: {album_artist}")
        else:
            logger.warning(f"⚠️ 未找到艺术家名称")

        # 准备详细的歌曲信息
        songs_info = []
        for song_info in self.download_stats['downloaded_songs']:
            songs_info.append({
                'title': song_info['name'],
                'song_name': song_info.get('song_name', ''),  # 添加原始歌曲名称
                'filename': Path(song_info['filepath']).name if 'filepath' in song_info else '',
                'size_mb': song_info['size'] / (1024 * 1024),
                'file_format': song_info.get('file_format', 'mp3'),  # 添加文件格式信息
                'status': 'downloaded'
            })

        return {
            'success': self.download_stats['downloaded_files'] > 0,
            'message': f"专辑下载完成，成功 {self.download_stats['downloaded_files']}/{self.download_stats['total_files']} 首",
            'album_name': album_title,
            'total_songs': self.download_stats['total_files'],
            'downloaded_songs': self.download_stats['downloaded_files'],
            'total_size_mb': self.download_stats['total_size'] / (1024 * 1024),
            'download_path': str(album_dir),
            'songs': songs_info,
            'quality': quality
        }

    def download_album_by_id(self, album_id: str, download_dir: str = "./downloads/netease", quality: str = '128k', progress_callback=None) -> Dict:
        """通过专辑ID直接下载专辑"""
        logger.info(f"🎵 开始通过专辑ID下载: {album_id}")

        # 重置统计信息
        self.download_stats = {
            'total_files': 0,
            'downloaded_files': 0,
            'total_size': 0,
            'downloaded_songs': []
        }
        
        # 设置专辑下载标志，避免单个文件下载完成时发送finished回调
        self._in_album_download = True

        try:
            # 直接通过专辑ID获取专辑歌曲
            album_songs = self.get_album_songs(album_id)

            if not album_songs:
                logger.error(f"❌ 无法获取专辑ID {album_id} 的歌曲信息")
                return {
                    'success': False,
                    'error': f'无法获取专辑ID {album_id} 的歌曲信息',
                    'album_name': '',
                    'total_songs': 0,
                    'downloaded_songs': 0,
                    'total_size_mb': 0,
                    'download_path': download_dir,
                    'songs': [],
                    'quality': quality
                }

            # 获取专辑名称（从第一首歌的专辑信息）
            album_title = album_songs[0].get('album', f'专辑_{album_id}')
            logger.info(f"📀 专辑名称: {album_title}")
            logger.info(f"🎵 专辑歌曲数量: {len(album_songs)}")

            # 使用配置的目录结构格式
            artist_name = album_songs[0].get('artist', '未知艺术家')
            
            # 构建专辑文件夹名称（使用NCM_ALBUM_FOLDER_FORMAT）
            if '{AlbumName}' in self.album_folder_format:
                # 替换专辑名称占位符
                album_folder_name = self.album_folder_format.replace('{AlbumName}', album_title)
                
                # 如果有发布日期占位符，尝试获取发布日期
                if '{ReleaseDate}' in album_folder_name:
                    try:
                        # 尝试从歌曲信息中获取发布日期
                        release_date = album_songs[0].get('publish_time', '')
                        if release_date and release_date != 0:
                            # 转换时间戳为年份
                            try:
                                # 处理不同格式的时间戳
                                if isinstance(release_date, str) and release_date.isdigit():
                                    release_date = int(release_date)
                                
                                if isinstance(release_date, (int, float)) and release_date > 0:
                                    # 判断时间戳是秒还是毫秒
                                    # 使用更合理的阈值：大于9999999999认为是毫秒级
                                    timestamp_seconds = release_date / 1000 if release_date > 9999999999 else release_date
                                    year = time.strftime('%Y', time.localtime(timestamp_seconds))
                                    album_folder_name = album_folder_name.replace('{ReleaseDate}', year)
                                    logger.info(f"✅ 成功获取发布日期: {year}")
                                else:
                                    logger.warning(f"⚠️ 发布日期无效: {release_date}")
                                    album_folder_name = album_folder_name.replace('{ReleaseDate}', '')
                            except Exception as e:
                                logger.warning(f"⚠️ 转换发布日期失败: {e}")
                                album_folder_name = album_folder_name.replace('{ReleaseDate}', '')
                        else:
                            logger.warning(f"⚠️ 无法获取发布日期，移除占位符")
                            album_folder_name = album_folder_name.replace('{ReleaseDate}', '')
                    except Exception as e:
                        logger.warning(f"⚠️ 处理发布日期时出错: {e}")
                        album_folder_name = album_folder_name.replace('{ReleaseDate}', '')
                
                # 清理文件名中的非法字符
                safe_album_folder_name = self.clean_filename(album_folder_name)
            else:
                # 如果没有占位符，直接使用专辑名称
                safe_album_folder_name = self.clean_filename(album_title)
            
            # 构建完整的目录路径（使用NCM_DIR_FORMAT）
            if '{ArtistName}' in self.dir_format and '{AlbumName}' in self.dir_format:
                # 格式：{ArtistName}/{AlbumName} - 艺术家/专辑
                safe_artist_name = self.clean_filename(artist_name)
                album_dir = Path(download_dir) / safe_artist_name / safe_album_folder_name
                logger.info(f"🔍 使用艺术家/专辑目录结构: {safe_artist_name}/{safe_album_folder_name}")
            elif '{AlbumName}' in self.dir_format:
                # 格式：{AlbumName} - 直接以专辑命名
                album_dir = Path(download_dir) / safe_album_folder_name
                logger.info(f"🔍 使用专辑目录结构: {safe_album_folder_name}")
            else:
                # 默认格式：直接以专辑命名
                album_dir = Path(download_dir) / safe_album_folder_name
                logger.info(f"🔍 使用默认专辑目录结构: {safe_album_folder_name}")
            
            album_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"📁 专辑目录: {album_dir}")

            # 更新统计信息
            self.download_stats['total_files'] = len(album_songs)

            print(f"🎵 开始下载专辑: {album_title}")
            print(f"🎚️ 音质: {quality}")
            print(f"📊 歌曲数量: {len(album_songs)}")
            print()

            # 下载每首歌曲
            for i, song in enumerate(album_songs, 1):
                song_id = song.get('id')
                song_name = song.get('name', 'Unknown')
                artist = song.get('artist', 'Unknown')

                print(f"[{i}/{len(album_songs)}] {song_name} - {artist}")

                # 获取下载链接（支持音质降级）
                download_url, actual_quality, file_format = self.get_music_url_with_fallback(str(song_id), quality)

                if not download_url:
                    print(f"  ❌ 无法获取下载链接")
                    continue

                # 使用配置的歌曲文件名格式
                safe_song_name = self.clean_filename(song_name)
                safe_artist = self.clean_filename(artist)

                # 使用从URL推断的实际文件格式
                ext = file_format

                # 构建自定义文件名（使用NCM_SONG_FILE_FORMAT）
                if '{SongNumber}' in self.song_file_format or '{SongName}' in self.song_file_format or '{ArtistName}' in self.song_file_format:
                    # 替换占位符
                    custom_filename = self.song_file_format
                    
                    # 替换歌曲编号
                    if '{SongNumber}' in custom_filename:
                        custom_filename = custom_filename.replace('{SongNumber}', f"{i:02d}")
                    
                    # 替换歌曲名称
                    if '{SongName}' in custom_filename:
                        custom_filename = custom_filename.replace('{SongName}', safe_song_name)
                    
                    # 替换艺术家名称
                    if '{ArtistName}' in custom_filename:
                        custom_filename = custom_filename.replace('{ArtistName}', safe_artist)
                    
                    # 添加文件扩展名
                    filename = f"{custom_filename}.{ext}"
                else:
                    # 如果没有占位符，使用默认格式
                    filename = f"{i:02d}. {safe_artist} - {safe_song_name}.{ext}"
                
                filepath = album_dir / filename

                # 下载文件
                success = self.download_file(
                    download_url,
                    str(filepath),
                    f"{song_name} - {artist}",
                    progress_callback=progress_callback
                )

                if success:
                    # 获取文件大小
                    file_size = filepath.stat().st_size if filepath.exists() else 0

                    # 更新统计信息
                    self.download_stats['downloaded_files'] += 1
                    self.download_stats['total_size'] += file_size
                    self.download_stats['downloaded_songs'].append({
                        'name': f"{song_name} - {artist}",
                        'song_name': song_name,  # 添加原始歌曲名称
                        'size': file_size,
                        'filepath': str(filepath)
                    })

                    # 为下载的音乐文件添加元数据（优先使用 get_album_songs 中注入的专辑级信息）
                    song_info = {
                        'name': song_name,
                        'artist': artist,
                        'album': album_title,
                        'album_artist': song.get('album_artist', artist),
                        'pic_url': song.get('pic_url', ''),
                        'publish_time': song.get('publish_time', ''),
                        'track_number': i
                    }
                    album_info = {
                        'name': album_title,
                        'artist': song.get('album_artist', artist),
                        'pic_url': song.get('pic_url', album_songs[0].get('pic_url', '') if album_songs else ''),
                        'publish_time': song.get('publish_time', album_songs[0].get('publish_time', '') if album_songs else '')
                    }
                    self.add_metadata_to_music_file(str(filepath), song_info, album_info)

                    # 下载歌词文件
                    self.download_song_lyrics(str(song_id), str(filepath), song_info)

                    size_mb = file_size / (1024 * 1024)
                    logger.info(f"✅ 下载成功: {filename} ({size_mb:.1f}MB)")
                else:
                    logger.warning(f"❌ 下载失败: {song_name}")

                # 避免请求过快
                time.sleep(1)

            # 显示下载统计
            self.show_download_summary(album_title, str(album_dir), quality)

            # 检查是否启用cover下载（动态读取配置）
            cover_download_enabled = True
            try:
                # 优先从bot配置获取cover下载设置
                if hasattr(self, 'bot') and hasattr(self.bot, 'netease_cover_download'):
                    cover_download_enabled = self.bot.netease_cover_download
                    logger.info(f"🖼️ 从bot配置获取cover下载设置: {'启用' if cover_download_enabled else '禁用'}")
                else:
                    # 如果bot配置不可用，尝试从配置文件直接读取
                    try:
                        # 尝试多个可能的配置文件路径
                        possible_paths = [
                            Path("config/settings.json"),
                            Path("./config/settings.json"),
                            Path("../config/settings.json"),
                            Path("settings.json")
                        ]
                        
                        config_found = False
                        for config_path in possible_paths:
                            logger.info(f"🔍 尝试配置文件路径: {config_path.absolute()}")
                            if config_path.exists():
                                with open(config_path, 'r', encoding='utf-8') as f:
                                    config_data = json.load(f)
                                    cover_download_enabled = config_data.get("netease_cover_download", True)
                                    logger.info(f"🖼️ 从配置文件 {config_path} 获取cover下载设置: {'启用' if cover_download_enabled else '禁用'}")
                                    config_found = True
                                    break
                        
                        if not config_found:
                            logger.warning("⚠️ 所有可能的配置文件路径都不存在")
                            logger.info(f"🔍 当前工作目录: {os.getcwd()}")
                            logger.info(f"🔍 当前目录内容: {list(os.listdir('.'))}")
                    except Exception as e:
                        logger.warning(f"⚠️ 读取配置文件失败: {e}")
                        cover_download_enabled = True
            except Exception as e:
                logger.warning(f"⚠️ 获取cover下载设置失败，使用默认值: {e}")
            
            # 下载专辑封面到音乐文件同目录（如果启用）
            if album_songs and album_songs[0].get('pic_url') and cover_download_enabled:
                cover_url = album_songs[0]['pic_url']
                logger.info(f"🖼️ 开始下载专辑封面: {cover_url}")
                cover_success = self.download_cover_image(cover_url, str(album_dir), "cover.jpg")
                if cover_success:
                    logger.info(f"✅ 专辑封面下载成功: {album_dir}/cover.jpg")
                else:
                    logger.warning(f"⚠️ 专辑封面下载失败")
            elif album_songs and album_songs[0].get('pic_url') and not cover_download_enabled:
                logger.info(f"🖼️ cover下载已禁用，跳过专辑封面下载")
            else:
                logger.warning(f"⚠️ 未找到专辑封面URL")

            # 检查是否启用artist下载（动态读取配置）
            artist_download_enabled = True
            try:
                # 优先从bot配置获取artist下载设置
                if hasattr(self, 'bot') and hasattr(self.bot, 'netease_artist_download'):
                    artist_download_enabled = self.bot.netease_artist_download
                    logger.info(f"🎨 从bot配置获取artist下载设置: {'启用' if artist_download_enabled else '禁用'}")
                else:
                    # 如果bot配置不可用，尝试从配置文件直接读取
                    try:
                        # 尝试多个可能的配置文件路径
                        possible_paths = [
                            Path("config/settings.json"),
                            Path("./config/settings.json"),
                            Path("../config/settings.json"),
                            Path("settings.json")
                        ]
                        
                        config_found = False
                        for config_path in possible_paths:
                            logger.info(f"🔍 尝试配置文件路径: {config_path.absolute()}")
                            if config_path.exists():
                                with open(config_path, 'r', encoding='utf-8') as f:
                                    config_data = json.load(f)
                                    artist_download_enabled = config_data.get("netease_artist_download", True)
                                    logger.info(f"🎨 从配置文件 {config_path} 获取artist下载设置: {'启用' if artist_download_enabled else '禁用'}")
                                    config_found = True
                                    break
                        
                        if not config_found:
                            logger.warning("⚠️ 所有可能的配置文件路径都不存在")
                            logger.info(f"🔍 当前工作目录: {os.getcwd()}")
                            logger.info(f"🔍 当前目录内容: {list(os.listdir('.'))}")
                    except Exception as e:
                        logger.warning(f"⚠️ 读取配置文件失败: {e}")
                        artist_download_enabled = True
            except Exception as e:
                logger.warning(f"⚠️ 获取artist下载设置失败，使用默认值: {e}")
            
            # 下载艺术家头像到艺术家目录（如果启用）
            if artist_name and artist_download_enabled:
                logger.info(f"🎨 开始下载艺术家头像: {artist_name}")
                # 根据目录结构确定艺术家头像保存位置
                if '{ArtistName}' in self.dir_format:
                    # 格式：{ArtistName}/{AlbumName} - 保存到艺术家目录
                    safe_artist_name = self.clean_filename(artist_name)
                    artist_dir = Path(download_dir) / safe_artist_name
                    artist_success = self.download_artist_image(artist_name, str(artist_dir), "artist.jpg")
                    if artist_success:
                        logger.info(f"✅ 艺术家头像下载成功: {artist_dir}/artist.jpg")
                    else:
                        logger.warning(f"⚠️ 艺术家头像下载失败")
                else:
                    # 格式：{AlbumName} - 保存到专辑目录
                    artist_success = self.download_artist_image(artist_name, str(album_dir), "artist.jpg")
                    if artist_success:
                        logger.info(f"✅ 艺术家头像下载成功: {album_dir}/artist.jpg")
                    else:
                        logger.warning(f"⚠️ 艺术家头像下载失败")
            elif artist_name and not artist_download_enabled:
                logger.info(f"🎨 artist下载已禁用，跳过艺术家头像下载: {artist_name}")
            else:
                logger.warning(f"⚠️ 未找到艺术家名称")

            # 发送专辑下载完成的进度回调
            if progress_callback:
                progress_callback({
                    'status': 'finished',
                    'filename': f"{album_title} (专辑)",
                    'total_bytes': self.download_stats['total_size'],
                    'downloaded_bytes': self.download_stats['total_size'],
                    'speed': 0,
                    'eta': 0
                })
            
            # 清除专辑下载标志
            self._in_album_download = False

            # 准备详细的歌曲信息
            songs_info = []
            for song_info in self.download_stats['downloaded_songs']:
                songs_info.append({
                    'title': song_info['name'],
                    'song_name': song_info.get('song_name', ''),  # 添加原始歌曲名称
                    'filename': Path(song_info['filepath']).name if 'filepath' in song_info else '',
                    'size_mb': song_info['size'] / (1024 * 1024),
                    'status': 'downloaded'
                })

            return {
                'success': self.download_stats['downloaded_files'] > 0,
                'message': f"专辑下载完成，成功 {self.download_stats['downloaded_files']}/{self.download_stats['total_files']} 首",
                'album_name': album_title,
                'total_songs': self.download_stats['total_files'],
                'downloaded_songs': self.download_stats['downloaded_files'],
                'total_size_mb': self.download_stats['total_size'] / (1024 * 1024),
                'download_path': str(album_dir),
                'songs': songs_info,
                'quality': quality
            }

        except Exception as e:
            logger.error(f"❌ 专辑下载异常: {e}")
            # 清除专辑下载标志
            self._in_album_download = False
            return {
                'success': False,
                'error': f'专辑下载失败: {str(e)}',
                'album_name': '',
                'total_songs': 0,
                'downloaded_songs': 0,
                'total_size_mb': 0,
                'download_path': download_dir,
                'songs': [],
                'quality': quality
            }

    def show_download_summary(self, album_name: str, save_path: str, quality: str):
        """显示下载完成统计信息"""
        stats = self.download_stats

        print("\n🎵 **网易云音乐专辑下载完成**\n")
        
        print(f"📀 专辑名称: {album_name}")
        print(f"🎵 下载歌曲: {stats['downloaded_files']}/{stats['total_files']} 首")
        
        # 获取音质信息
        quality_code = self.quality_map.get(quality, quality)
        quality_info = self._get_detailed_quality_info(quality_code)
        
        print(f"🎚️ 音质: {quality_info['name']}")
        
        # 格式化总大小
        total_size_mb = stats['total_size'] / (1024 * 1024)
        print(f"💾 总大小: {total_size_mb:.2f} MB")
        print()
        
        # 文件格式和码率（带图标）
        print(f"🎼 文件格式: {quality_info['format']}")
        print(f"📊 码率: {quality_info['bitrate']}")
        print()
        
        print(f"📂 保存位置: {save_path}")
        print()

        if stats['downloaded_songs']:
            print("🎵 歌曲列表:")
            print()

            for i, song in enumerate(stats['downloaded_songs'], 1):
                size_mb = song['size'] / (1024 * 1024)
                song_name = song['name']
                
                # 检查实际文件名是否已经包含序号（格式如 "01.歌曲名" 或 "1.歌曲名"）
                import re
                from pathlib import Path
                
                # 从文件路径中提取文件名
                if 'filepath' in song and song['filepath']:
                    filename = Path(song['filepath']).name
                    has_numbering = re.match(r'^\s*\d+\.\s*', filename)
                    
                    # 如果song_name看起来就是文件名，使用更清晰的显示
                    if song_name.endswith(('.flac', '.mp3', '.m4a', '.wav')):
                        # song_name是文件名，从中提取歌曲名称
                        song_name_without_ext = Path(song_name).stem
                        if has_numbering:
                            # 文件名已有序号，直接显示文件名（去掉扩展名）
                            print(f"{song_name_without_ext} ({size_mb:.1f}MB)")
                        else:
                            # 文件名没有序号，添加序号
                            print(f"{i:02d}.{song_name_without_ext} ({size_mb:.1f}MB)")
                    else:
                        # song_name是歌曲名称，正常处理
                        if has_numbering:
                            # 如果文件名已经包含序号，直接显示歌曲名称
                            print(f"{song_name} ({size_mb:.1f}MB)")
                        else:
                            # 如果文件名没有序号，添加序号
                            print(f"{i:02d}. {song_name} ({size_mb:.1f}MB)")
                else:
                    # 如果没有文件路径信息，检查歌曲名称本身
                    has_numbering = re.match(r'^\s*\d+\.\s*', song_name)
                    if has_numbering:
                        # 如果歌曲名称已经包含序号，直接显示
                        print(f"{song_name} ({size_mb:.1f}MB)")
                    else:
                        # 如果歌曲名称没有序号，添加序号
                        print(f"{i:02d}. {song_name} ({size_mb:.1f}MB)")

        print()

    def _get_detailed_quality_info(self, quality_code: str) -> Dict[str, str]:
        """获取详细的音质信息（包含格式和码率）"""
        quality_info_map = {
            '128k': {
                'name': '标准',
                'format': 'MP3',
                'bitrate': '128k'
            },
            '320k': {
                'name': '较高',
                'format': 'MP3', 
                'bitrate': '320k'
            },
            'flac': {
                'name': '无损',
                'format': 'FLAC',
                'bitrate': '999k'
            },
            'flac24bit': {
                'name': '高解析度无损',
                'format': 'FLAC',
                'bitrate': '1999k'
            }
        }
        
        return quality_info_map.get(quality_code, {
            'name': quality_code.upper(),
            'format': 'Unknown',
            'bitrate': 'Unknown'
        })

    def _get_quality_info(self, quality: str, file_size_mb: float) -> Dict[str, str]:
        """根据音质参数和文件大小获取音质信息"""
        quality_map = {
            '128k': {'name': '标准', 'bitrate': '128kbps'},
            '320k': {'name': '高音质', 'bitrate': '320kbps'},
            'flac': {'name': '无损', 'bitrate': 'FLAC'},
            'lossless': {'name': '无损', 'bitrate': 'FLAC'},
            'hires': {'name': '高解析度无损', 'bitrate': 'Hi-Res'},
            'master': {'name': '母带', 'bitrate': 'Master'},
            'surround': {'name': '环绕声', 'bitrate': 'Surround'}
        }

        # 获取基本信息
        info = quality_map.get(quality, {'name': '未知', 'bitrate': '未知'})

        # 根据文件大小进一步判断音质
        if file_size_mb > 25:
            info = {'name': '无损', 'bitrate': 'FLAC'}
        elif file_size_mb > 15:
            info = {'name': '高音质', 'bitrate': '320kbps'}
        elif file_size_mb > 8:
            info = {'name': '高音质', 'bitrate': '320kbps'}
        elif file_size_mb > 4:
            info = {'name': '标准', 'bitrate': '128kbps'}

        return info

    def _format_duration(self, duration_ms: int) -> str:
        """格式化时长（毫秒转为分:秒格式）"""
        if duration_ms <= 0:
            return "未知"

        # 转换为秒
        total_seconds = duration_ms // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60

        return f"{minutes}:{seconds:02d}"

    def download_song_by_id(self, song_id: str, download_dir: str = "./downloads/netease", quality: str = '128k', progress_callback=None, song_info: Dict = None) -> Dict:
        """通过歌曲ID直接下载单曲"""
        logger.info(f"🎵 开始通过歌曲ID下载: {song_id}")

        try:
            # 获取下载链接（支持音质降级）
            download_url, actual_quality, file_format = self.get_music_url_with_fallback(str(song_id), quality)

            if not download_url:
                logger.error(f"❌ 无法获取歌曲ID {song_id} 的下载链接")
                return {
                    'success': False,
                    'error': f'无法获取歌曲ID {song_id} 的下载链接',
                    'song_title': f'歌曲_{song_id}',
                    'song_artist': 'Unknown',
                    'size_mb': 0,
                    'download_path': download_dir,
                    'filename': '',
                    'quality': quality
                }

            # 优先使用传入的歌曲信息，如果没有则尝试获取
            if song_info:
                song_name = song_info.get('name', f'歌曲_{song_id}')
                artist = song_info.get('artist', 'Unknown')
                duration_ms = song_info.get('duration', 0)
                logger.info(f"🎵 使用传入的歌曲信息: {song_name} - {artist}")
            else:
                # 直接通过歌曲ID获取歌曲信息
                song_info = self.get_song_info(song_id)

                if song_info:
                    song_name = song_info.get('name', f'歌曲_{song_id}')
                    artist = song_info.get('artist', 'Unknown')
                    duration_ms = song_info.get('duration', 0)
                else:
                    # 如果API获取失败，使用默认值
                    song_name = f'歌曲_{song_id}'
                    artist = 'Unknown'
                    duration_ms = 0

                logger.info(f"🎵 歌曲信息: {song_name} - {artist}")

            # 创建下载目录
            download_path = Path(download_dir)
            download_path.mkdir(parents=True, exist_ok=True)

            # 构建文件名
            safe_song_name = self.clean_filename(song_name)
            safe_artist = self.clean_filename(artist)

            # 使用从URL推断的实际文件格式
            ext = file_format

            filename = f"{safe_artist} - {safe_song_name}.{ext}"
            filepath = download_path / filename

            logger.info(f"📁 下载到: {filepath}")

            # 下载文件
            success = self.download_file(
                download_url,
                str(filepath),
                f"{song_name} - {artist}",
                progress_callback=progress_callback
            )

            if success:
                # 获取文件大小
                file_size = filepath.stat().st_size if filepath.exists() else 0
                size_mb = file_size / (1024 * 1024)

                # 获取音质信息
                quality_info = self._get_quality_info(quality, size_mb)

                # 格式化时长信息
                duration_text = self._format_duration(duration_ms)

                logger.info(f"✅ 单曲下载成功: {filename} ({size_mb:.1f}MB)")

                # 为下载的音乐文件添加元数据
                if song_info:
                    metadata_song_info = {
                        'name': song_name,
                        'artist': artist,
                        'album': song_info.get('album', ''),
                        'pic_url': song_info.get('pic_url', ''),
                        'publish_time': song_info.get('publish_time', ''),
                        'track_number': 1
                    }
                    self.add_metadata_to_music_file(str(filepath), metadata_song_info)
                    
                    # 下载歌词文件
                    self.download_song_lyrics(str(song_id), str(filepath), metadata_song_info)

                return {
                    'success': True,
                    'message': f'单曲下载完成: {song_name} - {artist}',
                    'song_title': song_name,
                    'song_artist': artist,
                    'size_mb': size_mb,
                    'download_path': str(download_path),
                    'filename': filename,
                    'quality': quality,
                    'quality_name': quality_info['name'],
                    'bitrate': quality_info['bitrate'],
                    'duration': duration_text,
                    'file_format': ext.upper()
                }
            else:
                logger.error(f"❌ 单曲下载失败: {song_name}")
                return {
                    'success': False,
                    'error': f'单曲下载失败: {song_name}',
                    'song_title': song_name,
                    'song_artist': artist,
                    'size_mb': 0,
                    'download_path': str(download_path),
                    'filename': filename,
                    'quality': quality
                }

        except Exception as e:
            logger.error(f"❌ 单曲下载异常: {e}")
            return {
                'success': False,
                'error': f'单曲下载失败: {str(e)}',
                'song_title': '',
                'song_artist': '',
                'size_mb': 0,
                'download_path': download_dir,
                'filename': '',
                'quality': quality
            }

# 注意：此文件已集成到Telegram机器人中，不再需要命令行功能
# 如需单独使用，可以创建简单的测试脚本调用 NeteaseDownloader 类

    def download_cover_image(self, cover_url: str, save_dir: str, filename: str = "cover.jpg") -> bool:
        """下载专辑封面图片到指定目录"""
        try:
            if not cover_url:
                logger.warning("⚠️ 封面URL为空，跳过下载")
                return False
            
            # 确保保存目录存在
            save_path = Path(save_dir)
            save_path.mkdir(parents=True, exist_ok=True)
            
            # 构建完整的文件路径
            file_path = save_path / filename
            
            # 如果文件已存在，跳过下载
            if file_path.exists():
                logger.info(f"📁 封面文件已存在: {file_path}")
                return True
            
            # 下载封面图片
            logger.info(f"🖼️ 开始下载封面: {cover_url}")
            response = self.session.get(cover_url, timeout=30)
            response.raise_for_status()
            
            # 保存图片文件
            with open(file_path, 'wb') as f:
                f.write(response.content)
            
            # 验证文件大小
            file_size = file_path.stat().st_size
            if file_size > 0:
                logger.info(f"✅ 封面下载成功: {file_path} ({file_size} bytes)")
                return True
            else:
                logger.error(f"❌ 封面文件大小为0: {file_path}")
                file_path.unlink(missing_ok=True)  # 删除空文件
                return False
                
        except Exception as e:
            logger.error(f"❌ 下载封面失败: {e}")
            # 清理可能的部分文件
            try:
                if 'file_path' in locals() and file_path.exists():
                    file_path.unlink()
            except:
                pass
            return False

    def download_artist_image(self, artist_name: str, save_dir: str, filename: str = "artist.jpg") -> bool:
        """下载艺术家头像到指定目录"""
        try:
            # 确保保存目录存在
            save_path = Path(save_dir)
            save_path.mkdir(parents=True, exist_ok=True)
            
            # 构建完整的文件路径
            file_path = save_path / filename
            
            # 如果文件已存在，跳过下载
            if file_path.exists():
                logger.info(f"📁 艺术家头像已存在: {file_path}")
                return True
            
            # 使用用户提供的方法获取艺术家头像
            # 通过搜索页面获取头像URL，然后去除?param=...部分
            avatar_url = self._get_artist_avatar_url(artist_name)
            
            if not avatar_url:
                logger.warning(f"⚠️ 未找到艺术家 {artist_name} 的头像，跳过下载")
                return False
            
            # 下载头像图片
            logger.info(f"🎨 开始下载艺术家头像: {avatar_url}")
            response = self.session.get(avatar_url, timeout=30)
            response.raise_for_status()
            
            # 保存图片文件
            with open(file_path, 'wb') as f:
                f.write(response.content)
            
            # 验证文件大小
            file_size = file_path.stat().st_size
            if file_size > 0:
                logger.info(f"✅ 艺术家头像下载成功: {file_path} ({file_size} bytes)")
                return True
            else:
                logger.error(f"❌ 艺术家头像文件大小为0: {file_path}")
                file_path.unlink(missing_ok=True)  # 删除空文件
                return False
                
        except Exception as e:
            logger.error(f"❌ 下载艺术家头像失败: {e}")
            # 清理可能的部分文件
            try:
                if 'file_path' in locals() and file_path.exists():
                    file_path.unlink()
            except:
                pass
            return False

    def _get_artist_avatar_url(self, artist_name: str) -> Optional[str]:
        """通过用户提供的方法获取艺术家头像URL"""
        try:
            # 已知艺术家头像URL映射（基于用户提供的高质量头像）
            known_artist_avatars = {
                "薛之谦": "http://p1.music.126.net/jj_Ke8S0q8lpDtohy9seDw==/109951168719781607.jpg",
                "陈奕迅": "http://p2.music.126.net/ODuFZql3x08Q4AaW7y20Aw==/109951169014571694.jpg",
                "王力宏": "http://p1.music.126.net/Esjm32Q05PQoWXzVhxqj5Q==/109951165793871057.jpg",  # 已失效，需要更新
                "周杰伦": "http://p1.music.126.net/Esjm32Q05PQoWXzVhxqj5Q==/109951165793871057.jpg",  # 已失效，需要更新
                "林俊杰": "http://p1.music.126.net/6y-UleOR2b6hUcLeu3msQw==/109951165793871057.jpg"  # 已失效，需要更新
            }
            
            # 优先使用已知的高质量头像URL
            if artist_name in known_artist_avatars:
                avatar_url = known_artist_avatars[artist_name]
                logger.info(f"🎨 使用已知头像URL: {avatar_url}")
                
                # 验证URL是否有效
                try:
                    response = self.session.head(avatar_url, timeout=10)
                    if response.status_code == 200:
                        return avatar_url
                    else:
                        logger.warning(f"⚠️ 已知头像URL已失效: {avatar_url}")
                        # 移除失效的URL
                        del known_artist_avatars[artist_name]
                except Exception as e:
                    logger.warning(f"⚠️ 验证已知头像URL失败: {e}")
                    # 移除失效的URL
                    del known_artist_avatars[artist_name]
            
            # 如果不在已知列表中或URL已失效，使用用户提供的方法
            # 通过搜索页面获取头像URL
            logger.info(f"🔍 通过搜索页面获取艺术家头像: {artist_name}")
            
            # 按照用户提供的方法：
            # 1. 访问搜索页面：https://music.163.com/#/search/m/?s={artist_name}&type=100
            # 2. 复制图片地址
            # 3. 去除?param=...部分
            
            # 由于我们无法直接访问浏览器页面，这里提供获取方法说明
            search_url = f"https://music.163.com/#/search/m/?s={artist_name}&type=100"
            logger.info(f"🔍 请访问搜索页面获取头像: {search_url}")
            
            # 尝试通过搜索API获取艺术家信息（可能受到反爬虫限制）
            avatar_url = self._try_get_avatar_from_search_api(artist_name)
            if avatar_url:
                logger.info(f"🎨 通过搜索API获取到头像URL: {avatar_url}")
                return avatar_url
            
            logger.warning(f"⚠️ 艺术家 {artist_name} 的头像获取失败，请手动获取并添加到known_artist_avatars")
            logger.info(f"💡 获取方法：访问 {search_url}，复制头像地址，去除?param=...部分")
            return None
            
        except Exception as e:
            logger.error(f"❌ 获取艺术家头像URL失败: {e}")
            return None

    def _try_get_avatar_from_search_api(self, artist_name: str) -> Optional[str]:
        """尝试通过搜索API获取艺术家头像（可能受到反爬虫限制）"""
        try:
            # 尝试使用不同的搜索类型
            search_types = [
                ('100', '艺术家'),  # 艺术家搜索
                ('1', '单曲'),      # 单曲搜索（可能包含艺术家头像）
            ]
            
            for search_type, type_name in search_types:
                try:
                    logger.info(f"🔍 尝试{type_name}搜索: {artist_name}")
                    
                    # 构建搜索参数
                    search_params = {
                        'csrf_token': '',
                        'type': search_type,
                        's': artist_name,
                        'offset': 0,
                        'total': 'true',
                        'limit': 5
                    }
                    
                    # 发送搜索请求
                    search_url = "https://music.163.com/api/search/get"
                    response = self.session.get(search_url, params=search_params, timeout=10)
                    
                    if response.status_code == 200:
                        try:
                            data = response.json()
                            
                            # 根据搜索类型解析结果
                            if search_type == '100' and 'result' in data and 'artists' in data['result']:
                                # 艺术家搜索
                                artists = data['result']['artists']
                                for artist in artists:
                                    if artist.get('name') == artist_name:
                                        # 获取头像URL
                                        avatar_url = artist.get('img1v1Url') or artist.get('picUrl')
                                        if avatar_url:
                                            # 去除?param=...部分，获取完整尺寸
                                            if '?param=' in avatar_url:
                                                avatar_url = avatar_url.split('?param=')[0]
                                            logger.info(f"🎨 找到艺术家头像: {avatar_url}")
                                            return avatar_url
                                            
                            elif search_type == '1' and 'result' in data and 'songs' in data['result']:
                                # 单曲搜索
                                songs = data['result']['songs']
                                for song in songs:
                                    # 检查歌曲的艺术家信息
                                    if 'artists' in song and song['artists']:
                                        for artist in song['artists']:
                                            if artist.get('name') == artist_name:
                                                # 获取头像URL
                                                avatar_url = artist.get('img1v1Url') or artist.get('picUrl')
                                                if avatar_url:
                                                    # 去除?param=...部分，获取完整尺寸
                                                    if '?param=' in avatar_url:
                                                        avatar_url = avatar_url.split('?param=')[0]
                                                    logger.info(f"🎨 通过单曲找到艺术家头像: {avatar_url}")
                                                    return avatar_url
                                                    
                        except json.JSONDecodeError as e:
                            logger.warning(f"⚠️ {type_name}搜索JSON解析失败: {e}")
                            # 可能是加密数据，继续尝试其他方法
                            continue
                            
                except Exception as e:
                    logger.warning(f"⚠️ {type_name}搜索失败: {e}")
                    continue
            
            logger.warning(f"⚠️ 所有搜索方法都失败了，{artist_name} 的头像获取失败")
            return None
            
        except Exception as e:
            logger.error(f"❌ 搜索API获取头像异常: {e}")
            return None

    def get_artist_info(self, artist_name: str) -> Optional[Dict]:
        """获取艺术家信息（预留方法，用于未来扩展）"""
        try:
            # 这里可以添加更多获取艺术家信息的逻辑
            # 目前返回基本信息
            return {
                'name': artist_name,
                'type': 'artist'
            }
        except Exception as e:
            logger.error(f"❌ 获取艺术家信息失败: {e}")
            return None

    def get_playlist_info(self, playlist_id: str) -> Optional[Dict]:
        """获取歌单信息"""
        try:
            logger.info(f"📋 获取歌单信息: {playlist_id}")
            
            # 构建API请求URL
            api_url = f"https://music.163.com/api/playlist/detail"
            params = {
                'id': playlist_id,
                'csrf_token': ''
            }
            
            # 发送请求
            response = self.session.get(api_url, params=params, timeout=10)
            
            if response.status_code != 200:
                logger.error(f"❌ 获取歌单信息失败，状态码: {response.status_code}")
                return None
            
            # 解析JSON响应
            try:
                data = response.json()
                logger.info(f"🔍 API响应数据: {data}")
            except json.JSONDecodeError as e:
                logger.error(f"❌ 解析歌单信息JSON失败: {e}")
                logger.error(f"🔍 原始响应内容: {response.text[:500]}")
                return None
            
            # 检查响应状态
            if data.get('code') != 200:
                logger.error(f"❌ 歌单API返回错误: {data.get('msg', '未知错误')}")
                logger.error(f"🔍 完整响应: {data}")
                return None
            
            # 网易云API返回的数据结构是 {'result': {...}, 'code': 200}
            playlist_info = data.get('result', {})
            if not playlist_info:
                logger.error("❌ 歌单信息为空")
                logger.error(f"🔍 完整响应: {data}")
                return None
            
            # 提取歌单基本信息
            playlist_name = playlist_info.get('name', f'歌单_{playlist_id}')
            creator = playlist_info.get('creator', {}).get('nickname', '未知用户')
            track_count = playlist_info.get('trackCount', 0)
            play_count = playlist_info.get('playCount', 0)
            description = playlist_info.get('description', '')
            cover_url = playlist_info.get('coverImgUrl', '')
            
            # 提取歌曲列表（API默认只返回前20首）
            tracks = playlist_info.get('tracks', [])
            songs = []
            
            # 处理API返回的歌曲
            for i, track in enumerate(tracks):
                if track:
                    # 提取艺术家信息
                    artists = track.get('artists', [])
                    artist_name = '未知艺术家'
                    if artists and len(artists) > 0:
                        artist_name = artists[0].get('name', '未知艺术家')
                    
                    # 提取专辑信息
                    album_info = track.get('album', {})
                    album_name = album_info.get('name', '未知专辑') if album_info else '未知专辑'
                    
                    song_info = {
                        'id': track.get('id'),
                        'name': track.get('name', f'歌曲_{i+1}'),
                        'artist': artist_name,
                        'album': album_name,
                        'duration': track.get('dt', 0),
                        'track_number': i + 1
                    }
                    songs.append(song_info)
            
            # 如果歌单歌曲数量超过20首，尝试获取完整歌单
            # 尝试获取完整歌单（API可能限制返回数量）
            if len(songs) < 50:  # 如果获取的歌曲少于50首，尝试获取完整歌单
                logger.info(f"🔄 歌单包含 {track_count} 首歌曲，但API只返回了 {len(songs)} 首，尝试获取完整歌单...")
                
                # 尝试使用分页API获取完整歌单
                all_songs = self._get_full_playlist_songs(playlist_id, track_count)
                if all_songs:
                    songs = all_songs
                    logger.info(f"✅ 成功获取完整歌单: {len(songs)} 首歌曲")
                else:
                    logger.warning(f"⚠️ 无法获取完整歌单，将使用API返回的 {len(songs)} 首歌曲")
            
            logger.info(f"✅ 成功获取歌单信息: {playlist_name} - {creator}")
            logger.info(f"📊 歌单统计: {len(songs)} 首歌曲（总数: {track_count}），播放量: {play_count}")
            
            return {
                'id': playlist_id,
                'name': playlist_name,
                'creator': creator,
                'track_count': track_count,
                'play_count': play_count,
                'description': description,
                'cover_url': cover_url,
                'songs': songs
            }
            
        except Exception as e:
            logger.error(f"❌ 获取歌单信息异常: {e}")
            return None

    def get_playlist_info_v1(self, playlist_id: str) -> Optional[Dict]:
        """获取歌单信息 - 基于测试验证的v1 API"""
        try:
            logger.info(f"📋 获取歌单信息 (v1 API): {playlist_id}")
            
            # 使用验证过的API端点
            api_url = f"https://music.163.com/api/v1/playlist/detail"
            params = {'id': playlist_id}
            
            # 发送请求
            response = self.session.get(api_url, params=params, timeout=10)
            
            if response.status_code != 200:
                logger.error(f"❌ 获取歌单信息失败，状态码: {response.status_code}")
                return None
            
            # 解析JSON响应
            try:
                data = response.json()
            except json.JSONDecodeError as e:
                logger.error(f"❌ 解析歌单信息JSON失败: {e}")
                logger.error(f"🔍 原始响应内容: {response.text[:500]}")
                return None
            
            # 检查响应状态
            if data.get('code') != 200:
                logger.error(f"❌ 歌单API返回错误: {data.get('message', '未知错误')}")
                return None
            
            # 获取歌单信息
            playlist_info = data.get('playlist', {})
            if not playlist_info:
                logger.error("❌ 歌单信息为空")
                return None
            
            # 提取歌单基本信息
            playlist_name = playlist_info.get('name', f'歌单_{playlist_id}')
            creator = playlist_info.get('creator', {}).get('nickname', '未知用户')
            track_count = playlist_info.get('trackCount', 0)
            play_count = playlist_info.get('playCount', 0)
            description = playlist_info.get('description', '')
            cover_url = playlist_info.get('coverImgUrl', '')
            
            # 提取歌曲列表（API默认只返回前10首）
            tracks = playlist_info.get('tracks', [])
            track_ids = playlist_info.get('trackIds', [])
            
            logger.info(f"📊 歌单统计: 歌曲总数 {track_count}，已获取详情 {len(tracks)} 首，trackIds数量 {len(track_ids)}")
            
            # 处理已获取详情的歌曲
            songs = []
            for i, track in enumerate(tracks):
                if track:
                    # 提取艺术家信息
                    artists = track.get('ar', [])
                    artist_name = '未知艺术家'
                    if artists and len(artists) > 0:
                        artist_name = artists[0].get('name', '未知艺术家')
                    
                    # 提取专辑信息
                    album_info = track.get('al', {})
                    album_name = album_info.get('name', '未知专辑') if album_info else '未知专辑'
                    
                    song_info = {
                        'id': track.get('id'),
                        'name': track.get('name', f'歌曲_{i+1}'),
                        'artist': artist_name,
                        'album': album_name,
                        'duration': track.get('dt', 0),
                        'track_number': i + 1
                    }
                    songs.append(song_info)
            
            # 如果歌单歌曲数量超过已获取的详情，使用trackIds构建完整列表
            if track_count > len(tracks) and track_ids:
                logger.info(f"🔄 大歌单，创建混合歌曲列表...")
                logger.info(f"   前 {len(tracks)} 首有详细信息")
                logger.info(f"   后 {len(track_ids) - len(tracks)} 首只有ID")
                
                # 从trackIds构建剩余歌曲列表
                for i, track_id_info in enumerate(track_ids[len(tracks):], len(tracks)):
                    song_info = {
                        'id': track_id_info['id'],
                        'name': f"歌曲_{i+1}",  # 使用序号作为默认名称
                        'artist': '未知艺术家',
                        'album': '未知专辑',
                        'duration': 0,
                        'track_number': i + 1
                    }
                    songs.append(song_info)
                
                logger.info(f"✅ 创建了 {len(songs)} 首歌曲的混合列表")
            
            logger.info(f"✅ 成功获取歌单信息: {playlist_name} - {creator}")
            logger.info(f"📊 歌单统计: {len(songs)} 首歌曲（总数: {track_count}），播放量: {play_count}")
            
            return {
                'id': playlist_id,
                'name': playlist_name,
                'creator': creator,
                'track_count': track_count,
                'play_count': play_count,
                'description': description,
                'cover_url': cover_url,
                'songs': songs
            }
            
        except Exception as e:
            logger.error(f"❌ 获取歌单信息时发生错误: {e}")
            return None

    def get_playlist_all_songs_details(self, playlist_id: str) -> Optional[Dict]:
        """获取歌单所有歌曲详情 - 完全基于musicapi.txt的实现"""
        logger.info(f"🎵 获取歌单 {playlist_id} 的所有歌曲详情")
        
        try:
            # 1. 获取歌单基本信息 - 使用musicapi.txt的方法
            data = {'id': playlist_id}
            headers = {
                'User-Agent': APIConstants.USER_AGENT,
                'Referer': APIConstants.REFERER
            }
            
            response = self.session.post(APIConstants.PLAYLIST_DETAIL_API, data=data, 
                                       headers=headers, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            if result.get('code') != 200:
                logger.error(f"❌ 获取歌单详情失败: {result.get('message', '未知错误')}")
                return None
            
            playlist = result.get('playlist', {})
            if not playlist:
                logger.error("❌ 歌单数据为空")
                return None
            
            playlist_name = playlist.get('name', f'歌单_{playlist_id}')
            creator = playlist.get('creator', {}).get('nickname', '未知创建者')
            track_count = playlist.get('trackCount', 0)
            play_count = playlist.get('playCount', 0)
            
            logger.info(f"✅ 歌单: {playlist_name} - {creator}")
            logger.info(f"📊 歌曲总数: {track_count}")
            
            # 2. 获取所有trackIds并分批获取详细信息 - 完全按照musicapi.txt的实现
            track_ids = [str(t['id']) for t in playlist.get('trackIds', [])]
            all_songs = []
            
            for i in range(0, len(track_ids), 100):
                batch_ids = track_ids[i:i+100]
                batch_num = i // 100 + 1
                total_batches = (len(track_ids) + 99) // 100
                
                logger.info(f"📦 处理第 {batch_num}/{total_batches} 批: {len(batch_ids)} 首歌曲")
                
                # 使用musicapi.txt的精确方法
                song_data = {'c': json.dumps([{'id': int(sid), 'v': 0} for sid in batch_ids])}
                
                try:
                    song_resp = self.session.post(APIConstants.SONG_DETAIL_V3, data=song_data, 
                                                headers=headers, timeout=30)
                    song_resp.raise_for_status()
                    
                    song_result = song_resp.json()
                    if song_result.get('code') == 200 and song_result.get('songs'):
                        songs = song_result['songs']
                        logger.info(f"✅ 成功获取 {len(songs)} 首歌曲详情")
                        
                        # 处理歌曲数据 - 按照musicapi.txt的格式
                        for song in songs:
                            artists = song.get('ar', [])
                            artist_name = '/'.join(artist['name'] for artist in artists) if artists else '未知艺术家'
                            
                            album_info = song.get('al', {})
                            album_name = album_info.get('name', '未知专辑') if album_info else '未知专辑'
                            
                            song_info = {
                                'id': song.get('id'),
                                'name': song.get('name', '未知歌曲'),
                                'artist': artist_name,
                                'album': album_name,
                                'duration': song.get('dt', 0),
                                'track_number': len(all_songs) + 1
                            }
                            all_songs.append(song_info)
                            logger.info(f"   ✅ {song_info['name']} - {song_info['artist']}")
                    else:
                        logger.error(f"❌ 第 {batch_num} 批获取失败: {song_result.get('message', '未知错误')}")
                
                except Exception as e:
                    logger.error(f"❌ 第 {batch_num} 批请求异常: {e}")
                
                # 批次间延迟
                if i + 100 < len(track_ids):
                    time.sleep(1)
            
            logger.info(f"📊 获取完成: 共 {len(all_songs)} 首歌曲")
            
            return {
                'id': playlist_id,
                'name': playlist_name,
                'creator': creator,
                'track_count': track_count,
                'play_count': play_count,
                'songs': all_songs
            }
            
        except Exception as e:
            logger.error(f"❌ 获取歌单所有歌曲详情失败: {e}")
            return None

    def download_playlist_with_track_ids(self, playlist_id: str, download_dir: str = "./downloads/netease", quality: str = '128k', progress_callback=None) -> Dict:
        """通过trackIds下载完整歌单 - 基于测试验证的方法"""
        logger.info(f"📋 开始下载完整歌单 (trackIds方法): {playlist_id}")
        
        try:
            # 获取歌单基本信息
            playlist_info = self.get_playlist_info_v1(playlist_id)
            if not playlist_info:
                return {
                    'success': False,
                    'error': f'无法获取歌单 {playlist_id} 的信息',
                    'playlist_name': f'歌单_{playlist_id}',
                    'total_songs': 0,
                    'downloaded_songs': 0,
                    'total_size_mb': 0,
                    'download_path': download_dir,
                    'songs': [],
                    'quality': quality
                }
            
            playlist_name = playlist_info['name']
            creator = playlist_info['creator']
            track_count = playlist_info['track_count']
            songs = playlist_info['songs']
            
            logger.info(f"📋 歌单: {playlist_name} - {creator}")
            logger.info(f"🎵 歌曲数量: {len(songs)} 首 (总数: {track_count})")
            
            # 创建歌单下载目录
            safe_playlist_name = self.clean_filename(playlist_name)
            playlist_dir = Path(download_dir) / safe_playlist_name
            playlist_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"📁 歌单目录: {playlist_dir}")
            
            # 下载歌单中的每首歌曲
            downloaded_songs = []
            total_size = 0
            failed_songs = []
            
            for i, song in enumerate(songs, 1):
                try:
                    logger.info(f"🎵 下载歌曲 {i}/{len(songs)}: {song['name']} - {song['artist']}")
                    
                    # 调用单曲下载方法，传入歌曲信息
                    song_result = self.download_song_by_id(
                        str(song['id']), 
                        str(playlist_dir), 
                        quality, 
                        progress_callback,
                        song_info=song  # 传入歌曲信息
                    )
                    
                    if song_result.get('success'):
                        downloaded_songs.append(song_result)
                        total_size += song_result.get('size_mb', 0)
                        logger.info(f"✅ 歌曲下载成功: {song['name']}")
                    else:
                        failed_songs.append({
                            'song': song,
                            'error': song_result.get('error', '未知错误')
                        })
                        logger.error(f"❌ 歌曲下载失败: {song['name']} - {song_result.get('error')}")
                        
                except Exception as e:
                    failed_songs.append({
                        'song': song,
                        'error': str(e)
                    })
                    logger.error(f"❌ 下载歌曲时发生异常: {song['name']} - {e}")
                
                # 添加延迟，避免请求过于频繁
                if i < len(songs):
                    time.sleep(0.5)
            
            # 计算下载统计
            downloaded_count = len(downloaded_songs)
            failed_count = len(failed_songs)
            total_size_mb = total_size
            
            logger.info(f"📊 歌单下载完成统计:")
            logger.info(f"  ✅ 成功: {downloaded_count}/{len(songs)}")
            logger.info(f"  ❌ 失败: {failed_count}/{len(songs)}")
            logger.info(f"  💾 总大小: {total_size_mb:.1f} MB")
            
            return {
                'success': True,
                'message': f'歌单下载完成: {playlist_name} - {creator}',
                'playlist_name': playlist_name,
                'creator': creator,
                'total_songs': len(songs),
                'downloaded_songs': downloaded_count,
                'failed_songs': failed_count,
                'total_size_mb': total_size_mb,
                'download_path': str(playlist_dir),
                'songs': downloaded_songs,
                'failed_list': failed_songs,
                'quality': quality
            }
            
        except Exception as e:
            logger.error(f"❌ 下载歌单时发生错误: {e}")
            return {
                'success': False,
                'error': f'下载歌单时发生错误: {e}',
                'playlist_name': f'歌单_{playlist_id}',
                'total_songs': 0,
                'downloaded_songs': 0,
                'total_size_mb': 0,
                'download_path': download_dir,
                'songs': [],
                'quality': quality
            }

    def _get_full_playlist_songs(self, playlist_id: str, total_count: int) -> Optional[List[Dict]]:
        """获取完整歌单的所有歌曲（通过移动端API）"""
        try:
            logger.info(f"🔄 开始获取完整歌单歌曲: {playlist_id} (总数: {total_count})")
            
            all_songs = []
            page_size = 1000  # 每页最多1000首
            total_pages = (total_count + page_size - 1) // page_size
            
            for page in range(total_pages):
                offset = page * page_size
                limit = min(page_size, total_count - offset)
                
                logger.info(f"📄 获取第 {page + 1}/{total_pages} 页歌曲 (offset: {offset}, limit: {limit})")
                
                # 使用移动端API获取歌单详情
                api_url = f"https://music.163.com/api/playlist/detail"
                params = {
                    'id': playlist_id,
                    'limit': limit,
                    'offset': offset,
                    'total': 'true',
                    'n': 1000
                }
                
                # 使用移动端请求头
                headers = {
                    'Referer': 'https://music.163.com/',
                    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1',
                    'Accept': 'application/json,text/plain,*/*',
                    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
                }
                
                response = self.session.get(api_url, params=params, headers=headers, timeout=15)
                
                if response.status_code != 200:
                    logger.warning(f"⚠️ 获取第 {page + 1} 页失败，状态码: {response.status_code}")
                    continue
                
                try:
                    data = response.json()
                    if data.get('code') != 200:
                        logger.warning(f"⚠️ 第 {page + 1} 页API返回错误: {data.get('msg', '未知错误')}")
                        continue
                    
                    # 从result中获取歌曲列表
                    result = data.get('result', {})
                    songs = result.get('tracks', [])
                    
                    if not songs:
                        logger.info(f"�� 第 {page + 1} 页无更多歌曲，停止获取")
                        break
                    
                    # 处理歌曲信息
                    for i, track in enumerate(songs):
                        if track:
                            # 提取艺术家信息
                            artists = track.get('ar', [])  # 注意：这里使用'ar'字段
                            artist_name = '未知艺术家'
                            if artists and len(artists) > 0:
                                artist_name = artists[0].get('name', '未知艺术家')
                            
                            # 提取专辑信息
                            album_info = track.get('al', {})  # 注意：这里使用'al'字段
                            album_name = album_info.get('name', '未知专辑') if album_info else '未知专辑'
                            
                            song_info = {
                                'id': track.get('id'),
                                'name': track.get('name', f'歌曲_{len(all_songs)+1}'),
                                'artist': artist_name,
                                'album': album_name,
                                'duration': track.get('dt', 0),
                                'track_number': len(all_songs) + 1
                            }
                            all_songs.append(song_info)
                    
                    logger.info(f"✅ 第 {page + 1} 页获取成功: {len(songs)} 首歌曲")
                    
                    # 如果这一页的歌曲数量少于limit，说明已经是最后一页
                    if len(songs) < limit:
                        logger.info(f"📄 第 {page + 1} 页是最后一页，停止获取")
                        break
                        
                except json.JSONDecodeError as e:
                    logger.warning(f"⚠️ 解析第 {page + 1} 页JSON失败: {e}")
                    continue
                
                # 添加延迟，避免请求过于频繁
                time.sleep(0.5)
            
            logger.info(f"📊 完整歌单获取完成: {len(all_songs)} 首歌曲")
            return all_songs
            
        except Exception as e:
            logger.error(f"❌ 获取完整歌单歌曲异常: {e}")
            return None
    def _get_full_playlist_songs_web(self, playlist_id: str, total_count: int) -> Optional[List[Dict]]:
        """通过网页爬虫获取完整歌单的所有歌曲"""
        try:
            logger.info(f"🔄 开始通过网页爬虫获取完整歌单歌曲: {playlist_id} (总数: {total_count})")
            
            # 使用移动端页面获取完整歌单
            url = f"https://music.163.com/m/playlist?id={playlist_id}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1',
                'Referer': 'https://music.163.com/',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            }
            
            response = self.session.get(url, headers=headers, timeout=15)
            
            if response.status_code != 200:
                logger.warning(f"⚠️ 网页访问失败，状态码: {response.status_code}")
                return None
            
            logger.info(f"✅ 网页访问成功，内容长度: {len(response.text)} 字符")
            
            page_text = response.text
            
            # 查找JavaScript中的歌曲数据
            import re
            import json
            
            # 方法1: 查找window.__INITIAL_STATE__数据
            script_pattern = r'window\.__INITIAL_STATE__\s*=\s*({.*?});'
            script_matches = re.findall(script_pattern, page_text, re.DOTALL)
            
            for script_content in script_matches:
                try:
                    data = json.loads(script_content)
                    
                    # 查找歌单信息
                    if 'playlist' in data:
                        playlist_info = data['playlist']
                        if 'trackCount' in playlist_info:
                            track_count = playlist_info['trackCount']
                            logger.info(f"🎵 通过JavaScript数据找到歌曲数量: {track_count} 首")
                            
                            # 如果trackCount大于10，说明有更多歌曲
                            if track_count > 10:
                                logger.info(f"🔄 歌单实际包含 {track_count} 首歌曲，尝试获取完整列表...")
                                
                                # 查找歌曲列表
                                if 'tracks' in playlist_info:
                                    tracks = playlist_info['tracks']
                                    if len(tracks) > 10:
                                        logger.info(f"✅ 从JavaScript数据获取到 {len(tracks)} 首歌曲")
                                        return self._process_tracks_from_web(tracks)
                                
                                # 如果tracks中没有完整列表，尝试其他方法
                                logger.info("🔄 JavaScript数据中歌曲列表不完整，尝试其他方法...")
                                return self._get_playlist_songs_alternative(playlist_id, track_count)
                            else:
                                logger.info(f"📊 歌单实际只有 {track_count} 首歌曲")
                                return None
                except Exception as e:
                    logger.warning(f"⚠️ 解析JavaScript数据失败: {e}")
                    continue
            
            # 方法2: 查找歌曲链接
            song_link_pattern = r'/song\?id=(\d+)'
            song_links = re.findall(song_link_pattern, page_text)
            if song_links:
                logger.info(f"🎵 通过歌曲链接找到 {len(song_links)} 首歌曲")
                if len(song_links) > 10:
                    return self._get_songs_by_ids(song_links)
            
            logger.warning("⚠️ 无法通过网页爬虫获取完整歌单")
            return None
            
        except Exception as e:
            logger.error(f"❌ 网页爬虫获取歌单异常: {e}")
            return None
    
    def _process_tracks_from_web(self, tracks: List[Dict]) -> List[Dict]:
        """处理从网页获取的歌曲数据"""
        all_songs = []
        
        for i, track in enumerate(tracks):
            if track:
                # 提取艺术家信息
                artists = track.get('ar', [])
                artist_name = '未知艺术家'
                if artists and len(artists) > 0:
                    artist_name = artists[0].get('name', '未知艺术家')
                
                # 提取专辑信息
                album_info = track.get('al', {})
                album_name = album_info.get('name', '未知专辑') if album_info else '未知专辑'
                
                song_info = {
                    'id': track.get('id'),
                    'name': track.get('name', f'歌曲_{i+1}'),
                    'artist': artist_name,
                    'album': album_name,
                    'duration': track.get('dt', 0),
                    'track_number': i + 1
                }
                all_songs.append(song_info)
        
        logger.info(f"✅ 处理完成，共 {len(all_songs)} 首歌曲")
        return all_songs
    
    def _get_songs_by_ids(self, song_ids: List[str]) -> List[Dict]:
        """通过歌曲ID获取歌曲信息"""
        try:
            logger.info(f"🔄 通过歌曲ID获取歌曲信息: {len(song_ids)} 首")
            
            # 批量获取歌曲详情
            api_url = "https://music.163.com/api/song/detail"
            params = {
                'ids': ','.join(song_ids[:100])  # 限制一次最多100首
            }
            
            headers = {
                'Referer': 'https://music.163.com/',
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1'
            }
            
            response = self.session.get(api_url, params=params, headers=headers, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('code') == 200:
                    songs = data.get('songs', [])
                    logger.info(f"✅ 成功获取 {len(songs)} 首歌曲详情")
                    return self._process_tracks_from_web(songs)
            
            logger.warning("⚠️ 通过歌曲ID获取详情失败")
            return []
            
        except Exception as e:
            logger.error(f"❌ 通过歌曲ID获取歌曲信息异常: {e}")
            return []
    
    def _get_playlist_songs_alternative(self, playlist_id: str, total_count: int) -> Optional[List[Dict]]:
        """备用方法：尝试其他方式获取歌单歌曲"""
        try:
            logger.info(f"🔄 尝试备用方法获取歌单歌曲: {playlist_id}")
            
            # 尝试使用不同的API端点
            api_urls = [
                f"https://music.163.com/api/playlist/detail?id={playlist_id}&limit={total_count}",
                f"https://music.163.com/api/playlist/detail?id={playlist_id}&limit=1000",
                f"https://music.163.com/api/playlist/detail?id={playlist_id}&n=1000"
            ]
            
            headers = {
                'Referer': 'https://music.163.com/',
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1'
            }
            
            for api_url in api_urls:
                try:
                    logger.info(f"🔄 尝试API: {api_url}")
                    response = self.session.get(api_url, headers=headers, timeout=15)
                    
                    if response.status_code == 200:
                        data = response.json()
                        if data.get('code') == 200:
                            result = data.get('result', {})
                            tracks = result.get('tracks', [])
                            
                            if len(tracks) > 10:
                                logger.info(f"✅ 备用方法成功获取 {len(tracks)} 首歌曲")
                                return self._process_tracks_from_web(tracks)
                    
                    time.sleep(1)  # 避免请求过于频繁
                    
                except Exception as e:
                    logger.warning(f"⚠️ API {api_url} 失败: {e}")
                    continue
            
            logger.warning("⚠️ 所有备用方法都失败了")
            return None
            
        except Exception as e:
            logger.error(f"❌ 备用方法异常: {e}")
            return None

    def download_playlist_by_id(self, playlist_id: str, download_dir: str = "./downloads/netease", quality: str = '128k', progress_callback=None) -> Dict:
        """通过歌单ID下载歌单 - 优先使用获取所有歌曲详情的方法"""
        logger.info(f"📋 开始下载歌单: {playlist_id}")
        
        try:
            # 优先使用获取所有歌曲详情的方法
            playlist_info = self.get_playlist_all_songs_details(playlist_id)
            if not playlist_info:
                # 如果获取所有详情失败，回退到v1 API
                logger.warning("⚠️ 获取所有歌曲详情失败，回退到v1 API")
                playlist_info = self.get_playlist_info_v1(playlist_id)
            if not playlist_info:
                # 如果v1 API也失败，回退到原API
                logger.warning("⚠️ v1 API也失败，回退到原API")
                playlist_info = self.get_playlist_info(playlist_id)
            if not playlist_info:
                return {
                    'success': False,
                    'error': f'无法获取歌单 {playlist_id} 的信息',
                    'playlist_name': f'歌单_{playlist_id}',
                    'total_songs': 0,
                    'downloaded_songs': 0,
                    'total_size_mb': 0,
                    'download_path': download_dir,
                    'songs': [],
                    'quality': quality
                }
            
            playlist_name = playlist_info['name']
            creator = playlist_info['creator']
            songs = playlist_info['songs']
            track_count = len(songs)
            
            logger.info(f"📋 歌单: {playlist_name} - {creator}")
            logger.info(f"🎵 歌曲数量: {track_count} 首")
            
            # 创建歌单下载目录 - 直接使用歌单名称
            safe_playlist_name = self.clean_filename(playlist_name)
            playlist_dir = Path(download_dir) / safe_playlist_name
            
            playlist_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"📁 歌单目录: {playlist_dir}")
            
            # 歌单不下载封面，因为包含多个不同歌手的歌曲
            logger.info("📋 歌单下载模式：跳过封面下载（避免多歌手冲突）")
            
            # 下载歌单中的每首歌曲
            downloaded_songs = []
            total_size = 0
            failed_songs = []
            
            for i, song in enumerate(songs, 1):
                try:
                    logger.info(f"🎵 下载歌曲 {i}/{track_count}: {song['name']} - {song['artist']}")
                    
                    # 调用单曲下载方法，传入歌曲信息
                    song_result = self.download_song_by_id(
                        str(song['id']), 
                        str(playlist_dir), 
                        quality, 
                        progress_callback,
                        song_info=song  # 传入歌曲信息
                    )
                    
                    if song_result.get('success'):
                        downloaded_songs.append(song_result)
                        total_size += song_result.get('size_mb', 0)
                        logger.info(f"✅ 歌曲下载成功: {song['name']}")
                    else:
                        failed_songs.append({
                            'song': song,
                            'error': song_result.get('error', '未知错误')
                        })
                        logger.error(f"❌ 歌曲下载失败: {song['name']} - {song_result.get('error')}")
                        
                except Exception as e:
                    failed_songs.append({
                        'song': song,
                        'error': str(e)
                    })
                    logger.error(f"❌ 下载歌曲时发生异常: {song['name']} - {e}")
                
                # 添加延迟，避免请求过于频繁
                if i < track_count:
                    time.sleep(0.5)
            
            # 计算下载统计
            downloaded_count = len(downloaded_songs)
            failed_count = len(failed_songs)
            total_size_mb = total_size
            
            logger.info(f"📊 歌单下载完成统计:")
            logger.info(f"  ✅ 成功: {downloaded_count}/{track_count}")
            logger.info(f"  ❌ 失败: {failed_count}/{track_count}")
            logger.info(f"  💾 总大小: {total_size_mb:.1f} MB")
            
            # 生成下载报告
            if failed_songs:
                logger.warning("⚠️ 部分歌曲下载失败:")
                for failed in failed_songs:
                    logger.warning(f"  - {failed['song']['name']}: {failed['error']}")
            
            return {
                'success': True,
                'message': f'歌单下载完成: {playlist_name} - {creator}',
                'playlist_name': playlist_name,
                'creator': creator,
                'total_songs': track_count,
                'downloaded_songs': downloaded_count,
                'failed_songs': failed_count,
                'total_size_mb': total_size_mb,
                'download_path': str(playlist_dir),
                'songs': downloaded_songs,
                'quality': quality,
                'failed_details': failed_songs
            }
            
        except Exception as e:
            logger.error(f"❌ 歌单下载异常: {e}")
            return {
                'success': False,
                'error': f'歌单下载失败: {str(e)}',
                'playlist_name': f'歌单_{playlist_id}',
                'total_songs': 0,
                'downloaded_songs': 0,
                'total_size_mb': 0,
                'download_path': download_dir,
                'songs': [],
                'quality': quality
            }            
        except Exception as e:
            logger.error(f"❌ 备用方法异常: {e}")
            return None


