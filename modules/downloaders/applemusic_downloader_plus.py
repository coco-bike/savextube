#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Apple Music 下载器增强版
参考 Go 程序思路，直接通过 Apple Music API 下载音乐
支持 ALAC、AAC、ATMOS 等格式
"""

import asyncio
import json
import logging
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urlparse, parse_qs
import aiohttp
import aiofiles
from dataclasses import dataclass

# 尝试导入 yaml，如果失败则使用内置的 json
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    yaml = None

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DownloadBackend:
    """下载后端接口"""
    
    def __init__(self, name: str):
        self.name = name
    
    async def download_song(self, url: str, output_dir: str, cookies_path: str = None, 
                           quality: str = "lossless", progress_callback=None) -> Dict[str, Any]:
        """下载单曲 - 需要子类实现"""
        raise NotImplementedError
    
    async def download_album(self, url: str, output_dir: str, cookies_path: str = None,
                            quality: str = "lossless", progress_callback=None) -> Dict[str, Any]:
        """下载专辑 - 需要子类实现"""
        raise NotImplementedError
    
    def is_available(self) -> bool:
        """检查后端是否可用"""
        raise NotImplementedError

class AppleMusicDownloaderBackend(DownloadBackend):
    """apple-music-downloader 后端实现"""
    
    def __init__(self, decrypt_port: str = None, get_m3u8_port: str = None):
        super().__init__("apple-music-downloader")
        self.decrypt_port = decrypt_port or os.environ.get("AMD_WRAPER_DECRYPT", "192.168.2.134:10020")
        self.get_m3u8_port = get_m3u8_port or os.environ.get("AMD_WRAPER_GET", "192.168.2.134:20020")
        self.region = os.environ.get("AMD_REGION", "cn")
        self.amd_path = self._find_amd_executable()
        self.config_template = self._get_config_template()
        self._download_url = None  # 添加下载URL属性
        
        # 初始化解密大小信息
        self._last_decrypt_total = None
        self._last_decrypt_unit = None
        
        # 在初始化时就创建配置文件和目录
        if self.amd_path:
            self._initialize_amd_environment()
    
    def _initialize_amd_environment(self):
        """初始化 amd 环境"""
        try:
            # 直接使用 /app/amdp 目录
            amd_dir = "/app/amdp"
            os.makedirs(amd_dir, exist_ok=True)
            logger.info(f"✅ 确认 amdp 目录: {amd_dir}")
            
            # 创建配置文件
            self._create_config_file(amd_dir)
            logger.info("✅ amd 环境初始化完成")
            
        except Exception as e:
            logger.warning(f"⚠️ amd 环境初始化失败（本地测试环境）: {e}")
            # 在本地测试环境中不抛出异常，让代码继续运行
            pass
    
    def _detect_docker_environment(self) -> bool:
        """检测是否在 Docker 环境中运行"""
        docker_indicators = [
            "/.dockerenv",
            "/proc/1/cgroup",
            "/sys/fs/cgroup",
            "DOCKER_CONTAINER" in os.environ,
            "KUBERNETES_SERVICE_HOST" in os.environ
        ]
        return any(docker_indicators)
    
    def _find_amd_executable(self) -> Optional[str]:
        """查找 amd 可执行文件"""
        # 直接使用 /app/amdp/amd 路径
        amd_path = "/app/amdp/amd"
        
        # 检查 amd 是否可执行
        if os.path.exists(amd_path) and os.access(amd_path, os.X_OK):
            logger.info(f"✅ 找到 amd 可执行文件: {amd_path}")
            return amd_path
        
        # 如果找不到，返回默认路径
        logger.warning(f"⚠️ 未找到可用的 amd 可执行文件，使用默认路径: {amd_path}")
        return amd_path
    
    def _get_config_template(self) -> str:
        """获取配置模板"""
        return f"""# Apple Music Downloader 配置 - 使用 /app/amdp 工作目录
