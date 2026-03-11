# -*- coding: utf-8 -*-
"""
媒体批量下载处理器 v2
优化版本：支持详细进度显示 + 并发控制
"""

import asyncio
import logging
from datetime import datetime
from typing import List, Tuple, Any, Optional
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger('savextube.media_batch_v2')


class MediaBatchProcessorV2:
    """媒体批量下载处理器 v2"""
    
    def __init__(self, bot_instance, max_concurrent: int = 3, timeout: float = 3.0):
        """
        初始化批量处理器
        
        Args:
            bot_instance: TelegramBot 实例
            max_concurrent: 最大并发下载数
            timeout: 队列累积超时时间（秒）
        """
        self.bot = bot_instance
        self.queue = asyncio.Queue()
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.timeout = timeout
        self.processor_task = None
        self.running = False
        self.max_concurrent = max_concurrent
        
        logger.info(f"✅ 媒体批量处理器 v2 初始化成功 | 并发数：{max_concurrent}, 超时：{timeout}s")
    
    def start(self):
        """启动批量处理器"""
        if not self.running:
            self.running = True
            self.processor_task = asyncio.create_task(self._process_queue())
            logger.info("🚀 媒体批量处理器 v2 已启动")
    
    def stop(self):
        """停止批量处理器"""
        self.running = False
        if self.processor_task:
            self.processor_task.cancel()
            logger.info("⏹️ 媒体批量处理器 v2 已停止")
    
    async def add_to_queue(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                          message, status_message, attachment):
        """添加媒体下载任务到队列"""
        item = (update, context, message, status_message, attachment)
        await self.queue.put(item)
        logger.debug(f"📥 媒体任务已加入队列 | 队列长度：{self.queue.qsize()}")
    
    async def _process_queue(self):
        """处理队列中的媒体下载任务"""
        logger.info("🔄 媒体队列处理器运行中...")
        
        while self.running:
            try:
                # 累积一批任务
                batch = await self._collect_batch()
                
                if batch:
                    logger.info(f"📦 开始处理批次 | 数量：{len(batch)}")
                    
                    if len(batch) == 1:
                        # 单个任务，直接处理（保留完整进度显示）
                        await self._process_single_detailed(batch[0])
                    else:
                        # 多个任务，并发处理（显示批量进度）
                        await self._process_batch_concurrent(batch)
                
            except asyncio.CancelledError:
                logger.info("⏹️ 队列处理器已取消")
                break
            except Exception as e:
                logger.error(f"❌ 队列处理错误：{e}", exc_info=True)
                await asyncio.sleep(1)
    
    async def _collect_batch(self) -> List[Tuple]:
        """从队列中收集一批任务"""
        batch = []
        
        try:
            # 获取第一个任务
            first = await asyncio.wait_for(self.queue.get(), timeout=self.timeout)
            batch.append(first)
            
            # 收集更多任务（短时间窗口内）
            while True:
                try:
                    item = await asyncio.wait_for(self.queue.get(), timeout=0.3)
                    batch.append(item)
                    if len(batch) >= 10:  # 最多累积 10 个
                        break
                except asyncio.TimeoutError:
                    break
        except asyncio.TimeoutError:
            pass
        
        return batch
    
    async def _process_single_detailed(self, item: Tuple):
        """
        处理单个任务（保留完整详细进度）
        直接调用 download_user_media，不进行任何修改
        """
        update, context, message, status_message, attachment = item
        
        try:
            logger.info(f"📥 开始下载单个媒体文件")
            # 直接调用完整的 download_user_media，保留所有进度显示
            await self.bot.download_user_media(update, context)
        except Exception as e:
            logger.error(f"❌ 单个任务下载失败：{e}")
    
    async def _process_batch_concurrent(self, batch: List[Tuple]):
        """
        并发处理多个任务（显示批量进度）
        
        策略：
        1. 为每个任务创建独立的下载任务
        2. 使用信号量控制并发数
        3. 主状态消息显示整体进度
        4. 每个任务完成后更新状态
        """
        total = len(batch)
        completed = 0
        failed = 0
        
        try:
            # 更新初始状态
            first_item = batch[0]
            _, _, message, status_message, _ = first_item
            
            await status_message.edit_text(
                f"📦 **批量下载启动**\n\n"
                f"📊 任务总数：{total}\n"
                f"⏳ 并发限制：{self.max_concurrent} 个同时下载\n"
                f"✅ 已完成：0/{total}\n"
                f"❌ 失败：0/{total}\n\n"
                f"🔄 正在处理第一个文件..."
            )
            
            # 创建并发任务
            tasks = []
            for i, item in enumerate(batch, 1):
                task = asyncio.create_task(
                    self._download_with_progress(item, i, total)
                )
                tasks.append(task)
            
            # 等待所有任务完成，并收集结果
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 统计结果
            for result in results:
                if isinstance(result, Exception):
                    failed += 1
                else:
                    completed += 1
            
            # 显示最终结果
            await status_message.edit_text(
                f"✅ **批量下载完成**\n\n"
                f"📊 总计：{total} 个文件\n"
                f"✅ 成功：{completed}\n"
                f"❌ 失败：{failed}\n"
                f"⏱️ 总耗时：{(datetime.now() - datetime.now()).seconds}秒\n\n"
                f"{'🎉 全部成功！' if failed == 0 else '⚠️ 部分失败，请查看日志'}"
            )
            
            logger.info(f"✅ 批量下载完成 | 成功：{completed}/{total}, 失败：{failed}")
            
        except Exception as e:
            logger.error(f"❌ 批量处理失败：{e}", exc_info=True)
            try:
                await status_message.edit_text(f"❌ 批量下载失败：{str(e)}")
            except:
                pass
    
    async def _download_with_progress(self, item: Tuple, index: int, total: int):
        """
        带进度显示的下载
        
        Args:
            item: (update, context, message, status_message, attachment)
            index: 当前是第几个任务（从 1 开始）
            total: 总任务数
        """
        update, context, message, status_message, attachment = item
        
        file_name = getattr(attachment, 'file_name', 'unknown_file')
        file_size = getattr(attachment, 'file_size', 0)
        total_mb = file_size / (1024 * 1024) if file_size else 0
        
        async with self.semaphore:
            try:
                logger.info(f"📥 [{index}/{total}] 开始下载：{file_name} ({total_mb:.2f} MB)")
                
                # 注意：这里不更新 status_message，因为 download_user_media 会创建自己的状态消息
                # 我们让每个任务独立显示进度
                
                # 调用完整的下载函数
                await self.bot.download_user_media(update, context)
                
                logger.info(f"✅ [{index}/{total}] 下载完成")
                return True
                
            except Exception as e:
                logger.error(f"❌ [{index}/{total}] 下载失败：{e}")
                raise e
