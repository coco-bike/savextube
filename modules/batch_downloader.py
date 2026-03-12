# -*- coding: utf-8 -*-
"""
批量下载处理器
支持多个链接的并发下载
"""

import asyncio
import logging
from typing import List, Dict, Any, Callable
from pathlib import Path

logger = logging.getLogger(__name__)


class BatchDownloadProcessor:
    """批量下载处理器"""
    
    def __init__(self, multithread_downloader, max_concurrent: int = 3):
        """
        初始化批量下载处理器
        
        Args:
            multithread_downloader: 多线程下载器实例
            max_concurrent: 最大并发下载数
        """
        self.downloader = multithread_downloader
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
    
    async def download_batch(
        self,
        urls: List[str],
        get_ydl_opts_func: Callable,
        progress_callback: Callable = None
    ) -> List[Dict[str, Any]]:
        """
        批量下载多个链接
        
        Args:
            urls: URL 列表
            get_ydl_opts_func: 获取 yt-dlp 选项的函数
            progress_callback: 进度回调函数
            
        Returns:
            下载结果列表
        """
        logger.info(f"🚀 开始批量下载 {len(urls)} 个链接，最大并发：{self.max_concurrent}")
        
        # 创建下载任务
        total = len(urls)
        tasks = [
            self._download_with_semaphore(url, i, total, get_ydl_opts_func, progress_callback)
            for i, url in enumerate(urls)
        ]
        
        # 并发执行
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 统计结果
        success_count = sum(1 for r in results if isinstance(r, dict) and r.get('success'))
        fail_count = len(results) - success_count
        
        logger.info(f"✅ 批量下载完成 | 总数：{len(urls)} | 成功：{success_count} | 失败：{fail_count}")
        
        return results
    
    async def _download_with_semaphore(
        self,
        url: str,
        index: int,
        total: int,
        get_ydl_opts_func: Callable,
        progress_callback: Callable
    ) -> Dict[str, Any]:
        """带信号量控制的下载"""
        await self._emit_progress(progress_callback, {
            'status': 'queued',
            'url': url,
            'batch_index': index + 1,
            'batch_total': total,
        })

        async with self.semaphore:
            logger.info(f"📥 [{index+1}] 开始下载：{url}")

            await self._emit_progress(progress_callback, {
                'status': 'started',
                'url': url,
                'batch_index': index + 1,
                'batch_total': total,
            })
            
            try:
                # 获取 yt-dlp 选项
                ydl_opts = get_ydl_opts_func(url)
                
                # 应用多线程优化
                if hasattr(self.downloader, 'get_yt_dlp_options'):
                    ydl_opts = self.downloader.get_yt_dlp_options(ydl_opts)
                
                # 下载
                async def wrapped_progress_callback(payload):
                    if isinstance(payload, dict):
                        payload = {
                            **payload,
                            'url': url,
                            'batch_index': index + 1,
                            'batch_total': total,
                        }
                    await self._emit_progress(progress_callback, payload)

                result = await self.downloader.download_with_progress(
                    url=url,
                    output_template=self._generate_output_template(url),
                    ydl_opts=ydl_opts,
                    progress_callback=wrapped_progress_callback
                )
                
                result['index'] = index
                result['url'] = url

                await self._emit_progress(progress_callback, {
                    'status': 'result',
                    'success': result.get('success', False),
                    'error': result.get('error'),
                    'url': url,
                    'batch_index': index + 1,
                    'batch_total': total,
                    'output': result.get('output', ''),
                    'final_filename': result.get('final_filename'),
                    'title': result.get('title'),
                    'resolution': result.get('resolution', '未知'),
                    'quality': result.get('quality'),
                    'bitrate': result.get('bitrate'),
                    'thumbnail': result.get('thumbnail'),
                    'duration': result.get('duration'),
                    'file_size': result.get('file_size', 0),
                })
                
                return result
                
            except Exception as e:
                logger.error(f"❌ [{index+1}] 下载失败：{e}")
                await self._emit_progress(progress_callback, {
                    'status': 'error',
                    'error': str(e),
                    'url': url,
                    'batch_index': index + 1,
                    'batch_total': total,
                })
                return {
                    'success': False,
                    'error': str(e),
                    'index': index,
                    'url': url
                }

    async def _emit_progress(self, progress_callback: Callable, payload: Any):
        """兼容同步/异步回调，安全发送批量下载进度。"""
        if not progress_callback:
            return

        try:
            if asyncio.iscoroutinefunction(progress_callback):
                await progress_callback(payload)
                return

            callback_result = progress_callback(payload)
            if asyncio.iscoroutine(callback_result):
                await callback_result
        except Exception as callback_error:
            logger.warning(f"批量进度回调执行失败: {callback_error}")
    
    def _generate_output_template(self, url: str) -> str:
        """生成输出文件模板"""
        # 根据平台生成不同的模板
        from .url_extractor import URLExtractor
        
        if URLExtractor.is_youtube_url(url):
            return './downloads/YouTube/%(title)s.%(ext)s'
        elif URLExtractor.is_bilibili_url(url):
            return './downloads/Bilibili/%(title)s.%(ext)s'
        else:
            return './downloads/%(title)s.%(ext)s'
    
    def generate_summary(self, results: List[Dict[str, Any]]) -> str:
        """生成下载结果摘要"""
        if not results:
            return "❌ 未执行任何下载"
        
        success_results = [r for r in results if isinstance(r, dict) and r.get('success')]
        fail_results = [r for r in results if isinstance(r, dict) and not r.get('success')]
        
        summary = f"✅ 批量下载完成\n\n"
        summary += f"📊 总计：{len(results)}\n"
        summary += f"✅ 成功：{len(success_results)}\n"
        
        if fail_results:
            summary += f"❌ 失败：{len(fail_results)}\n"

        if success_results:
            summary += "\n📁 成功任务详情:\n"
            max_items = 5
            for idx, result in enumerate(success_results[:max_items], start=1):
                title = result.get('title') or '未知标题'
                filename = result.get('final_filename') or result.get('output') or '未知文件'
                filename = filename.split('/')[-1]
                size_text = self._format_size(result.get('file_size', 0))
                resolution = result.get('resolution', '未知')
                bitrate = self._format_bitrate(result.get('bitrate'))
                duration = self._format_duration(result.get('duration'))

                summary += (
                    f"\n✅ 任务 {idx}\n"
                    f"🏷 标题: {title}\n"
                    f"📝 文件名: {filename}\n"
                    f"💾 大小: {size_text}\n"
                    f"🎥 分辨率: {resolution}\n"
                )
                if bitrate:
                    summary += f"🎵 码率: {bitrate}\n"
                if duration:
                    summary += f"⏱ 时长: {duration}\n"

            if len(success_results) > max_items:
                summary += f"\n... 还有 {len(success_results) - max_items} 个成功任务未展开\n"

        if fail_results:
            summary += "\n❌ 失败任务详情:\n"
            max_fail_items = 3
            for idx, result in enumerate(fail_results[:max_fail_items], start=1):
                url = result.get('url', '未知链接')
                error = result.get('error', '未知错误')
                summary += (
                    f"\n❌ 任务 {idx}\n"
                    f"🔗 链接: {url}\n"
                    f"⚠️ 错误: {error}\n"
                )
            if len(fail_results) > max_fail_items:
                summary += f"\n... 还有 {len(fail_results) - max_fail_items} 个失败任务未展开\n"

        return summary

    @staticmethod
    def _format_size(size: int) -> str:
        """格式化文件大小显示。"""
        if not size:
            return "未知"

        units = ["B", "KB", "MB", "GB", "TB"]
        value = float(size)
        unit_idx = 0
        while value >= 1024 and unit_idx < len(units) - 1:
            value /= 1024
            unit_idx += 1
        return f"{value:.2f} {units[unit_idx]}"

    @staticmethod
    def _format_bitrate(bitrate_value) -> str:
        """格式化码率。"""
        if isinstance(bitrate_value, (int, float)) and bitrate_value > 0:
            return f"{int(bitrate_value)}kbps"
        return ""

    @staticmethod
    def _format_duration(duration_value) -> str:
        """格式化时长。"""
        if not isinstance(duration_value, (int, float)) or duration_value <= 0:
            return ""
        seconds = int(duration_value)
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"