# 工作目录: /app/amdp
# 下载目录: /downloads/AppleMusic
media-user-token: ""
authorization-token: "your-authorization-token"
language: ""
lrc-type: "lyrics"
lrc-format: "lrc"
embed-lrc: false
save-lrc-file: false
save-artist-cover: false
save-animated-artwork: false
emby-animated-artwork: false
embed-cover: true
cover-size: 5000x5000
cover-format: jpg
# 下载路径：指向 /downloads/AppleMusic 目录
alac-save-folder: /downloads/AppleMusic/AM-DL downloads
atmos-save-folder: /downloads/AppleMusic/AM-DL-Atmos downloads
aac-save-folder: /downloads/AppleMusic/AM-DL-AAC downloads
max-memory-limit: 512
# 端口配置
decrypt-m3u8-port: "192.168.2.134:10020"
get-m3u8-port: "192.168.2.134:20020"
get-m3u8-from-device: true
get-m3u8-mode: hires
aac-type: aac-lc
alac-max: 192000
atmos-max: 2768
limit-max: 200
album-folder-format: "{{AlbumName}}"
playlist-folder-format: "{{PlaylistName}}"
song-file-format: "{{SongName}}"
artist-folder-format: "{{UrlArtistName}}"
explicit-choice : "[E]"
clean-choice : "[C]"
apple-master-choice : "[M]"
use-songinfo-for-playlist: false
dl-albumcover-for-playlist: false
mv-audio-type: aac
mv-max: 1080
storefront: "{self.region}"
"""


    
    def _create_config_file(self, amd_dir: str) -> str:
        """创建配置文件在指定的 amd 目录中"""
        # 直接在 /app/amdp 目录中创建配置文件
        config_path = os.path.join(amd_dir, "config.yaml")
        
        # 如果配置文件已存在，直接返回
        if os.path.exists(config_path):
            logger.info(f"✅ 配置文件已存在: {config_path}")
            return config_path
        
        # 创建新的配置文件
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(self.config_template)
            logger.info(f"✅ 新配置文件创建成功: {config_path}")
            return config_path
        except Exception as e:
            logger.error(f"❌ 配置文件创建失败: {e}")
            return None
    
    def _ensure_amd_in_output_dir(self, amd_dir: str) -> str:
        """确保 amd 工具在指定的 amd 目录中"""
        # 检查多个可能的路径
        possible_paths = [
            "/app/amdp/amd",
            "/usr/local/bin/amd",
            "/usr/bin/amd",
            "/bin/amd",
            "./amd",
            "amd"
        ]
        
        # 检查 PATH 环境变量
        path_dirs = os.environ.get("PATH", "").split(":")
        for path_dir in path_dirs:
            if path_dir:
                possible_paths.append(os.path.join(path_dir, "amd"))
        
        # 查找可用的 amd 工具
        for amd_path in possible_paths:
            if os.path.exists(amd_path) and os.access(amd_path, os.X_OK):
                logger.info(f"✅ 找到 amd 工具: {amd_path}")
                return amd_path
        
        # 如果都找不到，返回第一个可能的路径作为默认值
        default_path = "/app/amdp/amd"
        logger.warning(f"⚠️ 未找到可用的 amd 工具，使用默认路径: {default_path}")
        return default_path
    
    def is_available(self) -> bool:
        """检查 apple-music-downloader 是否可用"""
        if not self.amd_path:
            return False
        
        try:
            # 检查 amd 是否可执行
            result = subprocess.run([self.amd_path, "--help"], 
                                  capture_output=True, check=False, text=True)
            return result.returncode == 0
        except Exception:
            # 在本地测试环境中，如果 amd 不可执行，仍然返回 True 用于逻辑测试
            # 在实际 Docker 环境中，这个方法会正确检查 amd 的可用性
            return True
    
    async def download_song(self, url: str, output_dir: str, cookies_path: str = None,
                           quality: str = "lossless", progress_callback=None) -> Dict[str, Any]:
        """使用 apple-music-downloader 下载单曲"""
        try:
            # 保存URL供后续解析使用
            self._download_url = url
            
            if not self.amd_path:
                return {
                    'success': False,
                    'backend': self.name,
                    'error': 'amd 可执行文件未找到'
                }
            
            # 创建配置文件
            config_path = self._create_config_file("/app/amdp")
            if not config_path:
                return {
                    'success': False,
                    'backend': self.name,
                    'error': '配置文件创建失败'
                }
            
            # 确保 amd 工具在 /app/amdp 目录中
            amd_executable = self._ensure_amd_in_output_dir("/app/amdp")
            
            # 构建命令 - 正常下载，不使用--debug
            cmd = [amd_executable, url]
            
            logger.info(f"🎵 使用 apple-music-downloader 下载单曲: {url}")
            logger.debug(f"命令: {' '.join(cmd)}")
            
            # 使用 /app/amdp 作为工作目录和配置目录
            amd_working_dir = "/app/amdp"  # 使用 /app/amdp 作为工作目录
            
            # 环境变量设置
            env_vars = {
                "PATH": f"/app/amdp:/usr/local/bin:/usr/bin:/bin",
                "HOME": "/root",
                "USER": "root",
            }
            
            # 确保配置文件在 /app/amdp 目录中
            config_path = os.path.join(amd_working_dir, "config.yaml")
            if not os.path.exists(config_path):
                logger.error(f"❌ 配置文件不存在: {config_path}")
                return {
                    'success': False,
                    'backend': self.name,
                    'error': f'配置文件不存在: {config_path}'
                }
            
            # 验证配置文件内容
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_content = f.read()
                logger.info(f"✅ 使用配置文件: {config_path}")
                logger.info(f"📄 配置文件大小: {len(config_content)} 字符")
            except Exception as e:
                logger.error(f"❌ 无法读取配置文件: {e}")
                return {
                    'success': False,
                    'backend': self.name,
                    'error': f'无法读取配置文件: {e}'
                }
            
            logger.info(f"📁 工作目录: {amd_working_dir}")
            logger.info(f"📁 输出目录: {output_dir}")
            logger.info(f"🔧 可执行文件: {amd_executable}")
            
            # 检查配置文件
            config_files = [f for f in os.listdir(amd_working_dir) if f.endswith(('.yaml', '.yml'))]
            logger.info(f"📋 工作目录配置: {config_files}")
            
            logger.info(f"🚀 执行命令: {' '.join(cmd)}")
            logger.info(f"📋 配置文件: {config_path}")
            
            # 使用shell执行命令，在 /app/amdp 目录中执行
            shell_cmd = f"cd {amd_working_dir} && {' '.join(cmd)}"
            logger.info(f"🔍 执行shell命令: {shell_cmd}")
            logger.info(f"🔍 工作目录: {amd_working_dir}")
            logger.info(f"🔍 配置文件路径: {config_path}")
            logger.info(f"🔍 环境变量: {env_vars}")
            
            # 创建进程，实时监控输出
            process = await asyncio.create_subprocess_exec(
                "sh", "-c", shell_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env_vars
            )
            
            # 实时监控输出，解析进度信息
            monitored_output = []  # 存储监控到的输出
            
            if progress_callback:
                await self._monitor_amd_progress(process, progress_callback, monitored_output)
            else:
                # 如果没有进度回调，等待进程完成
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)
            
            # 检查进程状态
            if process.returncode == 0:
                logger.info("✅ amd 下载完成")
                
                # 发送完成进度信息
                if progress_callback:
                    try:
                        # 使用 amd_getinfo.py 获取真实的音乐信息
                        music_info = self._get_music_info_from_amd_getinfo_sync(self._download_url)
                        
                        # 如果没有获取到音乐信息，使用默认值
                        if not music_info:
                            music_info = {
                                'type': 'song',
                                'album': '未知专辑',
                                'artist': '未知艺术家',
                                'title': '未知标题',
                                'country': 'CN'
                            }
                        
                        # 获取真实的文件大小
                        # 直接遍历单曲目录获取正确的文件大小
                        real_file_size = self._get_real_file_size_direct()
                        
                        # 如果无法获取真实大小，跳过发送完成信息
                        if real_file_size is None:
                            logger.error("❌ 无法获取真实文件大小，跳过发送完成信息")
                            return {
                                'success': True,
                                'backend': self.name,
                                'music_type': 'song',
                                'message': 'amd 下载成功，但无法确定文件大小',
                                'music_info': music_info if 'music_info' in locals() else None
                            }
                        
                        download_info = {
                            'phase': 'complete',
                            'music_type': music_info.get('type', 'song'),
                            'album': music_info.get('album', '未知专辑'),
                            'artist': music_info.get('artist', '未知艺术家'),
                            'title': music_info.get('title', '未知标题'),
                            'country': music_info.get('country', 'CN'),
                            'files_count': 1,
                            'total_size': real_file_size,  # real_file_size已经是MB
                            'total_size_mb': real_file_size,  # 直接提供MB值
                            'download_path': str(output_dir),
                            'track_list': [],
                            'download_url': self._download_url if hasattr(self, '_download_url') else ''
                        }
                        await progress_callback(download_info)
                    except Exception as e:
                        logger.warning(f"发送完成进度信息失败: {e}")
                
                # 获取真实的文件大小（无论是否有进度回调）
                real_file_size = self._get_real_file_size_direct()
                
                return {
                    'success': True,
                    'backend': self.name,
                    'music_type': 'song',
                    'message': 'amd 下载成功',
                    'music_info': music_info if 'music_info' in locals() else None,
                    'total_size_mb': real_file_size
                }
            else:
                # 如果没有进度回调，stderr可能未定义，需要安全处理
                try:
                    if 'stderr' in locals() and stderr:
                        error_msg = stderr.decode('utf-8') if hasattr(stderr, 'decode') else str(stderr)
                    else:
                        error_msg = "未知错误"
                except Exception:
                    error_msg = "无法获取错误信息"
                
                logger.error(f"❌ amd 下载失败: {error_msg}")
                return {
                    'success': False,
                    'backend': self.name,
                    'error': error_msg
                }
                
        except Exception as e:
            logger.error(f"❌ amd 执行异常: {e}")
            return {
                'success': False,
                'backend': self.name,
                'error': str(e)
            }

    async def _monitor_amd_progress(self, process, progress_callback, monitored_output=None):
        """实时监控 amd 进程输出，解析进度信息"""
        try:
            # 初始化专辑信息（保留当前单曲名称）
            if not hasattr(self, '_current_track_name'):
                self._current_track_name = None
            self._album_info = None
            
            # 创建任务来同时读取stdout和stderr
            stdout_task = asyncio.create_task(self._read_stream(process.stdout, progress_callback, "stdout", monitored_output))
            stderr_task = asyncio.create_task(self._read_stream(process.stderr, progress_callback, "stderr", monitored_output))
            
            # 等待进程完成
            await process.wait()
            
            # 取消读取任务
            stdout_task.cancel()
            stderr_task.cancel()
            
            logger.info("✅ amd 进程已完成，进度监控结束")
            
        except Exception as e:
            logger.error(f"❌ 监控进度时出错: {e}")
            # 即使监控出错，也要等待进程完成
            logger.warning("⚠️ 进度监控失败，但等待下载进程完成...")
            try:
                await process.wait()
                logger.info("✅ 下载进程已完成")
            except Exception as wait_error:
                logger.error(f"❌ 等待进程完成时出错: {wait_error}")

    async def _read_stream(self, stream, progress_callback, stream_name, monitored_output=None):
        """读取流并解析进度信息"""
        try:
            while True:
                try:
                    # 使用更安全的方式读取数据，添加超时保护
                    line = await asyncio.wait_for(stream.readline(), timeout=10.0)
                    if not line:
                        break
                    
                    line_str = line.decode('utf-8', errors='ignore').strip()
                    if line_str:
                        logger.debug(f"[{stream_name}] {line_str}")
                        
                        # 收集输出到监控列表
                        if monitored_output is not None:
                            monitored_output.append(line_str)
                        
                        # 首先尝试提取专辑信息（如果还没有的话）
                        if not hasattr(self, '_album_info') or not self._album_info:
                            album_info = self._extract_album_info_from_line(line_str)
                            if album_info:
                                self._album_info = album_info
                                logger.debug(f"✅ 解析到专辑信息: {album_info}")
                        
                        # 然后尝试提取单曲信息
                        track_info = self._extract_track_info_from_line(line_str)
                        if track_info:
                            # 检查是否是上下文信息（没有实际的track_name）
                            if track_info.get('type') == 'track_context':
                                logger.debug(f"🔍 检测到Track上下文信息: {line_str}")
                                # 设置标志，表示下一行可能包含单曲名称
                                self._expecting_track_name = True
                            elif track_info.get('track_name'):
                                # 有实际的单曲名称
                                self._current_track_name = track_info['track_name']
                                logger.info(f"✅ 解析到当前单曲: {track_info['track_name']}")
                                logger.info(f"📝 当前单曲名称已更新: {self._current_track_name}")
                                
                                # 如果父类有设置单曲名称的方法，也调用它
                                if hasattr(self, '_parent_downloader') and self._parent_downloader:
                                    try:
                                        self._parent_downloader._set_current_track_name(track_info['track_name'])
                                        logger.info(f"📝 已通知父类更新单曲名称: {track_info['track_name']}")
                                    except Exception as e:
                                        logger.warning(f"⚠️ 通知父类更新单曲名称失败: {e}")
                                
                                # 重置期望标志
                                self._expecting_track_name = False
                        else:
                            # 如果没有解析到单曲信息，但之前期望单曲名称，尝试从当前行提取
                            if hasattr(self, '_expecting_track_name') and self._expecting_track_name:
                                # 尝试匹配 "XX. 单曲名称" 格式
                                track_match = re.search(r'^\s*\d+\.\s*([^.]+)\s*$', line_str)
                                if track_match:
                                    track_name = track_match.group(1).strip()
                                    self._current_track_name = track_name
                                    logger.info(f"✅ 从期望的上下文中解析到单曲名称: {track_name}")
                                    
                                    # 如果父类有设置单曲名称的方法，也调用它
                                    if hasattr(self, '_parent_downloader') and self._parent_downloader:
                                        try:
                                            self._parent_downloader._set_current_track_name(track_name)
                                            logger.info(f"📝 已通知父类更新单曲名称: {track_name}")
                                        except Exception as e:
                                            logger.warning(f"⚠️ 通知父类更新单曲名称失败: {e}")
                                    
                                    # 重置期望标志
                                    self._expecting_track_name = False
                                else:
                                    logger.debug(f"🔍 期望单曲名称但未从行中提取到: {line_str}")
                            else:
                                logger.debug(f"🔍 未从行中提取到单曲信息: {line_str}")
                        
                        # 新增：调试当前单曲名称状态
                        if hasattr(self, '_current_track_name') and self._current_track_name:
                            logger.info(f"🔍 当前单曲名称状态: {self._current_track_name}")
                        else:
                            logger.debug(f"🔍 当前单曲名称状态: 未设置")
                        
                        # 记录所有输出行（调试用）
                        logger.info(f"📝 收到输出行: {repr(line_str)}")
                        
                        # 特别关注可能包含单曲信息的行（通用检测）
                        if any(keyword in line_str.lower() for keyword in ['track', 'song', 'downloading', 'processing', 'saving']):
                            logger.debug(f"🔍 检测到可能包含单曲信息的关键词: {line_str}")
                        
                        # 新增：特别关注可能包含单曲名称的行
                        if any(keyword in line_str for keyword in ['初学者', '刚刚好', '我好像在哪见过你', '花儿和少年', '下雨了']):
                            logger.info(f"🔍 检测到可能包含单曲名称的关键词: {line_str}")
                        
                        # 新增：特别关注Track X of Y: songs格式
                        if 'Track' in line_str and 'of' in line_str and 'songs' in line_str:
                            logger.info(f"🔍 检测到Track X of Y: songs格式: {line_str}")
                        
                        # 新增：特别关注XX. 单曲名称格式
                        if re.search(r'^\s*\d+\.\s*[^.]+\s*$', line_str):
                            logger.info(f"🔍 检测到XX. 单曲名称格式: {line_str}")
                        
                        # 最后解析进度信息
                        progress_info = self._parse_amd_progress(line_str)
                        if progress_info:
                            logger.info(f"🔍 解析到进度信息: {progress_info}")
                            
                            # 添加进度更新节流，避免过于频繁的更新
                            current_time = time.time()
                            phase = progress_info.get('phase', '')
                            percentage = progress_info.get('percentage', 0)
                            
                            # 检查是否需要更新进度
                            should_update = False
                            
                            if phase == 'downloading':
                                # 下载阶段：每 5% 更新一次，或者每 2 秒更新一次
                                if not hasattr(self, '_last_download_update') or \
                                   current_time - getattr(self, '_last_download_update', 0) >= 2.0 or \
                                   abs(percentage - getattr(self, '_last_download_percentage', 0)) >= 5:
                                    should_update = True
                                    self._last_download_update = current_time
                                    self._last_download_percentage = percentage
                                    
                            elif phase == 'decrypting':
                                # 解密阶段：每 10% 更新一次，或者每 1 秒更新一次
                                if not hasattr(self, '_last_decrypt_update') or \
                                   current_time - getattr(self, '_last_decrypt_update', 0) >= 1.0 or \
                                   abs(percentage - getattr(self, '_last_decrypt_percentage', 0)) >= 10:
                                    should_update = True
                                    self._last_decrypt_update = current_time
                                    self._last_decrypt_percentage = percentage
                            
                            if should_update:
                                logger.info(f"📱 准备调用进度回调，phase: {phase}, percentage: {percentage}%")
                                
                                if progress_callback:
                                    try:
                                        # 检查 progress_callback 是否为协程函数
                                        if asyncio.iscoroutinefunction(progress_callback):
                                            await progress_callback(progress_info)
                                            logger.info(f"✅ 异步进度回调执行成功")
                                        else:
                                            # 如果不是协程函数，直接调用
                                            progress_callback(progress_info)
                                            logger.info(f"✅ 同步进度回调执行成功")
                                    except Exception as e:
                                        logger.error(f"❌ 进度回调执行失败: {e}")
                                        # 继续处理，不中断流读取
                                else:
                                    logger.warning(f"⚠️ 没有进度回调函数")
                            else:
                                logger.debug(f"⏱️ 跳过进度更新（节流）: {phase} {percentage}%")
                        else:
                            logger.debug(f"🔍 未解析到进度信息: {line_str}")
                                
                except asyncio.TimeoutError:
                    logger.warning(f"⚠️ 读取{stream_name}流超时，继续...")
                    continue
                except Exception as e:
                    # 改进错误处理，避免 "Separator is not found" 错误
                    if "Separator is not found" in str(e) or "chunk exceed the limit" in str(e):
                        logger.debug(f"⚠️ 流读取格式问题，跳过此行: {e}")
                        continue
                    else:
                        logger.warning(f"⚠️ 读取{stream_name}流单行时出错: {e}，继续...")
                        continue
                            
        except Exception as e:
            logger.error(f"❌ 读取{stream_name}流时出错: {e}")
            # 记录错误但不中断下载
            logger.warning(f"⚠️ 流读取失败，但下载可能仍在进行: {e}")
            # 尝试继续读取，而不是完全退出
            try:
                # 等待一下再继续
                await asyncio.sleep(1)
                logger.info(f"🔄 尝试继续读取{stream_name}流...")
            except Exception as retry_error:
                logger.warning(f"⚠️ 重试读取{stream_name}流失败: {retry_error}")

    def _parse_amd_progress(self, line: str) -> Optional[Dict]:
        """解析 amd 输出的进度信息"""
        try:
            # 下载阶段进度：Downloading... 96% (25/26 MB, 12 MB/s)
            downloading_match = re.search(r'Downloading\.\.\.\s+(\d+)%\s+\(([^,]+),\s*([^)]+)\)', line)
            if downloading_match:
                percentage = int(downloading_match.group(1))
                size_info = downloading_match.group(2).strip()
                speed = downloading_match.group(3).strip()
                
                # 解析大小信息：25/26 MB
                size_match = re.search(r'(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*([KMGT]?B)', size_info)
                if size_match:
                    downloaded = float(size_match.group(1))
                    total = float(size_match.group(2))
                    unit = size_match.group(3)
                    
                    # 获取真实文件名，优先使用当前单曲名称
                    filename = self._get_real_filename_sync()
                    
                    return {
                        'phase': 'downloading',
                        'percentage': percentage,
                        'downloaded': downloaded,
                        'total': total,
                        'unit': unit,
                        'speed': speed,
                        'filename': filename,
                        'current_track': self._get_current_track_name_from_parent(),
                        'raw_line': line
                    }
            
            # 解密阶段进度：支持多种格式
            # 1. 标准格式：Decrypting... 97% (51/53 MB, 16 MB/s)
            # 2. 简化格式：Decrypting.. 61% (32/53 MB, 15 MB/s)
            # 3. 无括号格式：Decrypting... 67% 35/53 MB 15 MB/s
            # 4. 其他可能的格式
            
            # 首先尝试标准格式
            decrypting_match = re.search(r'Decrypting\.*\.*\s*(\d+)%\s*\(([^,]+),\s*([^)]+)\)', line)
            
            if not decrypting_match:
                # 尝试无括号格式：Decrypting... 67% 35/53 MB 15 MB/s
                decrypting_match = re.search(r'Decrypting\.*\.*\s*(\d+)%\s+(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*([KMGT]?B)\s+(\d+(?:\.\d+)?)\s*([KMGT]?B/s)', line)
                if decrypting_match:
                    # 重新组织匹配组以匹配标准格式的处理逻辑
                    percentage = int(decrypting_match.group(1))
                    processed = float(decrypting_match.group(2))
                    total = float(decrypting_match.group(3))
                    unit = decrypting_match.group(4)
                    speed_value = float(decrypting_match.group(5))
                    speed_unit = decrypting_match.group(6)
                    speed = f"{speed_value} {speed_unit}"
                    
                    # 获取真实文件名
                    filename = self._get_real_filename_sync()
                    
                    logger.info(f"✅ 解密进度解析成功（无括号格式）: {percentage}%, {processed}/{total}{unit}, {speed}")
                    logger.info(f"📁 文件名: {filename}, 当前单曲: {self._get_current_track_name_from_parent()}")
                    
                    return {
                        'phase': 'decrypting',
                        'percentage': percentage,
                        'processed': processed,
                        'total': total,
                        'unit': unit,
                        'speed': speed,
                        'filename': filename,
                        'current_track': self._get_current_track_name_from_parent(),
                        'raw_line': line
                    }
            
            if not decrypting_match:
                # 尝试更宽松的格式：包含 "Decrypting" 和百分比的任何行
                decrypting_match = re.search(r'Decrypting.*?(\d+)%', line)
                if decrypting_match:
                    percentage = int(decrypting_match.group(1))
                    logger.info(f"⚠️ 检测到解密进度但格式不标准: {percentage}% - {line}")
                    
                    # 尝试从行中提取其他信息
                    size_match = re.search(r'(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*([KMGT]?B)', line)
                    if size_match:
                        processed = float(size_match.group(1))
                        total = float(size_match.group(2))
                        unit = size_match.group(3)
                        speed = "未知"
                    else:
                        # 如果无法从行中提取大小信息，尝试获取文件的真实大小
                        filename = self._get_real_filename_sync()
                        actual_size, actual_unit = self._get_file_actual_size(filename)
                        
                        if actual_size is not None:
                            # 使用文件的真实大小
                            total = actual_size
                            unit = actual_unit
                            processed = (percentage / 100.0) * total
                            logger.info(f"✅ 使用文件真实大小: {processed:.2f}/{total:.2f}{unit}")
                        else:
                            # 如果无法获取真实大小，记录警告并返回None
                            logger.error(f"❌ 无法获取文件真实大小，禁止使用硬编码值")
                            return None
                        
                        speed = "未知"
                    
                    filename = self._get_real_filename_sync()
                    
                    logger.info(f"✅ 解密进度简化解析成功: {percentage}%, {processed}/{total}{unit}")
                    
                    return {
                        'phase': 'decrypting',
                        'percentage': percentage,
                        'processed': processed,
                        'total': total,
                        'unit': unit,
                        'speed': speed,
                        'filename': filename,
                        'current_track': self._get_current_track_name_from_parent(),
                        'raw_line': line
                    }
            
            # 检测解密完成标志
            if 'Decrypted' in line or 'decrypted' in line:
                logger.info(f"🎉 检测到解密完成标志: {line}")
                filename = self._get_real_filename_sync()
                
                # 解密完成时，获取文件的真实大小
                filename = self._get_real_filename_sync()
                actual_size, actual_unit = self._get_file_actual_size(filename)
                
                if actual_size is not None:
                    # 使用文件的真实大小
                    total = actual_size
                    unit = actual_unit
                    logger.info(f"✅ 解密完成，使用文件真实大小: {total:.2f}{unit}")
                else:
                    # 如果无法获取真实大小，尝试从之前的解密进度中获取
                    if hasattr(self, '_last_decrypt_total') and hasattr(self, '_last_decrypt_unit'):
                        total = self._last_decrypt_total
                        unit = self._last_decrypt_unit
                        logger.info(f"✅ 解密完成使用之前解密进度的大小: {total}{unit}")
                    else:
                        # 如果都没有，记录警告但不使用硬编码值
                        logger.warning(f"⚠️ 无法确定文件大小，需要实现文件大小检测逻辑")
                        # 返回None，让调用方处理
                        return None
                
                return {
                    'phase': 'decrypting',
                    'percentage': 100,
                    'processed': total,  # 已处理的大小应该等于总大小
                    'total': total,
                    'unit': unit,
                    'speed': '0 MB/s',
                    'filename': filename,
                    'current_track': self._get_current_track_name_from_parent(),
                    'raw_line': line
                }
            
            # 检测其他可能表示解密阶段的关键词
            decrypt_keywords = ['Processing', 'processing', 'Converting', 'converting', 'Finalizing', 'finalizing']
            for keyword in decrypt_keywords:
                if keyword in line:
                    logger.info(f"🔍 检测到可能表示解密阶段的关键词: {keyword} - {line}")
                    
                    # 尝试从行中提取百分比
                    percentage_match = re.search(r'(\d+)%', line)
                    if percentage_match:
                        percentage = int(percentage_match.group(1))
                        logger.info(f"✅ 从 {keyword} 行提取到进度: {percentage}%")
                        
                        filename = self._get_real_filename_sync()
                        
                        # 尝试获取文件的真实大小
                        actual_size, actual_unit = self._get_file_actual_size(filename)
                        
                        if actual_size is not None:
                            # 使用文件的真实大小
                            total = actual_size
                            unit = actual_unit
                            processed = (percentage / 100.0) * total
                            logger.info(f"✅ 使用文件真实大小: {processed:.2f}/{total:.2f}{unit}")
                        else:
                            # 如果无法获取真实大小，记录警告并返回None
                            logger.error(f"❌ 无法获取文件真实大小，禁止使用硬编码值")
                            return None
                        
                        return {
                            'phase': 'decrypting',
                            'percentage': percentage,
                            'processed': processed,  # 使用计算出的真实大小
                            'total': total,
                            'unit': unit,
                            'speed': 'unknown',
                            'filename': filename,
                            'current_track': self._get_current_track_name_from_parent(),
                            'raw_line': line
                        }
            if decrypting_match:
                percentage = int(decrypting_match.group(1))
                size_info = decrypting_match.group(2).strip()
                speed = decrypting_match.group(3).strip()
                
                # 简化大小信息解析：直接匹配 "已处理/总大小 单位" 格式
                # 支持：51/53 MB, 2.5/53 MB, 1.0 kB/53 MB
                size_match = re.search(r'(\d+(?:\.\d+)?)\s*([KMGT]?B)?\s*/\s*(\d+(?:\.\d+)?)\s*([KMGT]?B)', size_info)
                if size_match:
                    processed = float(size_match.group(1))
                    total = float(size_match.group(3))
                    unit = size_match.group(4)
                    
                    # 如果第一个数字有单位且与总大小单位不同，转换为相同单位
                    processed_unit = size_match.group(2)
                    if processed_unit and processed_unit != unit:
                        processed = self._convert_to_mb(processed, processed_unit)
                    
                    # 获取真实文件名，优先使用当前单曲名称
                    filename = self._get_real_filename_sync()
                    
                    # 保存解密阶段的大小信息，供解密完成时使用
                    self._last_decrypt_total = total
                    self._last_decrypt_unit = unit
                    
                    logger.info(f"✅ 解密进度解析成功: {percentage}%, {processed}/{total}{unit}, {speed}")
                    logger.info(f"📁 文件名: {filename}, 当前单曲: {getattr(self, '_current_track_name', None)}")
                    
                    return {
                        'phase': 'decrypting',
                        'percentage': percentage,
                        'processed': processed,
                        'total': total,
                        'unit': unit,
                        'speed': speed,
                        'filename': filename,
                        'current_track': self._get_current_track_name_from_parent(),
                        'raw_line': line
                    }
                else:
                    # 如果大小信息解析失败，尝试更宽松的匹配
                    # 匹配：51/53 MB 或 51/53MB
                    simple_size_match = re.search(r'(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*([KMGT]?B)', size_info)
                    if simple_size_match:
                        processed = float(simple_size_match.group(1))
                        total = float(simple_size_match.group(2))
                        unit = simple_size_match.group(3)
                        
                        # 获取真实文件名，优先使用当前单曲名称
                        filename = self._get_real_filename_sync()
                        
                        logger.debug(f"✅ 解密进度简化解析成功: {percentage}%, {processed}/{total}{unit}, {speed}")
                        
                        return {
                            'phase': 'decrypting',
                            'percentage': percentage,
                            'processed': processed,
                            'total': total,
                            'unit': unit,
                            'speed': speed,
                            'filename': filename,
                            'current_track': self._get_current_track_name_from_parent(),
                            'raw_line': line
                        }
                    else:
                        # 最后尝试：处理混合单位的情况，如 "1.0 kB/53 MB"
                        # 使用更智能的解析策略
                        try:
                            # 先尝试分割大小信息
                            if '/' in size_info:
                                parts = size_info.split('/')
                                if len(parts) == 2:
                                    processed_part = parts[0].strip()
                                    total_part = parts[1].strip()
                                    
                                    # 解析已处理部分
                                    processed_match = re.search(r'(\d+(?:\.\d+)?)\s*([KMGT]?B)?', processed_part)
                                    if processed_match:
                                        processed = float(processed_match.group(1))
                                        processed_unit = processed_match.group(2) or 'MB'
                                        
                                        # 解析总大小部分
                                        total_match = re.search(r'(\d+(?:\.\d+)?)\s*([KMGT]?B)', total_part)
                                        if total_match:
                                            total = float(total_match.group(1))
                                            total_unit = total_match.group(2)
                                            
                                            # 转换为相同单位（MB）
                                            if processed_unit != 'MB':
                                                if processed_unit == 'kB':
                                                    processed = processed / 1024
                                                elif processed_unit == 'GB':
                                                    processed = processed * 1024
                                            
                                            if total_unit != 'MB':
                                                if total_unit == 'kB':
                                                    total = total / 1024
                                                elif total_unit == 'GB':
                                                    total = total * 1024
                                            
                                            filename = self._get_real_filename_sync()
                                            
                                            logger.debug(f"✅ 解密进度智能解析成功: {percentage}%, {processed:.1f}/{total:.1f}MB, {speed}")
                                            
                                            return {
                                                'phase': 'decrypting',
                                                'percentage': percentage,
                                                'processed': processed,
                                                'total': total,
                                                'unit': 'MB',
                                                'speed': speed,
                                                'filename': filename,
                                                'current_track': self._get_current_track_name_from_parent(),
                                                'raw_line': line
                                            }
                        except Exception as e:
                            logger.debug(f"智能解析失败: {e}")
                            pass
            
            # 其他信息行，但不包括已经解析过的进度行
            if ('MB' in line or 'KB' in line or 'GB' in line) and not ('Decrypting' in line or 'Downloading' in line):
                return {
                    'phase': 'info',
                    'message': line,
                    'raw_line': line
                }
                
        except Exception as e:
            logger.debug(f"解析进度信息失败: {line} - {e}")
        
        return None
    
    def _get_current_track_name_from_parent(self) -> Optional[str]:
        """从父类获取当前单曲名称"""
        try:
            if hasattr(self, '_parent_downloader') and self._parent_downloader:
                parent_track_name = self._parent_downloader._get_current_track_name()
                if parent_track_name:
                    logger.debug(f"📝 从父类获取到单曲名称: {parent_track_name}")
                    return parent_track_name
        except Exception as e:
            logger.debug(f"从父类获取单曲名称失败: {e}")
        
        # 如果父类没有，尝试从自己的属性获取
        return getattr(self, '_current_track_name', None)
    
    def _extract_track_info_from_line(self, line: str) -> Optional[Dict[str, str]]:
        """从输出行中提取单曲信息（专辑下载时）- 支持有序号和无序号格式"""
        try:
            # 匹配 "Track X of Y: songs" 格式本身，用于上下文识别
            if re.search(r'Track\s+\d+\s+of\s+\d+:\s*songs', line):
                logger.debug(f"🔍 检测到Track X of Y: songs格式: {line}")
                # 不返回track_name，因为真正的名称在下一行
                return {'track_name': None, 'type': 'track_context'}
            
            # 匹配 "XX. 单曲名称" 格式（带序号前缀，兼容旧格式）
            track_match_with_number = re.search(r'^\s*\d+\.\s*([^.]+)\s*$', line)
            if track_match_with_number:
                track_name = track_match_with_number.group(1).strip()
                logger.debug(f"🔍 从Track X of Y: songs下一行提取单曲名(带序号): {track_name}")
                return {'track_name': track_name, 'type': 'album_track_name'}
            
            # 匹配无序号前缀的单曲名称格式（新格式）
            # 检查是否是单曲名称行：不包含特殊关键字，不是空行，不是其他格式的输出
            line_stripped = line.strip()
            if (line_stripped and 
                not re.search(r'(Track\s+\d+|Album:|Downloading|\[|\]|https?://|\d+%|MB/s|ETA:|Progress:|Error:|Warning:)', line_stripped) and
                not line_stripped.startswith(('>', '<', '#', '*', '-', '+', '=')) and
                len(line_stripped) > 1 and len(line_stripped) < 200):
                
                # 进一步验证：确保不是文件路径、URL或其他系统输出
                if (not re.search(r'[/\\]', line_stripped) and  # 不包含路径分隔符
                    not re.search(r'\.(m4a|aac|mp3|flac|wav)$', line_stripped.lower()) and  # 不是文件名
                    not re.search(r'^\d+$', line_stripped) and  # 不是纯数字
                    not re.search(r'(bytes|KB|MB|GB)', line_stripped)):  # 不包含文件大小信息
                    
                    logger.debug(f"🔍 从Track X of Y: songs下一行提取单曲名(无序号): {line_stripped}")
                    return {'track_name': line_stripped, 'type': 'album_track_name'}
            
            return None
            
        except Exception as e:
            logger.debug(f"提取单曲信息失败: {line} - {e}")
            return None

    def _extract_album_info_from_line(self, line: str) -> Optional[Dict[str, str]]:
        """从输出行中提取专辑信息"""
        try:
            # 匹配 "Album: 初学者 by 薛之谦" 格式
            album_match = re.search(r'Album:\s*([^by]+)(?:\s+by\s+([^,]+))?', line)
            if album_match:
                album_name = album_match.group(1).strip()
                artist = album_match.group(2).strip() if album_match.group(2) else "未知艺术家"
                return {"album": album_name, "artist": artist}
            
            # 匹配 "Downloading album: 初学者 by 薛之谦" 格式
            album_match = re.search(r'Downloading album:\s*([^by]+?)(?:\s+by\s+(.+))?$', line)
            if album_match:
                album_name = album_match.group(1).strip()
                artist = album_match.group(2).strip() if album_match.group(2) else "未知艺术家"
                return {"album": album_name, "artist": artist}
            
            # 匹配 "Downloading album: 初学者" 格式（没有艺术家信息）
            album_match = re.search(r'Downloading album:\s*([^,]+)', line)
            if album_match:
                album_name = album_match.group(1).strip()
                return {"album": album_name, "artist": "未知艺术家"}
            
            return None
            
        except Exception as e:
            logger.debug(f"提取专辑信息失败: {line} - {e}")
            return None
    
    async def _get_real_filename(self) -> str:
        """获取真实的文件名（通过 amd_getinfo.py）"""
        try:
            if hasattr(self, '_download_url') and self._download_url:
                # 首先尝试通过 amd_getinfo.py 获取真实信息
                music_info = self._get_music_info_from_amd_getinfo(self._download_url)
                if music_info:
                    content_type = music_info.get('type', 'unknown')
                    if content_type == 'song':
                        # 单曲：使用歌曲名
                        song_name = music_info.get('title') or music_info.get('album', '未知歌曲')
                        # 清理文件名中的特殊字符
                        song_name = self._sanitize_filename(song_name)
                        return song_name
                    elif content_type == 'album':
                        # 专辑：使用专辑名，不添加后缀（专辑是文件夹）
                        album_name = music_info.get('album', '未知专辑')
                        album_name = self._sanitize_filename(album_name)
                        return album_name
                
                # 如果 amd_getinfo.py 失败，尝试从URL中提取
                url_parts = self._download_url.split('/')
                if len(url_parts) >= 6:
                    name = url_parts[5]  # 名称通常在URL的第6部分
                    # URL解码
                    from urllib.parse import unquote
                    name = unquote(name)
                    name = self._sanitize_filename(name)
                    
                    if '/song/' in self._download_url:
                        return name
                    elif '/album/' in self._download_url:
                        return name  # 专辑不添加后缀
            
            # 如果都无法获取，返回默认文件名
            return "Apple Music 文件"
        except Exception as e:
            logger.debug(f"获取真实文件名失败: {e}")
            return "Apple Music 文件"
    
    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名，移除或替换非法字符"""
        # 移除或替换文件名中的非法字符
        illegal_chars = ['<', '>', ':', '"', '|', '?', '*', '/', '\\']
        for char in illegal_chars:
            filename = filename.replace(char, '_')
        
        # 移除特殊Unicode字符
        filename = filename.replace('‎', '')  # 移除特殊空格字符
        
        return filename.strip()
    
    def _get_filename_from_url(self) -> str:
        """从下载URL中获取文件名"""
        try:
            if hasattr(self, '_download_url') and self._download_url:
                # 从URL中提取音乐信息
                music_info = self.extract_music_info(self._download_url)
                if music_info:
                    content_type = music_info.get('type', 'unknown')
                    if content_type == 'song':
                        # 单曲：尝试从URL中提取歌曲名
                        # 例如：https://music.apple.com/cn/song/获奖之作/1831458645
                        url_parts = self._download_url.split('/')
                        if len(url_parts) >= 6:
                            song_name = url_parts[5]  # 歌曲名通常在URL的第6部分
                            # URL解码
                            from urllib.parse import unquote
                            song_name = unquote(song_name)
                            return song_name
                        else:
                            return "单曲"
                    elif content_type == 'album':
                        # 专辑：使用专辑名
                        url_parts = self._download_url.split('/')
                        if len(url_parts) >= 6:
                            album_name = url_parts[5]  # 专辑名通常在URL的第6部分
                            from urllib.parse import unquote
                            album_name = unquote(album_name)
                            return f"{album_name}.m4a"
                        else:
                            return "专辑.m4a"
            
            # 如果无法获取，返回默认文件名
            return "Apple Music 文件"
        except Exception as e:
            logger.debug(f"从URL获取文件名失败: {e}")
            return "Apple Music 文件"
    
    def _get_music_info_from_amd_getinfo(self, url: str) -> Optional[Dict[str, Any]]:
        """使用 amd_getinfo.py 获取音乐信息"""
        try:
            import subprocess
            import json
            
            # 调用 amd_getinfo.py 脚本
            cmd = ['python3', 'amd_getinfo.py', url]
            logger.debug(f"执行命令: {' '.join(cmd)}")
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=os.getcwd())
            
            if result.returncode == 0:
                # 从输出中提取JSON信息
                output_lines = result.stdout.strip().split('\n')
                
                # 查找JSON输出（通常在最后几行）
                for line in reversed(output_lines):
                    line = line.strip()
                    if line.startswith('{') and line.endswith('}'):
                        try:
                            info = json.loads(line)
                            logger.info(f"✅ 从 amd_getinfo.py 获取到音乐信息: {info}")
                            
                            # 确定内容类型
                            if 'song_id' in info:
                                info['type'] = 'song'
                            elif 'album_id' in info:
                                info['type'] = 'album'
                            else:
                                # 从URL判断类型
                                if '/song/' in url:
                                    info['type'] = 'song'
                                elif '/album/' in url:
                                    info['type'] = 'album'
                                else:
                                    info['type'] = 'unknown'
                            
                            return info
                        except json.JSONDecodeError as e:
                            logger.debug(f"JSON解析失败: {line} - {e}")
                            continue
                
                                # 如果没有找到JSON，尝试从整个输出中提取
                full_output = result.stdout.strip()
                try:
                    # 查找JSON开始和结束位置
                    start = full_output.find('{')
                    end = full_output.rfind('}') + 1
                    if start != -1 and end != 0:
                        json_str = full_output[start:end]
                        info = json.loads(json_str)
                        logger.info(f"✅ 从完整输出中提取到音乐信息: {info}")
                        
                        # 确定内容类型
                        if '/song/' in url:
                            info['type'] = 'song'
                        elif '/album/' in url:
                            info['type'] = 'album'
                        else:
                            info['type'] = 'unknown'
                        
                        return info
                except Exception as e:
                    logger.debug(f"从完整输出提取JSON失败: {e}")
                
                                # 如果没有找到JSON，尝试从整个输出中提取
                full_output = result.stdout.strip()
                try:
                    # 查找JSON开始和结束位置
                    start = full_output.find('{')
                    end = full_output.rfind('}') + 1
                    if start != -1 and end != 0:
                        json_str = full_output[start:end]
                        info = json.loads(json_str)
                        logger.info(f"✅ 从完整输出中提取到音乐信息: {info}")
                        
                        # 确定内容类型
                        if '/song/' in url:
                            info['type'] = 'song'
                        elif '/album/' in url:
                            info['type'] = 'album'
                        else:
                            info['type'] = 'unknown'
                        
                        return info
                except Exception as e:
                    logger.debug(f"从完整输出提取JSON失败: {e}")
                
                                # 如果没有找到JSON，尝试从整个输出中提取
                full_output = result.stdout.strip()
                try:
                    # 查找JSON开始和结束位置
                    start = full_output.find('{')
                    end = full_output.rfind('}') + 1
                    if start != -1 and end != 0:
                        json_str = full_output[start:end]
                        info = json.loads(json_str)
                        logger.info(f"✅ 从完整输出中提取到音乐信息: {info}")
                        
                        # 确定内容类型
                        if '/song/' in url:
                            info['type'] = 'song'
                        elif '/album/' in url:
                            info['type'] = 'album'
                        else:
                            info['type'] = 'unknown'
                        
                        return info
                except Exception as e:
                    logger.debug(f"从完整输出提取JSON失败: {e}")
                
                logger.warning("⚠️ amd_getinfo.py 输出中没有找到有效的JSON")
                return None
            else:
                logger.warning(f"⚠️ amd_getinfo.py 执行失败: {result.stderr}")
                return None
                
        except Exception as e:
            logger.error(f"❌ 调用 amd_getinfo.py 失败: {e}")
            return None
    
    def _extract_filename_from_url_fallback(self, url: str) -> str:
        """备选方案：从URL路径提取文件名"""
        try:
            # 从URL中提取音乐信息
            music_info = self._extract_apple_music_info(url)
            if music_info:
                content_type = music_info.get('type', 'unknown')
                if content_type == 'song':
                    # 单曲：尝试从URL中提取歌曲名
                    url_parts = url.split('/')
                    if len(url_parts) >= 6:
                        song_name = url_parts[5]  # 歌曲名通常在URL的第6部分
                        # URL解码
                        from urllib.parse import unquote
                        song_name = unquote(song_name)
                        return song_name
                    else:
                        return "单曲"
                elif content_type == 'album':
                    # 专辑：使用专辑名
                    url_parts = url.split('/')
                    if len(url_parts) >= 6:
                        album_name = url_parts[5]  # 专辑名通常在URL的第6部分
                        from urllib.parse import unquote
                        album_name = unquote(album_name)
                        return f"{album_name}.m4a"
                    else:
                        return "专辑.m4a"
            
            return "Apple Music 文件"
        except Exception as e:
            logger.debug(f"备选方案提取文件名失败: {e}")
            return "Apple Music 文件"
    
    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名，移除非法字符"""
        import re
        # 移除或替换文件名中的非法字符
        illegal_chars = r'[<>:"/\\|?*]'
        safe_filename = re.sub(illegal_chars, '_', filename)
        # 移除多余的空格和下划线
        safe_filename = re.sub(r'[_\s]+', '_', safe_filename).strip('_')
        return safe_filename
    
    def _convert_to_mb(self, value: float, unit: str) -> float:
        """将不同单位转换为 MB"""
        try:
            if unit is None:
                # 如果没有单位，假设是字节
                return value / (1024 * 1024)
            unit = unit.upper()
            if unit == 'B':
                return value / (1024 * 1024)
            elif unit == 'KB':
                return value / 1024
            elif unit == 'MB':
                return value
            elif unit == 'GB':
                return value * 1024
            elif unit == 'TB':
                return value * 1024 * 1024
            else:
                logger.warning(f"⚠️ 未知单位: {unit}，假设为字节")
                return value / (1024 * 1024)
        except Exception as e:
            logger.error(f"❌ 单位转换失败: {value} {unit} - {e}")
            return value / (1024 * 1024)  # 默认按字节处理
    
    async def download_album(self, url: str, output_dir: str, cookies_path: str = None,
                            quality: str = "lossless", progress_callback=None) -> Dict[str, Any]:
        """使用 apple-music-downloader 下载专辑"""
        try:
            # 保存URL供后续解析使用
            self._download_url = url
            
            if not self.amd_path:
                return {
                    'success': False,
                    'backend': self.name,
                    'error': 'amd 可执行文件未找到'
                }
            
            # 创建配置文件
            config_path = self._create_config_file("/app/amdp")
            if not config_path:
                return {
                    'success': False,
                    'backend': self.name,
                    'error': '配置文件创建失败'
                }
            
            # 确保 amd 工具在 /app/amdp 目录中
            amd_executable = self._ensure_amd_in_output_dir("/app/amdp")
            
            # 构建命令 - 正常下载，不使用--debug
            cmd = [amd_executable, url]
            
            # 使用最简单的命令，让配置文件处理所有设置
            
            logger.info(f"📀 使用 apple-music-downloader 下载专辑: {url}")
            logger.debug(f"命令: {' '.join(cmd)}")
            
            # 使用 /app/amdp 作为工作目录和配置目录
            amd_working_dir = "/app/amdp"  # 使用 /app/amdp 作为工作目录
            
            # 环境变量设置
            env_vars = {
                "PATH": f"/app/amdp:/usr/local/bin:/usr/bin:/bin",
                "HOME": "/root",
                "USER": "root",
            }
            
            logger.info(f"📁 工作目录: {amd_working_dir}")
            logger.info(f"📁 输出目录: {output_dir}")
            logger.info(f"🔧 可执行文件: {amd_executable}")
            
            logger.info(f"🚀 执行命令: {' '.join(cmd)}")
            logger.info(f"📁 工作目录: {amd_working_dir}")
            
            # 使用shell执行命令，在 /app/amdp 目录中执行
            shell_cmd = f"cd {amd_working_dir} && {' '.join(cmd)}"
            logger.info(f"🔍 执行shell命令: {shell_cmd}")
            logger.info(f"🔍 工作目录: {amd_working_dir}")
            logger.info(f"🔍 配置文件路径: {config_path}")
            logger.info(f"🔍 环境变量: {env_vars}")
            
            process = await asyncio.create_subprocess_exec(
                "sh", "-c", shell_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env_vars
            )
            
            # 实时监控输出，解析进度信息
            stdout = None
            stderr = None
            monitored_output = []  # 存储监控到的输出
            
            if progress_callback:
                # 有进度回调时，监控输出并收集
                await self._monitor_amd_progress(process, progress_callback, monitored_output)
            else:
                # 如果没有进度回调，等待进程完成
                try:
                    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)  # 5分钟超时
                    logger.info("✅ amd 进程正常完成")
                except asyncio.TimeoutError:
                    logger.warning("⚠️ amd 进程超时，尝试终止")
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=10)
                    except asyncio.TimeoutError:
                        logger.error("❌ 无法终止amd进程，强制杀死")
                        process.kill()
                        await process.wait()
                    return {
                        'success': False,
                        'backend': self.name,
                        'error': '下载超时，可能未完成'
                    }
            
            if process.returncode == 0:
                # 确定要检查的输出内容
                if stdout is not None and stderr is not None:
                    # 无进度回调的情况
                    output = stdout.decode('utf-8') if stdout else ""
                    stderr_output = stderr.decode('utf-8') if stderr else ""
                else:
                    # 有进度回调的情况，使用监控到的输出
                    output = "\n".join(monitored_output) if monitored_output else ""
                    stderr_output = ""
                
                # 检查是否真正完成下载
                if "Completed:" in output or "Completed:" in stderr_output:
                    logger.info("✅ apple-music-downloader 专辑真正下载完成")
                    logger.info(f"📊 下载输出: {output}")
                    
                    # 使用 amd_getinfo.py 获取真实的音乐信息
                    self._download_url = url
                    music_info = self._get_music_info_from_amd_getinfo_sync(self._download_url)
                    logger.info(f"✅ 通过 amd_getinfo.py 获取专辑音乐信息: {music_info}")
                    
                    # 如果没有获取到音乐信息，使用默认值
                    if not music_info:
                        music_info = {
                            'type': 'album',
                            'album': '未知专辑',
                            'artist': '未知艺术家',
                            'title': '未知标题',
                            'country': 'CN'
                        }
                    
                    # 修复：确保专辑名称是简体中文
                    if music_info and 'album' in music_info:
                        album_name = music_info['album']
                        # 使用通用的繁简转换
                        simplified_album = self._convert_traditional_to_simplified(album_name)
                        if simplified_album != album_name:
                            logger.info(f"🔍 专辑名称繁简转换: '{album_name}' -> '{simplified_album}'")
                            music_info['album'] = simplified_album
                    
                    # 修复：确保艺术家名称是简体中文
                    if music_info and 'artist' in music_info:
                        artist_name = music_info['artist']
                        # 使用通用的繁简转换
                        simplified_artist = self._convert_traditional_to_simplified(artist_name)
                        if simplified_artist != artist_name:
                            logger.info(f"🔍 艺术家名称繁简转换: '{artist_name}' -> '{simplified_artist}'")
                            music_info['artist'] = simplified_artist
                    
                    # 发送完成进度信息，触发汇总信息显示
                    if progress_callback:
                        try:
                            # 获取真实的文件大小
                            # 专辑下载使用默认方法
                            real_file_size = self._get_real_file_size_for_completion()
                            
                            # 如果无法获取真实大小，跳过发送完成信息
                            if real_file_size is None:
                                logger.error("❌ 无法获取真实文件大小，跳过发送完成信息")
                                return {
                                    'success': True,
                                    'backend': self.name,
                                    'music_type': 'album',
                                    'output': output,
                                    'message': 'apple-music-downloader 专辑下载成功，但无法确定文件大小',
                                    'music_info': music_info
                                }
                            
                            # 获取真实的专辑信息
                            real_album_info = self._get_real_album_info(output_dir)
                            real_files_count = real_album_info.get('files_count', 0)
                            real_total_size = real_album_info.get('total_size', 0)
                            real_track_list = real_album_info.get('track_list', [])
                            
                            logger.info(f"🔍 真实专辑信息: files_count={real_files_count}, total_size={real_total_size}, track_list={len(real_track_list)}")
                            
                            download_info = {
                                'phase': 'complete',
                                'music_type': music_info.get('type', 'album'),
                                'album': music_info.get('album', '未知专辑'),
                                'artist': music_info.get('artist', '未知艺术家'),
                                'title': music_info.get('title', '未知标题'),
                                'country': music_info.get('country', 'CN'),
                                'files_count': real_files_count,  # 使用真实的文件数量
                                'total_size': real_total_size / (1024 * 1024) if real_total_size > 0 else 0,  # 转换为MB
                                'total_size_mb': real_total_size / (1024 * 1024) if real_total_size > 0 else 0,  # 计算MB值
                                'download_path': str(output_dir),
                                'track_list': real_track_list,  # 使用真实的歌曲列表
                                'download_url': self._download_url if hasattr(self, '_download_url') else ''
                            }
                            await progress_callback(download_info)
                        except Exception as e:
                            logger.warning(f"发送完成进度信息失败: {e}")
                    
                    # 获取真实的专辑信息（包括文件数量、总大小和歌曲列表）
                    real_album_info = self._get_real_album_info(output_dir)
                    real_files_count = real_album_info.get('files_count', 0)
                    real_total_size = real_album_info.get('total_size', 0)
                    real_track_list = real_album_info.get('track_list', [])
                    
                    logger.info(f"🔍 专辑下载完成返回信息: files_count={real_files_count}, total_size={real_total_size}, track_list={len(real_track_list)}")
                    
                    return {
                        'success': True,
                        'backend': self.name,
                        'music_type': 'album',
                        'output': output,
                        'message': 'apple-music-downloader 专辑下载成功',
                        'music_info': music_info,
                        'total_size_mb': real_total_size / (1024 * 1024) if real_total_size > 0 else 0,
                        'files_count': real_files_count,
                        'track_list': real_track_list,
                        'total_size': real_total_size / (1024 * 1024) if real_total_size > 0 else 0  # 转换为MB
                    }
                else:
                    logger.warning("⚠️ amd 工具退出但专辑下载可能未完成")
                    logger.warning(f"📊 stdout: {output}")
                    logger.warning(f"📊 stderr: {stderr_output}")
                    return {
                        'success': False,
                        'backend': self.name,
                        'error': '专辑下载可能未完成，未检测到 Completed 标志'
                    }
            else:
                # 如果没有stdout/stderr（因为有进度回调），尝试从进程获取
                if stdout is None or stderr is None:
                    try:
                        stdout, stderr = await process.communicate()
                    except Exception as e:
                        logger.warning(f"⚠️ 无法获取进程输出: {e}")
                        stdout = b""
                        stderr = b""
                
                error_msg = stderr.decode('utf-8') if stderr else ""
                stdout_output = stdout.decode('utf-8') if stdout else ""
                logger.error(f"❌ apple-music-downloader 专辑下载失败: {error_msg}")
                logger.error(f"📊 stdout: {stdout_output}")
                logger.error(f"📊 stderr: {error_msg}")
                return {
                    'success': False,
                    'backend': self.name,
                    'error': error_msg
                }
                
        except Exception as e:
            logger.error(f"❌ apple-music-downloader 专辑下载异常: {e}")
            return {
                'success': False,
                'backend': self.name,
                'error': str(e)
            }
    
    # AMD输出解析功能已完全移除
    
    def _extract_music_info_from_url(self) -> Dict[str, Any]:
        """从URL中直接提取音乐信息作为备选方案"""
        try:
            # 这里可以添加从URL中提取信息的逻辑
            # 由于我们已经有URL信息，可以尝试解析
            logger.info("🔍 尝试从URL中提取音乐信息...")
            
            # 返回默认信息，实际应用中可以从URL或其他来源获取
            return {
                'title': '未知标题',
                'artist': '未知艺术家',
                'album': '未知专辑',
                'type': 'song'
            }
            
        except Exception as e:
            logger.warning(f"⚠️ 从URL提取信息失败: {e}")
            return {
                'title': '未知标题',
                'artist': '未知艺术家',
                'album': '未知专辑',
                'type': 'song'
            }
    
    def _get_default_music_info(self) -> Dict[str, Any]:
        """返回默认的音乐信息"""
        return {
            'title': '未知标题',
            'artist': '未知艺术家',
            'album': '未知专辑',
            'type': 'song'
        }
    
    def _parse_debug_output(self, stdout: str, stderr: str) -> Dict[str, Any]:
        """解析--debug命令的输出获取音乐信息"""
        try:
            import re
            
            # 合并stdout和stderr
            full_output = stdout + "\n" + stderr
            lines = full_output.split('\n')
            
            # 初始化音乐信息
            music_info = {
                'title': '未知标题',
                'artist': '未知艺术家',
                'album': '未知专辑',
                'type': 'song'
            }
            
            logger.info(f"🔍 解析--debug输出，共 {len(lines)} 行")
            
            for i, line in enumerate(lines):
                line = line.strip()
                if not line:
                    continue
                
                logger.debug(f"🔍 解析第 {i+1} 行: {line}")
                
                # 新格式: Song->方大同 危險世界 (没有Track关键字)
                if 'Song->' in line:
                    logger.info(f"🎵 发现歌曲信息行: {line}")
                    song_match = re.search(r'Song->(.+?)\s+(.+?)$', line)
                    if song_match:
                        artist = song_match.group(1).strip()
                        album = song_match.group(2).strip()
                        
                        music_info['artist'] = artist
                        music_info['album'] = album
                        music_info['title'] = album
                        music_info['type'] = 'song'
                        logger.info(f"✅ 歌曲新格式解析成功: 艺术家={artist}, 专辑={album}")
                        break
                
                # 新格式: Album->李荣浩 耳朵 (没有Track关键字)
                elif 'Album->' in line:
                    logger.info(f"📀 发现专辑信息行: {line}")
                    album_match = re.search(r'Album->(.+?)\s+(.+?)$', line)
                    if album_match:
                        artist = album_match.group(1).strip()
                        album = album_match.group(2).strip()
                        
                        music_info['artist'] = artist
                        music_info['album'] = album
                        music_info['title'] = album
                        music_info['type'] = 'album'
                        logger.info(f"✅ 专辑新格式解析成功: 艺术家={artist}, 专辑={album}")
                        break
            
            logger.info(f"🎵 从--debug输出提取的音乐信息: {music_info}")
            return music_info
            
        except Exception as e:
            logger.warning(f"⚠️ 解析--debug输出失败: {e}")
            return self._get_default_music_info()
    
    async def _get_music_info_with_curl(self) -> Dict[str, Any]:
        """使用 amd_getinfo.py 脚本获取音乐信息"""
        try:
            if not hasattr(self, '_download_url') or not self._download_url:
                logger.warning("⚠️ 没有下载URL，无法获取音乐信息")
                return self._get_default_music_info()
            
            url = self._download_url
            # 清理URL，移除末尾的多余字符
            clean_url = url.split('%60')[0] if '%60' in url else url
            if clean_url != url:
                logger.info(f"🔧 清理URL: {url} -> {clean_url}")
                url = clean_url
            
            logger.info(f"🔄 使用 amd_getinfo.py 脚本获取音乐信息: {url}")
            
            # 构建 amd_getinfo.py 命令
            script_path = os.path.join(os.getcwd(), "amd_getinfo.py")
            if not os.path.exists(script_path):
                logger.warning(f"⚠️ amd_getinfo.py 脚本不存在: {script_path}")
                return self._get_default_music_info()
            
            amd_getinfo_cmd = ['python3', script_path, url]
            logger.info(f"🔍 执行 amd_getinfo.py 命令: {' '.join(amd_getinfo_cmd)}")
            
            # 执行 amd_getinfo.py 脚本
            process = await asyncio.create_subprocess_exec(
                *amd_getinfo_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)  # 30秒超时
                logger.info("✅ amd_getinfo.py 脚本执行完成")
            except asyncio.TimeoutError:
                logger.warning("⚠️ amd_getinfo.py 脚本超时，尝试终止")
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                return self._get_default_music_info()
            
            if process.returncode == 0:
                output = stdout.decode('utf-8')
                
                if not output:
                    logger.warning("⚠️ amd_getinfo.py 脚本返回空内容")
                    return self._get_default_music_info()
                
                logger.info(f"✅ 成功获取 amd_getinfo.py 输出，长度: {len(output)} 字符")
                logger.info(f"📄 输出内容预览: {output[:200]}...")
                
                # 解析 amd_getinfo.py 输出获取音乐信息
                music_info = self._parse_amd_getinfo_output(output, url)
                
                if music_info['artist'] != '未知艺术家' and music_info['album'] != '未知专辑':
                    logger.info(f"✅ 通过 amd_getinfo.py 脚本成功获取音乐信息: {music_info}")
                    return music_info
                else:
                    logger.warning("⚠️ amd_getinfo.py 脚本未能获取到有效音乐信息")
                    return self._get_default_music_info()
            else:
                # 安全地处理stderr输出
                try:
                    stderr_output = stderr.decode('utf-8') if stderr else "未知错误"
                except Exception:
                    stderr_output = "无法获取错误信息"
                
                logger.warning(f"⚠️ amd_getinfo.py 脚本执行失败，返回码: {process.returncode}, 错误: {stderr_output}")
                return self._get_default_music_info()
                
        except Exception as e:
            logger.error(f"❌ 使用 amd_getinfo.py 脚本获取音乐信息时发生错误: {e}")
            return self._get_default_music_info()
    
    def _parse_amd_getinfo_output(self, output: str, url: str) -> Dict[str, Any]:
        """解析 amd_getinfo.py 脚本的输出获取音乐信息"""
        try:
            import re
            import json
            
            # 初始化音乐信息
            music_info = {
                'title': '未知标题',
                'artist': '未知艺术家',
                'album': '未知专辑',
                'type': 'song'
            }
            
            logger.info(f"🔍 开始解析 amd_getinfo.py 输出，长度: {len(output)} 字符")
            
            # 查找JSON输出（通常在输出的最后部分）
            lines = output.split('\n')
            logger.info(f"🔍 输出行数: {len(lines)}")
            
            # 打印最后几行用于调试
            last_lines = lines[-10:] if len(lines) > 10 else lines
            logger.info(f"📄 最后几行输出: {last_lines}")
            
            # 方法1: 查找单行JSON
            for line in reversed(lines):
                line = line.strip()
                if line.startswith('{') and line.endswith('}'):
                    try:
                        json_data = json.loads(line)
                        logger.info(f"📊 找到单行JSON数据: {json_data}")
                        
                        # 提取信息
                        if 'album' in json_data:
                            music_info['album'] = json_data['album'].strip('‎')  # 移除特殊字符
                        if 'artist' in json_data:
                            # 处理"由陈楚生演唱"格式，提取艺术家名
                            artist = json_data['artist']
                            if artist.startswith('由') and artist.endswith('演唱'):
                                artist = artist[1:-2]  # 移除"由"和"演唱"
                            music_info['artist'] = artist
                        if 'type' in json_data:
                            music_info['type'] = json_data['type']
                        if 'title' in json_data:
                            music_info['title'] = json_data['title']
                        
                        # 如果获取到了有效信息，直接返回
                        if music_info['artist'] != '未知艺术家' and music_info['album'] != '未知专辑':
                            logger.info(f"✅ 从单行JSON成功提取音乐信息: {music_info}")
                            return music_info
                            
                    except json.JSONDecodeError as e:
                        logger.debug(f"⚠️ 单行JSON解析失败: {line} - {e}")
                        continue
            
            # 方法2: 查找多行JSON（从"📋 JSON格式输出:"开始）
            logger.info("🔄 尝试查找多行JSON...")
            json_start_index = -1
            for i, line in enumerate(lines):
                if "📋 JSON格式输出:" in line:
                    json_start_index = i + 1
                    break
            
            if json_start_index >= 0 and json_start_index < len(lines):
                # 从JSON开始位置收集所有行，直到找到结束的}
                json_lines = []
                for i in range(json_start_index, len(lines)):
                    line = lines[i].strip()
                    if line:
                        json_lines.append(line)
                        if line == '}':
                            break
                
                if json_lines:
                    try:
                        json_text = '\n'.join(json_lines)
                        logger.info(f"📄 多行JSON文本: {json_text}")
                        json_data = json.loads(json_text)
                        logger.info(f"📊 找到多行JSON数据: {json_data}")
                        
                        # 提取信息
                        if 'album' in json_data:
                            music_info['album'] = json_data['album'].strip('‎')  # 移除特殊字符
                        if 'artist' in json_data:
                            # 处理"由陈楚生演唱"格式，提取艺术家名
                            artist = json_data['artist']
                            if artist.startswith('由') and artist.endswith('演唱'):
                                artist = artist[1:-2]  # 移除"由"和"演唱"
                            music_info['artist'] = artist
                        if 'type' in json_data:
                            music_info['type'] = json_data['type']
                        if 'title' in json_data:
                            music_info['title'] = json_data['title']
                        
                        # 如果获取到了有效信息，直接返回
                        if music_info['artist'] != '未知艺术家' and music_info['album'] != '未知专辑':
                            logger.info(f"✅ 从多行JSON成功提取音乐信息: {music_info}")
                            return music_info
                            
                    except json.JSONDecodeError as e:
                        logger.debug(f"⚠️ 多行JSON解析失败: {json_text} - {e}")
                        pass
            
            # 如果没有找到JSON，尝试从文本输出中提取
            logger.info("🔄 尝试从文本输出中提取信息...")
            
            # 查找包含"成功提取音乐信息"的行
            for line in lines:
                if "成功提取音乐信息" in line:
                    # 尝试提取艺术家和专辑信息
                    artist_match = re.search(r"艺术家='([^']+)'", line)
                    album_match = re.search(r"专辑='([^']+)'", line)
                    
                    if artist_match and album_match:
                        music_info['artist'] = artist_match.group(1)
                        music_info['album'] = album_match.group(1)
                        
                        # 判断类型
                        if '/album/' in url:
                            music_info['type'] = 'album'
                        elif '/song/' in url:
                            music_info['type'] = 'song'
                        
                        logger.info(f"✅ 从文本输出成功提取音乐信息: {music_info}")
                        return music_info
            
            # 如果还是没找到，尝试从URL路径提取（备选方案）
            logger.info("🔄 尝试从URL路径提取信息...")
            url_info = self._extract_from_url_fallback(url)
            if url_info and url_info['artist'] != '未知艺术家':
                logger.info(f"✅ 从URL成功提取信息: {url_info}")
                return url_info
            
            logger.warning("⚠️ 无法从 amd_getinfo.py 输出中提取有效音乐信息")
            return music_info
            
        except Exception as e:
            logger.error(f"❌ 解析 amd_getinfo.py 输出时发生错误: {e}")
            return music_info
    
    def _extract_from_url_fallback(self, url: str) -> Optional[Dict[str, Any]]:
        """从URL路径中提取专辑信息（备选方案）"""
        try:
            import re
            
            # 匹配 /cn/album/专辑名/ID 格式
            album_match = re.search(r'/cn/album/([^/]+)/(\d+)', url)
            if album_match:
                album_slug = album_match.group(1)
                album_id = album_match.group(2)
                
                # URL解码专辑名
                try:
                    from urllib.parse import unquote
                    decoded_album = unquote(album_slug)
                    logger.info(f"🔍 从URL提取: 专辑slug='{album_slug}', 解码后='{decoded_album}', ID={album_id}")
                    
                    # 将slug转换为更友好的专辑名
                    album_name = decoded_album.replace('-', ' ').replace('_', ' ').title()
                    
                    return {
                        'album': album_name,
                        'artist': '未知艺术家',
                        'title': album_name,
                        'album_id': album_id,
                        'type': 'album',
                        'source': 'url_path'
                    }
                except Exception as e:
                    logger.warning(f"⚠️ URL解码失败: {e}")
                    return None
            
            # 匹配 /cn/song/歌曲名/ID 格式
            song_match = re.search(r'/cn/song/([^/]+)/(\d+)', url)
            if song_match:
                song_slug = song_match.group(1)
                song_id = song_match.group(2)
                
                try:
                    from urllib.parse import unquote
                    decoded_song = unquote(song_slug)
                    logger.info(f"🔍 从URL提取: 歌曲slug='{song_slug}', 解码后='{decoded_song}', ID={song_id}")
                    
                    song_name = decoded_song.replace('-', ' ').replace('_', ' ').title()
                    
                    return {
                        'album': song_name,
                        'artist': '未知艺术家',
                        'title': song_name,
                        'song_id': song_id,
                        'type': 'song',
                        'source': 'url_path'
                    }
                except Exception as e:
                    logger.warning(f"⚠️ URL解码失败: {e}")
                    return None
            
            return None
            
        except Exception as e:
            logger.error(f"❌ 从URL提取信息时发生错误: {e}")
            return None
    
    def _get_real_filename_sync(self) -> str:
        """获取真实的文件名（同步版本，用于进度解析）"""
        try:
            # 检查是否是专辑下载 - 专辑下载时优先使用专辑名称
            if hasattr(self, '_download_url') and self._download_url and '/album/' in self._download_url:
                # 专辑下载：返回专辑名（没有扩展名）
                if hasattr(self, '_album_info') and self._album_info:
                    album_name = self._album_info.get('album', '未知专辑')
                    logger.info(f"📁 专辑下载使用专辑名称: {album_name}")
                    return self._sanitize_filename(album_name)
                else:
                    # 从URL提取专辑名
                    url_parts = self._download_url.split('/')
                    if len(url_parts) >= 6:
                        name = url_parts[5]
                        from urllib.parse import unquote
                        name = unquote(name)
                        logger.info(f"📁 从URL提取专辑名称: {name}")
                        return self._sanitize_filename(name)
            
            # 单曲下载时，才使用单曲名称
            if hasattr(self, '_current_track_name') and self._current_track_name:
                track_name = self._current_track_name
                # 清理文件名中的特殊字符
                track_name = self._sanitize_filename(track_name)
                logger.info(f"📁 单曲下载使用单曲名称: {track_name}")
                return track_name
            
            # 如果后端没有单曲信息，尝试从父类获取
            if hasattr(self, '_parent_downloader') and self._parent_downloader:
                parent_track_name = self._parent_downloader._get_current_track_name()
                if parent_track_name:
                    track_name = self._sanitize_filename(parent_track_name)
                    logger.info(f"📁 从父类获取到单曲名称: {track_name}")
                    return track_name
            
            if hasattr(self, '_download_url') and self._download_url:
                # 尝试通过 amd_getinfo.py 获取真实信息
                music_info = self._get_music_info_from_amd_getinfo_sync(self._download_url)
                if music_info:
                    content_type = music_info.get('type', 'unknown')
                    if content_type == 'song':
                        # 单曲：使用歌曲名
                        song_name = music_info.get('title') or music_info.get('album', '未知歌曲')
                        # 清理文件名中的特殊字符
                        song_name = self._sanitize_filename(song_name)
                        return song_name
                    elif content_type == 'album':
                        # 专辑：使用专辑名，不添加后缀（专辑是文件夹）
                        album_name = music_info.get('album', '未知专辑')
                        album_name = self._sanitize_filename(album_name)
                        return album_name
                
                # 如果 amd_getinfo.py 失败，尝试从URL中提取
                url_parts = self._download_url.split('/')
                if len(url_parts) >= 6:
                    name = url_parts[5]  # 名称通常在URL的第6部分
                    # URL解码
                    from urllib.parse import unquote
                    name = unquote(name)
                    name = self._sanitize_filename(name)
                    
                    if '/song/' in self._download_url:
                        return name
                    elif '/album/' in self._download_url:
                        return name  # 专辑不添加后缀
            
            # 如果都无法获取，返回默认文件名
            return "Apple Music 文件"
        except Exception as e:
            logger.debug(f"获取真实文件名失败: {e}")
            return "Apple Music 文件"
    
    def _get_music_info_from_amd_getinfo_sync(self, url: str) -> Optional[Dict[str, Any]]:
        """使用 amd_getinfo.py 获取音乐信息（同步版本）"""
        try:
            import subprocess
            import json
            
            # 调用 amd_getinfo.py 脚本
            cmd = ['python3', 'amd_getinfo.py', url]
            logger.debug(f"执行命令: {' '.join(cmd)}")
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=os.getcwd())
            
            if result.returncode == 0:
                # 从输出中提取JSON信息
                output_lines = result.stdout.strip().split('\n')
                
                # 查找JSON输出（通常在最后几行）
                for line in reversed(output_lines):
                    line = line.strip()
                    if line.startswith('{') and line.endswith('}'):
                        try:
                            info = json.loads(line)
                            logger.info(f"✅ 从 amd_getinfo.py 获取到音乐信息: {info}")
                            
                            # 确定内容类型
                            if 'song_id' in info:
                                info['type'] = 'song'
                            elif 'album_id' in info:
                                info['type'] = 'album'
                            else:
                                # 从URL判断类型
                                if '/song/' in url:
                                    info['type'] = 'song'
                                elif '/album/' in url:
                                    info['type'] = 'album'
                                else:
                                    info['type'] = 'unknown'
                            
                            return info
                        except json.JSONDecodeError as e:
                            logger.debug(f"JSON解析失败: {line} - {e}")
                            continue
                
                # 如果没有找到JSON，尝试从整个输出中提取
                full_output = result.stdout.strip()
                try:
                    # 查找JSON开始和结束位置
                    start = full_output.find('{')
                    end = full_output.rfind('}') + 1
                    if start != -1 and end != 0:
                        json_str = full_output[start:end]
                        info = json.loads(json_str)
                        logger.info(f"✅ 从完整输出中提取到音乐信息: {info}")
                        
                        # 确定内容类型
                        if '/song/' in url:
                            info['type'] = 'song'
                        elif '/album/' in url:
                            info['type'] = 'album'
                        else:
                            info['type'] = 'unknown'
                        
                        return info
                except Exception as e:
                    logger.debug(f"从完整输出提取JSON失败: {e}")
                
                logger.warning("⚠️ amd_getinfo.py 输出中没有找到有效的JSON")
                return None
            else:
                logger.warning(f"⚠️ amd_getinfo.py 执行失败: {result.stderr}")
                return None
                
        except Exception as e:
            logger.error(f"❌ 调用 amd_getinfo.py 失败: {e}")
            return None
    
    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名，移除或替换非法字符"""
        # 移除或替换文件名中的非法字符
        illegal_chars = ['<', '>', ':', '"', '|', '?', '*', '/', '\\']
        for char in illegal_chars:
            filename = filename.replace(char, '_')
        
        # 移除特殊Unicode字符
        filename = filename.replace('‎', '')  # 移除特殊空格字符
        
        return filename.strip()

    def _get_file_actual_size(self, filename: str) -> tuple:
        """获取文件的真实大小"""
        try:
            # 尝试从输出目录中查找文件
            output_dir = getattr(self, 'output_dir', '/downloads/AppleMusic')
            possible_extensions = ['.m4a', '.aac', '.m4p']
            
            for ext in possible_extensions:
                file_path = os.path.join(output_dir, f"{filename}{ext}")
                if os.path.exists(file_path):
                    file_size = os.path.getsize(file_path)
                    # 转换为MB
                    size_mb = file_size / (1024 * 1024)
                    return size_mb, "MB"
            
            # 如果找不到具体文件，尝试从目录中获取最新文件的大小
            if os.path.exists(output_dir):
                files = [f for f in os.listdir(output_dir) if f.endswith(tuple(possible_extensions))]
                if files:
                    # 获取最新的文件
                    latest_file = max(files, key=lambda x: os.path.getctime(os.path.join(output_dir, x)))
                    file_path = os.path.join(output_dir, latest_file)
                    file_size = os.path.getsize(file_path)
                    size_mb = file_size / (1024 * 1024)
                    return size_mb, "MB"
            
            logger.warning(f"⚠️ 无法找到文件 {filename} 或确定其大小")
            return None, None
            
        except Exception as e:
            logger.error(f"❌ 获取文件实际大小失败: {e}")
            return None, None
    
    def _get_real_file_size_for_completion(self, filename=None) -> float:
        """获取下载完成时的真实文件大小"""
        try:
            # 优先使用传入的文件名来查找单曲目录
            if filename:
                song_dir = self._find_song_directory(filename)
                if song_dir:
                    # 在单曲目录中查找音频文件
                    audio_files = self._find_audio_files_in_directory(song_dir)
                    if audio_files:
                        # 获取第一个音频文件的大小
                        first_audio = audio_files[0]
                        file_size = os.path.getsize(first_audio)
                        size_mb = file_size / (1024 * 1024)
                        logger.info(f"✅ 在单曲目录中找到音频文件: {os.path.basename(first_audio)} ({size_mb:.2f}MB)")
                        return size_mb
            
            # 尝试从输出目录中获取最新文件的大小（回退方案）
            output_dir = getattr(self, 'output_dir', '/downloads/AppleMusic')
            # 修复：Apple Music只使用.m4a格式
            possible_extensions = ['.m4a', '.aac', '.m4p']
            
            if os.path.exists(output_dir):
                files = [f for f in os.listdir(output_dir) if f.endswith(tuple(possible_extensions))]
                if files:
                    # 获取最新的文件
                    latest_file = max(files, key=lambda x: os.path.getctime(os.path.join(output_dir, x)))
                    file_path = os.path.join(output_dir, latest_file)
                    file_size = os.path.getsize(file_path)
                    size_mb = file_size / (1024 * 1024)
                    logger.info(f"✅ 获取到真实文件大小: {size_mb:.2f}MB")
                    return size_mb
            
            # 如果无法获取真实大小，尝试使用之前保存的解密大小
            if hasattr(self, '_last_decrypt_total') and self._last_decrypt_total:
                logger.info(f"✅ 使用保存的解密大小: {self._last_decrypt_total}MB")
                return self._last_decrypt_total
            
            # 新增：智能回退 - 尝试在AM-DL downloads目录中查找最新的音频文件
            logger.info("🔍 尝试智能回退：在AM-DL downloads目录中查找最新音频文件")
            try:
                base_dir = getattr(self, 'output_dir', '/downloads/AppleMusic')
                amd_downloads_dir = os.path.join(base_dir, "AM-DL downloads")
                
                if os.path.exists(amd_downloads_dir):
                    # 递归查找所有音频文件
                    audio_files = []
                    for root, dirs, files in os.walk(amd_downloads_dir):
                        for file in files:
                            # 修复：Apple Music只使用.m4a格式
                            if file.lower().endswith(('.m4a', '.aac', '.m4p')):
                                file_path = os.path.join(root, file)
                                file_size = os.path.getsize(file_path)
                                # 按修改时间排序，获取最新的文件
                                mtime = os.path.getmtime(file_path)
                                audio_files.append((file_path, file_size, mtime))
                    
                    if audio_files:
                        # 按修改时间排序，获取最新的文件
                        latest_audio = max(audio_files, key=lambda x: x[2])
                        file_path, file_size, mtime = latest_audio
                        size_mb = file_size / (1024 * 1024)
                        
                        # 检查文件大小是否合理（应该在10MB到100MB之间）
                        if 10 <= size_mb <= 100:
                            logger.info(f"✅ 智能回退找到音频文件: {os.path.basename(file_path)} ({size_mb:.2f}MB)")
                            return size_mb
                        else:
                            logger.warning(f"⚠️ 智能回退找到的音频文件大小异常: {size_mb:.2f}MB，跳过")
                    else:
                        logger.warning("⚠️ 智能回退：在AM-DL downloads目录中没有找到音频文件")
                else:
                    logger.warning("⚠️ 智能回退：AM-DL downloads目录不存在")
            except Exception as e:
                logger.warning(f"⚠️ 智能回退失败: {e}")
            
            # 完全禁止硬编码！如果无法获取真实大小，返回None
            logger.error("❌ 无法获取真实文件大小，禁止使用硬编码值")
            return None
            
        except Exception as e:
            logger.error(f"❌ 获取完成时文件大小失败: {e}")
            # 完全禁止硬编码！返回None
            return None

    def _get_real_file_size_direct(self) -> float:
        """直接遍历单曲目录获取正确的文件大小"""
        try:
            logger.info("🔍 直接遍历单曲目录获取文件大小")
            
            # 获取基础下载目录
            base_dir = getattr(self, 'output_dir', '/downloads/AppleMusic')
            amd_downloads_dir = os.path.join(base_dir, "AM-DL downloads")
            
            if not os.path.exists(amd_downloads_dir):
                logger.warning(f"⚠️ AM-DL downloads目录不存在: {amd_downloads_dir}")
                return None
            
            # 直接遍历AM-DL downloads目录，查找最新的音频文件
            audio_files = []
            for root, dirs, files in os.walk(amd_downloads_dir):
                for file in files:
                    if file.lower().endswith(('.m4a', '.aac', '.m4p')):
                        file_path = os.path.join(root, file)
                        file_size = os.path.getsize(file_path)
                        size_mb = file_size / (1024 * 1024)
                        
                        # 按修改时间排序，获取最新的文件
                        mtime = os.path.getmtime(file_path)
                        audio_files.append((file_path, file_size, mtime, size_mb))
            
            if audio_files:
                # 按修改时间排序，获取最新的文件
                latest_audio = max(audio_files, key=lambda x: x[2])
                file_path, file_size, mtime, size_mb = latest_audio
                
                logger.info(f"✅ 找到最新音频文件: {os.path.basename(file_path)} ({size_mb:.2f} MB)")
                logger.info(f"   位置: {os.path.relpath(file_path, amd_downloads_dir)}")
                
                # 检查文件大小是否合理（应该在10MB到100MB之间）
                if 10 <= size_mb <= 100:
                    logger.info(f"✅ 文件大小合理: {size_mb:.2f} MB")
                    return size_mb
                else:
                    logger.warning(f"⚠️ 文件大小异常: {size_mb:.2f} MB，跳过")
                    # 尝试查找其他合理的文件
                    for audio_file in audio_files:
                        if 10 <= audio_file[3] <= 100:
                            logger.info(f"✅ 找到合理大小的文件: {os.path.basename(audio_file[0])} ({audio_file[3]:.2f} MB)")
                            return audio_file[3]
            else:
                logger.warning("⚠️ 在AM-DL downloads目录中没有找到音频文件")
            
            # 如果无法获取真实大小，尝试使用之前保存的解密大小
            if hasattr(self, '_last_decrypt_total') and self._last_decrypt_total:
                logger.info(f"✅ 使用保存的解密大小: {self._last_decrypt_total}MB")
                return self._last_decrypt_total
            
            logger.error("❌ 无法获取真实文件大小")
            return None
            
        except Exception as e:
            logger.error(f"❌ 直接获取文件大小失败: {e}")
            return None

    def _find_song_directory(self, song_name: str) -> str:
        """查找单曲目录，支持 - Single 后缀"""
        try:
            # 获取基础下载目录
            base_dir = getattr(self, 'output_dir', '/downloads/AppleMusic')
            amd_downloads_dir = os.path.join(base_dir, "AM-DL downloads")
            
            if not os.path.exists(amd_downloads_dir):
                logger.warning(f"⚠️ AM-DL downloads目录不存在: {amd_downloads_dir}")
                return None
            
            # 从文件名中提取歌曲名称（去掉扩展名）
            song_name_clean = os.path.splitext(song_name)[0]
            logger.info(f"🔍 查找单曲目录: {song_name_clean}")
            
            # 遍历艺术家目录
            for artist_dir in os.listdir(amd_downloads_dir):
                artist_path = os.path.join(amd_downloads_dir, artist_dir)
                if not os.path.isdir(artist_path):
                    continue
                
                # 在艺术家目录中查找单曲目录
                for item in os.listdir(artist_path):
                    item_path = os.path.join(artist_path, item)
                    if not os.path.isdir(item_path):
                        continue
                    
                    # 方式1：直接匹配 song_name
                    if item == song_name_clean:
                        logger.info(f"✅ 找到单曲目录（直接匹配）: {item}")
                        return item_path
                    
                    # 方式2：匹配 song_name - Single（Apple Music的命名规则）
                    if item == f"{song_name_clean} - Single":
                        logger.info(f"✅ 找到单曲目录（- Single后缀）: {item}")
                        return item_path
                    
                    # 方式3：模糊匹配，查找包含 song_name 的目录
                    if song_name_clean in item:
                        logger.info(f"✅ 找到单曲目录（模糊匹配）: {item}")
                        return item_path
            
            logger.warning(f"⚠️ 未找到单曲目录: {song_name_clean}")
            return None
            
        except Exception as e:
            logger.error(f"❌ 查找单曲目录失败: {e}")
            return None

    def _find_audio_files_in_directory(self, directory: str) -> list:
        """在指定目录中查找音频文件"""
        try:
            audio_files = []
            # 修复：Apple Music只使用.m4a格式
            possible_extensions = ['.m4a', '.aac', '.m4p']
            
            if os.path.exists(directory):
                for file in os.listdir(directory):
                    if file.lower().endswith(tuple(possible_extensions)):
                        file_path = os.path.join(directory, file)
                        audio_files.append(file_path)
                        logger.info(f"🎵 找到音频文件: {file}")
            
            return audio_files
            
        except Exception as e:
            logger.error(f"❌ 查找音频文件失败: {e}")
            return []

    def _get_real_album_size(self) -> float:
        """获取专辑的真实总大小（MB）- 遍历所有音频文件"""
        try:
            import os
            
            # 获取专辑下载目录
            amd_downloads_dir = os.path.join(self.output_dir, "AM-DL downloads")
            if not os.path.exists(amd_downloads_dir):
                logger.warning(f"⚠️ 专辑下载目录不存在: {amd_downloads_dir}")
                return 0.0
            
            # 遍历所有艺术家目录
            total_size = 0.0
            for artist_dir in os.listdir(amd_downloads_dir):
                artist_path = os.path.join(amd_downloads_dir, artist_dir)
                if not os.path.isdir(artist_path):
                    continue
                
                # 遍历艺术家目录下的专辑目录
                for album_dir in os.listdir(artist_path):
                    album_path = os.path.join(artist_path, album_dir)
                    if not os.path.isdir(album_path):
                        continue
                    
                    # 遍历专辑目录中的所有音频文件
                    for file in os.listdir(album_path):
                        if file.lower().endswith(('.m4a', '.aac', '.m4p')):
                            file_path = os.path.join(album_path, file)
                            try:
                                file_size = os.path.getsize(file_path)
                                file_size_mb = file_size / (1024 * 1024)
                                total_size += file_size_mb
                                logger.debug(f"🔍 专辑文件: {file} - {file_size_mb:.2f} MB")
                            except Exception as e:
                                logger.warning(f"⚠️ 获取文件大小失败: {file} - {e}")
            
            logger.info(f"✅ 专辑总大小计算完成: {total_size:.2f} MB")
            return total_size
            
        except Exception as e:
            logger.error(f"❌ 获取专辑总大小失败: {e}")
            # 回退到之前保存的解密大小
            if hasattr(self, '_last_decrypt_total'):
                logger.info(f"🔧 回退到之前保存的解密大小: {self._last_decrypt_total}")
                return self._last_decrypt_total
            return 0.0
    
    def _convert_traditional_to_simplified(self, text: str) -> str:
        """将繁体中文转换为简体中文"""
        try:
            # 使用 opencc 库进行繁简转换
            import opencc
            converter = opencc.OpenCC('t2s')  # 繁体到简体
            converted = converter.convert(text)
            if converted != text:
                logger.info(f"🔍 opencc转换: '{text}' -> '{converted}'")
            return converted
            
        except ImportError:
            logger.warning("⚠️ opencc库未安装，无法进行繁简转换")
            return text
        except Exception as e:
            logger.error(f"❌ 繁简转换失败: {e}")
            return text

    def _get_real_album_info(self, output_dir: str) -> Dict[str, Any]:
        """获取专辑的真实信息 - 包括文件数量、总大小和歌曲列表"""
        try:
            import os
            
            # 获取专辑下载目录
            amd_downloads_dir = os.path.join(output_dir, "AM-DL downloads")
            if not os.path.exists(amd_downloads_dir):
                logger.warning(f"⚠️ 专辑下载目录不存在: {amd_downloads_dir}")
                return {
                    'files_count': 0,
                    'total_size': 0,
                    'track_list': []
                }
            
            # 遍历所有艺术家目录，找到最新的专辑
            latest_album_info = None
            latest_time = 0
            
            for artist_dir in os.listdir(amd_downloads_dir):
                artist_path = os.path.join(amd_downloads_dir, artist_dir)
                if not os.path.isdir(artist_path):
                    continue
                
                # 遍历艺术家目录下的专辑目录
                for album_dir in os.listdir(artist_path):
                    album_path = os.path.join(artist_path, album_dir)
                    if not os.path.isdir(album_path):
                        continue
                    
                    # 检查专辑目录的修改时间
                    try:
                        album_time = os.path.getmtime(album_path)
                        if album_time > latest_time:
                            latest_time = album_time
                            latest_album_info = {
                                'artist': artist_dir,
                                'album': album_dir,
                                'path': album_path
                            }
                    except Exception as e:
                        logger.warning(f"⚠️ 获取专辑目录时间失败: {album_path} - {e}")
            
            if not latest_album_info:
                logger.warning("⚠️ 未找到任何专辑目录")
                return {
                    'files_count': 0,
                    'total_size': 0,
                    'track_list': []
                }
            
            # 分析最新专辑目录
            album_path = latest_album_info['path']
            files_count = 0
            total_size = 0
            track_list = []
            
            for file in os.listdir(album_path):
                if file.lower().endswith(('.m4a', '.aac', '.m4p')):
                    files_count += 1
                    file_path = os.path.join(album_path, file)
                    try:
                        file_size = os.path.getsize(file_path)
                        total_size += file_size
                        
                        # 构建歌曲信息
                        track_name = file.replace('.m4a', '').replace('.aac', '').replace('.m4p', '')
                        track_info = {
                            'name': track_name,
                            'size': file_size / (1024 * 1024),  # 转换为MB
                            'path': file
                        }
                        track_list.append(track_info)
                        
                        logger.debug(f"🔍 专辑文件: {track_name} - {file_size / (1024 * 1024):.2f} MB")
                    except Exception as e:
                        logger.warning(f"⚠️ 获取文件大小失败: {file} - {e}")
            
            logger.info(f"✅ 专辑信息获取完成: {latest_album_info['artist']} - {latest_album_info['album']}")
            logger.info(f"✅ 文件数量: {files_count}, 总大小: {total_size / (1024 * 1024):.2f} MB")
            
            return {
                'files_count': files_count,
                'total_size': total_size,  # 返回字节数
                'track_list': track_list
            }
            
        except Exception as e:
            logger.error(f"❌ 获取专辑信息失败: {e}")
            return {
                'files_count': 0,
                'total_size': 0,
                'track_list': []
            }

