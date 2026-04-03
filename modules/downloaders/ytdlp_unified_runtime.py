# -*- coding: utf-8 -*-
"""统一 yt-dlp 下载运行时逻辑。"""

import os
import threading
from pathlib import Path
from typing import Any, Dict

import yt_dlp

from modules.utils.progress_hooks import (
    create_single_video_progress_hook as single_video_progress_hook,
)

async def download_with_ytdlp_unified_runtime(
    downloader,
    url: str,
    download_path: Path,
    message_updater=None,
    platform_name: str = "Unknown",
    content_type: str = "video",
    format_spec: str = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
    cookies_path: str = None,
    *,
    logger,
) -> Dict[str, Any]:
        """
        统一的 yt-dlp 下载函数

        Args:
            url: 下载URL
            download_path: 下载目录
            message_updater: 消息更新器
            platform_name: 平台名称
            content_type: 内容类型 (video/image)
            format_spec: 格式规格
            cookies_path: cookies文件路径

        Returns:
            Dict[str, Any]: 下载结果
        """
        try:
            import yt_dlp

            # 确保下载目录存在
            os.makedirs(download_path, exist_ok=True)

            # 配置 yt-dlp
            # 根据设置决定文件名模板
            if hasattr(downloader, 'bot') and hasattr(downloader.bot, 'youtube_id_tags') and downloader.bot.youtube_id_tags and downloader.is_youtube_url(url):
                outtmpl = '%(title).50s[%(id)s].%(ext)s'
            else:
                outtmpl = '%(title).50s.%(ext)s'

            ydl_opts = {
                'format': format_spec,
                'outtmpl': os.path.join(str(download_path), outtmpl),
                'verbose': False,
                'no_warnings': True,
                'js_runtimes': {'node': {}},
                'extract_flat': False,
                'ignoreerrors': False,
                'no_check_certificate': True,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }
            }

            # 添加 cookies 支持
            if cookies_path and os.path.exists(cookies_path):
                ydl_opts["cookiefile"] = cookies_path
                logger.info(f"🍪 使用cookies: {cookies_path}")

            # 进度数据存储
            multithread_downloader = getattr(downloader, "multithread_downloader", None)
            if multithread_downloader and hasattr(multithread_downloader, "get_yt_dlp_options"):
                ydl_opts = multithread_downloader.get_yt_dlp_options(ydl_opts)

            progress_data = {"final_filename": None, "lock": threading.Lock()}

            # 使用统一的单集下载进度回调
            # 检查 message_updater 是否是增强版进度回调函数
            if callable(message_updater) and message_updater.__name__ == 'enhanced_progress_callback':
                # 如果是增强版进度回调，直接使用它返回的 progress_hook
                progress_hook = message_updater(progress_data)
            else:
                # 否则使用标准的 single_video_progress_hook
                progress_hook = single_video_progress_hook(
                    message_updater=message_updater,
                    progress_data=progress_data,
                    status_message=None,
                    context=None,
                )

            ydl_opts["progress_hooks"] = [progress_hook]

            # 开始下载
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                logger.info(f"🎬 yt-dlp 开始下载 {platform_name} {content_type}...")
                info = ydl.extract_info(url, download=True)

                if not info:
                    raise Exception(f"yt-dlp 未获取到{content_type}信息")

                # 检查info的类型，确保它是字典
                if not isinstance(info, dict):
                    logger.error(f"❌ yt-dlp 返回了非字典类型的结果: {type(info)}, 内容: {info}")
                    raise Exception(f"yt-dlp 返回了意外的数据类型: {type(info)}")

                # 查找下载的文件
                filename = ydl.prepare_filename(info)
                logger.info(f"🔍 yt-dlp 准备的文件名: {filename}")

                if not os.path.exists(filename):
                    logger.info(f"⚠️ 准备的文件名不存在，尝试查找实际下载的文件...")
                    # 尝试查找实际下载的文件
                    download_path_found = downloader.single_video_find_downloaded_file(
                        download_path,
                        progress_data,
                        info.get('title', ''),
                        url
                    )
                    if download_path_found:
                        filename = download_path_found
                        logger.info(f"✅ 找到实际下载的文件: {filename}")
                    else:
                        raise Exception(f"未找到下载的{content_type}文件")
                else:
                    logger.info(f"✅ 使用yt-dlp准备的文件名: {filename}")

                # 重命名文件以使用清理过的文件名
                try:
                    original_filename = filename
                    file_dir = os.path.dirname(filename)
                    file_ext = os.path.splitext(filename)[1]

                    # 获取原始标题并清理
                    original_title = info.get('title', f'{platform_name}_{content_type}')
                    clean_title = downloader._sanitize_filename(original_title)

                    # 构建新的文件名
                    new_filename = os.path.join(file_dir, f"{clean_title}{file_ext}")

                    # 如果新文件名与旧文件名不同，则重命名
                    if new_filename != original_filename:
                        # 如果新文件名已存在，添加数字后缀
                        counter = 1
                        final_filename = new_filename
                        while os.path.exists(final_filename):
                            name_without_ext = os.path.splitext(new_filename)[0]
                            final_filename = f"{name_without_ext}_{counter}{file_ext}"
                            counter += 1

                        # 重命名文件
                        os.rename(original_filename, final_filename)
                        filename = final_filename
                        logger.info(f"✅ 文件已重命名为: {os.path.basename(filename)}")
                    else:
                        logger.info(f"✅ 文件名无需重命名")

                except Exception as e:
                    logger.warning(f"⚠️ 重命名文件失败，使用原始文件名: {e}")
                    # 继续使用原始文件名

                # 获取文件信息
                file_size = os.path.getsize(filename)
                size_mb = file_size / 1024 / 1024

                logger.info(f"✅ {platform_name} {content_type}下载成功: {filename} ({size_mb:.1f} MB)")

                # 构建返回结果
                result = {
                    "success": True,
                    "platform": platform_name,
                    "content_type": content_type,
                    "download_path": filename,
                    "full_path": filename,
                    "size_mb": size_mb,
                    "title": info.get('title', f'{platform_name}{content_type}'),
                    "uploader": info.get('uploader', f'{platform_name}用户'),
                    "filename": os.path.basename(filename),
                }

                # 根据内容类型添加特定信息
                if content_type == "video":
                    # 视频特有信息
                    duration = info.get('duration', 0)
                    width = info.get('width', 0)
                    height = info.get('height', 0)
                    resolution = f"{width}x{height}" if width and height else "未知"

                    # 格式化时长
                    if duration:
                        minutes, seconds = divmod(int(duration), 60)
                        hours, minutes = divmod(minutes, 60)
                        if hours > 0:
                            duration_str = f"{hours}:{minutes:02d}:{seconds:02d}"
                        else:
                            duration_str = f"{minutes}:{seconds:02d}"
                    else:
                        duration_str = "未知"

                    result.update({
                        "duration": duration,
                        "duration_str": duration_str,
                        "resolution": resolution,
                        "width": width,
                        "height": height,
                    })
                else:
                    # 图片特有信息
                    width = info.get('width', 0)
                    height = info.get('height', 0)
                    resolution = f"{width}x{height}" if width and height else "未知"

                    result.update({
                        "resolution": resolution,
                        "width": width,
                        "height": height,
                    })

                return result

        except Exception as e:
            logger.error(f"❌ yt-dlp 下载 {platform_name} {content_type}失败: {e}")
            return {
                "success": False,
                "error": f"yt-dlp 下载失败: {str(e)}",
                "platform": platform_name,
                "content_type": content_type
            }
