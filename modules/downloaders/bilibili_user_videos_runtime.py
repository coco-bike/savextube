# -*- coding: utf-8 -*-
"""Bilibili UP主全量视频下载运行时逻辑。"""

from pathlib import Path
from typing import Any, Dict


async def download_bilibili_user_all_videos(
    downloader, uid: str, download_path: Path, message_updater=None, *, logger
) -> Dict[str, Any]:
        """下载B站UP主的所有视频（参考YouTube频道下载模式）"""
        import re  # 在函数开头导入，确保整个函数都能使用
        import time
        import os

        logger.info(f"🎬 开始下载B站UP主的所有视频: UID={uid}")
        logger.info(f"🔍 message_updater参数: type={type(message_updater)}, callable={callable(message_updater)}")

        try:
            # 步骤1: 使用yt-dlp获取UP主的视频列表
            logger.info("🔍 步骤1: 使用yt-dlp获取UP主的视频列表...")

            if message_updater:
                try:
                    import asyncio
                    if asyncio.iscoroutinefunction(message_updater):
                        await message_updater("🔍 正在获取UP主的视频列表...")
                    else:
                        message_updater("🔍 正在获取UP主的视频列表...")
                except Exception as e:
                    logger.warning(f"更新状态消息失败: {e}")

            # 构建UP主空间URL
            user_space_url = f"https://space.bilibili.com/{uid}"

            # 配置yt-dlp选项，增强对B站的兼容性
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": True,
                "socket_timeout": 120,  # 增加超时时间
                "retries": 10,  # 增加重试次数
                "playlistend": None,  # 不限制，获取所有视频
                "sleep_interval": 2,  # 添加请求间隔
                "max_sleep_interval": 5,
                "sleep_interval_subtitles": 1,
                # 添加更多B站兼容性选项
                "extractor_args": {
                    "bilibili": {
                        "api_version": "app",  # 使用APP API
                    }
                },
                # 添加用户代理
                "http_headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Referer": "https://www.bilibili.com/",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
                    "Accept-Encoding": "gzip, deflate, br",
                }
            }

            if downloader.proxy_host:
                ydl_opts["proxy"] = downloader.proxy_host
            if downloader.b_cookies_path and os.path.exists(downloader.b_cookies_path):
                ydl_opts["cookiefile"] = downloader.b_cookies_path
                logger.info(f"🍪 使用B站cookies文件: {downloader.b_cookies_path}")

                # 检查cookies文件内容
                try:
                    with open(downloader.b_cookies_path, 'r', encoding='utf-8') as f:
                        cookies_content = f.read()
                        if 'SESSDATA' in cookies_content:
                            logger.info("✅ Cookies文件包含SESSDATA，格式正确")
                        else:
                            logger.warning("⚠️ Cookies文件可能缺少SESSDATA字段")

                        # 检查文件大小
                        file_size = len(cookies_content)
                        logger.info(f"📊 Cookies文件大小: {file_size} 字符")

                except Exception as e:
                    logger.warning(f"⚠️ 无法读取cookies文件内容: {e}")
            else:
                logger.warning("⚠️ 未配置B站cookies，可能无法访问某些内容")

            import yt_dlp

            # 尝试多种方式获取UP主的视频列表
            info = None
            last_error = None

            # 方式1: 直接访问UP主空间
            try:
                logger.info(f"🔍 方式1: 直接访问UP主空间 {user_space_url}")
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(user_space_url, download=False)
                logger.info("✅ 方式1成功")
            except Exception as e:
                last_error = str(e)
                logger.warning(f"❌ 方式1失败: {e}")

                # 方式2: 尝试使用投稿页面
                try:
                    video_url = f"https://space.bilibili.com/{uid}/video"
                    logger.info(f"🔍 方式2: 尝试投稿页面 {video_url}")
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(video_url, download=False)
                    logger.info("✅ 方式2成功")
                except Exception as e2:
                    last_error = str(e2)
                    logger.warning(f"❌ 方式2失败: {e2}")

                    # 方式3: 尝试使用不同的URL格式
                    try:
                        channel_url = f"https://space.bilibili.com/{uid}/channel/series"
                        logger.info(f"🔍 方式3: 尝试频道系列页面 {channel_url}")
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            info = ydl.extract_info(channel_url, download=False)
                        logger.info("✅ 方式3成功")
                    except Exception as e3:
                        last_error = str(e3)
                        logger.warning(f"❌ 方式3失败: {e3}")

                        # 方式4: 降级处理，使用更宽松的配置
                        try:
                            logger.info(f"🔍 方式4: 降级处理，使用更宽松的配置")
                            limited_opts = {
                                "quiet": True,
                                "extract_flat": True,
                                "socket_timeout": 180,
                                "retries": 3,
                                "playlistend": None,  # 不限制，获取所有视频
                                "sleep_interval": 1,  # 减少请求间隔
                            }
                            if downloader.proxy_host:
                                limited_opts["proxy"] = downloader.proxy_host
                            if downloader.b_cookies_path and os.path.exists(downloader.b_cookies_path):
                                limited_opts["cookiefile"] = downloader.b_cookies_path

                            with yt_dlp.YoutubeDL(limited_opts) as ydl:
                                info = ydl.extract_info(user_space_url, download=False)
                            logger.info("✅ 方式4成功（宽松配置）")
                        except Exception as e4:
                            last_error = str(e4)
                            logger.error(f"❌ 方式4失败: {e4}")

                            # 方式5: 最后尝试，使用最简单的配置但获取所有视频
                            try:
                                logger.info(f"🔍 方式5: 最简配置尝试（获取所有视频）")
                                simple_opts = {
                                    "quiet": True,
                                    "extract_flat": True,
                                    "playlistend": None,  # 不限制，获取所有视频
                                    "socket_timeout": 120,
                                    "retries": 3,
                                }
                                if downloader.b_cookies_path and os.path.exists(downloader.b_cookies_path):
                                    simple_opts["cookiefile"] = downloader.b_cookies_path

                                with yt_dlp.YoutubeDL(simple_opts) as ydl:
                                    info = ydl.extract_info(user_space_url, download=False)
                                logger.info("✅ 方式5成功（最简模式，获取所有视频）")
                            except Exception as e5:
                                last_error = str(e5)
                                logger.error(f"❌ 方式5失败: {e5}")

                                # 方式6: 如果还是失败，尝试分页获取
                                try:
                                    logger.info(f"🔍 方式6: 分页获取模式")
                                    paginated_opts = {
                                        "quiet": True,
                                        "extract_flat": True,
                                        "playlistend": 500,  # 限制为500个，避免超时
                                        "socket_timeout": 180,
                                        "retries": 2,
                                    }
                                    if downloader.b_cookies_path and os.path.exists(downloader.b_cookies_path):
                                        paginated_opts["cookiefile"] = downloader.b_cookies_path

                                    with yt_dlp.YoutubeDL(paginated_opts) as ydl:
                                        info = ydl.extract_info(user_space_url, download=False)
                                    logger.info("✅ 方式6成功（分页模式）")
                                except Exception as e6:
                                    last_error = str(e6)
                                    logger.error(f"❌ 方式6失败: {e6}")

            if not info:
                error_msg = f"无法获取UP主 {uid} 的视频信息。最后错误: {last_error}"
                logger.error(error_msg)

                # 检查是否是B站限制问题
                if "352" in str(last_error) or "rejected by server" in str(last_error).lower():
                    error_msg += "\n\n💡 建议解决方案:\n1. 配置B站cookies文件\n2. 使用代理服务器\n3. 稍后重试"

                return {'success': False, 'error': error_msg}

            # 获取UP主信息
            uploader_name = info.get('uploader', f'UP主_{uid}')
            uploader_id = info.get('uploader_id', uid)

            # 获取视频列表
            entries = info.get('entries', [])
            if not entries:
                error_msg = f"UP主 {uid} 没有任何视频"
                logger.error(error_msg)
                return {'success': False, 'error': error_msg}

            logger.info(f"📊 找到 {len(entries)} 个视频")

            # 检查是否获取完整
            total_count = info.get('playlist_count') or info.get('_total_count') or len(entries)
            if total_count and total_count > len(entries):
                logger.warning(f"⚠️ 可能未获取完整视频列表: 获取到 {len(entries)} 个，预期 {total_count} 个")
            else:
                logger.info(f"✅ 成功获取完整视频列表: {len(entries)} 个视频")

            if message_updater:
                try:
                    # message_updater是同步函数，直接调用
                    message_updater(f"🔍 正在分析 {len(entries)} 个视频...")
                except Exception as e:
                    logger.warning(f"更新状态消息失败: {e}")

            # 步骤2: 创建UP主专用下载目录（参考YouTube频道模式）
            # 清理UP主名称，移除文件系统不支持的字符
            clean_uploader_name = re.sub(r'[\\/:*?"<>|]', "_", uploader_name).strip()
            user_download_path = download_path / clean_uploader_name
            user_download_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"📁 UP主目录: {user_download_path}")

            # 步骤3: 简化分析：按播放列表分组，但不进行复杂的类型检测
            logger.info("🚀 采用简化播放列表分文件夹模式")
            logger.info("🔍 步骤3: 简单分析播放列表...")

            if message_updater and callable(message_updater):
                try:
                    # message_updater是同步函数，直接调用
                    message_updater(f"🔍 正在分析 {len(entries)} 个视频的播放列表...")
                except Exception as e:
                    logger.warning(f"更新状态消息失败: {e}")
            elif message_updater:
                logger.warning("⚠️ message_updater 不是可调用对象")

            # 增强合集识别：基于URL特征、标题模式和BV号
            playlists = {}
            single_videos = []

            # 用于存储BV号对应的合集信息
            bv_playlists = {}

            for entry in entries:
                if not entry:
                    continue

                video_url = entry.get('url') or entry.get('webpage_url')
                video_title = entry.get('title', '')

                if not video_url:
                    single_videos.append(entry)
                    continue

                # 检查URL中是否有明显的播放列表标识
                playlist_id = None
                playlist_name = "未知播放列表"
                playlist_type = "unknown"

                # 检查UGC合集 (list_id参数)
                if 'list_id=' in video_url:
                    match = re.search(r'list_id=(\d+)', video_url)
                    if match:
                        playlist_id = f"ugc_{match.group(1)}"
                        playlist_name = f"UGC合集_{match.group(1)}"
                        playlist_type = "ugc"

                # 检查多P视频 (p=参数)
                elif '?p=' in video_url or '&p=' in video_url:
                    bv_match = re.search(r'BV([A-Za-z0-9]+)', video_url)
                    if bv_match:
                        bv_id = bv_match.group(1)
                        playlist_id = f"multipart_{bv_id}"
                        # 从标题中提取合集名称
                        if '【' in video_title and '】' in video_title:
                            # 提取【】中的内容作为合集名
                            title_match = re.search(r'【([^】]+)】', video_title)
                            if title_match:
                                playlist_name = title_match.group(1)
                            else:
                                playlist_name = f"多P视频_{bv_id}"
                        else:
                            playlist_name = f"多P视频_{bv_id}"
                        playlist_type = "multipart"

                # 增强：检查标题模式识别合集
                if not playlist_id and video_title:
                    # 检查标题中的合集标识
                    title_patterns = [
                        r'第(\d+)集',           # 第X集
                        r'Part\s*(\d+)',       # Part X
                        r'(\d+)\s*[话話]',     # X话
                        r'第(\d+)章',           # 第X章
                        r'第(\d+)回',           # 第X回
                        r'(\d+)\s*[期期]',     # X期
                        r'第(\d+)课',           # 第X课
                        r'第(\d+)讲',           # 第X讲
                    ]

                    for pattern in title_patterns:
                        match = re.search(pattern, video_title)
                        if match:
                            episode_num = match.group(1)
                            # 提取合集名称（去掉集数部分）
                            clean_title = re.sub(pattern, '', video_title).strip()
                            clean_title = re.sub(r'[【】\[\]\(\)（）]', '', clean_title).strip()

                            if clean_title:
                                # 使用清理后的标题作为合集名
                                playlist_id = f"title_pattern_{clean_title}"
                                playlist_name = clean_title
                                playlist_type = "title_pattern"
                                break

                # 如果通过标题模式识别到合集，检查是否有对应的BV号
                if playlist_id and playlist_type == "title_pattern":
                    bv_match = re.search(r'BV([A-Za-z0-9]+)', video_url)
                    if bv_match:
                        bv_id = bv_match.group(1)
                        # 检查是否有相同BV号的其他视频
                        if bv_id in bv_playlists:
                            # 如果BV号已存在，使用相同的playlist_id
                            playlist_id = bv_playlists[bv_id]
                        else:
                            # 记录这个BV号对应的playlist_id
                            bv_playlists[bv_id] = playlist_id

                if playlist_id:
                    if playlist_id not in playlists:
                        playlists[playlist_id] = {
                            'name': playlist_name,
                            'type': playlist_type,
                            'videos': []
                        }
                    playlists[playlist_id]['videos'].append(entry)
                else:
                    single_videos.append(entry)

            logger.info(f"📊 简单分组结果: {len(playlists)} 个播放列表, {len(single_videos)} 个单独视频")

            # 显示预期的目录结构
            logger.info("📁 预期目录结构:")
            logger.info(f"  📂 UP主目录: {user_download_path}")
            for playlist_id, playlist_info in playlists.items():
                playlist_name = playlist_info['name']
                logger.info(f"    📁 合集: {playlist_name}/")
            if single_videos:
                logger.info(f"    📁 单独视频/")

            # 步骤5: 使用现有下载方法，复用进度显示和完成逻辑
            logger.info("🔍 步骤5: 使用现有下载方法处理各类视频...")

            downloaded_results = []
            total_downloaded = 0
            total_failed = 0
            total_size_mb = 0

            # 处理播放列表（UGC合集、多P视频等）
            playlist_index = 0
            for playlist_id, playlist_info in playlists.items():
                try:
                    playlist_index += 1
                    playlist_name = playlist_info['name']
                    videos = playlist_info['videos']

                    if message_updater:
                        try:
                            initial_msg = f"""📥 正在下载第{playlist_index}/{len(playlists)}个播放列表：{playlist_name}

📺 总视频数: {len(videos)}
📊 状态: 开始下载..."""
                            import asyncio
                            if asyncio.iscoroutinefunction(message_updater):
                                await message_updater(initial_msg)
                            elif callable(message_updater):
                                message_updater(initial_msg)
                        except Exception as e:
                            logger.warning(f"更新状态消息失败: {e}")

                    logger.info(f"🎬 开始处理播放列表: {playlist_name} ({len(videos)} 个视频)")

                    # 为播放列表中的每个视频调用现有的下载方法
                    playlist_downloaded = 0
                    playlist_failed = 0

                    # 创建播放列表目录
                    playlist_path = user_download_path / playlist_name
                    playlist_path.mkdir(parents=True, exist_ok=True)
                    logger.info(f"📁 创建播放列表目录: {playlist_path}")

                    for video_idx, video in enumerate(videos, 1):
                        video_url = video.get('url') or video.get('webpage_url')
                        video_title = video.get('title', '')

                        if video_url:
                            try:
                                logger.info(f"🎬 调用现有下载方法处理视频 {video_idx}/{len(videos)}: {video_url}")
                                logger.info(f"🔍 传递给download_video的message_updater: {type(message_updater)}, callable: {callable(message_updater)}")

                                # 生成更好的文件名
                                clean_title = re.sub(r'[\\/:*?"<>|]', "_", video_title).strip()
                                if playlist_type == "multipart":
                                    # 多P视频使用集数命名
                                    episode_match = re.search(r'p=(\d+)', video_url)
                                    if episode_match:
                                        episode_num = episode_match.group(1)
                                        filename = f"{episode_num:02d}. {clean_title}.mp4"
                                    else:
                                        filename = f"{video_idx:02d}. {clean_title}.mp4"
                                elif playlist_type == "title_pattern":
                                    # 标题模式识别的合集，尝试提取集数
                                    episode_patterns = [
                                        r'第(\d+)集', r'Part\s*(\d+)', r'(\d+)\s*[话話]',
                                        r'第(\d+)章', r'第(\d+)回', r'(\d+)\s*[期期]',
                                        r'第(\d+)课', r'第(\d+)讲'
                                    ]
                                    episode_num = None
                                    for pattern in episode_patterns:
                                        match = re.search(pattern, video_title)
                                        if match:
                                            episode_num = int(match.group(1))
                                            break

                                    if episode_num:
                                        filename = f"{episode_num:02d}. {clean_title}.mp4"
                                    else:
                                        filename = f"{video_idx:02d}. {clean_title}.mp4"
                                else:
                                    # 其他类型使用索引命名
                                    filename = f"{video_idx:02d}. {clean_title}.mp4"

                                logger.info(f"📝 生成文件名: {filename}")



                                # 临时修改下载路径到播放列表目录
                                original_bilibili_path = downloader.bilibili_download_path
                                downloader.bilibili_download_path = playlist_path
                                logger.info(f"🔧 临时修改B站下载路径: {downloader.bilibili_download_path}")

                                try:
                                    # 创建同步进度更新器，兼容yt-dlp的进度回调
                                    def progress_updater(progress_text):
                                        logger.info(f"🔍 播放列表进度更新器被调用: type={type(progress_text)}")

                                        if isinstance(progress_text, str):
                                            # 如果是字符串，直接显示
                                            logger.info(f"🔍 收到字符串消息: {progress_text[:100]}...")
                                            # 对于字符串消息，我们暂时跳过，因为异步调用复杂
                                            logger.info(f"⚠️ 跳过字符串消息的异步调用")
                                        else:
                                            # 如果是字典（yt-dlp进度数据），转换为格式化消息
                                            d = progress_text
                                            logger.info(f"🔍 收到进度字典: status={d.get('status')}, filename={d.get('filename', 'N/A')}")

                                            if d.get("status") == "downloading":
                                                # 控制更新频率
                                                import time
                                                current_time = time.time()
                                                if not hasattr(progress_updater, 'last_update'):
                                                    progress_updater.last_update = 0

                                                if current_time - progress_updater.last_update < 3:  # 3秒更新一次
                                                    return
                                                progress_updater.last_update = current_time
                                                # 获取进度信息
                                                filename = d.get("filename", "未知文件")
                                                if filename:
                                                    filename = os.path.basename(filename)

                                                # 调试：打印所有可用的字段
                                                logger.info(f"🔍 播放列表进度字典所有字段: {list(d.keys())}")
                                                logger.info(f"🔍 播放列表进度字典内容: {d}")

                                                downloaded_bytes = d.get("downloaded_bytes", 0)
                                                total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                                                speed = d.get("speed", 0)

                                                # 调试：打印原始数值
                                                logger.info(f"🔍 播放列表原始数值: downloaded_bytes={downloaded_bytes}, total_bytes={total_bytes}, speed={speed}")

                                                # 格式化大小和速度
                                                downloaded_mb = downloaded_bytes / (1024 * 1024) if downloaded_bytes else 0
                                                total_mb = total_bytes / (1024 * 1024) if total_bytes else 0
                                                speed_mb = speed / (1024 * 1024) if speed else 0

                                                # 计算进度
                                                if total_bytes > 0:
                                                    progress_percent = (downloaded_bytes / total_bytes) * 100
                                                else:
                                                    progress_percent = 0

                                                # 计算预计剩余时间
                                                eta_seconds = d.get("eta", 0)
                                                if eta_seconds and eta_seconds > 0:
                                                    eta_minutes = eta_seconds // 60
                                                    eta_secs = eta_seconds % 60
                                                    eta_str = f"{eta_minutes:02d}:{eta_secs:02d}"
                                                else:
                                                    eta_str = "未知"

                                                # 创建进度条
                                                bar_length = 20
                                                filled_length = int(bar_length * progress_percent / 100)
                                                bar = '█' * filled_length + '░' * (bar_length - filled_length)

                                                # 构建详细的进度消息
                                                progress_text = f"""📥 正在下载第{playlist_index}/{len(playlists)}个播放列表：{playlist_name}

📺 当前视频: {video_idx}/{len(videos)}
📝 文件: {filename}
💾 大小: {downloaded_mb:.2f}MB / {total_mb:.2f}MB
⚡️ 速度: {speed_mb:.2f}MB/s
⏳ 预计剩余: {eta_str}
📊 进度: [{bar}] {progress_percent:.1f}%"""

                                                # 发送进度消息（使用线程安全的方式）
                                                if message_updater and callable(message_updater):
                                                    try:
                                                        import asyncio
                                                        import threading

                                                        # 直接调用同步的message_updater（update_progress），线程安全地编辑TG消息
                                                        try:
                                                            message_updater(progress_text)
                                                            logger.info(f"✅ 播放列表进度消息发送成功")
                                                        except Exception as e:
                                                            logger.warning(f"发送播放列表进度消息失败: {e}")

                                                    except Exception as e:
                                                        logger.warning(f"创建播放列表进度消息线程失败: {e}")

                                    # 创建简化的进度更新器
                                    async def simple_progress_updater(progress_text):
                                        try:
                                            logger.info(f"🔍 [DEBUG] 播放列表simple_progress_updater被调用: type={type(progress_text)}")
                                            logger.info(f"🔍 [DEBUG] 播放列表message_updater状态: {message_updater}, type={type(message_updater)}")

                                            if isinstance(progress_text, str):
                                                # 字符串消息直接发送
                                                if message_updater and callable(message_updater):
                                                    logger.info(f"🔍 [DEBUG] 播放列表准备调用message_updater")
                                                    # message_updater是同步函数，直接调用
                                                    message_updater(progress_text)
                                                    logger.info(f"✅ [DEBUG] 播放列表message_updater调用成功")
                                                else:
                                                    logger.warning(f"⚠️ [DEBUG] 播放列表message_updater不可用: {message_updater}")
                                            else:
                                                # 字典数据处理，转换为进度消息
                                                logger.info(f"🔍 [DEBUG] 播放列表处理字典数据: {progress_text}")

                                                if isinstance(progress_text, dict) and progress_text.get("status") == "downloading":
                                                    d = progress_text

                                                    # 获取进度信息
                                                    filename = d.get("filename", "未知文件")
                                                    if filename:
                                                        filename = os.path.basename(filename)

                                                    downloaded_bytes = d.get("downloaded_bytes", 0)
                                                    total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                                                    speed = d.get("speed", 0)

                                                    # 格式化大小和速度
                                                    downloaded_mb = downloaded_bytes / (1024 * 1024) if downloaded_bytes else 0
                                                    total_mb = total_bytes / (1024 * 1024) if total_bytes else 0
                                                    speed_mb = speed / (1024 * 1024) if speed else 0

                                                    # 计算进度
                                                    if total_bytes > 0:
                                                        progress_percent = (downloaded_bytes / total_bytes) * 100
                                                    else:
                                                        progress_percent = 0

                                                    # 计算预计剩余时间
                                                    eta_seconds = d.get("eta", 0)
                                                    if eta_seconds and eta_seconds > 0:
                                                        if eta_seconds >= 3600:  # 超过1小时
                                                            eta_hours = eta_seconds // 3600
                                                            eta_minutes = (eta_seconds % 3600) // 60
                                                            eta_str = f"{eta_hours}小时{eta_minutes}分钟"
                                                        elif eta_seconds >= 60:  # 超过1分钟
                                                            eta_minutes = eta_seconds // 60
                                                            eta_secs = eta_seconds % 60
                                                            eta_str = f"{eta_minutes}分{eta_secs:02d}秒"
                                                        else:  # 小于1分钟
                                                            eta_str = f"{eta_seconds}秒"
                                                    else:
                                                        eta_str = "未知"

                                                    # 创建进度条（使用你要的格式）
                                                    bar_length = 20
                                                    filled_length = int(bar_length * progress_percent / 100)
                                                    bar = '█' * filled_length + '░' * (bar_length - filled_length)

                                                    # 构建简洁的进度消息（你要的格式）
                                                    progress_text = f"""📥 下载中 ({video_idx}/{len(videos)})
📝 文件名: {filename}
💾 大小: {downloaded_mb:.2f}MB / {total_mb:.2f}MB
⚡️ 速度: {speed_mb:.2f}MB/s
⏳ 预计剩余: {eta_str}
📊 进度: {bar} {progress_percent:.1f}%"""

                                                    # 发送进度消息
                                                    if message_updater and callable(message_updater):
                                                        logger.info(f"🔍 [DEBUG] 播放列表发送实时进度消息")
                                                        try:
                                                            # message_updater是同步函数，直接调用
                                                            logger.info(f"🔍 [DEBUG] 播放列表调用message_updater(dict): {type(message_updater)}")
                                                            message_updater(d)
                                                            logger.info(f"✅ [DEBUG] 播放列表实时进度字典发送成功")
                                                        except Exception as e:
                                                            logger.warning(f"❌ [DEBUG] 播放列表实时进度消息发送失败: {e}")
                                                            logger.warning(f"🔍 [DEBUG] 播放列表message_updater详情: {type(message_updater)}")
                                                            import traceback
                                                            logger.warning(f"🔍 [DEBUG] 播放列表完整错误堆栈: {traceback.format_exc()}")
                                                else:
                                                    logger.info(f"🔍 [DEBUG] 播放列表跳过非下载状态的字典数据: {progress_text.get('status') if isinstance(progress_text, dict) else 'unknown'}")
                                        except Exception as e:
                                            logger.warning(f"播放列表简化进度更新失败: {e}")
                                            logger.warning(f"🔍 [DEBUG] 播放列表异常详情: message_updater={message_updater}, progress_text={progress_text}")

                                    # 调用download_video，直接传递上层的message_updater以使用统一的进度管道
                                    result = await downloader.download_video(video_url, message_updater if message_updater else None)

                                    # 手动发送进度更新（简化版本）
                                    if message_updater and callable(message_updater):
                                        try:
                                            # 获取文件名
                                            filename = "未知文件"
                                            if result.get('success', False) and result.get('filename'):
                                                filename = os.path.basename(result.get('filename'))

                                            progress_msg = f"""📥 正在下载第{playlist_index}/{len(playlists)}个播放列表：{playlist_name}

📺 当前视频: {video_idx}/{len(videos)}
📝 文件: {filename}
📊 状态: ✅ 下载完成
💾 大小: {result.get('size_mb', 0):.2f} MB"""
                                            # message_updater是同步函数，直接调用
                                            message_updater(progress_msg)
                                            logger.info(f"✅ 手动发送播放列表进度更新成功")
                                        except Exception as e:
                                            logger.warning(f"手动发送播放列表进度更新失败: {e}")

                                    # 发送简洁的进度更新，而不是详细的完成消息
                                    if result.get('success', False) and message_updater and callable(message_updater):
                                        try:
                                            # 只显示简单的进度更新，详细总结在最后显示
                                            progress_text = f"""📥 正在下载第{playlist_index}/{len(playlists)}个播放列表：{playlist_name}

📺 当前视频: {video_idx}/{len(videos)} ✅ 下载完成
📝 文件: {os.path.basename(result.get('filename', '未知文件'))}
💾 大小: {result.get('size_mb', 0):.2f} MB"""
                                            # message_updater是同步函数，直接调用
                                            message_updater(progress_text)
                                            logger.info(f"✅ 播放列表视频进度更新已发送")
                                        except Exception as e:
                                            logger.warning(f"发送播放列表视频进度更新失败: {e}")

                                except Exception as e:
                                    logger.error(f"播放列表视频下载异常: {e}")
                                    if message_updater and callable(message_updater):
                                        try:
                                            # message_updater是同步函数，直接调用
                                            message_updater(f"❌ 视频下载失败: {str(e)}")
                                        except Exception as msg_e:
                                            logger.warning(f"发送错误消息失败: {msg_e}")
                                    result = {'success': False, 'error': str(e)}
                                finally:
                                    # 恢复原始下载路径
                                    downloader.bilibili_download_path = original_bilibili_path
                                    logger.info(f"🔧 恢复B站下载路径: {downloader.bilibili_download_path}")

                                if result.get('success', False):
                                    playlist_downloaded += 1
                                    total_downloaded += 1
                                    # 累计文件大小
                                    if 'size_mb' in result:
                                        total_size_mb += result['size_mb']
                                    logger.info(f"✅ 播放列表视频下载成功: {video_idx}/{len(videos)}")
                                else:
                                    playlist_failed += 1
                                    total_failed += 1
                                    logger.error(f"❌ 播放列表视频下载失败: {video_idx}/{len(videos)} - {result.get('error', '未知错误')}")

                            except Exception as e:
                                playlist_failed += 1
                                total_failed += 1
                                logger.error(f"❌ 播放列表视频下载异常: {video_idx}/{len(videos)} - {e}")

                    # 记录播放列表结果
                    if playlist_downloaded > 0:
                        playlist_result = {
                            'title': playlist_name,
                            'type': '播放列表',
                            'video_count': playlist_downloaded,
                            'failed_count': playlist_failed,
                            'download_path': str(user_download_path / playlist_name)
                        }
                        downloaded_results.append(playlist_result)
                        logger.info(f"✅ 播放列表处理完成: {playlist_name} (成功: {playlist_downloaded}, 失败: {playlist_failed})")

                except Exception as e:
                    logger.error(f"❌ 播放列表处理异常: {playlist_name} - {e}")
                    total_failed += len(videos)

            # 下载单独视频
            if single_videos:
                try:
                    single_playlist_index = len(playlists) + 1
                    total_playlists_with_single = len(playlists) + 1

                    if message_updater:
                        try:
                            initial_msg = f"""📥 正在下载第{single_playlist_index}/{total_playlists_with_single}个播放列表：单独视频

📺 总视频数: {len(single_videos)}
📊 状态: 开始下载..."""
                            import asyncio
                            if asyncio.iscoroutinefunction(message_updater):
                                await message_updater(initial_msg)
                            elif callable(message_updater):
                                message_updater(initial_msg)
                        except Exception as e:
                            logger.warning(f"更新状态消息失败: {e}")

                    logger.info(f"🎬 开始处理单独视频: {len(single_videos)} 个")

                    # 为每个单独视频调用现有的下载方法
                    single_downloaded = 0
                    single_failed = 0

                    for video_idx, video in enumerate(single_videos, 1):
                        video_url = video.get('url') or video.get('webpage_url')
                        if video_url:
                            try:
                                logger.info(f"🎬 调用现有下载方法处理单独视频 {video_idx}/{len(single_videos)}: {video_url}")
                                logger.info(f"🔍 传递给download_video的message_updater: {type(message_updater)}, callable: {callable(message_updater)}")



                                # 创建单独视频目录（与合集同级）
                                single_video_path = user_download_path / "单独视频"
                                single_video_path.mkdir(parents=True, exist_ok=True)
                                logger.info(f"📁 创建单独视频目录: {single_video_path}")

                                # 生成更好的文件名
                                video_title = video.get('title', '')
                                clean_title = re.sub(r'[\\/:*?"<>|]', '_', video_title).strip()
                                filename = f"{video_idx:02d}. {clean_title}.mp4"
                                logger.info(f"📝 生成单视频文件名: {filename}")



                                # 临时修改下载路径到单独视频目录
                                original_bilibili_path = downloader.bilibili_download_path
                                downloader.bilibili_download_path = single_video_path
                                logger.info(f"🔧 临时修改B站下载路径: {downloader.bilibili_download_path}")

                                try:
                                    # 创建简化的进度更新器，确保能正常工作
                                    def progress_updater(progress_text):
                                        logger.info(f"🔍 [DEBUG] 单独视频进度更新器被调用: type={type(progress_text)}")

                                        if isinstance(progress_text, str):
                                            # 如果是字符串，直接显示
                                            logger.info(f"🔍 [DEBUG] 收到字符串消息: {progress_text[:100]}...")
                                        else:
                                            # 如果是字典（yt-dlp进度数据），转换为格式化消息
                                            d = progress_text
                                            logger.info(f"🔍 [DEBUG] 收到进度字典: status={d.get('status')}")

                                            if d.get("status") == "downloading":
                                                logger.info(f"🔍 [DEBUG] 处理下载进度...")

                                                # 简化的进度消息，先确保基本功能工作
                                                filename = d.get("filename", "未知文件")
                                                if filename:
                                                    filename = os.path.basename(filename)

                                                simple_progress = f"""📥 正在下载第{single_playlist_index}/{total_playlists_with_single}个播放列表：单独视频

📺 当前视频: {video_idx}/{len(single_videos)}
📝 文件: {filename}
📊 状态: 下载中..."""

                                                logger.info(f"🔍 [DEBUG] 准备发送简化进度消息")

                                                # 直接尝试发送消息，不使用复杂的线程
                                                if message_updater and callable(message_updater):
                                                    try:
                                                        logger.info(f"🔍 [DEBUG] 尝试发送进度消息...")
                                                        # 暂时跳过异步调用，只记录日志
                                                        logger.info(f"✅ [DEBUG] 模拟发送进度消息成功")
                                                    except Exception as e:
                                                        logger.warning(f"❌ [DEBUG] 发送进度消息失败: {e}")
                                                # 获取进度信息
                                                filename = d.get("filename", "未知文件")
                                                if filename:
                                                    filename = os.path.basename(filename)

                                                # 调试：打印所有可用的字段
                                                logger.info(f"🔍 进度字典所有字段: {list(d.keys())}")
                                                logger.info(f"🔍 进度字典内容: {d}")

                                                downloaded_bytes = d.get("downloaded_bytes", 0)
                                                total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                                                speed = d.get("speed", 0)

                                                # 调试：打印原始数值
                                                logger.info(f"🔍 原始数值: downloaded_bytes={downloaded_bytes}, total_bytes={total_bytes}, speed={speed}")

                                                # 格式化大小和速度
                                                downloaded_mb = downloaded_bytes / (1024 * 1024) if downloaded_bytes else 0
                                                total_mb = total_bytes / (1024 * 1024) if total_bytes else 0
                                                speed_mb = speed / (1024 * 1024) if speed else 0

                                                # 计算进度
                                                if total_bytes > 0:
                                                    progress_percent = (downloaded_bytes / total_bytes) * 100
                                                else:
                                                    progress_percent = 0

                                                # 计算预计剩余时间
                                                eta_seconds = d.get("eta", 0)
                                                if eta_seconds and eta_seconds > 0:
                                                    eta_minutes = eta_seconds // 60
                                                    eta_secs = eta_seconds % 60
                                                    eta_str = f"{eta_minutes:02d}:{eta_secs:02d}"
                                                else:
                                                    eta_str = "未知"

                                                # 创建进度条
                                                bar_length = 20
                                                filled_length = int(bar_length * progress_percent / 100)
                                                bar = '█' * filled_length + '░' * (bar_length - filled_length)

                                                # 构建详细的进度消息
                                                progress_text = f"""📥 正在下载第{single_playlist_index}/{total_playlists_with_single}个播放列表：单独视频

📺 当前视频: {video_idx}/{len(single_videos)}
📝 文件: {filename}
💾 大小: {downloaded_mb:.2f}MB / {total_mb:.2f}MB
⚡️ 速度: {speed_mb:.2f}MB/s
⏳ 预计剩余: {eta_str}
📊 进度: [{bar}] {progress_percent:.1f}%"""

                                                # 发送进度消息（使用线程安全的方式）
                                                if message_updater and callable(message_updater):
                                                    try:
                                                        import asyncio
                                                        import threading

                                                        # 创建一个新线程来处理异步调用
                                                        def send_progress_message():
                                                            try:
                                                                # 在新线程中创建事件循环
                                                                loop = asyncio.new_event_loop()
                                                                asyncio.set_event_loop(loop)

                                                                # 运行异步函数
                                                                loop.run_until_complete(message_updater(progress_text))
                                                                loop.close()

                                                                logger.info(f"✅ 线程中成功发送进度消息")
                                                            except Exception as e:
                                                                logger.warning(f"线程中发送进度消息失败: {e}")

                                                        # 启动线程（不等待完成）
                                                        thread = threading.Thread(target=send_progress_message, daemon=True)
                                                        thread.start()

                                                    except Exception as e:
                                                        logger.warning(f"创建进度消息线程失败: {e}")

                                    # 创建简化的进度更新器
                                    async def simple_progress_updater(progress_text):
                                        try:
                                            logger.info(f"🔍 [DEBUG] simple_progress_updater被调用: type={type(progress_text)}")
                                            logger.info(f"🔍 [DEBUG] message_updater状态: {message_updater}, type={type(message_updater)}")

                                            if isinstance(progress_text, str):
                                                # 字符串消息直接发送
                                                if message_updater and callable(message_updater):
                                                    logger.info(f"🔍 [DEBUG] 准备调用message_updater")
                                                    # message_updater是同步函数，直接调用
                                                    message_updater(progress_text)
                                                    logger.info(f"✅ [DEBUG] message_updater调用成功")
                                                else:
                                                    logger.warning(f"⚠️ [DEBUG] message_updater不可用: {message_updater}")
                                            else:
                                                # 字典数据处理，转换为进度消息
                                                logger.info(f"🔍 [DEBUG] 处理字典数据: {progress_text}")

                                                if isinstance(progress_text, dict) and progress_text.get("status") == "downloading":
                                                    d = progress_text

                                                    # 获取进度信息
                                                    filename = d.get("filename", "未知文件")
                                                    if filename:
                                                        filename = os.path.basename(filename)

                                                    downloaded_bytes = d.get("downloaded_bytes", 0)
                                                    total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                                                    speed = d.get("speed", 0)

                                                    # 格式化大小和速度
                                                    downloaded_mb = downloaded_bytes / (1024 * 1024) if downloaded_bytes else 0
                                                    total_mb = total_bytes / (1024 * 1024) if total_bytes else 0
                                                    speed_mb = speed / (1024 * 1024) if speed else 0

                                                    # 计算进度
                                                    if total_bytes > 0:
                                                        progress_percent = (downloaded_bytes / total_bytes) * 100
                                                    else:
                                                        progress_percent = 0

                                                    # 计算预计剩余时间
                                                    eta_seconds = d.get("eta", 0)
                                                    if eta_seconds and eta_seconds > 0:
                                                        if eta_seconds >= 3600:  # 超过1小时
                                                            eta_hours = eta_seconds // 3600
                                                            eta_minutes = (eta_seconds % 3600) // 60
                                                            eta_str = f"{eta_hours}小时{eta_minutes}分钟"
                                                        elif eta_seconds >= 60:  # 超过1分钟
                                                            eta_minutes = eta_seconds // 60
                                                            eta_secs = eta_seconds % 60
                                                            eta_str = f"{eta_minutes}分{eta_secs:02d}秒"
                                                        else:  # 小于1分钟
                                                            eta_str = f"{eta_seconds}秒"
                                                    else:
                                                        eta_str = "未知"

                                                    # 创建进度条（使用你要的格式）
                                                    bar_length = 20
                                                    filled_length = int(bar_length * progress_percent / 100)
                                                    bar = '░' * bar_length  # 先全部用空心
                                                    # 然后填充实心部分（从左到右）
                                                    bar = '█' * filled_length + '░' * (bar_length - filled_length)

                                                    # 构建简洁的进度消息（你要的格式）
                                                    progress_text = f"""📥 下载中
📝 文件名: {filename}
💾 大小: {downloaded_mb:.2f}MB / {total_mb:.2f}MB
⚡️ 速度: {speed_mb:.2f}MB/s
⏳ 预计剩余: {eta_str}
📊 进度: {bar} {progress_percent:.1f}%"""

                                                    # 发送进度消息
                                                    if message_updater and callable(message_updater):
                                                        logger.info(f"🔍 [DEBUG] 发送实时进度消息")
                                                        try:
                                                            # message_updater是同步函数，直接调用
                                                            logger.info(f"🔍 [DEBUG] 调用message_updater: {type(message_updater)}")
                                                            message_updater(progress_text)
                                                            logger.info(f"✅ [DEBUG] 实时进度消息发送成功")
                                                        except Exception as e:
                                                            logger.warning(f"❌ [DEBUG] 实时进度消息发送失败: {e}")
                                                            logger.warning(f"🔍 [DEBUG] message_updater详情: {type(message_updater)}")
                                                            import traceback
                                                            logger.warning(f"🔍 [DEBUG] 完整错误堆栈: {traceback.format_exc()}")
                                                else:
                                                    logger.info(f"🔍 [DEBUG] 跳过非下载状态的字典数据: {progress_text.get('status') if isinstance(progress_text, dict) else 'unknown'}")
                                        except Exception as e:
                                            logger.warning(f"简化进度更新失败: {e}")
                                            logger.warning(f"🔍 [DEBUG] 异常详情: message_updater={message_updater}, progress_text={progress_text}")

                                    # 调用download_video，直接传递上层的message_updater以使用统一的进度管道
                                    result = await downloader.download_video(video_url, message_updater if message_updater else None)

                                    # 手动发送进度更新（简化版本）
                                    logger.info(f"🔍 检查message_updater状态: type={type(message_updater)}, callable={callable(message_updater) if message_updater else False}")
                                    if message_updater and callable(message_updater):
                                        try:
                                            # 获取文件名
                                            filename = "未知文件"
                                            if result.get('success', False) and result.get('filename'):
                                                filename = os.path.basename(result.get('filename'))

                                            progress_msg = f"""📥 正在下载第{single_playlist_index}/{total_playlists_with_single}个播放列表：单独视频

📺 当前视频: {video_idx}/{len(single_videos)}
📝 文件: {filename}
📊 状态: ✅ 下载完成
💾 大小: {result.get('size_mb', 0):.2f} MB"""

                                            logger.info(f"🔍 准备发送进度消息，message_updater类型: {type(message_updater)}")
                                            # message_updater是同步函数，直接调用
                                            message_updater(progress_msg)
                                            logger.info(f"✅ 手动发送进度更新成功")
                                        except Exception as e:
                                            logger.warning(f"手动发送进度更新失败: {e}")
                                    else:
                                        logger.warning(f"⚠️ message_updater不可用: {message_updater}")

                                    # 发送简洁的进度更新，而不是详细的完成消息
                                    logger.info(f"🔍 检查进度更新发送条件: success={result.get('success', False)}, message_updater={type(message_updater)}")
                                    if result.get('success', False) and message_updater and callable(message_updater):
                                        try:
                                            # 检查所有变量是否为None
                                            filename = result.get('filename', '未知文件')
                                            size_mb = result.get('size_mb', 0)

                                            logger.info(f"🔍 [DEBUG] 进度更新变量检查: filename={filename}, size_mb={size_mb}, single_video_path={single_video_path}")

                                            # 只显示简单的进度更新，详细总结在最后显示
                                            progress_text = f"""📥 正在下载第{single_playlist_index}/{total_playlists_with_single}个播放列表：单独视频

📺 当前视频: {video_idx}/{len(single_videos)} ✅ 下载完成
📝 文件: {os.path.basename(filename)}
💾 大小: {size_mb:.2f} MB"""

                                            logger.info(f"🔍 准备发送进度更新，message_updater类型: {type(message_updater)}")
                                            logger.info(f"🔍 [DEBUG] 进度更新内容: {progress_text}")

                                            # message_updater是同步函数，直接调用
                                            message_updater(progress_text)
                                            logger.info(f"✅ 单独视频进度更新已发送")
                                        except Exception as e:
                                            logger.warning(f"发送单独视频进度更新失败: {e}")
                                            import traceback
                                            logger.warning(f"🔍 [DEBUG] 进度更新发送错误堆栈: {traceback.format_exc()}")
                                    else:
                                        logger.warning(f"⚠️ 跳过进度更新发送: success={result.get('success', False)}, message_updater={message_updater}")

                                except Exception as e:
                                    logger.error(f"单独视频下载异常: {e}")
                                    if message_updater and callable(message_updater):
                                        try:
                                            # message_updater是同步函数，直接调用
                                            message_updater(f"❌ 视频下载失败: {str(e)}")
                                        except Exception as msg_e:
                                            logger.warning(f"发送错误消息失败: {msg_e}")
                                    result = {'success': False, 'error': str(e)}
                                finally:
                                    # 恢复原始下载路径
                                    downloader.bilibili_download_path = original_bilibili_path
                                    logger.info(f"🔧 恢复B站下载路径: {downloader.bilibili_download_path}")

                                if result.get('success', False):
                                    single_downloaded += 1
                                    total_downloaded += 1
                                    # 累计文件大小
                                    if 'size_mb' in result:
                                        total_size_mb += result['size_mb']
                                    logger.info(f"✅ 单独视频下载成功: {video_idx}/{len(single_videos)}")
                                else:
                                    single_failed += 1
                                    total_failed += 1
                                    logger.error(f"❌ 单独视频下载失败: {video_idx}/{len(single_videos)} - {result.get('error', '未知错误')}")

                            except Exception as e:
                                single_failed += 1
                                total_failed += 1
                                logger.error(f"❌ 单独视频下载异常: {video_idx}/{len(single_videos)} - {e}")

                    # 记录单独视频结果
                    if single_downloaded > 0:
                        single_result = {
                            'title': '单独视频',
                            'type': '单独视频',
                            'video_count': single_downloaded,
                            'failed_count': single_failed,
                            'download_path': str(user_download_path / "单独视频")
                        }
                        downloaded_results.append(single_result)
                        logger.info(f"✅ 单独视频处理完成: (成功: {single_downloaded}, 失败: {single_failed})")

                except Exception as e:
                    logger.error(f"❌ 单独视频下载异常: {e}")
                    total_failed += len(single_videos)

            # 步骤6: 统计下载结果
            logger.info("🔍 步骤6: 统计下载结果...")

            # 计算成功率和失败数量
            total_videos = len(entries)
            success_rate = (total_downloaded / total_videos) * 100 if total_videos > 0 else 0

            # 格式化总大小显示
            if total_size_mb >= 1024:
                total_size_str = f"{total_size_mb / 1024:.2f}GB"
            else:
                total_size_str = f"{total_size_mb:.2f}MB"

            logger.info(f"📊 下载统计: {total_downloaded}/{total_videos} 个视频成功，成功率: {success_rate:.1f}%")
            logger.info(f"📊 播放列表统计: {len(downloaded_results)} 个播放列表")

            # 步骤7: 构建完成消息
            if message_updater and callable(message_updater):
                try:
                    completion_text = f"""📺 B站UP主播放列表下载完成

📺 UP主: {clean_uploader_name}
📊 播放列表数量: {len(downloaded_results)}
📊 单集数量: {total_videos}

已下载的播放列表:

"""

                    # 添加每个播放列表的详细信息（参考YouTube格式）
                    for i, playlist in enumerate(downloaded_results, 1):
                        playlist_title = playlist.get('title', f'播放列表{i}')
                        video_count = playlist.get('video_count', 0)
                        failed_count = playlist.get('failed_count', 0)

                        # 显示成功和失败的视频数量
                        if failed_count > 0:
                            completion_text += f"  {i}. {playlist_title} ({video_count} 集, ❌ {failed_count} 失败)\n"
                        else:
                            completion_text += f"  {i}. {playlist_title} ({video_count} 集)\n"

                    completion_text += f"""

📊 下载统计:
总计: {total_videos} 个
✅ 成功: {total_downloaded} 个
❌ 失败: {total_failed} 个
💾 文件总大小: {total_size_str}
📂 保存位置: {user_download_path}"""

                    # message_updater是同步函数，直接调用
                    message_updater(completion_text)
                except Exception as e:
                    logger.warning(f"更新完成消息失败: {e}")

            # 步骤8: 返回结果
            if total_downloaded > 0:
                logger.info(f"🎉 UP主所有视频下载完成: {total_downloaded}/{total_videos} 个成功")

                # 添加详细的下载总结日志
                logger.info("=" * 60)
                logger.info("📊 B站UP主下载完成总结")
                logger.info("=" * 60)
                logger.info(f"🎯 UP主: {clean_uploader_name} (UID: {uid})")
                logger.info(f"📁 下载目录: {user_download_path}")
                logger.info(f"📊 总视频数: {total_videos}")
                logger.info(f"✅ 成功下载: {total_downloaded}")
                logger.info(f"❌ 下载失败: {total_failed}")
                logger.info(f"📈 成功率: {success_rate:.1f}%")
                logger.info(f"💾 总文件大小: {total_size_str}")

                # 显示播放列表详情
                if downloaded_results:
                    logger.info(f"\n📋 播放列表详情:")
                    for i, playlist in enumerate(downloaded_results, 1):
                        playlist_title = playlist.get('title', f'播放列表{i}')
                        video_count = playlist.get('video_count', 0)
                        failed_count = playlist.get('failed_count', 0)
                        download_path = playlist.get('download_path', '未知')
                        logger.info(f"  {i}. {playlist_title}")
                        logger.info(f"     视频数: {video_count}, 失败: {failed_count}")
                        logger.info(f"     保存位置: {download_path}")

                # 显示目录结构
                logger.info(f"\n📂 最终目录结构:")
                try:
                    def log_directory_structure(path, indent=""):
                        if os.path.isdir(path):
                            logger.info(f"{indent}📁 {os.path.basename(path)}/")
                            try:
                                for item in sorted(os.listdir(path)):
                                    item_path = os.path.join(path, item)
                                    if os.path.isdir(item_path):
                                        log_directory_structure(item_path, indent + "  ")
                                    else:
                                        size = os.path.getsize(item_path) / (1024 * 1024)  # MB
                                        logger.info(f"{indent}  📄 {item} ({size:.2f}MB)")
                            except PermissionError:
                                logger.warning(f"{indent}  ⚠️ 无法访问目录内容")
                        else:
                            logger.info(f"{indent}📄 {os.path.basename(path)}")

                    log_directory_structure(user_download_path)
                except Exception as e:
                    logger.warning(f"无法显示目录结构: {e}")

                logger.info("=" * 60)

                return {
                    'success': True,
                    'is_channel': True,
                    'platform': 'bilibili',
                    'video_type': 'user_all_videos',
                    'channel_title': clean_uploader_name,
                    'uploader_id': uploader_id,
                    'uid': uid,
                    'total_videos': total_videos,
                    'downloaded_videos': total_downloaded,
                    'failed_videos': total_failed,
                    'success_rate': success_rate,
                    'total_size_mb': total_size_mb,
                    'download_path': str(user_download_path),
                    'playlists_downloaded': [p['title'] for p in downloaded_results],
                    'playlist_stats': downloaded_results
                }
            else:
                return {'success': False, 'error': '所有视频下载都失败了'}

        except Exception as e:
            error_msg = f"UP主合集下载过程中出错: {e}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