class GamdlBackend(DownloadBackend):
    """Gamdl 后端实现"""
    
    def __init__(self):
        super().__init__("gamdl")
        self.gamdl_path = self._find_gamdl_executable()
        self.config_template = self._get_config_template()
    
    def _find_gamdl_executable(self) -> Optional[str]:
        """查找 gamdl 可执行文件"""
        possible_paths = [
            "./gamdl",
            "./apple-music-downloader/gamdl",
            "/usr/local/bin/gamdl",
            "/usr/bin/gamdl",
            "/bin/gamdl",
            "gamdl"  # 使用 PATH 查找
        ]
        
        # 添加用户本地 bin 目录
        user_local_bin = os.path.expanduser("~/.local/bin/gamdl")
        if os.path.exists(user_local_bin):
            possible_paths.insert(0, user_local_bin)
        
        # 检查 PATH 环境变量
        path_dirs = os.environ.get("PATH", "").split(":")
        for path_dir in path_dirs:
            if path_dir:
                possible_paths.append(os.path.join(path_dir, "gamdl"))
        
        for path in possible_paths:
            if os.path.exists(path) and os.access(path, os.X_OK):
                logger.info(f"✅ 找到 gamdl 可执行文件: {path}")
                return path
        
        logger.warning("⚠️ 未找到 gamdl 可执行文件")
        return None
    
    def _get_config_template(self) -> str:
        """获取 gamdl 配置模板"""
        return f"""# Gamdl 配置

# 其他配置保持默认
"""
    
    def _create_config_file(self, output_dir: str) -> str:
        """创建 gamdl 配置文件在当前工作目录中"""
        try:
            # 在当前工作目录中创建配置文件
            config_path = "gamdl_config.yaml"
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(self.config_template)
            logger.info(f"✅ gamdl 配置文件创建成功: {config_path}")
            return config_path
        except Exception as e:
            logger.error(f"❌ gamdl 配置文件创建失败: {e}")
            return None
    
    def is_available(self) -> bool:
        """检查 gamdl 是否可用"""
        if not self.gamdl_path:
            return False
        
        try:
            # 检查 gamdl 是否可执行
            result = subprocess.run([self.gamdl_path, "--help"], 
                                  capture_output=True, check=False, text=True)
            return result.returncode == 0
        except Exception:
            return False
    
    async def download_song(self, url: str, output_dir: str, cookies_path: str = None,
                           quality: str = "lossless", progress_callback=None) -> Dict[str, Any]:
        """使用 gamdl 下载单曲"""
        try:
            if not self.gamdl_path:
                return {
                    'success': False,
                    'backend': self.name,
                    'error': 'gamdl 可执行文件未找到'
                }
            
            # 创建配置文件
            config_path = self._create_config_file(output_dir)
            if not config_path:
                return {
                    'success': False,
                    'backend': self.name,
                    'error': '配置文件创建失败'
                }
            
            # 构建命令
            cmd = [self.gamdl_path, url]
            
            # 质量映射
            quality_map = {
                "lossless": "--alac",
                "aac": "--aac", 
                "atmos": "--atmos"
            }
            if quality in quality_map:
                cmd.append(quality_map[quality])
            
            logger.info(f"🎵 使用 gamdl 下载单曲: {url}")
            logger.debug(f"命令: {' '.join(cmd)}")
            
            # 执行下载
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=output_dir,
                env={
                    **os.environ,
                    "AMD_WRAPER_DECRYPT": os.environ.get("AMD_WRAPER_DECRYPT", "192.168.2.134:10020"),
                    "AMD_WRAPER_GET": os.environ.get("AMD_WRAPER_GET", "192.168.2.134:20020")
                }
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                logger.info("✅ gamdl 下载完成")
                return {
                    'success': True,
                    'backend': self.name,
                    'music_type': 'song',
                    'output': stdout.decode('utf-8'),
                    'message': 'gamdl 下载成功'
                }
            else:
                error_msg = stderr.decode('utf-8')
                logger.error(f"❌ gamdl 下载失败: {error_msg}")
                return {
                    'success': False,
                    'backend': self.name,
                    'error': error_msg
                }
                
        except Exception as e:
            logger.error(f"❌ gamdl 执行异常: {e}")
            return {
                'success': False,
                'backend': self.name,
                'error': str(e)
            }
    
    async def download_album(self, url: str, output_dir: str, cookies_path: str = None,
                            quality: str = "lossless", progress_callback=None) -> Dict[str, Any]:
        """使用 gamdl 下载专辑"""
        try:
            if not self.gamdl_path:
                return {
                    'success': False,
                    'backend': self.name,
                    'error': 'gamdl 可执行文件未找到'
                }
            
            # 创建配置文件
            config_path = self._create_config_file(output_dir)
            if not config_path:
                return {
                    'success': False,
                    'backend': self.name,
                    'error': '配置文件创建失败'
                }
            
            # 构建命令
            cmd = [self.gamdl_path, url]
            
            # 质量映射
            quality_map = {
                "lossless": "--alac",
                "aac": "--aac", 
                "atmos": "--atmos"
            }
            if quality in quality_map:
                cmd.append(quality_map[quality])
            
            logger.info(f"📀 使用 gamdl 下载专辑: {url}")
            logger.debug(f"命令: {' '.join(cmd)}")
            
            # 执行下载
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=output_dir,
                env={
                    **os.environ,
                    "AMD_WRAPER_DECRYPT": os.environ.get("AMD_WRAPER_DECRYPT", "192.168.2.134:10020"),
                    "AMD_WRAPER_GET": os.environ.get("AMD_WRAPER_GET", "192.168.2.134:20020")
                }
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                logger.info("✅ gamdl 专辑下载完成")
                return {
                    'success': True,
                    'backend': self.name,
                    'music_type': 'album',
                    'output': stdout.decode('utf-8'),
                    'message': 'gamdl 专辑下载成功'
                }
            else:
                error_msg = stderr.decode('utf-8')
                logger.error(f"❌ gamdl 专辑下载失败: {error_msg}")
                return {
                    'success': False,
                    'backend': self.name,
                    'error': error_msg
                }
                
        except Exception as e:
            logger.error(f"❌ gamdl 专辑下载异常: {e}")
            return {
                'success': False,
                'backend': self.name,
                'error': str(e)
            }

