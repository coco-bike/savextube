# -*- coding: utf-8 -*-
"""
歌单管理器
支持歌单解析、风格分类、批量搜索下载
"""

import logging
import asyncio
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger('savextube.playlist_manager')


class PlaylistManager:
    """歌单管理器"""
    
    def __init__(self, netease_parser, tg_searcher, download_path: str = '/downloads/music'):
        """
        初始化歌单管理器
        
        Args:
            netease_parser: 网易云解析器实例
            tg_searcher: TG 搜索器实例
            download_path: 下载根目录
        """
        self.netease_parser = netease_parser
        self.tg_searcher = tg_searcher
        self.download_path = Path(download_path)
        
        # 风格分类关键词
        self.style_keywords = {
            '华语流行': ['周杰伦', '林俊杰', '陈奕迅', '王菲', '张学友', '刘德华', '蔡依林', '邓紫棋', '李荣浩', '薛之谦'],
            '网络热歌': ['抖音', '快手', '热歌', '网红', 'DJ', 'remix'],
            '欧美流行': ['Taylor', 'Justin', 'Ariana', 'Ed', 'Bruno', 'Billie', 'Dua', 'The Weeknd'],
            '日韩音乐': ['BTS', 'BLACKPINK', 'IU', 'EXO', 'TWICE', '日剧', '韩剧', 'OST'],
            '古典音乐': ['古典', '交响', '贝多芬', '莫扎特', '巴赫', '钢琴', '小提琴'],
            '轻音乐': ['轻音乐', '纯音乐', 'instrumental', 'peaceful', 'relax'],
            '影视原声': ['电影', '电视剧', 'OST', 'soundtrack', '主题曲', '插曲'],
            '民谣': ['民谣', 'folk', '赵雷', '宋冬野', '马頔'],
            '摇滚': ['摇滚', 'rock', 'Beyond', '五月天', '苏打绿'],
            '电子': ['电子', 'electronic', 'EDM', 'DJ', '舞曲'],
        }
    
    def parse_playlist(self, url: str) -> Optional[Dict]:
        """
        解析网易云歌单
        
        Args:
            url: 网易云歌单链接
            
        Returns:
            歌单信息字典
        """
        logger.info(f"开始解析网易云歌单：{url}")
        
        try:
            result = self.netease_parser.parse(url)
            
            if result:
                logger.info(f"解析成功：{result['playlist']['name']} - {result['total']} 首歌曲")
                return result
            else:
                logger.error("解析失败")
                return None
                
        except Exception as e:
            logger.error(f"解析异常：{e}")
            return None
    
    def classify_by_style(self, tracks: List[Dict]) -> Dict[str, List[Dict]]:
        """
        按风格分类歌曲
        
        Args:
            tracks: 歌曲列表
            
        Returns:
            {风格名：歌曲列表}
        """
        logger.info(f"开始按风格分类 {len(tracks)} 首歌曲")
        
        classified = {style: [] for style in self.style_keywords.keys()}
        classified['其他'] = []  # 无法分类的放这里
        
        for track in tracks:
            style = self._detect_style(track)
            classified[style].append(track)
        
        # 移除空的分类
        classified = {k: v for k, v in classified.items() if v}
        
        logger.info(f"分类完成：共 {len(classified)} 个风格分类")
        for style, songs in classified.items():
            logger.info(f"  - {style}: {len(songs)} 首")
        
        return classified
    
    def _detect_style(self, track: Dict) -> str:
        """
        检测歌曲风格
        
        Args:
            track: 歌曲信息
            
        Returns:
            风格名称
        """
        # 获取歌曲信息
        title = track.get('name', '').lower()
        artist = track.get('artist', '').lower()
        album = track.get('album', '').lower()
        
        text = f"{title} {artist} {album}"
        
        # 匹配风格关键词
        for style, keywords in self.style_keywords.items():
            for keyword in keywords:
                if keyword.lower() in text:
                    logger.debug(f"歌曲 '{track['name']}' 匹配风格：{style} (关键词：{keyword})")
                    return style
        
        # 默认返回"其他"
        return '其他'
    
    async def search_and_download(
        self,
        style: str,
        tracks: List[Dict],
        lossless_only: bool = True,
        max_concurrent: int = 3
    ) -> Dict:
        """
        搜索并下载某个风格的歌曲
        
        Args:
            style: 风格名称
            tracks: 歌曲列表
            lossless_only: 是否仅下载无损
            max_concurrent: 最大并发数
            
        Returns:
            下载结果统计
        """
        logger.info(f"开始下载 {style} 风格，共 {len(tracks)} 首歌曲")
        
        results = {
            'style': style,
            'total': len(tracks),
            'success': 0,
            'failed': 0,
            'songs': []
        }
        
        for i, track in enumerate(tracks, 1):
            logger.info(f"[{i}/{len(tracks)}] 搜索：{track['name']} - {track['artist']}")
            
            try:
                # 搜索
                search_results = await self.tg_searcher.search_music(
                    keyword=track['name'],
                    artist=track['artist'],
                    lossless_only=lossless_only
                )
                
                if search_results:
                    # 找到资源，下载第一个（最优音质）
                    best_match = search_results[0]
                    logger.info(f"  ✅ 找到资源：{best_match['quality_text']} ({best_match['file_size_text']})")
                    
                    # TODO: 调用下载函数
                    # await self._download_track(best_match, style)
                    
                    results['success'] += 1
                    results['songs'].append({
                        'track': track,
                        'source': best_match,
                        'status': 'success'
                    })
                else:
                    logger.warning(f"  ❌ 未找到资源")
                    results['failed'] += 1
                    results['songs'].append({
                        'track': track,
                        'source': None,
                        'status': 'not_found'
                    })
                
            except Exception as e:
                logger.error(f"  ❌ 下载失败：{e}")
                results['failed'] += 1
                results['songs'].append({
                    'track': track,
                    'source': None,
                    'status': 'failed',
                    'error': str(e)
                })
        
        logger.info(f"{style} 风格下载完成：成功 {results['success']}/{results['total']}")
        return results
    
    async def process_playlist(
        self,
        url: str,
        lossless_only: bool = True,
        max_concurrent: int = 3
    ) -> Dict:
        """
        处理整个歌单（解析→分类→下载）
        
        Args:
            url: 网易云歌单链接
            lossless_only: 是否仅下载无损
            max_concurrent: 最大并发数
            
        Returns:
            完整处理结果
        """
        logger.info(f"开始处理歌单：{url}")
        
        # 1. 解析歌单
        playlist_info = self.parse_playlist(url)
        if not playlist_info:
            return {'status': 'failed', 'error': '解析失败'}
        
        # 2. 按风格分类
        classified = self.classify_by_style(playlist_info['tracks'])
        
        # 3. 逐个风格下载
        all_results = {
            'status': 'success',
            'playlist': playlist_info['playlist'],
            'styles': {},
            'summary': {
                'total_styles': len(classified),
                'total_songs': playlist_info['total'],
                'success': 0,
                'failed': 0
            }
        }
        
        for style, tracks in classified.items():
            logger.info(f"\n{'='*50}")
            logger.info(f"处理风格：{style} ({len(tracks)} 首)")
            logger.info(f"{'='*50}")
            
            result = await self.search_and_download(
                style=style,
                tracks=tracks,
                lossless_only=lossless_only,
                max_concurrent=max_concurrent
            )
            
            all_results['styles'][style] = result
            all_results['summary']['success'] += result['success']
            all_results['summary']['failed'] += result['failed']
        
        logger.info(f"\n{'='*50}")
        logger.info(f"歌单处理完成！")
        logger.info(f"总计：{all_results['summary']['success']}/{all_results['summary']['total_songs']}")
        logger.info(f"{'='*50}")
        
        return all_results
    
    def generate_report(self, results: Dict) -> str:
        """
        生成处理报告
        
        Args:
            results: 处理结果
            
        Returns:
            报告文本
        """
        report = []
        report.append("📊 歌单下载报告")
        report.append("=" * 50)
        report.append("")
        report.append(f"📀 歌单：{results['playlist']['name']}")
        report.append(f"📁 风格分类：{results['summary']['total_styles']} 个")
        report.append(f"🎵 总歌曲：{results['summary']['total_songs']} 首")
        report.append(f"✅ 成功：{results['summary']['success']} 首")
        report.append(f"❌ 失败：{results['summary']['failed']} 首")
        report.append("")
        
        for style, result in results['styles'].items():
            report.append(f"🎼 {style}: {result['success']}/{result['total']}")
        
        report.append("")
        report.append("=" * 50)
        
        return "\n".join(report)


# 使用示例
if __name__ == '__main__':
    print("歌单管理器模块")
    # 实际使用需要传入解析器和搜索器实例
