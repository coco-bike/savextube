# -*- coding: utf-8 -*-
"""
Telegram 消息处理器
支持批量链接处理和并发下载
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes
from typing import List

logger = logging.getLogger(__name__)


class TelegramMessageHandler:
    """Telegram 消息处理器"""
    
    def __init__(self, bot_instance):
        """
        初始化消息处理器
        
        Args:
            bot_instance: TelegramBot 实例
        """
        self.bot = bot_instance
        # 获取 VideoDownloader 实例（batch_processor 在它里面）
        self.downloader = bot_instance.downloader if hasattr(bot_instance, 'downloader') else None
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理文本消息（支持批量链接）"""
        user_id = update.message.from_user.id
        
        # 权限检查
        if not self.bot._check_user_permission(user_id):
            await update.message.reply_text("❌ 您没有权限使用此机器人")
            return
        
        message = update.message
        
        # 检查搜索命令
        if message.text and message.text.startswith("/search"):
            await self.bot._handle_search_command(message, context)
            return
        
        # 提取所有链接
        urls = self._extract_urls_from_message(message)
        
        if not urls:
            await message.reply_text(
                "🤔 请发送一个有效的链接或包含链接的消息。\n\n"
                "💡 提示：\n"
                "• 直接发送链接\n"
                "• 转发包含链接的消息\n"
                "• 回复包含链接的消息\n"
                "• 支持批量发送多个链接（每行一个）"
            )
            return
        
        # 发送响应
        if len(urls) == 1:
            status_message = await message.reply_text("🚀 正在处理您的请求...")
            logger.info(f"收到 1 个链接：{urls[0]}")
        else:
            status_message = await message.reply_text(
                f"🚀 收到 {len(urls)} 个链接，准备并发下载...\n\n"
                f"📊 最大并发数：{self.bot.batch_processor.max_concurrent if hasattr(self.bot, 'batch_processor') else 3}"
            )
            logger.info(f"收到 {len(urls)} 个链接：{urls}")
        
        # 异步处理下载
        if len(urls) == 1:
            # 单个链接，使用原有方法
            logger.info(f"📥 单个链接，使用标准下载：{urls[0]}")
            import asyncio
            asyncio.create_task(
                self.bot._process_download_async(update, context, urls[0], status_message)
            )
        else:
            # 多个链接，使用批量下载
            logger.info(f"🚀 多个链接（{len(urls)}个），使用批量并发下载：{urls}")
            import asyncio
            asyncio.create_task(
                self._process_batch_download_async(update, context, urls, status_message)
            )
    
    def _extract_urls_from_message(self, message) -> List[str]:
        """从消息中提取所有链接"""
        from .url_extractor import URLExtractor
        
        urls = []
        
        # 从文本中提取
        if message.text:
            urls = URLExtractor.extract_all_urls(message.text)
        
        # 从实体中提取
        if not urls and message.entities:
            for entity in message.entities:
                if entity.type == "url":
                    url = message.text[entity.offset:entity.offset + entity.length]
                    if url and url not in urls:
                        urls.append(url)
                elif entity.type == "text_link":
                    if entity.url and entity.url not in urls:
                        urls.append(entity.url)
        
        # 检查转发消息
        if not urls and hasattr(message, 'forward_from_chat') and message.forward_from_chat and message.text:
            urls = URLExtractor.extract_all_urls(message.text)
        
        # 检查回复消息
        if not urls and message.reply_to_message:
            reply_msg = message.reply_to_message
            if reply_msg.text:
                urls = URLExtractor.extract_all_urls(reply_msg.text)
            if not urls and reply_msg.entities:
                for entity in reply_msg.entities:
                    if entity.type == "url":
                        url = reply_msg.text[entity.offset:entity.offset + entity.length]
                        if url and url not in urls:
                            urls.append(url)
                    elif entity.type == "text_link":
                        if entity.url and entity.url not in urls:
                            urls.append(entity.url)
        
        return urls
    
    async def _process_batch_download_async(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        urls: List[str],
        status_message
    ):
        """异步处理批量下载"""
        try:
            # 检查 batch_processor（在 VideoDownloader 中）
            if not self.downloader or not hasattr(self.downloader, 'batch_processor') or not self.downloader.batch_processor:
                await status_message.edit_text("❌ 批量下载功能未初始化")
                return
            
            # 进度回调
            async def progress_callback(text):
                try:
                    await status_message.edit_text(text)
                except Exception as e:
                    logger.warning(f"更新进度消息失败：{e}")
            
            # 执行批量下载
            results = await self.downloader.batch_processor.download_batch(
                urls=urls,
                get_ydl_opts_func=lambda url: self.downloader._get_ydl_opts(url) if hasattr(self.downloader, '_get_ydl_opts') else {},
                progress_callback=progress_callback
            )
            
            # 发送结果
            summary = self.bot.batch_processor.generate_summary(results)
            await status_message.edit_text(summary)
            
        except Exception as e:
            logger.error(f"批量下载失败：{e}")
            await status_message.edit_text(f"❌ 批量下载失败：{str(e)}")