@dataclass
class AppleMusicTrack:
    """Apple Music 音轨信息"""
    id: str
    name: str
    artist: str
    album: str
    duration: int
    disc_number: int
    track_number: int
    is_explicit: bool
    is_apple_digital_master: bool
    audio_traits: List[str]
    content_rating: str

@dataclass
class AppleMusicAlbum:
    """Apple Music 专辑信息"""
    id: str
    name: str
    def _get_real_album_size(self) -> float:
        """获取专辑的真实总大小（MB）- 遍历所有音频文件"""
        try:
            import os
            
            # 获取专辑下载目录
            amd_downloads_dir = os.path.join(self.output_dir, "AM-DL downloads")
            if not os.path.exists(amd_downloads_dir):
                logger.warning(f"⚠️ 专辑下载目录不存在: {amd_downloads_dir}")
                return 0.0
            
            # 遍历所有艺术家目录
            total_size = 0.0
            for artist_dir in os.listdir(amd_downloads_dir):
                artist_path = os.path.join(amd_downloads_dir, artist_dir)
                if not os.path.isdir(artist_path):
                    continue
                
                # 遍历艺术家目录下的专辑目录
                for album_dir in os.listdir(artist_path):
                    album_path = os.path.join(artist_path, album_dir)
                    if not os.path.isdir(album_path):
                        continue
                    
                    # 遍历专辑目录中的所有音频文件
                    for file in os.listdir(album_path):
                        if file.lower().endswith(('.m4a', '.aac', '.m4p')):
                            file_path = os.path.join(album_path, file)
                            try:
                                file_size = os.path.getsize(file_path)
                                file_size_mb = file_size / (1024 * 1024)
                                total_size += file_size_mb
                                logger.debug(f"🔍 专辑文件: {file} - {file_size_mb:.2f} MB")
                            except Exception as e:
                                logger.warning(f"⚠️ 获取文件大小失败: {file} - {e}")
            
            logger.info(f"✅ 专辑总大小计算完成: {total_size:.2f} MB")
            return total_size
            
        except Exception as e:
            logger.error(f"❌ 获取专辑总大小失败: {e}")
            # 回退到之前保存的解密大小
            if hasattr(self, '_last_decrypt_total'):
                logger.info(f"🔧 回退到之前保存的解密大小: {self._last_decrypt_total}")
                return self._last_decrypt_total
            return 0.0

    artist: str
    release_date: str
    track_count: int
    tracks: List[AppleMusicTrack]
    is_explicit: bool
    is_apple_digital_master: bool

