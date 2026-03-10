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
        tasks = [
            self._download_with_semaphore(url, i, get_ydl_opts_func, progress_callback)
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
        get_ydl_opts_func: Callable,
        progress_callback: Callable
    ) -> Dict[str, Any]:
        """带信号量控制的下载"""
        async with self.semaphore:
            logger.info(f"📥 [{index+1}] 开始下载：{url}")
            
            try:
                # 获取 yt-dlp 选项
                ydl_opts = get_ydl_opts_func(url)
                
                # 应用多线程优化
                if hasattr(self.downloader, 'get_yt_dlp_options'):
                    ydl_opts = self.downloader.get_yt_dlp_options(ydl_opts)
                
                # 下载
                result = await self.downloader.download_with_progress(
                    url=url,
                    output_template=self._generate_output_template(url),
                    ydl_opts=ydl_opts,
                    progress_callback=progress_callback
                )
                
                result['index'] = index
                result['url'] = url
                
                return result
                
            except Exception as e:
                logger.error(f"❌ [{index+1}] 下载失败：{e}")
                return {
                    'success': False,
                    'error': str(e),
                    'index': index,
                    'url': url
                }
    
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
            summary += f"\n📁 下载的文件:\n"
            for result in success_results[:5]:  # 只显示前 5 个
                filename = result.get('output', '未知')
                size = result.get('file_size', 0)
                size_mb = size / (1024 * 1024)
                summary += f"• {filename.split('/')[-1]} ({size_mb:.1f} MB)\n"
            
            if len(success_results) > 5:
                summary += f"... 还有 {len(success_results) - 5} 个文件\n"
        
        return summary
