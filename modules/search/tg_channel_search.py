# -*- coding: utf-8 -*-
"""
Telegram 频道搜索模块
在配置的频道中搜索高品质音乐
"""

import logging
from typing import List, Dict, Optional
from telethon import TelegramClient
from telethon.tl.types import MessageMediaDocument
import re

logger = logging.getLogger('savextube.search.tg_channel')


class TGChannelSearcher:
    """Telegram 频道搜索器"""
    
    def __init__(self, client: TelegramClient, channels_config: List[Dict]):
        """
        初始化搜索器
        
        Args:
            client: Telethon 客户端
            channels_config: 频道配置列表
        """
        self.client = client
        self.channels = channels_config
        self.search_limit = 1000  # 每个频道最多搜索 1000 条消息
    
    async def search_music(
        self,
        keyword: str,
        artist: Optional[str] = None,
        lossless_only: bool = False
    ) -> List[Dict]:
        """
        在频道中搜索音乐
        
        Args:
            keyword: 搜索关键词（歌曲名）
            artist: 艺术家名称（可选）
            lossless_only: 是否仅搜索无损音质
            
        Returns:
            搜索结果列表
        """
        results = []
        
        # 构建搜索查询
        search_query = keyword
        if artist:
            search_query = f"{keyword} {artist}"
        
        logger.info(f"开始搜索：{search_query} (无损优先：{lossless_only})")
        
        # 按优先级排序频道
        sorted_channels = sorted(self.channels, key=lambda x: x.get('priority', 999))
        
        for channel in sorted_channels:
            if not channel.get('enabled', True):
                continue
            
            try:
                channel_results = await self._search_in_channel(
                    channel,
                    search_query,
                    lossless_only
                )
                results.extend(channel_results)
                
            except Exception as e:
                logger.error(f"在频道 {channel.get('name')} 中搜索失败：{e}")
        
        # 去重并排序
        results = self._deduplicate_and_sort(results, lossless_only)
        
        logger.info(f"搜索完成：共 {len(results)} 个结果")
        return results
    
    async def _search_in_channel(
        self,
        channel: Dict,
        query: str,
        lossless_only: bool
    ) -> List[Dict]:
        """
        在单个频道中搜索
        
        Args:
            channel: 频道配置
            query: 搜索词
            lossless_only: 是否仅无损
            
        Returns:
            搜索结果列表
        """
        results = []
        
        try:
            # 获取频道实体
            channel_entity = await self.client.get_entity(
                channel.get('username') or channel.get('chat_id')
            )
            
            # 搜索消息
            async for message in self.client.iter_messages(
                channel_entity,
                search=query,
                limit=self.search_limit
            ):
                if not message.media:
                    continue
                
                # 检查是否为音频/视频文件
                if isinstance(message.media, MessageMediaDocument):
                    file_info = self._extract_file_info(message)
                    
                    # 音质过滤
                    if lossless_only and file_info['quality_type'] != 'lossless':
                        continue
                    
                    if file_info:
                        file_info['channel'] = channel.get('name', 'Unknown')
                        file_info['channel_username'] = channel.get('username', '')
                        file_info['message_id'] = message.id
                        results.append(file_info)
        
        except Exception as e:
            logger.error(f"搜索频道 {channel.get('name')} 异常：{e}")
        
        return results
    
    def _extract_file_info(self, message) -> Dict:
        """
        从消息中提取文件信息
        
        Args:
            message: Telegram 消息
            
        Returns:
            文件信息字典
        """
        media = message.media
        file_info = {
            'id': f"{message.chat_id}_{message.id}",
            'title': 'Unknown',
            'artist': 'Unknown',
            'file_size': 0,
            'file_size_text': '0 MB',
            'quality_type': 'standard',
            'quality_text': '标准品质',
            'mime_type': '',
            'message_id': message.id
        }
        
        # 获取文件名
        if hasattr(media, 'document') and media.document:
            doc = media.document
            
            # 文件名
            for attr in doc.attributes:
                if hasattr(attr, 'file_name'):
                    file_name = attr.file_name
                    file_info['title'] = self._parse_title_from_filename(file_name)
                    break
            
            # 文件大小
            file_info['file_size'] = doc.size
            file_info['file_size_text'] = self._format_file_size(doc.size)
            
            # MIME 类型
            file_info['mime_type'] = doc.mime_type or ''
            
            # 音质判断
            file_info['quality_type'], file_info['quality_text'] = self._evaluate_quality(
                doc.size,
                file_info['mime_type'],
                getattr(attr, 'duration', 0) if hasattr(doc, 'attributes') else 0
            )
        
        # 尝试从消息文本中提取信息
        if message.text:
            # 尝试提取歌曲名和艺术家
            text = message.text.strip()
            if len(text) < 100:  # 短文本可能是标题
                file_info['title'] = text
        
        return file_info
    
    def _parse_title_from_filename(self, filename: str) -> str:
        """从文件名解析歌曲信息"""
        # 去除扩展名
        name = filename.rsplit('.', 1)[0] if '.' in filename else filename
        
        # 常见格式：艺术家 - 歌曲名
        if ' - ' in name:
            parts = name.split(' - ', 1)
            return f"{parts[1]} - {parts[0]}"
        
        return name
    
    def _format_file_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        if size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
    
    def _evaluate_quality(self, file_size: int, mime_type: str, duration: int = 0) -> tuple:
        """
        评估音质
        
        Returns:
            (quality_type, quality_text)
        """
        # 无损格式
        if mime_type in ['audio/flac', 'audio/wav', 'audio/x-flac']:
            return ('lossless', 'FLAC/WAV 无损')
        
        # 根据文件大小和时长判断
        if duration > 0:
            # 比特率估算 (kbps)
            bitrate = (file_size * 8) / (duration / 1000) / 1000
            
            if bitrate > 800:
                return ('lossless', '估计无损 (>800kbps)')
            elif bitrate > 256:
                return ('high', '高品质 (320kbps)')
            else:
                return ('standard', '标准品质')
        
        # 仅根据文件大小判断（假设 4 分钟歌曲）
        if file_size > 30 * 1024 * 1024:  # >30MB
            return ('lossless', '估计无损')
        elif file_size > 10 * 1024 * 1024:  # >10MB
            return ('high', '高品质')
        else:
            return ('standard', '标准品质')
    
    def _deduplicate_and_sort(self, results: List[Dict], lossless_only: bool) -> List[Dict]:
        """
        去重并排序
        
        Args:
            results: 搜索结果
            lossless_only: 是否仅无损
            
        Returns:
            处理后的结果
        """
        # 按标题去重，保留最高音质的版本
        unique_results = {}
        for result in results:
            key = result['title'].lower()
            if key not in unique_results:
                unique_results[key] = result
            else:
                # 保留音质更好的
                quality_order = {'lossless': 3, 'high': 2, 'standard': 1}
                if quality_order.get(result['quality_type'], 0) > \
                   quality_order.get(unique_results[key]['quality_type'], 0):
                    unique_results[key] = result
        
        # 排序：无损优先，然后按文件大小
        sorted_results = sorted(
            unique_results.values(),
            key=lambda x: (
                {'lossless': 0, 'high': 1, 'standard': 2}.get(x['quality_type'], 3),
                -x['file_size']
            )
        )
        
        return sorted_results


# 测试代码
if __name__ == '__main__':
    print("TG Channel Searcher Module")
    # 实际使用需要 Telethon 客户端