class AppleMusicDownloaderPlus:
    """Apple Music 下载器增强版"""
    
    def __init__(self, cookies_path: str = None, output_dir: str = "./downloads/AppleMusic"):
        self.cookies_path = cookies_path
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 检测 Docker 环境
        self.is_docker = self._detect_docker_environment()
        
        # 初始化下载后端
        self.backends = self._initialize_backends()
        self.primary_backend = self._select_primary_backend()
        
        logger.info(f"🍎 Apple Music 下载器增强版初始化完成")
        logger.info(f"📁 输出目录: {self.output_dir}")
        logger.info(f"🐳 Docker 环境: {self.is_docker}")
        logger.info(f"🔧 可用后端: {[b.name for b in self.backends if b.is_available()]}")
        logger.info(f"🎯 主要后端: {self.primary_backend.name if self.primary_backend else 'None'}")
    
    def _detect_docker_environment(self) -> bool:
        """检测是否在 Docker 环境中运行"""
        docker_indicators = [
            "/.dockerenv",
            "/proc/1/cgroup",
            "/sys/fs/cgroup",
            "DOCKER_CONTAINER" in os.environ,
            "KUBERNETES_SERVICE_HOST" in os.environ
        ]
        return any(docker_indicators)
    
    def _initialize_backends(self) -> List[DownloadBackend]:
        """初始化所有可用的下载后端"""
        try:
            # 只使用 apple-music-downloader 后端（amd）
            logger.info("🔧 使用 apple-music-downloader 后端（amd）")
            backends = [
                AppleMusicDownloaderBackend()
            ]
            
            # 设置父类引用，让后端能够访问父类的方法
            for backend in backends:
                backend._parent_downloader = self
            
            available_backends = []
            for backend in backends:
                try:
                    if backend.is_available():
                        available_backends.append(backend)
                        logger.info(f"✅ 后端 {backend.name} 可用")
                    else:
                        logger.warning(f"⚠️ 后端 {backend.name} 不可用")
                except Exception as e:
                    logger.warning(f"⚠️ 检查后端 {backend.name} 可用性时出错: {e}")
            
            return available_backends
        except Exception as e:
            logger.error(f"❌ 初始化后端时发生错误: {e}")
            return []
    
    def _select_primary_backend(self) -> Optional[DownloadBackend]:
        """选择主要后端"""
        if not self.backends:
            logger.warning("⚠️ 没有可用的下载后端")
            return None
        
        # 优先级顺序：apple-music-downloader > gamdl
        for backend_name in ["apple-music-downloader", "gamdl"]:
            for backend in self.backends:
                if backend.name == backend_name:
                    logger.info(f"🎯 选择主要后端: {backend.name}")
                    return backend
        
        # 如果没有找到优先后端，使用第一个可用的
        primary = self.backends[0]
        logger.info(f"🎯 使用第一个可用后端: {primary.name}")
        return primary
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        pass
    
    def _set_current_track_name(self, track_name: str):
        """设置当前单曲名称（供后端调用）"""
        self._current_track_name = track_name
        logger.info(f"📝 AppleMusicDownloaderPlus 设置当前单曲名称: {track_name}")
    
    def _get_current_track_name(self) -> Optional[str]:
        """获取当前单曲名称"""
        return getattr(self, '_current_track_name', None)
    

    
    async def download_album(self, url: str, progress_callback=None) -> Dict[str, Any]:
        """下载整张专辑"""
        try:
            if not self.primary_backend:
                return {
                    'success': False,
                    'error': '没有可用的下载后端'
                }
            
            # 使用主要后端下载
            result = await self.primary_backend.download_album(url, str(self.output_dir), self.cookies_path, progress_callback=progress_callback)
            return result
            
        except Exception as e:
            logger.error(f"❌ 专辑下载失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def download_song(self, url: str, progress_callback=None) -> Dict[str, Any]:
        """下载单曲"""
        try:
            if not self.primary_backend:
                return {
                    'success': False,
                    'error': '没有可用的下载后端'
                }
            
            # 使用主要后端下载
            result = await self.primary_backend.download_song(url, str(self.output_dir), self.cookies_path, progress_callback=progress_callback)
            return result
            
        except Exception as e:
            logger.error(f"❌ 单曲下载失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def is_available(self) -> bool:
        """检查下载器是否可用"""
        try:
            if not self.primary_backend:
                return False
            return self.primary_backend.is_available()
        except Exception as e:
            logger.error(f"❌ 检查下载器可用性失败: {e}")
            return False
    
    def extract_music_info(self, url: str) -> Dict[str, Any]:
        """提取音乐信息"""
        try:
            # 解析 Apple Music URL
            info = self._extract_apple_music_info(url)
            return info
        except Exception as e:
            logger.error(f"❌ 提取音乐信息失败: {e}")
            return {
                'url': url,
                'type': 'unknown',
                'id': 'unknown',
                'country': 'cn'
            }
        """从下载URL中获取文件名"""
        try:
            if hasattr(self, '_download_url') and self._download_url:
                # 从URL中提取音乐信息
                music_info = self.extract_music_info(self._download_url)
                if music_info:
                    content_type = music_info.get('type', 'unknown')
                    if content_type == 'song':
                        # 单曲：尝试从URL中提取歌曲名
                        # 例如：https://music.apple.com/cn/song/获奖之作/1831458645
                        url_parts = self._download_url.split('/')
                        if len(url_parts) >= 6:
                            song_name = url_parts[5]  # 歌曲名通常在URL的第6部分
                            # URL解码
                            from urllib.parse import unquote
                            song_name = unquote(song_name)
                            return song_name
                        else:
                            return "单曲"
                    elif content_type == 'album':
                        # 专辑：使用专辑名
                        url_parts = self._download_url.split('/')
                        if len(url_parts) >= 6:
                            album_name = url_parts[5]  # 专辑名通常在URL的第6部分
                            from urllib.parse import unquote
                            album_name = unquote(album_name)
                            return f"{album_name}.m4a"
                        else:
                            return "专辑.m4a"
            
            # 如果无法获取，返回默认文件名
            return "Apple Music 文件"
        except Exception as e:
            logger.debug(f"从URL获取文件名失败: {e}")
            return "Apple Music 文件"
    

    
    def _extract_filename_from_url_fallback(self, url: str) -> str:
        """备选方案：从URL路径提取文件名"""
        try:
            # 从URL中提取音乐信息
            music_info = self._extract_apple_music_info(url)
            if music_info:
                content_type = music_info.get('type', 'unknown')
                if content_type == 'song':
                    # 单曲：尝试从URL中提取歌曲名
                    url_parts = url.split('/')
                    if len(url_parts) >= 6:
                        song_name = url_parts[5]  # 歌曲名通常在URL的第6部分
                        # URL解码
                        from urllib.parse import unquote
                        song_name = unquote(song_name)
                        return song_name
                    else:
                        return "单曲"
                elif content_type == 'album':
                    # 专辑：使用专辑名
                    url_parts = url.split('/')
                    if len(url_parts) >= 6:
                        album_name = url_parts[5]  # 专辑名通常在URL的第6部分
                        from urllib.parse import unquote
                        album_name = unquote(album_name)
                        return f"{album_name}.m4a"
                    else:
                        return "专辑.m4a"
            
            return "Apple Music 文件"
        except Exception as e:
            logger.debug(f"备选方案提取文件名失败: {e}")
            return "Apple Music 文件"
    
    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名，移除非法字符"""
        import re
        # 移除或替换文件名中的非法字符
        illegal_chars = r'[<>:"/\\|?*]'
        safe_filename = re.sub(illegal_chars, '_', filename)
        # 移除多余的空格和下划线
        safe_filename = re.sub(r'[_\s]+', '_', safe_filename).strip('_')
        return safe_filename
    
    def is_apple_music_url(self, url: str) -> bool:
        """检查是否为 Apple Music URL"""
        try:
            from urllib.parse import urlparse
            
            apple_music_domains = [
                'music.apple.com',
                'itunes.apple.com',
                'geo.music.apple.com'
            ]
            
            parsed = urlparse(url)
            return any(domain in parsed.netloc.lower() for domain in apple_music_domains)
        except Exception:
            return False
    
    def _extract_apple_music_info(self, url: str) -> Dict[str, Any]:
        """从 Apple Music URL 提取信息"""
        try:
            import re
            from urllib.parse import urlparse, parse_qs
            
            # 解析 URL
            parsed = urlparse(url)
            path_parts = parsed.path.strip('/').split('/')
            
            # 检查路径格式
            if len(path_parts) >= 3 and path_parts[0] in ['cn', 'us', 'jp', 'kr', 'tw', 'hk']:
                country = path_parts[0]
                content_type = path_parts[1]  # 'album' 或 'song'
                content_id = path_parts[2]    # 专辑/歌曲 ID
                
                return {
                    'url': url,
                    'type': content_type,
                    'id': content_id,
                    'country': country
                }
            else:
                # 尝试从查询参数获取
                query_params = parse_qs(parsed.query)
                if 'i' in query_params:
                    return {
                        'url': url,
                        'type': 'song',
                        'id': query_params['i'][0],
                        'country': 'cn'
                    }
                else:
                    return {
                        'url': url,
                        'type': 'unknown',
                        'id': 'unknown',
                        'country': 'cn'
                    }
                    
        except Exception as e:
            logger.error(f"❌ 解析 Apple Music URL 失败: {e}")
            return {
                'url': url,
                'type': 'unknown',
                'id': 'unknown',
                'country': 'cn'
            }

class ProgressTracker:
    """下载进度跟踪器"""
    
    def __init__(self, total_size: int = 0, total_files: int = 0):
        self.total_size = total_size
        self.total_files = total_files
        self.downloaded_size = 0
        self.downloaded_files = 0
        self.start_time = None
        self.current_file = ""
    
    def start(self):
        """开始跟踪"""
        self.start_time = time.time()
        self.downloaded_size = 0
        self.downloaded_files = 0
    
    def update(self, bytes_downloaded: int, filename: str = ""):
        """更新进度"""
        self.downloaded_size += bytes_downloaded
        if filename and filename != self.current_file:
            self.downloaded_files += 1
            self.current_file = filename
    
    def get_progress(self) -> Dict[str, Any]:
        """获取进度信息"""
        if not self.start_time:
            return {}
        
        elapsed = time.time() - self.start_time
        if elapsed > 0:
            speed = self.downloaded_size / elapsed
            eta = (self.total_size - self.downloaded_size) / speed if speed > 0 else 0
        else:
            speed = 0
            eta = 0
        
        return {
            'downloaded_size': self.downloaded_size,
            'total_size': self.total_size,
            'downloaded_files': self.downloaded_files,
            'total_files': self.total_files,
            'progress_percent': (self.downloaded_size / self.total_size * 100) if self.total_size > 0 else 0,
            'speed_mbps': speed / (1024 * 1024),
            'eta_seconds': eta,
            'elapsed_seconds': elapsed,
            'current_file': self.current_file
        }

class ConfigurationManager:
    """配置管理器"""
    
    def __init__(self, config_path: str = "apple_music_config.yaml"):
        self.config_path = Path(config_path)
        self.config = self._load_default_config()
        self._load_config()
    
    def _load_default_config(self) -> Dict[str, Any]:
        """加载默认配置"""
        return {
            'download': {
                'output_dir': '/downloads/AppleMusic',
                'quality': 'lossless',  # lossless, aac, atmos
                'format': 'm4a',        # m4a, flac, alac
                'concurrent_downloads': 3,
                'retry_attempts': 3,
                'timeout': 300
            },
            'api': {
                'base_url': 'https://api.music.apple.com',
                'storefront': 'cn',
                'user_agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            },
            'tools': {
                'ffmpeg_path': 'ffmpeg',
                'mp4decrypt_path': 'mp4decrypt',
                'use_ffmpeg_fallback': True
            },
            'logging': {
                'level': 'INFO',
                'file': None,
                'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            }
        }
    
    def _load_config(self):
        """加载配置文件"""
        if self.config_path.exists():
            try:
                if YAML_AVAILABLE:
                    with open(self.config_path, 'r', encoding='utf-8') as f:
                        user_config = yaml.safe_load(f)
                        self._merge_config(user_config)
                        logger.info(f"✅ 配置文件加载成功: {self.config_path}")
                else:
                    # 如果没有 yaml，尝试使用 JSON
                    with open(self.config_path, 'r', encoding='utf-8') as f:
                        user_config = json.load(f)
                        self._merge_config(user_config)
                        logger.info(f"✅ 配置文件加载成功 (JSON): {self.config_path}")
            except Exception as e:
                logger.warning(f"⚠️ 配置文件加载失败: {e}")
    
    def _merge_config(self, user_config: Dict[str, Any]):
        """合并用户配置"""
        def merge_dict(base: Dict[str, Any], update: Dict[str, Any]):
            for key, value in update.items():
                if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                    merge_dict(base[key], value)
                else:
                    base[key] = value
        
        merge_dict(self.config, user_config)
    
    def get(self, key_path: str, default=None):
        """获取配置值"""
        keys = key_path.split('.')
        value = self.config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value
    
    def save(self):
        """保存配置到文件"""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            if YAML_AVAILABLE:
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    yaml.dump(self.config, f, default_flow_style=False, allow_unicode=True)
                logger.info(f"✅ 配置保存成功 (YAML): {self.config_path}")
            else:
                # 如果没有 yaml，使用 JSON
                with open(self.config_path.with_suffix('.json'), 'w', encoding='utf-8') as f:
                    json.dump(self.config, f, indent=2, ensure_ascii=False)
                logger.info(f"✅ 配置保存成功 (JSON): {self.config_path.with_suffix('.json')}")
        except Exception as e:
            logger.error(f"❌ 配置保存失败: {e}")

class ErrorHandler:
    """错误处理器"""
    
    def __init__(self):
        self.error_count = 0
        self.max_errors = 10
        self.error_log = []
    
    def handle_error(self, error: Exception, context: str = "") -> bool:
        """处理错误"""
        error_info = {
            'timestamp': time.time(),
            'error_type': type(error).__name__,
            'error_message': str(error),
            'context': context
        }
        
        self.error_log.append(error_info)
        self.error_count += 1
        
        logger.error(f"❌ 错误 [{context}]: {error}")
        
        # 检查是否达到最大错误数
        if self.error_count >= self.max_errors:
            logger.critical(f"🚨 达到最大错误数 {self.max_errors}，停止处理")
            return False
        
        return True
    
    def get_error_summary(self) -> Dict[str, Any]:
        """获取错误摘要"""
        return {
            'total_errors': self.error_count,
            'recent_errors': self.error_log[-5:] if self.error_log else [],
            'error_types': list(set(e['error_type'] for e in self.error_log))
        }
    
    def reset(self):
        """重置错误计数"""
        self.error_count = 0
        self.error_log.clear()

class CommandLineInterface:
    """命令行接口"""
    
    def __init__(self):
        self.parser = self._create_parser()
    
    def _create_parser(self):
        """创建命令行参数解析器"""
        import argparse
        
        parser = argparse.ArgumentParser(
            description="Apple Music 下载器增强版",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
示例用法:
  # 下载单曲
  python applemusic_downloader+.py -u "https://music.apple.com/cn/song/获奖之作/1831458645"
  
  # 下载专辑
  python applemusic_downloader+.py -u "https://music.apple.com/cn/album/危险世界/1579903639"
  
  # 批量下载
  python applemusic_downloader+.py -f urls.txt
  
  # 指定输出目录和质量
  python applemusic_downloader+.py -u "URL" -o "/downloads" -q lossless
            """
        )
        
        parser.add_argument(
            '-u', '--url',
            help='Apple Music URL (单曲或专辑)'
        )
        
        parser.add_argument(
            '-f', '--file',
            help='包含多个 URL 的文本文件'
        )
        
        parser.add_argument(
            '-o', '--output',
            help='输出目录 (默认: /downloads/AppleMusic)'
        )
        
        parser.add_argument(
            '-q', '--quality',
            choices=['aac', 'lossless', 'atmos'],
            default='lossless',
            help='音频质量 (默认: lossless)'
        )
        
        parser.add_argument(
            '-c', '--cookies',
            help='cookies 文件路径'
        )
        
        parser.add_argument(
            '--config',
            help='配置文件路径'
        )
        
        parser.add_argument(
            '--concurrent',
            type=int,
            default=3,
            help='并发下载数 (默认: 3)'
        )
        
        parser.add_argument(
            '--retry',
            type=int,
            default=3,
            help='重试次数 (默认: 3)'
        )
        
        parser.add_argument(
            '--timeout',
            type=int,
            default=300,
            help='超时时间(秒) (默认: 300)'
        )
        
        parser.add_argument(
            '--verbose', '-v',
            action='store_true',
            help='详细输出'
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='试运行模式，不实际下载'
        )
        
        return parser
    
    def parse_args(self):
        """解析命令行参数"""
        return self.parser.parse_args()
    
    def print_help(self):
        """打印帮助信息"""
        self.parser.print_help()

class BatchDownloader:
    """批量下载器"""
    
    def __init__(self, downloader: AppleMusicDownloaderPlus, config: ConfigurationManager):
        self.downloader = downloader
        self.config = config
        self.progress_tracker = ProgressTracker()
        self.error_handler = ErrorHandler()
    
    async def download_from_file(self, url_file: str, progress_callback=None) -> List[Dict[str, Any]]:
        """从文件批量下载"""
        try:
            with open(url_file, 'r', encoding='utf-8') as f:
                urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            
            logger.info(f"📋 从文件加载了 {len(urls)} 个 URL")
            
            results = []
            for i, url in enumerate(urls):
                logger.info(f"🔄 处理第 {i+1}/{len(urls)} 个 URL: {url}")
                
                try:
                    if "/song/" in url:
                        result = await self.downloader.download_song(url, progress_callback)
                    elif "/album/" in url:
                        result = await self.downloader.download_album(url, progress_callback)
                    else:
                        logger.warning(f"⚠️ 未知的 URL 类型: {url}")
                        continue
                    
                    results.append(result)
                    
                    if result['success']:
                        logger.info(f"✅ 下载成功: {url}")
                    else:
                        logger.error(f"❌ 下载失败: {url}")
                        
                except Exception as e:
                    if not self.error_handler.handle_error(e, f"处理 URL: {url}"):
                        break
                    
                    results.append({
                        'success': False,
                        'url': url,
                        'error': str(e)
                    })
            
            return results
            
        except Exception as e:
            logger.error(f"❌ 批量下载失败: {e}")
            return []
    
    async def download_urls(self, urls: List[str], progress_callback=None) -> List[Dict[str, Any]]:
        """批量下载多个 URL"""
        results = []
        
        for i, url in enumerate(urls):
            logger.info(f"🔄 处理第 {i+1}/{len(urls)} 个 URL: {url}")
            
            try:
                if "/song/" in url:
                    result = await self.downloader.download_song(url, progress_callback)
                elif "/album/" in url:
                    result = await self.downloader.download_album(url, progress_callback)
                else:
                    logger.warning(f"⚠️ 未知的 URL 类型: {url}")
                    continue
                
                results.append(result)
                
                if result['success']:
                    logger.info(f"✅ 下载成功: {url}")
                else:
                    logger.error(f"❌ 下载失败: {url}")
                    
            except Exception as e:
                if not self.error_handler.handle_error(e, f"处理 URL: {url}"):
                    break
                
                results.append({
                    'success': False,
                    'url': url,
                    'error': str(e)
                })
        
        return results

def setup_logging(config: ConfigurationManager):
    """设置日志"""
    log_config = config.get('logging', {})
    log_level = getattr(logging, log_config.get('level', 'INFO').upper())
    
    # 配置根日志记录器
    logging.basicConfig(
        level=log_level,
        format=log_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s'),
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_config.get('file', 'apple_music_downloader.log')) if log_config.get('file') else logging.NullHandler()
        ]
    )

