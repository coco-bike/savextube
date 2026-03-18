# -*- coding: utf-8 -*-
"""
多线程下载增强模块
为 SaveXTube 添加多线程下载支持，提升下载速度

功能：
1. 支持多线程下载单个文件（使用 aria2c 或 yt-dlp 内置并发）
2. 支持并发下载多个任务
3. 可配置的线程数和并发数
"""

import os
import subprocess
import asyncio
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from pathlib import Path
import time

logger = logging.getLogger(__name__)


@dataclass
class DownloadConfig:
    """下载配置"""
    # 单个文件下载的线程数（aria2c 分片数）
    file_threads: int = 16
    # 同时下载的文件数量（并发任务数）
    concurrent_files: int = 3
    # 是否使用 aria2c 加速器
    use_aria2c: bool = True
    # aria2c 服务器连接数
    aria2c_connections: int = 16
    # 每个服务器的分片数
    aria2c_splits: int = 16
    # 最小分片大小
    aria2c_min_split_size: str = "1M"
    # 下载速度限制（0 表示不限制），格式：500K, 1M, 10M
    speed_limit: str = "0"
    # 重试次数
    retries: int = 5
    # 超时时间（秒）
    timeout: int = 60


class MultiThreadDownloader:
    """多线程下载器"""
    
    def __init__(self, config: Optional[DownloadConfig] = None):
        """
        初始化多线程下载器
        
        Args:
            config: 下载配置，None 则使用默认配置
        """
        self.config = config or DownloadConfig()
        self.aria2c_path = None
        self._check_aria2c()
    
    def _check_aria2c(self):
        """检查 aria2c 是否可用"""
        try:
            result = subprocess.run(
                ['aria2c', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                self.aria2c_path = 'aria2c'
                logger.info(f"✅ aria2c 可用：{result.stdout.split()[0]}")
            else:
                logger.warning("⚠️ aria2c 不可用，将使用 yt-dlp 内置下载")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            logger.warning("⚠️ aria2c 未安装，将使用 yt-dlp 内置下载")
            logger.info("💡 安装 aria2c 可以获得更快的下载速度：")
            logger.info("   Ubuntu/Debian: sudo apt install aria2")
            logger.info("   CentOS/RHEL: sudo yum install aria2")
            logger.info("   macOS: brew install aria2")
    
    def get_yt_dlp_options(self, base_options: Optional[Dict] = None) -> Dict:
        """
        获取优化后的 yt-dlp 下载选项
        
        Args:
            base_options: 基础选项，会被多线程优化选项覆盖
        
        Returns:
            优化后的 yt-dlp 选项字典
        """
        options = base_options.copy() if base_options else {}
        
        # 如果使用 aria2c 作为外部下载器
        if self.config.use_aria2c and self.aria2c_path:
            logger.info(f"🚀 启用 aria2c 多线程下载（{self.config.file_threads}线程）")

            # Python API 中 external_downloader_args 需要传 aria2c 的真实参数
            # 不能传 yt-dlp CLI 形态的 --aria2c-args=... 字符串。
            aria2c_opts = [
                f'-x{self.config.file_threads}',
                f'-s{self.config.aria2c_splits}',
                '-k1M',
                '-c',
                f'--min-split-size={self.config.aria2c_min_split_size}',
                f'--max-connection-per-server={self.config.aria2c_connections}',
                '--download-result=hide',
            ]

            # 如果有速度限制
            if self.config.speed_limit and self.config.speed_limit != "0":
                aria2c_opts.append(f'--max-download-limit={self.config.speed_limit}')

            options['external_downloader'] = 'aria2c'
            options['external_downloader_args'] = {'default': aria2c_opts}
        else:
            # 使用 yt-dlp 内置的并发下载
            logger.info(f"📥 使用 yt-dlp 内置下载（{self.config.file_threads}分片）")
            options['hls_use_mpegts'] = True
            options['http_chunk_size'] = '10M'
            options['concurrent_fragment_downloads'] = max(1, min(self.config.file_threads, 32))
        
        # 通用优化选项
        options.update({
            'retries': self.config.retries,
            'socket_timeout': self.config.timeout,
            'fragment_retries': self.config.retries,
            'continuedl': True,  # 支持断点续传
            'nopart': False,  # 保留.part 文件以便断点续传
        })
        
        return options
    
    async def download_with_progress(
        self,
        url: str,
        output_template: str,
        ydl_opts: Dict,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        带进度回调的下载
        
        Args:
            url: 下载链接
            output_template: 输出文件模板
            ydl_opts: yt-dlp 选项
            progress_callback: 进度回调函数
        
        Returns:
            下载结果字典
        """
        import yt_dlp
        
        result = {
            'success': False,
            'url': url,
            'output': output_template,
            'error': None,
            'start_time': time.time(),
            'end_time': None,
            'duration': None,
            'file_size': 0,
            'final_filename': None,
            'title': None,
            'resolution': '未知',
            'quality': None,
            'bitrate': None,
            'thumbnail': None,
            'duration': None,
        }

        progress_snapshot = {
            'final_filename': None,
            'title': None,
            'resolution': '未知',
            'quality': None,
            'bitrate': None,
            'thumbnail': None,
            'duration': None,
            'total_bytes': 0,
        }

        # 获取当前事件循环（必须在定义 progress_hook 之前）
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        # 添加进度钩子
        def progress_hook(d):
            status = d.get('status', 'unknown')
            info = d.get('info_dict') or {}

            # 提取视频信息（仅在第一次或信息变化时）
            if info:
                new_title = info.get('title')
                if new_title and new_title != progress_snapshot['title']:
                    progress_snapshot['title'] = new_title
                    logger.info(f"🎬 开始下载: {new_title}")

                progress_snapshot['resolution'] = (
                    info.get('resolution')
                    or (f"{info.get('width')}x{info.get('height')}" if info.get('width') and info.get('height') else None)
                    or progress_snapshot['resolution']
                )
                progress_snapshot['quality'] = info.get('format_note') or info.get('format') or progress_snapshot['quality']
                progress_snapshot['bitrate'] = (
                    info.get('abr')
                    or info.get('tbr')
                    or progress_snapshot['bitrate']
                )
                progress_snapshot['thumbnail'] = info.get('thumbnail') or progress_snapshot['thumbnail']
                progress_snapshot['duration'] = info.get('duration') or progress_snapshot['duration']

            # 构建增强的进度数据
            enhanced_d = dict(d)
            enhanced_d['_title'] = progress_snapshot['title']
            enhanced_d['_resolution'] = progress_snapshot['resolution']
            enhanced_d['_quality'] = progress_snapshot['quality']

            if status == 'downloading':
                downloaded = d.get('downloaded_bytes', 0)
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                progress_snapshot['total_bytes'] = total or progress_snapshot['total_bytes']
                speed = d.get('speed', 0) or 0
                eta = d.get('eta', 0) or 0

                if total > 0:
                    percent = (downloaded / total) * 100
                    # 每 5% 或速度变化超过 20% 时记录日志
                    prev_percent = getattr(progress_hook, '_last_percent', 0)
                    prev_speed = getattr(progress_hook, '_last_speed', 0)

                    if abs(percent - prev_percent) >= 5 or abs(speed - prev_speed) / max(prev_speed, 1) > 0.2:
                        logger.info(
                            f"📥 下载进度: {percent:.1f}% | "
                            f"已下载: {self._format_size(downloaded)} / {self._format_size(total)} | "
                            f"速度: {self._format_speed(speed)} | "
                            f"剩余: {self._format_time(eta)}"
                        )
                        progress_hook._last_percent = percent
                        progress_hook._last_speed = speed

                    # 添加格式化后的进度信息到回调数据
                    enhanced_d['_percent'] = percent
                    enhanced_d['_downloaded_str'] = self._format_size(downloaded)
                    enhanced_d['_total_str'] = self._format_size(total)
                    enhanced_d['_speed_str'] = self._format_speed(speed)
                    enhanced_d['_eta_str'] = self._format_time(eta)

            elif status == 'finished':
                progress_snapshot['final_filename'] = d.get('filename') or progress_snapshot['final_filename']
                final_size = d.get('total_bytes', 0)
                logger.info(
                    f"✅ 下载完成: {progress_snapshot['title'] or '未知'} | "
                    f"文件: {os.path.basename(d.get('filename', 'unknown'))} | "
                    f"大小: {self._format_size(final_size)}"
                )

            # 调用上层回调（传递增强后的数据）
            if progress_callback and loop:
                try:
                    if asyncio.iscoroutinefunction(progress_callback):
                        asyncio.run_coroutine_threadsafe(progress_callback(enhanced_d), loop)
                    else:
                        callback_result = progress_callback(enhanced_d)
                        if asyncio.iscoroutine(callback_result):
                            asyncio.run_coroutine_threadsafe(callback_result, loop)
                except Exception as callback_error:
                    logger.warning(f"⚠️ 进度回调执行失败: {callback_error}")

        existing_hooks = ydl_opts.get('progress_hooks', [])
        if not isinstance(existing_hooks, list):
            existing_hooks = [existing_hooks]
        ydl_opts['progress_hooks'] = existing_hooks + [progress_hook]

        try:
            
            def download_task():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.download([url])
            
            await loop.run_in_executor(None, download_task)
            
            result['success'] = True
            result['end_time'] = time.time()
            result['duration'] = result['end_time'] - result['start_time']
            result['final_filename'] = progress_snapshot['final_filename']
            result['title'] = progress_snapshot['title']
            result['resolution'] = progress_snapshot['resolution']
            result['quality'] = progress_snapshot['quality']
            result['bitrate'] = progress_snapshot['bitrate']
            result['thumbnail'] = progress_snapshot['thumbnail']
            result['duration'] = progress_snapshot['duration']
            
            # 获取下载的文件大小
            result['file_size'] = self._get_downloaded_file_size(output_template)
            if result['file_size'] <= 0 and progress_snapshot['total_bytes']:
                result['file_size'] = progress_snapshot['total_bytes']
            
            logger.info(
                f"🎉 下载完成 | "
                f"耗时：{result['duration']:.2f}s | "
                f"大小：{self._format_size(result['file_size'])}"
            )
            
        except Exception as e:
            logger.error(f"❌ 下载失败：{e}")
            result['error'] = str(e)
            result['end_time'] = time.time()
            result['duration'] = result['end_time'] - result['start_time']
        
        return result
    
    async def download_multiple_files(
        self,
        urls: List[str],
        get_ydl_opts_func: callable,
        progress_callback: Optional[callable] = None,
        max_concurrent: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        并发下载多个文件
        
        Args:
            urls: URL 列表
            get_ydl_opts_func: 获取 yt-dlp 选项的函数
            progress_callback: 进度回调函数
            max_concurrent: 最大并发数，None 则使用配置值
        
        Returns:
            下载结果列表
        """
        concurrent = max_concurrent or self.config.concurrent_files
        logger.info(f"🚀 开始并发下载 {len(urls)} 个文件，最大并发：{concurrent}")
        
        # 创建信号量控制并发数
        semaphore = asyncio.Semaphore(concurrent)
        
        async def download_with_semaphore(url, index):
            async with semaphore:
                logger.info(f"📥 [{index+1}/{len(urls)}] 开始下载：{url}")
                
                # 获取该 URL 的 yt-dlp 选项
                ydl_opts = get_ydl_opts_func(url)
                # 应用多线程优化
                ydl_opts = self.get_yt_dlp_options(ydl_opts)
                
                # 生成输出模板
                output_template = self._generate_output_template(url)
                
                result = await self.download_with_progress(
                    url=url,
                    output_template=output_template,
                    ydl_opts=ydl_opts,
                    progress_callback=progress_callback
                )
                
                result['index'] = index
                return result
        
        # 创建所有下载任务
        tasks = [
            download_with_semaphore(url, i)
            for i, url in enumerate(urls)
        ]
        
        # 并发执行
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 统计结果
        success_count = sum(1 for r in results if isinstance(r, dict) and r.get('success'))
        fail_count = len(results) - success_count
        
        logger.info(
            f"🎉 并发下载完成 | "
            f"总数：{len(urls)} | "
            f"成功：{success_count} | "
            f"失败：{fail_count}"
        )
        
        return results
    
    def _generate_output_template(self, url: str) -> str:
        """生成输出文件模板"""
        # 默认模板，实际使用时应该根据平台和信息生成更精确的模板
        return "./downloads/%(title)s.%(ext)s"
    
    def _get_downloaded_file_size(self, output_template: str) -> int:
        """获取下载文件的总大小"""
        total_size = 0
        
        # 尝试查找匹配的文件
        base_path = Path(output_template.replace('%(title)s', '').replace('%(ext)s', '').strip('./'))
        
        if base_path.exists():
            for file in base_path.iterdir():
                if file.is_file():
                    total_size += file.stat().st_size
        
        return total_size
    
    @staticmethod
    def _format_speed(speed: float) -> str:
        """格式化速度显示"""
        if speed is None or speed == 0:
            return "0 B/s"
        
        units = ['B/s', 'KB/s', 'MB/s', 'GB/s']
        unit_index = 0
        speed_value = speed
        
        while speed_value >= 1024 and unit_index < len(units) - 1:
            speed_value /= 1024
            unit_index += 1
        
        return f"{speed_value:.2f} {units[unit_index]}"
    
    @staticmethod
    def _format_size(size: int) -> str:
        """格式化文件大小显示"""
        if size is None or size == 0:
            return "0 B"

        units = ['B', 'KB', 'MB', 'GB', 'TB']
        unit_index = 0
        size_value = float(size)

        while size_value >= 1024 and unit_index < len(units) - 1:
            size_value /= 1024
            unit_index += 1

        return f"{size_value:.2f} {units[unit_index]}"

    @staticmethod
    def _format_time(seconds: int) -> str:
        """格式化时间显示（秒转时分秒）"""
        if seconds is None or seconds <= 0:
            return "计算中..."

        if seconds < 60:
            return f"{int(seconds)}秒"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}分{secs}秒"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}小时{minutes}分"


def create_downloader(
    file_threads: int = 16,
    concurrent_files: int = 3,
    use_aria2c: bool = True
) -> MultiThreadDownloader:
    """
    创建多线程下载器的便捷函数
    
    Args:
        file_threads: 单个文件的下载线程数
        concurrent_files: 并发下载的文件数
        use_aria2c: 是否使用 aria2c
    
    Returns:
        MultiThreadDownloader 实例
    """
    config = DownloadConfig(
        file_threads=file_threads,
        concurrent_files=concurrent_files,
        use_aria2c=use_aria2c
    )
    return MultiThreadDownloader(config)
