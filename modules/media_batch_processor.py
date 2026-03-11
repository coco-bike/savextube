# -*- coding: utf-8 -*-
"""
媒体批量下载处理器
支持 Telegram 媒体文件的批量并发下载
"""

import asyncio
import logging
from typing import List, Tuple, Any
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


class MediaBatchProcessor:
    """媒体批量下载处理器"""
    
    def __init__(self, bot_instance, max_concurrent: int = 3, timeout: float = 5.0):
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
        
        logger.info(f"✅ 媒体批量处理器初始化成功 | 并发数：{max_concurrent}, 超时：{timeout}s")
    
    def start(self):
        """启动批量处理器"""
        if not self.running:
            self.running = True
            self.processor_task = asyncio.create_task(self._process_queue())
            logger.info("🚀 媒体批量处理器已启动")
    
    def stop(self):
        """停止批量处理器"""
        self.running = False
        if self.processor_task:
            self.processor_task.cancel()
            logger.info("⏹️ 媒体批量处理器已停止")
    
    async def add_to_queue(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                          message, status_message, attachment):
        """
        添加媒体下载任务到队列
        
        Args:
            update: Telegram Update
            context: Telegram Context
            message: 原始消息
            status_message: 状态消息
            attachment: 媒体附件
        """
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
                        # 单个任务，直接处理
                        await self._process_single(batch[0])
                    else:
                        # 多个任务，并发处理
                        await self._process_batch(batch)
                
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
    
    async def _process_batch(self, batch: List[Tuple]):
        """并发处理一批任务"""
        total = len(batch)
        logger.info(f"🚀 开始并发下载 {total} 个媒体文件")
        
        # 创建并发任务
        tasks = []
        for i, item in enumerate(batch):
            update, context, message, status_message, attachment = item
            task = asyncio.create_task(
                self._download_with_semaphore(update, context, message, status_message, attachment, i + 1, total)
            )
            tasks.append(task)
        
        # 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 统计结果
        success = sum(1 for r in results if r is True)
        failed = total - success
        
        logger.info(f"✅ 批次完成 | 成功：{success}/{total}, 失败：{failed}")
    
    async def _download_with_semaphore(self, update, context, message, status_message, attachment, index, total):
        """带信号量控制的下载"""
        async with self.semaphore:
            try:
                logger.info(f"📥 [{index}/{total}] 开始下载")
                
                # 更新进度
                try:
                    await status_message.edit_text(
                        f"📦 **批量下载进度** ({index}/{total})\n\n"
                        f"📥 正在下载：第 {index} 个文件\n"
                        f"⏳ 并发限制：最多同时下载 {self.semaphore._value} 个文件"
                    )
                except Exception as e:
                    logger.warning(f"更新进度失败：{e}")
                
                # 执行实际下载
                await self._execute_download(update, context, message, status_message, attachment)
                
                return True
                
            except Exception as e:
                logger.error(f"❌ [{index}] 下载失败：{e}")
                return False
    
    async def _process_single(self, item: Tuple):
        """处理单个任务"""
        update, context, message, status_message, attachment = item
        try:
            await self._execute_download(update, context, message, status_message, attachment)
        except Exception as e:
            logger.error(f"❌ 单个任务下载失败：{e}")
    
    async def _execute_download(self, update, context, message, status_message, attachment):
        """
        执行实际下载（调用原有 download_user_media 的核心逻辑）
        """
        try:
            # 调用 bot 的媒体下载核心方法
            if hasattr(self.bot, '_process_telethon_media_download'):
                await self.bot._process_telethon_media_download(
                    update, context, message, status_message, attachment
                )
            else:
                # 降级：尝试直接调用 download_user_media（会重复一些逻辑）
                logger.warning("⚠️ 使用降级下载方案")
                # 这里会重复权限检查等，但能保证功能正常
                await self.bot.download_user_media(update, context)
        except Exception as e:
            logger.error(f"❌ 执行下载失败：{e}", exc_info=True)
            try:
                await status_message.edit_text(f"❌ 下载失败：{str(e)}")
            except:
                pass
            raise