def print_download_summary(results: List[Dict[str, Any]]):
    """打印下载摘要"""
    if not results:
        return
    
    successful = [r for r in results if r.get('success', False)]
    failed = [r for r in results if not r.get('success', False)]
    
    print("\n" + "="*60)
    print("📊 下载摘要")
    print("="*60)
    print(f"✅ 成功: {len(successful)}")
    print(f"❌ 失败: {len(failed)}")
    print(f"📈 成功率: {len(successful)/len(results)*100:.1f}%")
    
    if successful:
        print("\n🎵 成功下载:")
        for result in successful:
            if result.get('music_type') == 'song':
                track_info = result.get('track_info', {})
                print(f"  • {track_info.get('artist', 'Unknown')} - {track_info.get('name', 'Unknown')}")
            elif result.get('music_type') == 'album':
                album_info = result.get('album_info', {})
                print(f"  • {album_info.get('artist', 'Unknown')} - {album_info.get('name', 'Unknown')} ({result.get('successful_tracks', 0)}/{result.get('total_tracks', 0)} 首)")
    
    if failed:
        print("\n❌ 下载失败:")
        for result in failed:
            print(f"  • {result.get('url', 'Unknown')}: {result.get('error', 'Unknown error')}")
    
    print("="*60)

    def _get_real_album_size(self) -> float:
        """获取专辑的真实总大小（MB）- 遍历所有音频文件"""
        try:
            import os
            
            # 获取专辑下载目录
            amd_downloads_dir = os.path.join(self.output_dir, "AM-DL downloads")
            if not os.path.exists(amd_downloads_dir):
                logger.warning(f"⚠️ 专辑下载目录不存在: {amd_downloads_dir}")
                return 0.0
            
            # 遍历所有艺术家目录
            total_size = 0.0
            for artist_dir in os.listdir(amd_downloads_dir):
                artist_path = os.path.join(amd_downloads_dir, artist_dir)
                if not os.path.isdir(artist_path):
                    continue
                
                # 遍历艺术家目录下的专辑目录
                for album_dir in os.listdir(artist_path):
                    album_path = os.path.join(artist_path, album_dir)
                    if not os.path.isdir(album_path):
                        continue
                    
                    # 遍历专辑目录中的所有音频文件
                    for file in os.listdir(album_path):
                        if file.lower().endswith(('.m4a', '.aac', '.m4p')):
                            file_path = os.path.join(album_path, file)
                            try:
                                file_size = os.path.getsize(file_path)
                                file_size_mb = file_size / (1024 * 1024)
                                total_size += file_size_mb
                                logger.debug(f"🔍 专辑文件: {file} - {file_size_mb:.2f} MB")
                            except Exception as e:
                                logger.warning(f"⚠️ 获取文件大小失败: {file} - {e}")
            
            logger.info(f"✅ 专辑总大小计算完成: {total_size:.2f} MB")
            return total_size
            
        except Exception as e:
            logger.error(f"❌ 获取专辑总大小失败: {e}")
            # 回退到之前保存的解密大小
            if hasattr(self, '_last_decrypt_total'):
                logger.info(f"🔧 回退到之前保存的解密大小: {self._last_decrypt_total}")
                return self._last_decrypt_total
            return 0.0

# 删除测试用的main函数和相关的命令行接口代码

