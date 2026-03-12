#!/usr/bin/env python3
"""
B站收藏夹订阅管理模块
负责处理B站收藏夹的订阅、检查和自动下载功能
"""

import os
import json
import time
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
import yt_dlp

# 设置日志
logger = logging.getLogger("savextube")

class BilibiliFavSubscriptionManager:
    """B站收藏夹订阅管理器"""
    
    def __init__(self, download_path: str, proxy_host: Optional[str] = None, 
                 cookies_path: Optional[str] = None):
        """
        初始化订阅管理器
        
        Args:
            download_path: 下载目录路径
            proxy_host: 代理服务器地址
            cookies_path: B站cookies文件路径
        """
        self.download_path = Path(download_path)
        self.proxy_host = proxy_host
        self.cookies_path = cookies_path
        
        # 从环境变量获取检查间隔（分钟）
        self.poll_interval = int(os.getenv("BILIBILI_POLL_INTERVAL", "60"))
        
        # 订阅数据文件路径
        self.subscriptions_file = self.download_path / "bilibili_subscriptions.json"
        
        # 订阅下载目录
        self.subscription_download_path = self.download_path / "Bilibili" / "Subscriptions"
        self.subscription_download_path.mkdir(parents=True, exist_ok=True)
        
        # 后台任务
        self.check_task: Optional[asyncio.Task] = None
        
        logger.info(f"📚 B站收藏夹订阅管理器初始化完成")
        logger.info(f"📁 下载目录: {self.download_path}")
        logger.info(f"⏰ 检查间隔: {self.poll_interval} 分钟")
        if self.proxy_host:
            logger.info(f"🌐 使用代理: {self.proxy_host}")
        if self.cookies_path:
            logger.info(f"🍪 使用cookies: {self.cookies_path}")
    
    def load_subscriptions(self) -> Dict[str, Any]:
        """加载订阅列表"""
        try:
            if self.subscriptions_file.exists():
                with open(self.subscriptions_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"📚 加载订阅列表失败: {e}")
            return {}
    
    def save_subscriptions(self, subscriptions: Dict[str, Any]) -> bool:
        """保存订阅列表"""
        try:
            self.subscriptions_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.subscriptions_file, 'w', encoding='utf-8') as f:
                json.dump(subscriptions, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"📚 保存订阅列表失败: {e}")
            return False
    
    def build_fav_url(self, fav_id: str) -> str:
        """构建收藏夹URL"""
        return f"https://www.bilibili.com/medialist/play/ml{fav_id}"
    
    async def validate_fav_id(self, fav_id: str) -> Dict[str, Any]:
        """
        验证收藏夹ID并获取基本信息
        
        Args:
            fav_id: 收藏夹ID
            
        Returns:
            包含验证结果和收藏夹信息的字典
        """
        try:
            # 验证ID格式
            if not fav_id.isdigit():
                return {"success": False, "error": "收藏夹ID必须是数字"}
            
            fav_url = self.build_fav_url(fav_id)
            
            # 配置yt-dlp选项
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": True,
                "socket_timeout": 30,
                "retries": 3,
            }
            
            if self.proxy_host:
                ydl_opts["proxy"] = self.proxy_host
            if self.cookies_path and os.path.exists(self.cookies_path):
                ydl_opts["cookiefile"] = self.cookies_path
            
            # 获取收藏夹信息
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(fav_url, download=False)
            
            if not info:
                return {"success": False, "error": "收藏夹不存在或无法访问"}
            
            # 提取收藏夹信息
            fav_title = info.get('title', f'收藏夹_{fav_id}')
            video_count = len(info.get('entries', []))
            
            return {
                "success": True,
                "fav_id": fav_id,
                "fav_url": fav_url,
                "title": fav_title,
                "video_count": video_count
            }
            
        except Exception as e:
            logger.error(f"📚 验证收藏夹 {fav_id} 失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def add_subscription(self, fav_id: str, user_id: int) -> Dict[str, Any]:
        """
        添加收藏夹订阅
        
        Args:
            fav_id: 收藏夹ID
            user_id: 用户ID
            
        Returns:
            操作结果字典
        """
        try:
            # 验证收藏夹
            validation_result = await self.validate_fav_id(fav_id)
            if not validation_result["success"]:
                return validation_result
            
            # 加载现有订阅
            subscriptions = self.load_subscriptions()
            
            # 检查是否已订阅
            if fav_id in subscriptions:
                return {
                    "success": False, 
                    "error": f"收藏夹 {fav_id} 已经订阅过了"
                }
            
            # 添加新订阅
            subscriptions[fav_id] = {
                'id': fav_id,
                'url': validation_result["fav_url"],
                'title': validation_result["title"],
                'video_count': validation_result["video_count"],
                'added_time': time.time(),
                'last_check': 0,
                'last_video_count': validation_result["video_count"],
                'user_id': user_id,
                'download_count': 0
            }
            
            # 保存订阅
            if self.save_subscriptions(subscriptions):
                logger.info(f"📚 成功添加订阅: {fav_id} - {validation_result['title']}")
                
                # 启动检查任务（如果还没启动）
                self.ensure_check_task_running()
                
                return {
                    "success": True,
                    "fav_id": fav_id,
                    "title": validation_result["title"],
                    "video_count": validation_result["video_count"],
                    "url": validation_result["fav_url"]
                }
            else:
                return {"success": False, "error": "保存订阅失败"}
                
        except Exception as e:
            logger.error(f"📚 添加订阅失败: {e}")
            return {"success": False, "error": str(e)}
    
    def remove_subscription(self, fav_id: str) -> Dict[str, Any]:
        """
        移除收藏夹订阅
        
        Args:
            fav_id: 收藏夹ID
            
        Returns:
            操作结果字典
        """
        try:
            subscriptions = self.load_subscriptions()
            
            if fav_id not in subscriptions:
                return {"success": False, "error": f"未找到收藏夹ID: {fav_id}"}
            
            # 获取收藏夹信息
            sub_info = subscriptions[fav_id]
            title = sub_info.get('title', f'收藏夹_{fav_id}')
            
            # 删除订阅
            del subscriptions[fav_id]
            
            # 保存订阅
            if self.save_subscriptions(subscriptions):
                logger.info(f"📚 成功移除订阅: {fav_id} - {title}")
                return {
                    "success": True,
                    "fav_id": fav_id,
                    "title": title
                }
            else:
                return {"success": False, "error": "保存订阅失败"}
                
        except Exception as e:
            logger.error(f"📚 移除订阅失败: {e}")
            return {"success": False, "error": str(e)}
    
    def get_subscriptions_list(self) -> List[Dict[str, Any]]:
        """获取订阅列表"""
        try:
            subscriptions = self.load_subscriptions()
            
            result = []
            for fav_id, sub_info in subscriptions.items():
                result.append({
                    'fav_id': fav_id,
                    'title': sub_info.get('title', f'收藏夹_{fav_id}'),
                    'video_count': sub_info.get('video_count', 0),
                    'added_time': sub_info.get('added_time', 0),
                    'last_check': sub_info.get('last_check', 0),
                    'download_count': sub_info.get('download_count', 0),
                    'url': sub_info.get('url', self.build_fav_url(fav_id))
                })
            
            return result
            
        except Exception as e:
            logger.error(f"📚 获取订阅列表失败: {e}")
            return []
    
    def ensure_check_task_running(self):
        """确保检查任务正在运行"""
        if self.check_task is None or self.check_task.done():
            self.check_task = asyncio.create_task(self._check_loop())
            logger.info(f"🔄 启动B站收藏夹订阅检查任务，检查间隔: {self.poll_interval} 分钟")
        else:
            logger.info("✅ B站收藏夹订阅检查任务已在运行中")

    def is_check_task_running(self) -> bool:
        """检查任务是否正在运行"""
        return self.check_task is not None and not self.check_task.done()
    
    async def stop_check_task(self):
        """停止检查任务"""
        if self.check_task and not self.check_task.done():
            self.check_task.cancel()
            try:
                await self.check_task
            except asyncio.CancelledError:
                pass
            logger.info("📚 订阅检查任务已停止")

    async def _check_loop(self):
        """订阅检查循环"""
        logger.info(f"📚 B站收藏夹订阅检查任务启动，检查间隔: {self.poll_interval} 分钟")

        while True:
            try:
                logger.info(f"⏰ 等待 {self.poll_interval} 分钟后进行下一次检查...")
                await asyncio.sleep(self.poll_interval * 60)  # 转换为秒
                logger.info("🔍 开始执行定期订阅检查...")
                await self._check_all_subscriptions()
                logger.info("✅ 定期订阅检查完成")
            except asyncio.CancelledError:
                logger.info("📚 订阅检查任务被取消")
                break
            except Exception as e:
                logger.error(f"📚 订阅检查任务异常: {e}")
                logger.info("⏰ 异常后等待5分钟再重试...")
                await asyncio.sleep(300)  # 异常时等待5分钟

    async def _check_all_subscriptions(self):
        """检查所有订阅的收藏夹"""
        try:
            subscriptions = self.load_subscriptions()
            if not subscriptions:
                return

            logger.info(f"📚 开始检查 {len(subscriptions)} 个订阅的收藏夹")

            # 标记是否有更新
            has_updates = False

            for fav_id in subscriptions.keys():
                try:
                    # 传递整个subscriptions字典，以便修改能被保存
                    updated = await self._check_single_subscription(fav_id, subscriptions)
                    if updated:
                        has_updates = True
                except Exception as e:
                    logger.error(f"📚 检查收藏夹 {fav_id} 失败: {e}")

            # 只有在有更新时才保存
            if has_updates:
                self.save_subscriptions(subscriptions)
                logger.info("📚 订阅信息已更新并保存")

        except Exception as e:
            logger.error(f"📚 检查订阅失败: {e}")

    async def _check_single_subscription(self, fav_id: str, subscriptions: Dict[str, Any]) -> bool:
        """
        检查单个订阅

        Args:
            fav_id: 收藏夹ID
            subscriptions: 完整的订阅字典

        Returns:
            bool: 是否有更新
        """
        try:
            sub_info = subscriptions[fav_id]
            fav_url = sub_info['url']
            logger.info(f"📚 检查收藏夹: {fav_id} - {sub_info.get('title', 'Unknown')}")

            # 获取当前收藏夹信息
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": True,
                "socket_timeout": 30,
                "retries": 3,
            }

            if self.proxy_host:
                ydl_opts["proxy"] = self.proxy_host
            if self.cookies_path and os.path.exists(self.cookies_path):
                ydl_opts["cookiefile"] = self.cookies_path

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(fav_url, download=False)

            if not info:
                logger.warning(f"📚 收藏夹 {fav_id} 无法访问")
                # 仍然更新检查时间
                subscriptions[fav_id]['last_check'] = time.time()
                return True

            current_video_count = len(info.get('entries', []))
            last_video_count = sub_info.get('last_video_count', 0)

            # 更新检查时间和视频数量
            subscriptions[fav_id]['last_check'] = time.time()
            subscriptions[fav_id]['video_count'] = current_video_count

            # 如果有新视频，进行下载
            if current_video_count > last_video_count:
                new_videos = current_video_count - last_video_count
                logger.info(f"📚 收藏夹 {fav_id} 发现 {new_videos} 个新视频，开始下载新增视频")

                # 只下载新增的视频
                download_result = await self._download_new_videos(fav_url, sub_info, info, last_video_count)
                if download_result["success"]:
                    subscriptions[fav_id]['last_video_count'] = current_video_count
                    subscriptions[fav_id]['download_count'] = subscriptions[fav_id].get('download_count', 0) + download_result.get('file_count', 0)
                    logger.info(f"📚 收藏夹 {fav_id} 新增视频下载完成，下载了 {download_result.get('file_count', 0)} 个新文件")
                else:
                    logger.error(f"📚 收藏夹 {fav_id} 下载失败: {download_result.get('error', 'Unknown')}")
            else:
                logger.info(f"📚 收藏夹 {fav_id} 无新视频")

            return True  # 总是返回True表示有更新（至少更新了检查时间）

        except Exception as e:
            logger.error(f"📚 检查收藏夹 {fav_id} 异常: {e}")
            # 即使出错也更新检查时间
            try:
                subscriptions[fav_id]['last_check'] = time.time()
                return True
            except:
                return False

    async def _download_fav_videos(self, fav_url: str, sub_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        下载收藏夹视频

        Args:
            fav_url: 收藏夹URL
            sub_info: 订阅信息

        Returns:
            下载结果字典
        """
        try:
            fav_id = sub_info['id']
            fav_title = sub_info.get('title', f'收藏夹_{fav_id}')

            # 创建收藏夹专用下载目录
            fav_download_path = self.subscription_download_path / f"{fav_title}[{fav_id}]"
            fav_download_path.mkdir(parents=True, exist_ok=True)

            # 配置yt-dlp下载选项 - 使用改进的格式选择，不使用序号
            ydl_opts = {
                "outtmpl": str(fav_download_path / "%(title)s[%(id)s].%(ext)s"),
                "format": (
                    "best[height<=720]/best[height<=480]/best[height<=360]/"
                    "worst[height>=360]/worst[height>=240]/worst"
                ),
                "ignoreerrors": True,  # 对于批量下载保持True
                "continue_dl": True,
                "socket_timeout": 60,
                "retries": 5,
                "writesubtitles": False,
                "writeautomaticsub": False,
            }

            if self.proxy_host:
                ydl_opts["proxy"] = self.proxy_host
            if self.cookies_path and os.path.exists(self.cookies_path):
                ydl_opts["cookiefile"] = self.cookies_path

            logger.info(f"📚 开始下载收藏夹: {fav_title} -> {fav_download_path}")

            # 执行下载
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([fav_url])

            # 统计下载的文件
            downloaded_files = list(fav_download_path.glob("*.mp4"))

            logger.info(f"📚 收藏夹下载完成: {fav_title}, 文件数量: {len(downloaded_files)}")

            return {
                "success": True,
                "fav_id": fav_id,
                "title": fav_title,
                "download_path": str(fav_download_path),
                "file_count": len(downloaded_files)
            }

        except Exception as e:
            logger.error(f"📚 下载收藏夹失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def _download_new_videos(self, fav_url: str, sub_info: Dict[str, Any],
                                   playlist_info: Dict[str, Any], last_video_count: int) -> Dict[str, Any]:
        """
        只下载新增的视频

        Args:
            fav_url: 收藏夹URL
            sub_info: 订阅信息
            playlist_info: 收藏夹信息（包含所有视频条目）
            last_video_count: 上次检查时的视频数量

        Returns:
            下载结果字典
        """
        try:
            fav_id = sub_info['id']
            fav_title = sub_info.get('title', f'收藏夹_{fav_id}')

            # 创建收藏夹专用下载目录
            fav_download_path = self.subscription_download_path / f"{fav_title}[{fav_id}]"
            fav_download_path.mkdir(parents=True, exist_ok=True)

            logger.info(f"📁 下载目录: {fav_download_path}")
            logger.info(f"📁 完整路径: {fav_download_path.absolute()}")

            # 获取所有视频条目
            entries = playlist_info.get('entries', [])
            current_video_count = len(entries)

            if current_video_count <= last_video_count:
                logger.info(f"📚 收藏夹 {fav_id} 没有新视频需要下载")
                return {
                    "success": True,
                    "fav_id": fav_id,
                    "title": fav_title,
                    "download_path": str(fav_download_path),
                    "file_count": 0
                }

            # 计算新增视频的范围
            # B站收藏夹通常是按添加时间倒序排列，新视频在前面
            new_videos_count = current_video_count - last_video_count
            new_entries = entries[:new_videos_count]  # 取前面的新视频

            logger.info(f"📚 准备下载 {len(new_entries)} 个新增视频")

            downloaded_count = 0

            # 逐个下载新增视频
            for i, entry in enumerate(new_entries):
                try:
                    if not entry:
                        continue

                    # 获取视频信息
                    video_url = entry.get('url') or entry.get('webpage_url') or entry.get('id')
                    video_title = entry.get('title') or entry.get('fulltitle') or f'视频_{i+1}'
                    video_id = entry.get('id', f'unknown_{i+1}')

                    # 如果URL不是完整的，尝试构建
                    if video_url and not video_url.startswith('http'):
                        if video_url.startswith('BV'):
                            video_url = f"https://www.bilibili.com/video/{video_url}"
                        else:
                            video_url = f"https://www.bilibili.com/video/BV{video_url}"

                    if not video_url:
                        logger.warning(f"📚 跳过无效视频: {video_title} (无URL)")
                        continue

                    logger.info(f"📚 处理视频 {i+1}/{len(new_entries)}: {video_title}")
                    logger.info(f"📚 视频ID: {video_id}")
                    logger.info(f"📚 视频URL: {video_url}")

                    # 尝试获取真实的视频信息
                    real_video_info = await self._get_video_info(video_url)
                    if real_video_info["success"]:
                        real_title = real_video_info["title"]
                        real_id = real_video_info["id"] or video_id
                        logger.info(f"📚 获取到真实标题: {real_title}")
                        logger.info(f"📚 获取到真实ID: {real_id}")
                    else:
                        real_title = video_title
                        real_id = video_id
                        logger.warning(f"📚 使用原始标题: {real_title}")

                    # 生成唯一的文件名（不使用序号）
                    safe_title = self._sanitize_filename(real_title)

                    # 使用视频ID确保文件名唯一性
                    if real_id and real_id != f'unknown_{i+1}':
                        safe_filename = f"{safe_title}[{real_id}]"
                    else:
                        safe_filename = f"{safe_title}_{i+1}"  # 如果没有ID，使用索引作为后缀

                    output_template = f"{safe_filename}.%(ext)s"
                    output_path = fav_download_path / output_template

                    # 检查文件是否已存在（使用更精确的匹配）
                    existing_files = list(fav_download_path.glob(f"{safe_filename}.*"))
                    if existing_files:
                        logger.info(f"📚 跳过已存在的文件: {video_title} -> {existing_files[0].name}")
                        downloaded_count += 1  # 已存在的文件也算作"下载成功"
                        continue

                    logger.info(f"📚 准备下载到: {output_path}")

                    logger.info(f"📚 下载新视频 {i+1}/{len(new_entries)}: {video_title}")

                    # 配置单个视频下载选项 - 使用更宽松的格式选择
                    ydl_opts = {
                        "outtmpl": str(output_path),
                        # 更宽松的格式选择策略，优先选择免费可用的格式
                        "format": (
                            "best[height<=720]/best[height<=480]/best[height<=360]/"
                            "worst[height>=360]/worst[height>=240]/worst"
                        ),
                        "ignoreerrors": False,
                        "continue_dl": True,
                        "socket_timeout": 60,
                        "retries": 3,
                        "no_warnings": False,
                        # 添加B站特定选项
                        "writesubtitles": False,
                        "writeautomaticsub": False,
                    }

                    if self.proxy_host:
                        ydl_opts["proxy"] = self.proxy_host
                    if self.cookies_path and os.path.exists(self.cookies_path):
                        ydl_opts["cookiefile"] = self.cookies_path

                    # 下载单个视频 - 使用B站专用的多策略重试
                    download_success = False
                    format_strategies = self._get_bilibili_format_strategies()
                    base_opts = self._get_bilibili_format_options()

                    for strategy_idx, format_selector in enumerate(format_strategies):
                        try:
                            # 构建当前策略的选项
                            current_opts = base_opts.copy()
                            current_opts["outtmpl"] = str(output_path)
                            current_opts["ignoreerrors"] = False

                            if format_selector:
                                current_opts["format"] = format_selector
                                logger.info(f"📚 尝试下载策略 {strategy_idx + 1}: {format_selector}")
                            else:
                                logger.info(f"📚 尝试下载策略 {strategy_idx + 1}: 默认格式")

                            with yt_dlp.YoutubeDL(current_opts) as ydl:
                                ydl.download([video_url])

                            # 验证文件是否真的下载成功（使用相同的文件名模式）
                            downloaded_files = list(fav_download_path.glob(f"{safe_filename}.*"))
                            if downloaded_files:
                                downloaded_count += 1
                                actual_file = downloaded_files[0]
                                logger.info(f"✅ 成功下载: {video_title} -> {actual_file.name}")
                                download_success = True
                                break
                            else:
                                logger.warning(f"⚠️ 策略 {strategy_idx + 1} 下载完成但文件未找到: {safe_filename}.*")

                        except Exception as download_e:
                            error_msg = str(download_e)
                            if "Requested format is not available" in error_msg:
                                logger.warning(f"⚠️ 策略 {strategy_idx + 1} 格式不可用，尝试下一个策略")
                            elif "premium member" in error_msg:
                                logger.warning(f"⚠️ 策略 {strategy_idx + 1} 需要会员权限，尝试下一个策略")
                            else:
                                logger.warning(f"⚠️ 策略 {strategy_idx + 1} 失败: {error_msg}")

                            if strategy_idx == len(format_strategies) - 1:
                                logger.error(f"❌ 所有下载策略都失败: {video_title}")
                            continue

                    if not download_success:
                        logger.error(f"❌ 下载失败: {video_title} - 所有格式策略都不可用")

                except Exception as video_e:
                    logger.error(f"❌ 下载视频失败: {video_title} - {video_e}")
                    continue

            # 最终验证下载结果
            final_files = list(fav_download_path.glob("*.mp4")) + list(fav_download_path.glob("*.flv")) + list(fav_download_path.glob("*.mkv"))

            logger.info(f"📚 新增视频下载完成: {fav_title}")
            logger.info(f"📊 下载统计: 成功 {downloaded_count}/{len(new_entries)} 个新视频")
            logger.info(f"📁 下载目录: {fav_download_path.absolute()}")
            logger.info(f"📄 目录中的文件数: {len(final_files)}")

            if final_files:
                logger.info("📄 下载的文件:")
                for file in final_files[:3]:  # 显示前3个文件
                    logger.info(f"   - {file.name}")
                if len(final_files) > 3:
                    logger.info(f"   ... 还有 {len(final_files) - 3} 个文件")

            return {
                "success": True,
                "fav_id": fav_id,
                "title": fav_title,
                "download_path": str(fav_download_path.absolute()),
                "file_count": downloaded_count,
                "total_files": len(final_files)
            }

        except Exception as e:
            logger.error(f"📚 下载新增视频失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名，移除不安全字符"""
        import re
        # 移除或替换不安全的字符
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        # 移除多余的空格和点
        filename = re.sub(r'\s+', ' ', filename).strip()
        filename = filename.strip('.')
        # 限制长度
        if len(filename) > 100:
            filename = filename[:100]
        return filename

    def _get_bilibili_format_options(self) -> Dict[str, Any]:
        """获取B站专用的yt-dlp选项"""
        base_opts = {
            "writesubtitles": False,
            "writeautomaticsub": False,
            "socket_timeout": 60,
            "retries": 3,
            "continue_dl": True,
        }

        # 添加代理和cookies
        if self.proxy_host:
            base_opts["proxy"] = self.proxy_host
        if self.cookies_path and os.path.exists(self.cookies_path):
            base_opts["cookiefile"] = self.cookies_path

        return base_opts

    def _get_bilibili_format_strategies(self) -> list:
        """获取B站视频格式选择策略列表"""
        return [
            # 策略1：优先720p及以下的免费格式
            "best[height<=720][tbr<=2000]/best[height<=480][tbr<=1500]",
            # 策略2：更低质量但稳定的格式
            "best[height<=480]/best[height<=360]",
            # 策略3：最低质量
            "worst[height>=240]/worst[height>=144]",
            # 策略4：任何可用的最差质量
            "worst",
            # 策略5：完全默认（移除所有格式限制）
            None
        ]

    async def _get_video_info(self, video_url: str) -> Dict[str, Any]:
        """获取单个视频的详细信息"""
        try:
            info_opts = self._get_bilibili_format_options()
            info_opts.update({
                "quiet": True,
                "no_warnings": True,
                "extract_flat": False,  # 获取完整信息
                "socket_timeout": 30,
            })

            with yt_dlp.YoutubeDL(info_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)

            return {
                "success": True,
                "title": info.get('title', '未知标题'),
                "id": info.get('id', ''),
                "duration": info.get('duration', 0),
                "uploader": info.get('uploader', ''),
                "description": info.get('description', ''),
            }

        except Exception as e:
            logger.warning(f"获取视频信息失败: {video_url} - {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def manual_download(self, fav_id: str) -> Dict[str, Any]:
        """
        手动下载指定收藏夹（下载所有视频，跳过已存在的）

        Args:
            fav_id: 收藏夹ID

        Returns:
            下载结果字典
        """
        try:
            subscriptions = self.load_subscriptions()

            if fav_id not in subscriptions:
                return {"success": False, "error": f"未找到收藏夹ID: {fav_id}"}

            sub_info = subscriptions[fav_id]
            fav_url = sub_info['url']

            logger.info(f"📚 手动下载收藏夹: {fav_id}")

            # 获取收藏夹信息
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": True,
                "socket_timeout": 30,
                "retries": 3,
            }

            if self.proxy_host:
                ydl_opts["proxy"] = self.proxy_host
            if self.cookies_path and os.path.exists(self.cookies_path):
                ydl_opts["cookiefile"] = self.cookies_path

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(fav_url, download=False)

            if not info:
                return {"success": False, "error": "收藏夹无法访问"}

            # 使用新的下载方法，但下载所有视频（last_video_count=0）
            result = await self._download_new_videos(fav_url, sub_info, info, 0)

            if result["success"]:
                # 更新订阅信息
                current_video_count = len(info.get('entries', []))
                subscriptions[fav_id]['last_check'] = time.time()
                subscriptions[fav_id]['video_count'] = current_video_count
                subscriptions[fav_id]['last_video_count'] = current_video_count
                subscriptions[fav_id]['download_count'] = subscriptions[fav_id].get('download_count', 0) + result.get('file_count', 0)
                self.save_subscriptions(subscriptions)

            return result

        except Exception as e:
            logger.error(f"📚 手动下载失败: {e}")
            return {"success": False, "error": str(e)}

