# -*- coding: utf-8 -*-
"""
下载风控管理
防止 Telegram 限制和封禁
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path
import json

logger = logging.getLogger('savextube.rate_limiter')


class RateLimiter:
    """下载速率限制器"""
    
    def __init__(self):
        """初始化速率限制器"""
        # 下载记录
        self.download_history = []
        
        # 限制配置
        self.config = {
            # 单个文件下载间隔（秒）
            'file_interval': 5,
            
            # 每小时最多下载数量
            'hourly_limit': 30,
            
            # 每天最多下载数量
            'daily_limit': 200,
            
            # 每次搜索间隔（秒）
            'search_interval': 3,
            
            # 连续失败次数限制
            'max_failures': 5,
            
            # 失败后等待时间（分钟）
            'failure_wait': 30,
            
            # 下载文件大小限制（MB）
            'max_file_size': 500,
        }
        
        # 失败计数
        self.failure_count = 0
        self.last_failure_time = None
        
        # 统计信息
        self.stats = {
            'today_downloads': 0,
            'today_failed': 0,
            'hourly_downloads': 0,
            'last_reset': datetime.now()
        }
    
    async def wait_if_needed(self, file_size_mb: float = 0):
        """
        检查是否需要等待
        
        Args:
            file_size_mb: 文件大小（MB）
        """
        now = datetime.now()
        
        # 1. 检查单文件间隔
        if self.download_history:
            last_download = self.download_history[-1]
            time_since_last = (now - last_download['time']).total_seconds()
            
            if time_since_last < self.config['file_interval']:
                wait_time = self.config['file_interval'] - time_since_last
                logger.info(f"⏳ 等待 {wait_time:.1f} 秒（频率限制）")
                await asyncio.sleep(wait_time)
        
        # 2. 检查每小时限制
        hour_ago = now - timedelta(hours=1)
        recent_downloads = [d for d in self.download_history if d['time'] > hour_ago]
        
        if len(recent_downloads) >= self.config['hourly_limit']:
            logger.warning(f"⚠️ 已达到每小时下载限制 ({self.config['hourly_limit']})")
            raise RateLimitError(f"每小时最多下载 {self.config['hourly_limit']} 个文件")
        
        # 3. 检查每天限制
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_downloads = [d for d in self.download_history if d['time'] > today_start]
        
        if len(today_downloads) >= self.config['daily_limit']:
            logger.warning(f"⚠️ 已达到每天下载限制 ({self.config['daily_limit']})")
            raise RateLimitError(f"每天最多下载 {self.config['daily_limit']} 个文件")
        
        # 4. 检查文件大小
        if file_size_mb > self.config['max_file_size']:
            logger.warning(f"⚠️ 文件过大 ({file_size_mb:.1f}MB > {self.config['max_file_size']}MB)")
            raise RateLimitError(f"文件大小不能超过 {self.config['max_file_size']}MB")
        
        # 5. 检查失败次数
        if self.failure_count >= self.config['max_failures']:
            if self.last_failure_time:
                time_since_failure = (now - self.last_failure_time).total_seconds() / 60
                
                if time_since_failure < self.config['failure_wait']:
                    wait_minutes = self.config['failure_wait'] - time_since_failure
                    logger.warning(f"⚠️ 连续失败 {self.failure_count} 次，等待 {wait_minutes:.1f} 分钟")
                    await asyncio.sleep(wait_minutes * 60)
    
    def record_download(self, file_size_mb: float = 0, success: bool = True):
        """
        记录下载
        
        Args:
            file_size_mb: 文件大小（MB）
            success: 是否成功
        """
        now = datetime.now()
        
        self.download_history.append({
            'time': now,
            'size': file_size_mb,
            'success': success
        })
        
        # 保留最近 24 小时的记录
        day_ago = now - timedelta(days=1)
        self.download_history = [d for d in self.download_history if d['time'] > day_ago]
        
        # 更新统计
        if success:
            self.stats['today_downloads'] += 1
            self.stats['hourly_downloads'] += 1
            self.failure_count = 0  # 重置失败计数
        else:
            self.stats['today_failed'] += 1
            self.failure_count += 1
            self.last_failure_time = now
        
        logger.info(f"📊 今日下载：{self.stats['today_downloads']}, 失败：{self.stats['today_failed']}")
    
    def get_status(self) -> Dict:
        """获取当前状态"""
        now = datetime.now()
        
        # 计算最近 1 小时的下载数
        hour_ago = now - timedelta(hours=1)
        recent = [d for d in self.download_history if d['time'] > hour_ago]
        
        return {
            'today_downloads': self.stats['today_downloads'],
            'today_failed': self.stats['today_failed'],
            'hourly_downloads': len(recent),
            'failure_count': self.failure_count,
            'limits': {
                'hourly': self.config['hourly_limit'],
                'daily': self.config['daily_limit'],
                'file_interval': self.config['file_interval'],
            }
        }


class RateLimitError(Exception):
    """速率限制错误"""
    pass


class DownloadStrategy:
    """下载策略管理器"""
    
    def __init__(self, rate_limiter: RateLimiter):
        """
        初始化下载策略
        
        Args:
            rate_limiter: 速率限制器实例
        """
        self.rate_limiter = rate_limiter
        
        # 策略配置
        self.strategies = {
            # 保守策略：安全但慢
            'conservative': {
                'file_interval': 10,
                'hourly_limit': 20,
                'daily_limit': 100,
                'max_concurrent': 1,
            },
            
            # 平衡策略：推荐
            'balanced': {
                'file_interval': 5,
                'hourly_limit': 30,
                'daily_limit': 200,
                'max_concurrent': 3,
            },
            
            # 激进策略：快但有风险
            'aggressive': {
                'file_interval': 2,
                'hourly_limit': 50,
                'daily_limit': 300,
                'max_concurrent': 5,
            },
        }
        
        # 当前策略
        self.current_strategy = 'balanced'
    
    def set_strategy(self, strategy_name: str):
        """
        设置下载策略
        
        Args:
            strategy_name: 策略名称
        """
        if strategy_name not in self.strategies:
            logger.warning(f"未知策略：{strategy_name}，使用平衡策略")
            strategy_name = 'balanced'
        
        self.current_strategy = strategy_name
        config = self.strategies[strategy_name]
        
        # 更新速率限制器配置
        for key, value in config.items():
            self.rate_limiter.config[key] = value
        
        logger.info(f"📋 使用下载策略：{strategy_name}")
    
    def get_recommendation(self, account_age_days: int, vip_level: str = 'free') -> str:
        """
        根据账号情况推荐策略
        
        Args:
            account_age_days: 账号天数
            vip_level: VIP 等级 (free/premium)
            
        Returns:
            推荐策略名称
        """
        # 新账号（<30 天）使用保守策略
        if account_age_days < 30:
            logger.info(f"🆕 新账号（{account_age_days}天），使用保守策略")
            return 'conservative'
        
        # VIP 用户可以使用激进策略
        if vip_level == 'premium':
            logger.info(f"⭐ VIP 用户，使用激进策略")
            return 'aggressive'
        
        # 普通账号使用平衡策略
        logger.info(f"👤 普通账号，使用平衡策略")
        return 'balanced'


class AntiBanManager:
    """防封禁管理器"""
    
    def __init__(self):
        """初始化防封禁管理器"""
        # 警告信号
        self.warning_signs = []
        
        # 最后检查时间
        self.last_check = None
        
        # 账号状态
        self.account_status = 'normal'  # normal/warning/restricted
    
    def check_warning_signs(self, error_message: str):
        """
        检查警告信号
        
        Args:
            error_message: 错误信息
        """
        warning_keywords = [
            'Flood wait',           # 频率限制
            'Too many requests',    # 请求过多
            'Timeout',              # 超时
            'Peer flood',           # 频道限制
            'Slow mode',            # 慢速模式
        ]
        
        for keyword in warning_keywords:
            if keyword.lower() in error_message.lower():
                self.warning_signs.append({
                    'time': datetime.now(),
                    'type': keyword,
                    'message': error_message
                })
                logger.warning(f"⚠️ 检测到警告信号：{keyword}")
        
        # 检查警告频率
        self._evaluate_risk()
    
    def _evaluate_risk(self):
        """评估风险等级"""
        now = datetime.now()
        hour_ago = now - timedelta(hours=1)
        
        # 统计最近 1 小时的警告次数
        recent_warnings = [w for w in self.warning_signs if w['time'] > hour_ago]
        
        if len(recent_warnings) >= 10:
            self.account_status = 'restricted'
            logger.error("🚨 账号已被限制，立即停止下载！")
        elif len(recent_warnings) >= 5:
            self.account_status = 'warning'
            logger.warning("⚠️ 账号有风险，建议降低下载频率")
        else:
            self.account_status = 'normal'
    
    def get_suggestions(self) -> List[str]:
        """获取建议"""
        suggestions = []
        
        if self.account_status == 'restricted':
            suggestions.extend([
                "🛑 立即停止所有下载活动",
                "⏰ 等待 24 小时后再试",
                "📞 联系 Telegram 支持（如果必要）",
            ])
        elif self.account_status == 'warning':
            suggestions.extend([
                "⚠️ 降低下载频率",
                "⏳ 增加文件间隔时间",
                "📊 使用保守策略",
                "🕐 避免高峰时段下载",
            ])
        else:
            suggestions.extend([
                "✅ 账号状态正常",
                "📊 继续使用当前策略",
            ])
        
        return suggestions


class BackupPlan:
    """备用方案管理器"""
    
    def __init__(self):
        """初始化备用方案"""
        self.backup_sources = []
        self.current_source = 'primary'
    
    def add_backup_source(self, name: str, source_type: str, config: Dict):
        """
        添加备用资源
        
        Args:
            name: 资源名称
            source_type: 类型 (tg_channel/web_api/local)
            config: 配置信息
        """
        self.backup_sources.append({
            'name': name,
            'type': source_type,
            'config': config,
            'status': 'active',
            'last_used': None
        })
        
        logger.info(f"✅ 添加备用资源：{name} ({source_type})")
    
    def get_available_sources(self) -> List[Dict]:
        """获取可用资源列表"""
        return [s for s in self.backup_sources if s['status'] == 'active']
    
    def mark_unavailable(self, source_name: str):
        """标记资源不可用"""
        for source in self.backup_sources:
            if source['name'] == source_name:
                source['status'] = 'unavailable'
                logger.warning(f"❌ 标记资源不可用：{source_name}")
                break
    
    def get_next_source(self) -> Optional[Dict]:
        """获取下一个可用资源"""
        available = self.get_available_sources()
        
        if not available:
            return None
        
        # 选择最近最少使用的资源
        available.sort(key=lambda x: x['last_used'] or datetime.min)
        
        return available[0]


# 使用示例
if __name__ == '__main__':
    print("风控管理模块")
    
    # 创建实例
    limiter = RateLimiter()
    strategy = DownloadStrategy(limiter)
    anti_ban = AntiBanManager()
    
    # 设置策略
    strategy.set_strategy('balanced')
    
    # 获取状态
    status = limiter.get_status()
    print(f"今日下载：{status['today_downloads']}")
    print(f"小时下载：{status['hourly_downloads']}")
