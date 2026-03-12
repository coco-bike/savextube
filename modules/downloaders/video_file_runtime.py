# -*- coding: utf-8 -*-
"""视频文件下载运行时逻辑。"""

import asyncio
import os
import re
import time

import httpx

async def download_video_file_runtime(downloader, video_info, download_dir, message_updater=None, start_message=None, *, logger):
        """下载视频文件"""
        try:
            # 生成文件名
            if video_info.title:
                # 清理标题，去除特殊字符和平台后缀
                clean_title = downloader._sanitize_filename(video_info.title)
                # 小红书、抖音和快手的特殊命名逻辑
                if video_info.platform in ["xiaohongshu", "douyin", "kuaishou"]:
                    # 去掉开头的#和空格
                    clean_title = clean_title.lstrip('#').strip()
                    # 用#分割，取第一个分割后的内容（即第2个#前的内容）
                    clean_title = clean_title.split('#')[0].strip()
                    # 如果处理后标题为空，使用平台+时间戳
                    if not clean_title:
                        clean_title = f"{video_info.platform}_{int(time.time())}"
                else:
                    # 其他平台保持原有逻辑
                    clean_title = re.split(r'#', clean_title)[0].strip()
                # 去除平台后缀
                clean_title = re.sub(r'[-_ ]*(抖音|快手|小红书|YouTube|youtube)$', '', clean_title, flags=re.IGNORECASE).strip()
                filename = f"{clean_title}.mp4"
            else:
                # 如果获取标题失败，使用时间戳
                filename = f"{video_info.platform}_{int(time.time())}.mp4"

            file_path = os.path.join(download_dir, filename)

            # 小红书使用简单下载逻辑，抖音保持现有逻辑
            if video_info.platform == 'xiaohongshu':
                # 小红书：简单下载逻辑，参考douyin.py
                async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                        'Referer': 'https://www.xiaohongshu.com/'
                    }

                    logger.info(f"🎬 开始下载小红书视频: {video_info.download_url}")

                    # 先检查响应状态和头信息
                    try:
                        async with client.stream("GET", video_info.download_url, headers=headers) as resp:
                            logger.info(f"📊 HTTP状态码: {resp.status_code}")
                            logger.info(f"📊 响应头: {dict(resp.headers)}")

                            total = int(resp.headers.get("content-length", 0))
                            logger.info(f"📊 文件大小: {total} bytes")

                            if resp.status_code != 200:
                                logger.error(f"❌ HTTP状态码错误: {resp.status_code}")
                                # 读取错误响应内容
                                error_content = await resp.aread()
                                logger.error(f"❌ 错误响应内容: {error_content[:500]}")
                                raise Exception(f"HTTP状态码错误: {resp.status_code}")

                            with open(file_path, "wb") as f:
                                downloaded = 0
                                chunk_size = 1024 * 256

                                async for chunk in resp.aiter_bytes(chunk_size=chunk_size):
                                    f.write(chunk)
                                    downloaded += len(chunk)

                                    # 更新进度 - 使用与 YouTube 相同的格式
                                    if total > 0:
                                        progress = downloaded / total * 100
                                    else:
                                        # 如果没有content-length，使用下载的字节数作为进度指示
                                        progress = min(downloaded / (1024 * 1024), 99)  # 假设至少1MB

                                    # 计算速度（每秒更新一次）
                                    current_time = time.time()
                                    if not hasattr(downloader, '_last_update_time'):
                                        downloader._last_update_time = current_time
                                        downloader._last_downloaded = 0

                                    if current_time - downloader._last_update_time >= 1.0:
                                        speed = (downloaded - downloader._last_downloaded) / (current_time - downloader._last_update_time)
                                        downloader._last_update_time = current_time
                                        downloader._last_downloaded = downloaded
                                    else:
                                        speed = 0

                                    # 计算ETA
                                    if speed > 0 and total > 0:
                                        remaining_bytes = total - downloaded
                                        eta_seconds = remaining_bytes / speed
                                    else:
                                        eta_seconds = 0

                                    # 构建进度数据，格式与 yt-dlp 一致
                                    progress_data = {
                                        'status': 'downloading',
                                        'downloaded_bytes': downloaded,
                                        'total_bytes': total,
                                        'speed': speed,
                                        'eta': eta_seconds,
                                        'filename': filename
                                    }

                                    # 使用 message_updater 更新进度
                                    if message_updater:
                                        try:
                                            import asyncio
                                            if asyncio.iscoroutinefunction(message_updater):
                                                # 如果是协程函数，需要在事件循环中运行
                                                try:
                                                    loop = asyncio.get_running_loop()
                                                except RuntimeError:
                                                    try:
                                                        loop = asyncio.get_event_loop()
                                                    except RuntimeError:
                                                        loop = asyncio.new_event_loop()
                                                        asyncio.set_event_loop(loop)
                                                asyncio.run_coroutine_threadsafe(message_updater(progress_data), loop)
                                            else:
                                                # 同步函数，直接调用
                                                message_updater(progress_data)
                                        except Exception as e:
                                            logger.warning(f"⚠️ 更新进度失败: {e}")

                                # 下载完成后的最终更新
                                logger.info(f"✅ 小红书视频下载完成: {downloaded} bytes @{video_info.download_url}")
                                if message_updater:
                                    try:
                                        final_progress_data = {
                                            'status': 'finished',
                                            'downloaded_bytes': downloaded,
                                            'total_bytes': total,
                                            'filename': filename
                                        }
                                        message_updater(final_progress_data)
                                    except Exception as e:
                                        logger.warning(f"⚠️ 更新完成状态失败: {e}")
                    except Exception as e:
                        logger.error(f"❌ 小红书下载异常: {e}")
                        raise
            else:
                # 抖音等其他平台：处理API重定向
                # 准备cookies（如果有）
                cookies_dict = {}
                if video_info.platform == 'douyin' and downloader.douyin_cookies_path and os.path.exists(downloader.douyin_cookies_path):
                    try:
                        cookies_dict = downloader._parse_douyin_cookies_file(downloader.douyin_cookies_path)
                        logger.info(f"📊 加载了{len(cookies_dict)}个cookies用于下载")
                    except Exception as e:
                        logger.warning(f"⚠️ 加载cookies失败: {e}")

                async with httpx.AsyncClient(follow_redirects=True, timeout=60, cookies=cookies_dict) as client:
                    # 使用手机版User-Agent（按照原始douyin.py）
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
                        'Accept': '*/*',
                        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                        'Referer': 'https://www.douyin.com/' if video_info.platform == 'douyin' else 'https://www.xiaohongshu.com/',
                        'Connection': 'keep-alive',
                    }

                    # 对于抖音API链接，直接使用stream下载（按照原始douyin.py的方式）
                    logger.info(f"🎬 开始下载抖音视频: {video_info.download_url}")

                    with open(file_path, "wb") as f:
                        async with client.stream("GET", video_info.download_url, headers=headers) as resp:
                            total = int(resp.headers.get("content-length", 0))
                            downloaded = 0
                            chunk_size = 1024 * 256
                            last_update_time = time.time()
                            last_downloaded = 0

                            logger.info(f"📊 Stream响应状态码: {resp.status_code}")
                            logger.info(f"📊 Stream文件大小: {total} bytes")
                            logger.info(f"📊 实际请求URL: {resp.url}")
                            logger.info(f"📊 响应头: {dict(resp.headers)}")

                            if resp.status_code != 200:
                                raise Exception(f"HTTP状态码错误: {resp.status_code}")

                            async for chunk in resp.aiter_bytes(chunk_size=chunk_size):
                                if not chunk:
                                    break
                                f.write(chunk)
                                downloaded += len(chunk)
                                current_time = time.time()

                                # 更新进度 - 使用与 YouTube 相同的格式
                                if total > 0:
                                    progress = downloaded / total * 100
                                else:
                                    # 如果没有content-length，使用下载的字节数作为进度指示
                                    progress = min(downloaded / (1024 * 1024), 99)  # 假设至少1MB

                                # 计算速度（每秒更新一次）
                                if current_time - last_update_time >= 1.0:
                                    speed = (downloaded - last_downloaded) / (current_time - last_update_time)
                                    last_update_time = current_time
                                    last_downloaded = downloaded

                                    # 计算ETA
                                    if speed > 0 and total > 0:
                                        remaining_bytes = total - downloaded
                                        eta_seconds = remaining_bytes / speed
                                    else:
                                        eta_seconds = 0

                                    # 构建进度数据，格式与 yt-dlp 一致
                                    progress_data = {
                                        'status': 'downloading',
                                        'downloaded_bytes': downloaded,
                                        'total_bytes': total,
                                        'speed': speed,
                                        'eta': eta_seconds,
                                        'filename': filename
                                    }

                                    # 使用 message_updater 更新进度
                                    if message_updater:
                                        try:
                                            import asyncio
                                            if asyncio.iscoroutinefunction(message_updater):
                                                # 如果是协程函数，需要在事件循环中运行
                                                try:
                                                    loop = asyncio.get_running_loop()
                                                except RuntimeError:
                                                    try:
                                                        loop = asyncio.get_event_loop()
                                                    except RuntimeError:
                                                        loop = asyncio.new_event_loop()
                                                        asyncio.set_event_loop(loop)
                                                asyncio.run_coroutine_threadsafe(message_updater(progress_data), loop)
                                            else:
                                                # 同步函数，直接调用
                                                message_updater(progress_data)
                                        except Exception as e:
                                            logger.warning(f"⚠️ 更新进度失败: {e}")
                                    else:
                                        # 如果没有 message_updater，使用原来的简单更新
                                        if start_message and hasattr(downloader, 'bot') and downloader.bot:
                                            try:
                                                await start_message.edit_text(
                                                    f"📥 下载中... {progress:.1f}% ({downloaded/(1024*1024):.1f}MB)"
                                                )
                                            except Exception as e:
                                                logger.warning(f"⚠️ 更新进度消息失败: {e}")
                                        else:
                                            logger.info(f"📥 下载中... {progress:.1f}% ({downloaded/(1024*1024):.1f}MB)")

                            # 下载完成后的最终更新
                            logger.info(f"✅ 下载完成: {downloaded} bytes")
                            if message_updater:
                                try:
                                    final_progress_data = {
                                        'status': 'finished',
                                        'downloaded_bytes': downloaded,
                                        'total_bytes': total,
                                        'filename': filename
                                    }
                                    import asyncio
                                    if asyncio.iscoroutinefunction(message_updater):
                                        # 如果是协程函数，需要在事件循环中运行
                                        try:
                                            loop = asyncio.get_running_loop()
                                        except RuntimeError:
                                            try:
                                                loop = asyncio.get_event_loop()
                                            except RuntimeError:
                                                loop = asyncio.new_event_loop()
                                                asyncio.set_event_loop(loop)
                                        asyncio.run_coroutine_threadsafe(message_updater(final_progress_data), loop)
                                    else:
                                        # 同步函数，直接调用
                                        message_updater(final_progress_data)
                                except Exception as e:
                                    logger.warning(f"⚠️ 更新完成状态失败: {e}")

            # 删除开始消息（如果存在）
            if start_message and hasattr(downloader, 'bot') and downloader.bot:
                try:
                    await start_message.delete()
                except Exception as e:
                    logger.warning(f"⚠️ 删除开始消息失败: {e}")

            # 获取文件信息
            file_size = os.path.getsize(file_path)
            size_mb = file_size / (1024 * 1024)

            # 使用 ffprobe 获取视频分辨率信息
            resolution = "未知"
            try:
                media_info = downloader.get_media_info(file_path)
                if media_info.get("resolution"):
                    resolution = media_info["resolution"]
                    logger.info(f"📺 获取到视频分辨率: {resolution}")
            except Exception as e:
                logger.warning(f"⚠️ 获取视频分辨率失败: {e}")

            logger.info(f"✅ {video_info.platform}视频下载成功: {filename} ({size_mb:.1f} MB, 分辨率: {resolution})")

            return {
                "success": True,
                "file_path": file_path,
                "filename": filename,
                "title": video_info.title,
                "author": video_info.author,
                "platform": video_info.platform,
                "content_type": "video",
                "size_mb": size_mb,
                "resolution": resolution,
                "download_path": download_dir,
                "full_path": file_path,
                "file_count": 1,
                "files": [file_path]
            }

        except Exception as e:
            logger.error(f"❌ 下载视频文件失败: {e}")
            # 确保在异常情况下也能返回有效的结果
            return {
                "success": False,
                "error": f"下载视频文件失败: {e}",
                "platform": video_info.platform,
                "content_type": "video",
                "downloaded_bytes": 0,
                "total_bytes": 0,
                "filename": video_info.title or f"{video_info.platform}_{int(time.time())}.mp4"
            }
