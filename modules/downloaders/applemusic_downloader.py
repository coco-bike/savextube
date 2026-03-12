#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Apple Music 音乐下载器
基于 gamdl 实现 Apple Music 音乐下载功能
"""

import os
import sys
import time
import asyncio
import json
import logging
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List
import re
from urllib.parse import urlparse, parse_qs

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AppleMusicDownloader:
    """Apple Music 音乐下载器"""
    
    def __init__(self, output_dir: str = "./downloads/apple_music", cookies_path: str = None):
        """
        初始化下载器
        
        Args:
            output_dir: 下载输出目录
            cookies_path: cookies 文件路径
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 设置 cookies 路径
        self.cookies_path = cookies_path
        
        # 检测是否在 Docker 环境中
        self.is_docker = self._detect_docker_environment()
        if self.is_docker:
            logger.info("🐳 检测到 Docker 环境，启用特殊优化")
            # Docker 环境下的特殊设置
            self.default_options = {
                'quality': '256',  # 音质：128, 256, 320
                'format': 'm4a',   # 格式：mp3, m4a, flac (Docker 环境使用 m4a)
                'cover': True,     # 是否下载封面
                'lyrics': True,    # 是否下载歌词
                'timeout': 900,    # 15分钟超时
                'retry_delay': 10  # 重试延迟增加到10秒
            }
        else:
            # 本地环境的默认设置
            self.default_options = {
                'quality': '256',  # 音质：128, 256, 320
                'format': 'mp3',   # 格式：mp3, m4a, flac
                'cover': True,     # 是否下载封面
                'lyrics': True,    # 是否下载歌词
            }
        
        # 检查 gamdl 是否可用
        self._check_gamdl_availability()
    
    def _check_gamdl_availability(self):
        """检查 gamdl 是否可用"""
        try:
            result = subprocess.run(['gamdl', '--version'], 
                                  capture_output=True, text=True, check=True)
            self.gamdl_available = True
            self.gamdl_version = result.stdout.strip()
            logger.info(f"✅ gamdl 可用，版本: {self.gamdl_version}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.gamdl_available = False
            logger.error("❌ gamdl 未安装或不可用")
            logger.info("💡 请安装 gamdl: pip install gamdl")
    
    def _detect_docker_environment(self) -> bool:
        """检测是否在 Docker 环境中运行"""
        try:
            # 检查常见的 Docker 环境标识
            docker_indicators = [
                '/.dockerenv',  # Docker 容器中的特殊文件
                '/proc/1/cgroup',  # cgroup 信息
                os.environ.get('DOCKER_CONTAINER'),  # Docker 环境变量
                os.environ.get('KUBERNETES_SERVICE_HOST')  # Kubernetes 环境
            ]
            
            # 检查 /.dockerenv 文件
            if os.path.exists('/.dockerenv'):
                return True
            
            # 检查 cgroup 信息
            try:
                with open('/proc/1/cgroup', 'r') as f:
                    content = f.read()
                    if 'docker' in content or 'kubepods' in content:
                        return True
            except:
                pass
            
            # 检查环境变量
            if any(indicator for indicator in docker_indicators if indicator):
                return True
            
            return False
            
        except Exception as e:
            logger.debug(f"🐳 Docker 环境检测失败: {e}")
            return False
    
    def _check_download_quality(self) -> bool:
        """检查下载质量是否正常"""
        try:
            if not self.output_dir.exists():
                return False
            
            # 查找音频文件
            audio_files = list(self.output_dir.rglob("*.m4a"))
            if not audio_files:
                return False
            
            # 检查音频文件大小
            for audio_file in audio_files:
                file_size = audio_file.stat().st_size
                # 音频文件应该至少 100KB (100*1024 字节)，因为有些短歌曲可能比较小
                min_size = 100 * 1024  # 100KB
                if file_size < min_size:
                    logger.warning(f"🍎 音频文件 {audio_file.name} 大小异常: {file_size} 字节 (小于 {min_size} 字节)")
                    return False
                else:
                    logger.info(f"🍎 音频文件 {audio_file.name} 大小正常: {file_size} 字节")
            
            return True
            
        except Exception as e:
            logger.error(f"🍎 检查下载质量失败: {e}")
            return False
    
    def is_apple_music_url(self, url: str) -> bool:
        """检查是否为 Apple Music URL"""
        apple_music_domains = [
            'music.apple.com',
            'itunes.apple.com',
            'geo.music.apple.com'
        ]
        
        try:
            parsed = urlparse(url)
            return any(domain in parsed.netloc.lower() for domain in apple_music_domains)
        except Exception:
            return False
    
    def extract_music_info(self, url: str) -> Dict[str, Any]:
        """从 URL 中提取音乐信息"""
        try:
            # 解析 URL 获取音乐类型和 ID
            parsed = urlparse(url)
            path_parts = parsed.path.strip('/').split('/')
            
            music_info = {
                'url': url,
                'type': 'unknown',
                'id': None,
                'country': 'us'
            }
            
            # 提取国家代码
            if len(path_parts) > 0:
                if len(path_parts[0]) == 2:  # 国家代码通常是2个字符
                    music_info['country'] = path_parts[0]
                    path_parts = path_parts[1:]
                
                # 提取音乐类型
                if len(path_parts) > 0:
                    if path_parts[0] in ['album', 'playlist', 'song']:
                        music_info['type'] = path_parts[0]
                        if len(path_parts) > 1:
                            music_info['id'] = path_parts[1]
            
            # 从查询参数中提取 ID
            query_params = parse_qs(parsed.query)
            if 'i' in query_params:
                music_info['id'] = query_params['i'][0]
            
            logger.info(f"📱 提取的 Apple Music 信息: {music_info}")
            return music_info
            
        except Exception as e:
            logger.error(f"❌ 提取音乐信息失败: {e}")
            return {'url': url, 'type': 'unknown', 'id': None, 'country': 'us'}
    
    async def download_music(self, url: str, progress_callback=None) -> Dict[str, Any]:
        """
        下载 Apple Music 音乐
        
        Args:
            url: Apple Music 链接
            progress_callback: 进度回调函数
            
        Returns:
            下载结果字典
        """
        if not self.gamdl_available:
            return {
                "success": False,
                "error": "gamdl 未安装或不可用"
            }
        
        if not self.is_apple_music_url(url):
            return {
                "success": False,
                "error": "不是有效的 Apple Music 链接"
            }
        
        try:
            # 提取音乐信息
            music_info = self.extract_music_info(url)
            
            # 发送开始下载消息
            if progress_callback:
                start_text = (
                    f"🍎 **开始下载 Apple Music**\n"
                    f"📝 类型: `{music_info['type']}`\n"
                    f"🌍 地区: `{music_info['country']}`\n"
                    f"🔗 链接: `{url}`"
                )
                await self._safe_callback(progress_callback, start_text)
            
            # 记录下载前的文件
            before_files = set()
            if self.output_dir.exists():
                for file_path in self.output_dir.rglob("*"):
                    if file_path.is_file():
                        relative_path = str(file_path.relative_to(self.output_dir))
                        before_files.add(relative_path)
            
            logger.info(f"📊 下载前文件数量: {len(before_files)}")
            
            # 构建 gamdl 命令
            cmd = ['gamdl']
            
            # 添加 cookies 参数
            if self.cookies_path and os.path.exists(self.cookies_path):
                cmd.extend(['--cookies-path', self.cookies_path])
                logger.info(f"🍪 使用 cookies 文件: {self.cookies_path}")
            else:
                logger.warning("⚠️ 未提供 cookies 文件，下载可能失败")
            
            # 添加输出路径
            if self.output_dir:
                cmd.extend(['--output-path', str(self.output_dir)])
            
            # 添加封面选项
            if self.default_options['cover']:
                cmd.append('--save-cover')
            
            # 添加网络优化参数
            cmd.extend(['--log-level', 'INFO'])  # 设置日志级别
            
            # 添加 URL
            cmd.append(url)
            
            logger.info(f"🍎 执行命令: {' '.join(cmd)}")
            
            # 创建进度监控任务
            progress_task = None
            if progress_callback:
                progress_task = asyncio.create_task(self._monitor_progress(
                    self.output_dir, before_files, progress_callback, music_info
                ))
            
            try:
                # 使用超时机制执行 gamdl 命令，添加重试机制
                max_retries = 3
                retry_count = 0
                
                while retry_count < max_retries:
                    logger.info(f"🍎 第 {retry_count + 1} 次尝试下载...")
                    
                    def run_gamdl():
                        # Docker 环境使用更长的超时时间
                        timeout = self.default_options.get('timeout', 600)
                        return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
                    
                    loop = asyncio.get_running_loop()
                    process = await loop.run_in_executor(None, run_gamdl)
                    
                    # 检查是否成功下载
                    if process.returncode == 0:
                        # 等待文件写入完成
                        await asyncio.sleep(3)
                        
                        # 检查是否有新文件下载
                        current_files = set()
                        if self.output_dir.exists():
                            for file_path in self.output_dir.rglob("*"):
                                if file_path.is_file():
                                    relative_path = str(file_path.relative_to(self.output_dir))
                                    current_files.add(relative_path)
                        
                        new_files = current_files - before_files
                        if len(new_files) > 0:
                            # 有文件下载，检查质量
                            if self._check_download_quality():
                                logger.info(f"🍎 第 {retry_count + 1} 次下载成功且质量正常")
                                break  # 下载成功且质量正常
                            else:
                                logger.warning(f"🍎 第 {retry_count + 1} 次下载质量异常，重试...")
                        else:
                            logger.warning(f"🍎 第 {retry_count + 1} 次下载没有产生新文件，重试...")
                    else:
                        logger.warning(f"🍎 第 {retry_count + 1} 次下载失败，返回码: {process.returncode}")
                    
                    retry_count += 1
                    if retry_count < max_retries:
                        # Docker 环境使用更长的重试延迟
                        retry_delay = self.default_options.get('retry_delay', 5)
                        logger.info(f"🍎 等待 {retry_delay} 秒后重试...")
                        await asyncio.sleep(retry_delay)
                
                if retry_count >= max_retries:
                    logger.error("❌ 下载重试次数已达上限，下载失败")
                    return {
                        "success": False,
                        "error": "下载重试失败，文件可能损坏"
                    }
                
                logger.info(f"🍎 gamdl 命令执行完成，返回码: {process.returncode}")
                
                if process.stdout:
                    logger.info(f"🍎 标准输出: {process.stdout[:500]}...")
                if process.stderr:
                    logger.warning(f"🍎 标准错误: {process.stderr[:500]}...")
                
            except subprocess.TimeoutExpired:
                logger.error("❌ gamdl 命令执行超时（5分钟）")
                # 取消进度监控任务
                if progress_task:
                    progress_task.cancel()
                return {
                    "success": False,
                    "error": "下载超时，请检查网络连接或链接有效性"
                }
            except Exception as e:
                logger.error(f"❌ gamdl 命令执行失败: {e}")
                # 取消进度监控任务
                if progress_task:
                    progress_task.cancel()
                return {
                    "success": False,
                    "error": f"命令执行失败: {str(e)}"
                }
            
            # 等待文件写入完成
            await asyncio.sleep(3)
            
            # 取消进度监控任务
            if progress_task:
                progress_task.cancel()
                try:
                    await progress_task
                except asyncio.CancelledError:
                    pass
            
            # 计算下载结果
            current_files = set()
            if self.output_dir.exists():
                for file_path in self.output_dir.rglob("*"):
                    if file_path.is_file():
                        relative_path = str(file_path.relative_to(self.output_dir))
                        current_files.add(relative_path)
            
            new_files = current_files - before_files
            files_count = len(new_files)
            
            if files_count == 0:
                return {
                    "success": False,
                    "error": f"没有下载到任何文件 (命令返回码: {process.returncode})"
                }
            
            # 计算总大小和文件格式
            total_size = 0
            file_formats = set()
            files_info = []
            
            for file_path in new_files:
                full_path = self.output_dir / file_path
                if full_path.exists():
                    file_size = full_path.stat().st_size
                    total_size += file_size
                    
                    # 提取文件格式
                    ext = full_path.suffix.lower().lstrip('.')
                    if ext:
                        file_formats.add(ext.upper())
                    
                    files_info.append({
                        'path': str(full_path),
                        'size': file_size,
                        'filename': full_path.name
                    })
            
            # 发送完成消息
            if progress_callback:
                final_text = (
                    f"✅ **Apple Music 下载完成**\n"
                    f"📝 类型: `{music_info['type']}`\n"
                    f"🌍 地区: `{music_info['country']}`\n"
                    f"🎵 文件数量: `{files_count} 个`\n"
                    f"💾 总大小: `{total_size / (1024*1024):.2f} MB`\n"
                    f"📄 文件格式: `{', '.join(file_formats)}`"
                )
                await self._safe_callback(progress_callback, final_text)
            
            return {
                "success": True,
                "music_type": music_info['type'],
                "country": music_info['country'],
                "files_count": files_count,
                "total_size": total_size,
                "file_formats": list(file_formats),
                "files": files_info,
                "download_path": str(self.output_dir)
            }
            
        except Exception as e:
            logger.error(f"❌ Apple Music 下载失败: {e}")
            return {
                "success": False,
                "error": f"下载失败: {str(e)}"
            }
    
    async def _monitor_progress(self, download_dir: Path, before_files: set, 
                               progress_callback, music_info: Dict[str, Any]):
        """监控下载进度"""
        try:
            last_count = 0
            last_update_time = time.time()
            update_interval = 1.0  # 1秒更新一次
            last_progress_text = ""  # 记录上次发送的进度文本
            start_time = time.time()
            
            while True:
                await asyncio.sleep(1)
                
                # 计算当前文件数量
                current_files = set()
                if download_dir.exists():
                    for file_path in download_dir.rglob("*"):
                        if file_path.is_file():
                            relative_path = str(file_path.relative_to(download_dir))
                            current_files.add(relative_path)
                
                # 计算新文件数量
                new_files = current_files - before_files
                current_count = len(new_files)
                
                # 如果文件数量有变化或时间间隔到了，更新进度
                if current_count != last_count or time.time() - last_update_time > update_interval:
                    last_count = current_count
                    last_update_time = time.time()
                    
                    # 获取当前正在下载的文件信息
                    current_file_info = self._get_current_download_info(download_dir, new_files)
                    
                    # 计算进度百分比
                    progress_percent = self._calculate_progress_percent(current_count, music_info['type'])
                    
                    # 计算下载速度
                    download_speed = self._calculate_download_speed(start_time, current_count)
                    
                    # 计算预计剩余时间
                    eta = self._calculate_eta(download_speed, current_count, music_info['type'])
                    
                    # 构建进度条
                    progress_bar = self._build_progress_bar(progress_percent)
                    
                    progress_text = (
                        f"🍎 **Apple Music 下载中**\n"
                        f"📝 文件: {current_file_info['filename']}\n"
                        f"💾 大小: {current_file_info['size_mb']:.2f}MB / {current_file_info['total_mb']:.2f}MB\n"
                        f"⚡️ 速度: {download_speed:.2f}MB/s\n"
                        f"⏳ 预计剩余: {eta}\n"
                        f"📊 进度: {progress_bar} {progress_percent:.1f}%"
                    )
                    
                    # 只有当进度文本发生变化时才发送
                    if progress_text != last_progress_text:
                        await self._safe_callback(progress_callback, progress_text)
                        last_progress_text = progress_text
                        logger.debug(f"🍎 进度更新: {current_count} 个文件, {progress_percent:.1f}%")
                    else:
                        logger.debug(f"🍎 进度无变化，跳过发送")
                    
        except asyncio.CancelledError:
            logger.info("📊 进度监控任务已取消")
        except Exception as e:
            logger.error(f"❌ 进度监控任务错误: {e}")
    
    async def _safe_callback(self, callback, text):
        """安全调用回调函数"""
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(text)
            else:
                callback(text)
        except Exception as e:
            # 如果是 Telegram 的 "Message is not modified" 错误，记录为 debug 级别
            if "Message is not modified" in str(e):
                logger.debug(f"🍎 进度消息未变化，跳过更新: {e}")
            else:
                logger.warning(f"⚠️ 回调函数调用失败: {e}")
    
    def set_options(self, **kwargs):
        """设置下载选项"""
        for key, value in kwargs.items():
            if key in self.default_options:
                self.default_options[key] = value
                logger.info(f"🔧 设置 {key}: {value}")
    
    def get_options(self) -> Dict[str, Any]:
        """获取当前下载选项"""
        return self.default_options.copy()
    
    def _get_current_download_info(self, download_dir: Path, new_files: set) -> Dict[str, Any]:
        """获取当前下载文件的信息"""
        if not new_files:
            return {
                'filename': '准备中...',
                'size_mb': 0.0,
                'total_mb': 0.0
            }
        
        # 获取最新的文件
        latest_file = sorted(new_files)[-1]
        file_path = download_dir / latest_file
        
        # 计算当前文件大小
        current_size = 0
        if file_path.exists():
            current_size = file_path.stat().st_size
        
        # 估算总大小（基于文件类型）
        total_size = self._estimate_total_size(len(new_files))
        
        return {
            'filename': latest_file,
            'size_mb': current_size / (1024 * 1024),
            'total_mb': total_size / (1024 * 1024)
        }
    
    def _estimate_total_size(self, file_count: int) -> int:
        """估算总文件大小"""
        # 基于经验值估算
        if file_count <= 1:
            return 10 * 1024 * 1024  # 10MB
        elif file_count <= 3:
            return 15 * 1024 * 1024  # 15MB
        else:
            return file_count * 8 * 1024 * 1024  # 每首歌约8MB
    
    def _calculate_progress_percent(self, current_count: int, music_type: str) -> float:
        """计算下载进度百分比"""
        if music_type == 'album':
            # 专辑通常有10-20首歌
            estimated_total = 15
        else:
            # 单曲
            estimated_total = 3  # 音频文件、封面、歌词
        
        progress = min(current_count / estimated_total * 100, 100.0)
        return progress
    
    def _calculate_download_speed(self, start_time: float, current_count: int) -> float:
        """计算下载速度 (MB/s)"""
        elapsed_time = time.time() - start_time
        if elapsed_time <= 0:
            return 0.0
        
        # 估算已下载的数据量
        downloaded_mb = current_count * 8  # 假设每个文件约8MB
        speed = downloaded_mb / elapsed_time
        return speed
    
    def _calculate_eta(self, speed: float, current_count: int, music_type: str) -> str:
        """计算预计剩余时间"""
        if speed <= 0:
            return "计算中..."
        
        if music_type == 'album':
            estimated_total = 15
        else:
            estimated_total = 3
        
        remaining_files = max(0, estimated_total - current_count)
        remaining_mb = remaining_files * 8  # 假设每个文件约8MB
        
        if remaining_mb <= 0:
            return "00:00"
        
        remaining_seconds = remaining_mb / speed
        minutes = int(remaining_seconds // 60)
        seconds = int(remaining_seconds % 60)
        
        return f"{minutes:02d}:{seconds:02d}"
    
    def _build_progress_bar(self, percent: float) -> str:
        """构建进度条"""
        bar_length = 20
        filled_length = int(bar_length * percent / 100)
        
        bar = "█" * filled_length + "░" * (bar_length - filled_length)
        return bar

async def main():
    """主函数 - 用于测试"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Apple Music 音乐下载器')
    parser.add_argument('urls', nargs='*', help='要下载的 Apple Music 链接')
    parser.add_argument('-d', '--dir', default='./downloads/apple_music', help='下载目录')
    parser.add_argument('-q', '--quality', choices=['128', '256', '320'], default='256', help='音质')
    parser.add_argument('-f', '--format', choices=['mp3', 'm4a', 'flac'], default='mp3', help='格式')
    parser.add_argument('--no-cover', action='store_true', help='不下载封面')
    parser.add_argument('--no-lyrics', action='store_true', help='不下载歌词')
    
    args = parser.parse_args()
    
    downloader = AppleMusicDownloader(output_dir=args.dir)
    
    # 设置下载选项
    downloader.set_options(
        quality=args.quality,
        format=args.format,
        cover=not args.no_cover,
        lyrics=not args.no_lyrics
    )
    
    # 如果没有通过命令行提供URL，使用交互式输入
    urls = args.urls
    if not urls:
        print("请输入 Apple Music 链接（输入 'quit' 退出）:")
        while True:
            url = input("URL: ").strip()
            if url.lower() == 'quit':
                break
            if url:
                urls.append(url)
    
    if not urls:
        print("没有提供任何链接")
        return
    
    print(f"准备下载 {len(urls)} 个 Apple Music 链接到目录: {args.dir}")
    print(f"下载选项: 音质={args.quality}, 格式={args.format}, 封面={not args.no_cover}, 歌词={not args.no_lyrics}")
    
    # 创建简单的进度回调函数
    async def progress_callback(text):
        print(f"🍎 进度: {text}")
    
    success_count = 0
    for i, url in enumerate(urls, 1):
        try:
            print(f"\n[{i}/{len(urls)}] 处理链接: {url}")
            
            result = await downloader.download_music(url, progress_callback)
            if result.get("success"):
                success_count += 1
                print(f"✅ 下载成功: {result.get('music_type', '未知类型')}")
            else:
                print(f"❌ 下载失败: {result.get('error', '未知错误')}")
            
            time.sleep(2)  # 避免请求过快
        except Exception as e:
            print(f"处理链接失败 {url}: {e}")
    
    print(f"\n完成！成功下载 {success_count}/{len(urls)} 个链接")

if __name__ == "__main__":
    asyncio.run(main())

