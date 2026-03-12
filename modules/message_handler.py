# -*- coding: utf-8 -*-
"""
Telegram 消息处理器
支持批量链接处理和并发下载
"""

import logging
import time
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
            
            last_update = {"time": 0.0, "text": ""}
            queue_state = {
                "completed": 0,
                "success": 0,
                "failed": 0,
                "done_items": set(),
            }

            # 进度回调
            async def progress_callback(payload):
                try:
                    self._update_queue_state(queue_state, payload)
                    progress_text = self._format_batch_progress_text(payload, queue_state)
                    if not progress_text:
                        return

                    now = time.time()
                    if progress_text == last_update["text"]:
                        return
                    if now - last_update["time"] < 2.0 and "✅ 下载完成" not in progress_text:
                        return

                    await status_message.edit_text(progress_text)
                    last_update["time"] = now
                    last_update["text"] = progress_text
                except Exception as e:
                    logger.warning(f"更新进度消息失败：{e}")
            
            # 执行批量下载
            results = await self.downloader.batch_processor.download_batch(
                urls=urls,
                get_ydl_opts_func=lambda url: self.downloader._get_ydl_opts(url) if hasattr(self.downloader, '_get_ydl_opts') else {},
                progress_callback=progress_callback
            )
            
            # 发送结果
            summary = self.downloader.batch_processor.generate_summary(results)
            summary_chunks = self._split_text_for_telegram(summary)

            # 第一段复用原状态消息，后续段落连续发送新消息
            await status_message.edit_text(summary_chunks[0])
            for chunk in summary_chunks[1:]:
                await status_message.reply_text(chunk)
            
        except Exception as e:
            logger.error(f"批量下载失败：{e}")
            await status_message.edit_text(f"❌ 批量下载失败：{str(e)}")

    def _format_batch_progress_text(self, payload, queue_state=None) -> str:
        """把下载进度 payload 统一格式化为 Telegram 文本。"""
        if isinstance(payload, str):
            return payload

        if not isinstance(payload, dict):
            return str(payload)

        status = payload.get("status", "")
        batch_index = payload.get("batch_index")
        batch_total = payload.get("batch_total")
        task_prefix = ""
        if isinstance(batch_index, int) and isinstance(batch_total, int) and batch_total > 0:
            task_prefix = f"[{batch_index}/{batch_total}] "

        queue_line = self._build_queue_state_line(queue_state, batch_total)

        if status == "queued":
            return f"🕒 {task_prefix}任务已入队，等待可用下载槽位...\n{queue_line}"

        if status == "started":
            return f"🚀 {task_prefix}开始下载\n{queue_line}"

        if status == "downloading":
            title = self._extract_title(payload)
            filename = payload.get("filename") or title or "未知文件"
            downloaded = payload.get("downloaded_bytes", 0) or 0
            total = payload.get("total_bytes") or payload.get("total_bytes_estimate") or 0
            speed = payload.get("speed", 0) or 0
            eta = payload.get("eta", 0)
            resolution = self._extract_resolution(payload)
            bitrate_text = self._extract_bitrate(payload)
            thumbnail = self._extract_thumbnail(payload)

            downloaded_mb = downloaded / (1024 * 1024)
            total_mb = total / (1024 * 1024) if total else 0
            speed_mb = speed / (1024 * 1024)

            if total > 0:
                percent = (downloaded / total) * 100
                filled = int(20 * percent / 100)
                bar = "█" * filled + "░" * (20 - filled)
                size_text = f"{downloaded_mb:.2f}MB / {total_mb:.2f}MB"
                progress_text = f"{bar} {percent:.1f}%"
            else:
                size_text = f"{downloaded_mb:.2f}MB"
                progress_text = "下载中..."

            eta_text = f"{eta}s" if isinstance(eta, (int, float)) and eta else "未知"

            lines = [
                f"📥 {task_prefix}批量下载进行中",
                queue_line,
                f"🏷 标题: {title}",
                f"📝 文件名: {filename}",
                f"💾 大小: {size_text}",
                f"🎥 分辨率: {resolution}",
            ]
            if bitrate_text:
                lines.append(f"🎵 码率: {bitrate_text}")
            lines.extend([
                f"⚡ 速度: {speed_mb:.2f}MB/s",
                f"⏳ 预计剩余: {eta_text}",
                f"📊 进度: {progress_text}",
            ])
            if thumbnail:
                lines.append(f"🖼 封面: {thumbnail}")

            return "\n".join(lines)

        if status == "finished":
            filename = payload.get("filename") or payload.get("info_dict", {}).get("title") or "未知文件"
            return f"✅ {task_prefix}下载完成\n{queue_line}\n📝 文件名: {filename}"

        if status == "result":
            if payload.get("success"):
                title = payload.get("title") or "未知标题"
                filename = payload.get("final_filename") or payload.get("output") or "未知文件"
                size_text = self._format_size(payload.get("file_size", 0))
                resolution = payload.get("resolution") or self._extract_resolution(payload)
                bitrate_value = payload.get("bitrate")
                duration_text = self._format_duration(payload.get("duration"))
                thumbnail = payload.get("thumbnail") or self._extract_thumbnail(payload)

                lines = [
                    f"✅ {task_prefix}任务完成",
                    queue_line,
                    f"🏷 标题: {title}",
                    f"📝 文件名: {filename}",
                    f"💾 大小: {size_text}",
                    f"🎥 分辨率: {resolution}",
                ]
                if isinstance(bitrate_value, (int, float)) and bitrate_value > 0:
                    lines.append(f"🎵 码率: {int(bitrate_value)}kbps")
                if duration_text:
                    lines.append(f"⏱ 时长: {duration_text}")
                if thumbnail:
                    lines.append(f"🖼 封面: {thumbnail}")
                return "\n".join(lines)
            return f"❌ {task_prefix}任务失败: {payload.get('error', '未知错误')}"

        if status == "error":
            return f"❌ {task_prefix}下载失败: {payload.get('error', '未知错误')}\n{queue_line}"

        return payload.get("progress_text") or str(payload)

    def _extract_resolution(self, payload: dict) -> str:
        """从 yt-dlp 进度 payload 中提取分辨率信息。"""
        if not isinstance(payload, dict):
            return "未知"

        if payload.get("resolution"):
            return str(payload.get("resolution"))

        info = payload.get("info_dict") or {}
        if info.get("resolution"):
            return str(info.get("resolution"))

        width = info.get("width")
        height = info.get("height")
        if width and height:
            return f"{width}x{height}"

        return "未知"

    def _extract_title(self, payload: dict) -> str:
        """提取标题信息。"""
        if not isinstance(payload, dict):
            return "未知标题"

        info = payload.get("info_dict") or {}
        return payload.get("title") or info.get("title") or "未知标题"

    def _extract_bitrate(self, payload: dict) -> str:
        """提取码率信息。"""
        if not isinstance(payload, dict):
            return ""

        if isinstance(payload.get("bitrate"), (int, float)) and payload.get("bitrate") > 0:
            return f"{int(payload.get('bitrate'))}kbps"

        info = payload.get("info_dict") or {}
        for key in ("abr", "tbr"):
            value = info.get(key)
            if isinstance(value, (int, float)) and value > 0:
                return f"{int(value)}kbps"
        return ""

    def _extract_thumbnail(self, payload: dict) -> str:
        """提取封面链接（截断显示，防止消息过长）。"""
        if not isinstance(payload, dict):
            return ""

        thumbnail = payload.get("thumbnail")
        if not thumbnail:
            info = payload.get("info_dict") or {}
            thumbnail = info.get("thumbnail")

        if not thumbnail:
            return ""

        thumbnail = str(thumbnail)
        if len(thumbnail) > 80:
            return thumbnail[:77] + "..."
        return thumbnail

    def _format_duration(self, duration_value) -> str:
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

    def _update_queue_state(self, queue_state: dict, payload: dict):
        """根据事件更新队列整体状态。"""
        if not isinstance(payload, dict):
            return

        status = payload.get("status")
        batch_index = payload.get("batch_index")
        if not isinstance(batch_index, int):
            return

        if status == "result":
            if batch_index in queue_state["done_items"]:
                return
            queue_state["done_items"].add(batch_index)
            queue_state["completed"] += 1
            if payload.get("success"):
                queue_state["success"] += 1
            else:
                queue_state["failed"] += 1
        elif status == "error":
            if batch_index in queue_state["done_items"]:
                return
            queue_state["done_items"].add(batch_index)
            queue_state["completed"] += 1
            queue_state["failed"] += 1

    def _build_queue_state_line(self, queue_state: dict, batch_total) -> str:
        """构建队列状态文本。"""
        if not queue_state or not isinstance(batch_total, int) or batch_total <= 0:
            return "📦 队列: 统计中"
        waiting = max(0, batch_total - queue_state["completed"])
        return (
            f"📦 队列: 总{batch_total} | 已完成{queue_state['completed']} | "
            f"成功{queue_state['success']} | 失败{queue_state['failed']} | 待处理{waiting}"
        )

    def _format_size(self, size: int) -> str:
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

    def _split_text_for_telegram(self, text: str, max_len: int = 3500) -> List[str]:
        """按 Telegram 消息长度限制分片，优先按段落切分。"""
        if not text:
            return [""]

        if len(text) <= max_len:
            return [text]

        chunks: List[str] = []
        current = ""

        # 先按空行切段，尽量保持每个任务块完整
        paragraphs = text.split("\n\n")
        for paragraph in paragraphs:
            segment = paragraph if not current else f"\n\n{paragraph}"

            if len(current) + len(segment) <= max_len:
                current += segment
                continue

            if current:
                chunks.append(current)
                current = ""

            # 单个段落本身过长时，再按行切
            if len(paragraph) > max_len:
                line_buffer = ""
                for line in paragraph.split("\n"):
                    line_segment = line if not line_buffer else f"\n{line}"
                    if len(line_buffer) + len(line_segment) <= max_len:
                        line_buffer += line_segment
                    else:
                        if line_buffer:
                            chunks.append(line_buffer)
                        line_buffer = line

                if line_buffer:
                    current = line_buffer
            else:
                current = paragraph

        if current:
            chunks.append(current)

        return chunks
