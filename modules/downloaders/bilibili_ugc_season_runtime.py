# -*- coding: utf-8 -*-
"""Bilibili UGC 合集下载运行时逻辑。"""

from pathlib import Path
from typing import Any, Dict
from modules.utils.progress_hooks import (
    create_single_video_progress_hook as single_video_progress_hook,
)


async def download_bilibili_ugc_season(downloader, bv_id: str, season_id: str, download_path: Path, message_updater=None, *, logger
) -> Dict[str, Any]:
    """下载B站UGC合集"""
    logger.info(f"🎬 开始下载B站UGC合集: BV={bv_id}, Season={season_id}")

    try:
        # 步骤1: 获取合集信息
        logger.info("🔍 步骤1: 获取UGC合集信息...")

        import requests
        api_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bv_id}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.bilibili.com/',
        }

        if message_updater:
            try:
                import asyncio
                if asyncio.iscoroutinefunction(message_updater):
                    await message_updater("🔍 正在获取UGC合集信息...")
                else:
                    message_updater("🔍 正在获取UGC合集信息...")
            except Exception as e:
                logger.warning(f"更新状态消息失败: {e}")

        try:
            response = requests.get(api_url, headers=headers, timeout=30)
            response.raise_for_status()  # 检查HTTP状态码
            data = response.json()
        except requests.exceptions.HTTPError as e:
            if response.status_code == 404:
                error_msg = f"视频不存在: BV号 {bv_id} 无效或视频已被删除"
            else:
                error_msg = f"HTTP请求失败: {e}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
        except requests.exceptions.RequestException as e:
            error_msg = f"网络请求失败: {e}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
        except ValueError as e:
            error_msg = f"响应解析失败: {e}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}

        if data.get('code') != 0:
            error_msg = f"获取合集信息失败: {data.get('message', '未知错误')}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}

        ugc_season = data.get('data', {}).get('ugc_season')
        if not ugc_season:
            error_msg = "视频不属于UGC合集"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}

        season_title = ugc_season.get('title', '未知合集')
        logger.info(f"📋 合集标题: {season_title}")

        # 创建合集专用子目录
        safe_season_title = downloader._sanitize_filename(season_title, max_length=50)
        season_download_path = download_path / safe_season_title
        season_download_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"📁 创建合集目录: {season_download_path}")

        # 步骤2: 提取所有视频
        all_videos = []
        sections = ugc_season.get('sections', [])

        for section in sections:
            episodes = section.get('episodes', [])
            for episode in episodes:
                video_info = {
                    'bvid': episode.get('bvid'),
                    'title': episode.get('title'),
                    'aid': episode.get('aid'),
                    'cid': episode.get('cid'),
                }
                if video_info['bvid']:
                    all_videos.append(video_info)

        if not all_videos:
            error_msg = "合集中没有找到视频"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}

        logger.info(f"📋 找到 {len(all_videos)} 个视频:")
        for i, video in enumerate(all_videos, 1):
            logger.info(f"  {i:02d}. {video['title']} ({video['bvid']})")

        # 步骤3: 逐个下载视频
        logger.info("🔍 步骤3: 开始逐个下载视频...")

        downloaded_files = []
        success_count = 0
        total_size_mb = 0
        failed_videos = []

        # 创建增强的进度回调函数，用于显示合集下载进度
        def create_ugc_progress_callback(video_index, video_title, total_count):
            """为UGC合集中的每个视频创建专门的进度回调"""
            def ugc_video_progress_hook(d):
                try:
                    if d.get('status') == 'downloading':
                        downloaded_bytes = d.get('downloaded_bytes', 0)
                        total_bytes = d.get('total_bytes', 0)
                        speed = d.get('speed', 0)
                        eta = d.get('eta', 0)
                        filename = d.get('filename', video_title)

                        if total_bytes and total_bytes > 0:
                            percent = (downloaded_bytes / total_bytes) * 100
                            downloaded_mb = downloaded_bytes / (1024 * 1024)
                            total_mb = total_bytes / (1024 * 1024)
                            speed_mb = speed / (1024 * 1024) if speed else 0

                            # 创建进度条 (20个字符)
                            progress_bar_length = 20
                            # 修复进度条计算：确保至少显示1个实心块当进度>0时
                            if percent > 0:
                                filled_length = max(1, int(progress_bar_length * percent / 100))
                            else:
                                filled_length = 0
                            bar = '█' * filled_length + '░' * (progress_bar_length - filled_length)

                            # 格式化ETA
                            if eta and eta > 0:
                                if eta < 60:
                                    eta_str = f"{int(eta)}秒"
                                elif eta < 3600:
                                    eta_str = f"{int(eta//60)}分{int(eta%60)}秒"
                                else:
                                    eta_str = f"{int(eta//3600)}时{int((eta%3600)//60)}分"
                            else:
                                eta_str = "计算中..."

                            # 构建图片格式的进度消息
                            # 使用上面已经计算好的bar

                            progress_msg = (
                                f"📥 下载中\n"
                                f"📝 文件名: {filename}\n"
                                f"💾 大小: {downloaded_mb:.2f}MB / {total_mb:.2f}MB\n"
                                f"⚡ 速度: {speed_mb:.2f}MB/s\n"
                                f"⏳ 预计剩余: {eta_str}\n"
                                f"📊 进度: {bar} {percent:.1f}%"
                            )

                            # 更新状态消息
                            if message_updater:
                                try:
                                    import asyncio
                                    if asyncio.iscoroutinefunction(message_updater):
                                        # 对于协程函数，需要在事件循环中运行
                                        try:
                                            loop = asyncio.get_running_loop()
                                            asyncio.run_coroutine_threadsafe(message_updater(progress_msg), loop)
                                        except RuntimeError:
                                            pass  # 如果没有运行的事件循环，跳过
                                    else:
                                        message_updater(progress_msg)
                                except Exception as e:
                                    logger.debug(f"更新进度消息失败: {e}")

                    elif d.get('status') == 'finished':
                        filename = d.get('filename', '')
                        if filename:
                            logger.info(f"✅ [{video_index}/{total_count}] 下载完成: {filename}")

                            # 显示完成消息
                            complete_msg = (
                                f"✅ 下载完成 [{video_index}/{total_count}]\n"
                                f"📝 文件名：{filename}\n"
                                f"📊 进度：████████████████████ 100.0%"
                            )
                            if message_updater:
                                try:
                                    import asyncio
                                    if asyncio.iscoroutinefunction(message_updater):
                                        try:
                                            loop = asyncio.get_running_loop()
                                            asyncio.run_coroutine_threadsafe(message_updater(complete_msg), loop)
                                        except RuntimeError:
                                            pass
                                    else:
                                        message_updater(complete_msg)
                                except Exception as e:
                                    logger.debug(f"更新完成消息失败: {e}")

                except Exception as e:
                    logger.debug(f"UGC进度回调处理失败: {e}")

            return ugc_video_progress_hook

        for i, video in enumerate(all_videos, 1):
            try:
                # 显示开始下载的消息 - 使用详细格式
                start_msg = (
                    f"📥 准备下载 [{i}/{len(all_videos)}]\n"
                    f"📝 文件名：{video['title']}\n"
                    f"💾 大小：获取中...\n"
                    f"⚡ 速度：准备中...\n"
                    f"⏳ 预计剩余：计算中...\n"
                    f"📊 进度：░░░░░░░░░░░░░░░░░░░░ 0.0%"
                )
                logger.info(f"🎬 开始下载: {video['title']}")

                if message_updater:
                    try:
                        import asyncio
                        if asyncio.iscoroutinefunction(message_updater):
                            await message_updater(start_msg)
                        else:
                            message_updater(start_msg)
                    except Exception as e:
                        logger.warning(f"更新状态消息失败: {e}")

                # 构建单个视频的URL
                video_url = f"https://www.bilibili.com/video/{video['bvid']}/"

                # 使用标准的single_video_progress_hook，但添加UGC合集信息
                import threading
                progress_data = {"final_filename": None, "lock": threading.Lock()}

                # 创建UGC专用的消息更新器，在标准进度消息前添加合集信息
                def ugc_message_updater(msg_or_dict):
                    """UGC专用消息更新器，添加合集信息"""
                    try:
                        if isinstance(msg_or_dict, str):
                            # 字符串消息，直接传递
                            ugc_msg = f"📥 UGC合集 [{i}/{len(all_videos)}]\n{msg_or_dict}"
                            if message_updater:
                                message_updater(ugc_msg)
                        elif isinstance(msg_or_dict, dict):
                            # 字典消息，传递给原始更新器处理
                            if message_updater:
                                message_updater(msg_or_dict)
                    except Exception as e:
                        logger.error(f"❌ UGC消息更新器失败: {e}")

                # 使用标准的single_video_progress_hook
                progress_callback = single_video_progress_hook(
                    message_updater=ugc_message_updater,
                    progress_data=progress_data,
                    status_message=None,
                    context=None,
                )

                # 使用smart_download_bilibili下载B站视频，获得更好的进度显示
                # 对于UGC合集，即使是单视频也应该继续下载
                import asyncio
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(
                    None,
                    downloader.smart_download_bilibili_for_ugc,
                    video_url,
                    str(season_download_path),
                    progress_callback,
                    False  # auto_playlist=False，只下载单个视频
                )

                # 处理smart_download_bilibili的返回结果
                if isinstance(result, dict) and result.get('status') == 'success':
                    success_count += 1
                    file_info = {
                        'filename': result.get('filename', ''),
                        'full_path': result.get('download_path', ''),
                        'size_mb': result.get('size_mb', 0),
                        'title': video['title'],
                        'bvid': video['bvid'],
                        'resolution': result.get('resolution', ''),
                        'duration': result.get('duration', ''),
                    }
                    downloaded_files.append(file_info)
                    total_size_mb += result.get('size_mb', 0)

                    success_msg = f"✅ 第 {i}/{len(all_videos)} 个视频下载成功: {result.get('filename', '')}"
                    logger.info(success_msg)

                elif result is True:
                    # smart_download_bilibili有时返回True表示成功，需要从目录中查找实际文件
                    success_count += 1

                    # 尝试从下载目录中找到实际的文件名
                    actual_filename = None
                    logger.info(f"🔍 查找第{i}个视频的实际文件名，目录: {season_download_path}")
                    try:
                        import os
                        all_files = os.listdir(season_download_path)
                        logger.info(f"📁 目录中的所有文件: {all_files}")

                        video_files = [f for f in all_files if f.endswith(('.mp4', '.mkv', '.avi', '.flv', '.webm'))]
                        logger.info(f"🎬 视频文件: {video_files}")

                        for file in video_files:
                            # 检查文件是否与当前视频相关（简单的标题匹配）
                            if any(word in file for word in video['title'].split()[:3]):
                                actual_filename = file
                                logger.info(f"✅ 找到匹配文件: {actual_filename}")
                                break

                        # 如果没找到匹配的文件，使用最新的视频文件
                        if not actual_filename and video_files:
                            # 按修改时间排序，取最新的
                            video_files.sort(key=lambda x: os.path.getmtime(season_download_path / x), reverse=True)
                            actual_filename = video_files[0]
                            logger.info(f"📊 使用最新文件: {actual_filename}")
                    except Exception as e:
                        logger.warning(f"查找实际文件名失败: {e}")

                    if not actual_filename:
                        actual_filename = f"{video['title']}.mp4"
                        logger.warning(f"⚠️ 未找到实际文件，使用默认名称: {actual_filename}")

                    # 获取文件大小
                    file_size_mb = 0
                    try:
                        file_path = season_download_path / actual_filename
                        if file_path.exists():
                            file_size_mb = file_path.stat().st_size / (1024 * 1024)
                    except Exception as e:
                        logger.debug(f"获取文件大小失败: {e}")

                    # 检测文件分辨率和时长
                    resolution_info = ''
                    duration_info = ''
                    try:
                        file_path = season_download_path / actual_filename
                        if file_path.exists():
                            # 使用现有的get_media_info方法检测视频信息
                            media_info = downloader.get_media_info(str(file_path))
                            resolution_info = media_info.get('resolution', '')
                            duration_info = media_info.get('duration', '')
                            logger.info(f"🔍 检测到视频信息: 分辨率={resolution_info}, 时长={duration_info}")
                    except Exception as e:
                        logger.debug(f"检测视频信息失败: {e}")

                    file_info = {
                        'filename': actual_filename,
                        'full_path': str(season_download_path / actual_filename),
                        'size_mb': file_size_mb,
                        'title': video['title'],
                        'bvid': video['bvid'],
                        'resolution': resolution_info,
                        'duration': duration_info,
                    }
                    downloaded_files.append(file_info)
                    total_size_mb += file_size_mb

                    success_msg = f"✅ 第 {i}/{len(all_videos)} 个视频下载成功: {actual_filename}"
                    logger.info(success_msg)
                else:
                    error_msg = f"❌ 第 {i}/{len(all_videos)} 个视频下载失败"
                    if isinstance(result, dict):
                        error_msg += f": {result.get('error', '未知错误')}"
                    logger.error(error_msg)
                    failed_videos.append({
                        'index': i,
                        'title': video['title'],
                        'bvid': video['bvid'],
                        'error': result.get('error', '未知错误') if isinstance(result, dict) else '下载失败'
                    })

            except Exception as e:
                error_msg = f"❌ 下载第 {i}/{len(all_videos)} 个视频时出错: {e}"
                logger.error(error_msg)
                failed_videos.append({
                    'index': i,
                    'title': video['title'],
                    'bvid': video['bvid'],
                    'error': str(e)
                })

        # 步骤4: 生成详细的下载结果报告
        logger.info("🔍 步骤4: 生成下载结果报告...")

        # 计算总时长和平均文件大小
        total_duration_seconds = 0
        for file_info in downloaded_files:
            duration_str = file_info.get('duration', '')
            if duration_str and ':' in duration_str:
                try:
                    parts = duration_str.split(':')
                    if len(parts) == 2:  # MM:SS
                        minutes, seconds = map(int, parts)
                        total_duration_seconds += minutes * 60 + seconds
                    elif len(parts) == 3:  # HH:MM:SS
                        hours, minutes, seconds = map(int, parts)
                        total_duration_seconds += hours * 3600 + minutes * 60 + seconds
                except ValueError:
                    pass

        # 格式化总时长
        if total_duration_seconds > 0:
            hours = total_duration_seconds // 3600
            minutes = (total_duration_seconds % 3600) // 60
            seconds = total_duration_seconds % 60
            if hours > 0:
                total_duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                total_duration_str = f"{minutes:02d}:{seconds:02d}"
        else:
            total_duration_str = "未知"

        # 生成详细的结果报告
        if success_count > 0:
            # 成功下载的统计
            avg_size_mb = total_size_mb / success_count if success_count > 0 else 0

            logger.info("🎬 **视频下载完成**")
            logger.info(f"📋 合集标题: {season_title}")
            logger.info("")
            logger.info("📝 文件名:")

            # 显示文件列表，格式与最终消息一致
            for i, file_info in enumerate(downloaded_files, 1):
                logger.info(f"  {i:02d}. {file_info['filename']}")

            logger.info("")
            logger.info(f"💾 文件大小: {total_size_mb:.2f} MB")
            logger.info(f"📊 集数: {success_count} 集")

            # 获取分辨率信息 - 使用ffprobe检测实际文件
            resolution_display = "未知"
            logger.info(f"🔍 开始分辨率检测，下载文件数量: {len(downloaded_files) if downloaded_files else 0}")
            logger.info(f"🔍 初始resolution_display值: '{resolution_display}'")

            if downloaded_files:
                logger.info(f"✅ 有下载文件信息，开始检测分辨率")
                # 尝试从第一个下载的文件获取分辨率
                first_file = downloaded_files[0]
                file_path = first_file.get('full_path', '')
                logger.info(f"🔍 检测文件路径: {file_path}")

                import os
                if file_path and os.path.exists(file_path):
                    logger.info(f"✅ 文件存在，开始检测分辨率")
                    try:
                        logger.info(f"🔍 使用get_media_info检测分辨率: {file_path}")

                        # 使用现有的get_media_info方法
                        media_info = downloader.get_media_info(file_path)
                        if media_info.get('resolution'):
                            resolution_display = media_info['resolution']
                            logger.info(f"✅ 成功获取分辨率: {resolution_display}")
                            logger.info(f"🔍 resolution_display变量当前值: '{resolution_display}'")
                        else:
                            logger.warning("⚠️ 无法获取分辨率信息")

                    except Exception as e:
                        logger.warning(f"⚠️ ffprobe输出解析失败: {e}")
                    except Exception as e:
                        logger.warning(f"⚠️ 获取分辨率时发生错误: {e}")
                else:
                    logger.warning(f"⚠️ 文件不存在或路径无效: {file_path}")
            else:
                logger.warning("⚠️ 没有下载文件信息，无法检测分辨率")

            logger.info(f"📊 最终分辨率值: '{resolution_display}'")
            logger.info(f"🖼️ 分辨率: {resolution_display}")

            logger.info(f"📂 保存位置: {season_download_path}")

            # 显示详细统计信息（仅在日志中）
            logger.info("")
            logger.info("📊 详细统计:")
            logger.info(f"  ✅ 成功: {success_count}/{len(all_videos)} 个视频")
            logger.info(f"  📏 平均大小: {avg_size_mb:.1f}MB")
            logger.info(f"  ⏱️ 总时长: {total_duration_str}")

            if failed_videos:
                logger.info(f"  ❌ 失败: {len(failed_videos)} 个视频")
                for failed in failed_videos:
                    logger.warning(f"    - 第{failed['index']}个: {failed['title']} (错误: {failed['error']})")

            # 生成美化的最终状态消息
            logger.info(f"🔍 开始生成最终消息，当前resolution_display值: '{resolution_display}'")
            final_msg = f"🎬 视频下载完成\n\n"
            final_msg += f"📝 文件名:\n"

            # 添加文件列表，按序号排列
            for i, file_info in enumerate(downloaded_files, 1):
                filename = file_info['filename']
                final_msg += f"  {i:02d}. {filename}\n"

            # 添加统计信息
            final_msg += f"\n💾 文件大小: {total_size_mb:.2f} MB\n"
            final_msg += f"📊 下载统计:\n"
            final_msg += f"✅ 成功: {success_count} 个\n"

            # 添加分辨率信息到最终消息
            logger.info(f"🔍 添加分辨率到消息，resolution_display值: '{resolution_display}'")
            final_msg += f"🖼️ 分辨率: {resolution_display}\n"
            final_msg += f"📂 保存位置: {season_download_path}"

            logger.info(f"🔍 最终消息生成完成，消息长度: {len(final_msg)} 字符")
            logger.info(f"🔍 最终消息预览: {final_msg[:200]}...")

            if failed_videos:
                final_msg += f"\n\n❌ 失败: {len(failed_videos)} 个视频"
                for failed in failed_videos:
                    final_msg += f"\n  - {failed['title']}"

            # 不在这里发送消息，让主程序处理
            logger.info(f"🔍 UGC合集下载完成，返回结果给主程序处理消息")

            return {
                'success': True,
                'is_playlist': True,  # 改为True，让主程序处理消息
                'file_count': success_count,
                'total_size_mb': total_size_mb,
                'files': downloaded_files,
                'platform': 'bilibili',  # 使用标准的bilibili标识
                'download_path': str(season_download_path),  # 使用合集子目录
                'base_download_path': str(download_path),    # 保留基础下载路径
                'season_title': season_title,
                'season_id': season_id,
                'failed_count': len(failed_videos),
                'failed_videos': failed_videos,
                'total_duration': total_duration_str,
                'average_size_mb': avg_size_mb,
                'ugc_season': True,  # 保留UGC合集标识
                'video_type': 'playlist',  # 标识为播放列表类型
                'count': success_count,  # 添加count字段
                'resolution': resolution_display,  # 添加分辨率信息
            }
        else:
            error_msg = f"UGC合集下载失败: 所有 {len(all_videos)} 个视频都下载失败"
            logger.error(error_msg)
            logger.error("失败详情:")
            for failed in failed_videos:
                logger.error(f"  - 第{failed['index']}个: {failed['title']} (错误: {failed['error']})")

            if message_updater:
                try:
                    import asyncio
                    if asyncio.iscoroutinefunction(message_updater):
                        await message_updater(f"❌ UGC合集下载失败: 所有视频都下载失败")
                    else:
                        message_updater(f"❌ UGC合集下载失败: 所有视频都下载失败")
                except Exception as e:
                    logger.warning(f"更新状态消息失败: {e}")

            return {
                'success': False,
                'error': error_msg,
                'failed_videos': failed_videos,
                'season_title': season_title,
                'season_id': season_id,
                'download_path': str(season_download_path),
                'base_download_path': str(download_path),
            }

    except Exception as e:
        error_msg = f"UGC合集下载过程中出错: {e}"
        logger.error(error_msg)
        return {'success': False, 'error': error_msg}
