# -*- coding: utf-8 -*-
"""单视频下载文件定位运行时逻辑。"""

import os
from pathlib import Path

import yt_dlp


def single_video_find_downloaded_file_runtime(
    downloader, download_path: Path, progress_data: dict = None, expected_title: str = None, url: str = None, *, logger
) -> str:
    """
    单视频下载的文件查找方法

    Args:
        downloader: 下载器实例
        download_path: 下载目录
        progress_data: 进度数据，包含final_filename
        expected_title: 预期的文件名（不包含扩展名）
        url: 原始URL，用于判断平台类型
        logger: 日志记录器

    Returns:
        str: 找到的文件路径，如果没找到返回None
    """
    # 1. 优先使用progress_hook记录的文件路径
    if progress_data and isinstance(progress_data, dict) and progress_data.get("final_filename"):
        final_file_path = progress_data["final_filename"]

        # 检查是否是中间文件，如果是则直接查找合并后的文件
        original_path = Path(final_file_path)
        base_name = original_path.stem

        # 检查是否是中间文件（包含.f140, .f401等格式标识符）
        is_intermediate_file = False
        if "." in base_name:
            parts = base_name.split(".")
            # 如果最后一部分是数字（如f140, f401），则移除它
            if (
                len(parts) > 1
                and parts[-1].startswith("f")
                and parts[-1][1:].isdigit()
            ):
                base_name = ".".join(parts[:-1])
                is_intermediate_file = True

        # 如果是中间文件，直接查找合并后的文件
        if is_intermediate_file:
            logger.info(f"🔍 检测到中间文件，直接查找合并后的文件: {final_file_path}")
            # 构造最终文件名（优先查找.mp4，然后是其他格式）
            possible_extensions = [".mp4", ".mkv", ".webm", ".avi", ".mov"]
            for ext in possible_extensions:
                final_merged_file = original_path.parent / f"{base_name}{ext}"
                logger.info(f"🔍 尝试查找合并后的文件: {final_merged_file}")

                if os.path.exists(final_merged_file):
                    logger.info(f"✅ 找到合并后的文件: {final_merged_file}")
                    return str(final_merged_file)

            logger.warning(f"⚠️ 未找到合并后的文件，基础名称: {base_name}")
        else:
            # 不是中间文件，直接检查是否存在
            if os.path.exists(final_file_path):
                logger.info(f"✅ 使用progress_hook记录的文件路径: {final_file_path}")
                return final_file_path

            # 检查是否为YouTube音频模式，如果是则查找对应的MP3文件
            if (hasattr(downloader, 'bot') and hasattr(downloader.bot, 'youtube_audio_mode') and
                downloader.bot.youtube_audio_mode and downloader.is_youtube_url(url)):
                # 将原始文件扩展名替换为.mp3
                original_path = Path(final_file_path)
                mp3_path = original_path.with_suffix('.mp3')
                if mp3_path.exists():
                    logger.info(f"✅ 音频模式：找到转换后的MP3文件: {mp3_path}")
                    return str(mp3_path)
                else:
                    logger.warning(f"⚠️ 音频模式：未找到转换后的MP3文件: {mp3_path}")
            else:
                # 检查是否为中间文件（包含格式代码的文件）
                original_path = Path(final_file_path)
                filename = original_path.name

                # 检查是否为DASH中间文件
                is_dash_intermediate = (
                    '.fdash-' in filename or
                    '.f' in filename and filename.count('.') >= 2 or
                    'dash-' in filename
                )

                if is_dash_intermediate:
                    logger.info(f"🔍 检测到DASH中间文件，尝试查找合并后的文件: {filename}")
                    # 尝试查找合并后的文件
                    base_name = filename.split('.f')[0] if '.f' in filename else filename.split('.')[0]
                    ext = '.mp4'  # 合并后通常是mp4格式
                    final_merged_file = original_path.parent / f"{base_name}{ext}"

                    if os.path.exists(final_merged_file):
                        logger.info(f"✅ 找到DASH合并后的文件: {final_merged_file}")
                        return str(final_merged_file)
                    else:
                        logger.info(f"🔍 DASH合并文件不存在，将使用其他方法查找: {final_merged_file}")
                else:
                    logger.warning(f"⚠️ progress_hook记录的文件路径不存在: {final_file_path}")

    # 2. 基于预期文件名查找
    if expected_title:
        logger.info(f"🔍 基于预期文件名查找: {expected_title}")
        # 使用统一的文件名清理方法
        safe_title = downloader._sanitize_filename(expected_title)
        if safe_title:
            # 尝试不同的扩展名
            possible_extensions = [".mp4", ".mkv", ".webm", ".avi", ".mov"]
            for ext in possible_extensions:
                expected_file = download_path / f"{safe_title}{ext}"
                logger.info(f"🔍 尝试查找文件: {expected_file}")
                if os.path.exists(expected_file):
                    logger.info(f"✅ 找到基于标题的文件: {expected_file}")
                    return str(expected_file)

            logger.warning(f"⚠️ 未找到基于标题的文件: {safe_title}")

    # 3. 基于平台特定逻辑查找
    if url:
        logger.info(f"🔍 基于平台特定逻辑查找: {url}")
        try:
            if downloader.is_x_url(url):
                # X平台：基于视频标题查找
                logger.info("🔍 X平台：尝试获取视频标题并查找")
                info_opts = {
                    "quiet": True,
                    "no_warnings": True,
                    "socket_timeout": 15,
                    "retries": 2,
                }
                if downloader.x_cookies_path and os.path.exists(downloader.x_cookies_path):
                    info_opts["cookiefile"] = downloader.x_cookies_path

                with yt_dlp.YoutubeDL(info_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    if info and info.get('title'):
                        title = info.get('title')
                        safe_title = downloader._sanitize_filename(title)
                        if safe_title:
                            logger.info(f"🔍 X平台标题: {safe_title}")
                            # 尝试不同的扩展名
                            possible_extensions = [".mp4", ".mkv", ".webm", ".avi", ".mov"]
                            for ext in possible_extensions:
                                expected_file = download_path / f"{safe_title}{ext}"
                                logger.info(f"🔍 尝试查找X平台文件: {expected_file}")
                                if os.path.exists(expected_file):
                                    logger.info(f"✅ 找到X平台文件: {expected_file}")
                                    return str(expected_file)

                            logger.warning(f"⚠️ 未找到X平台文件，标题: {safe_title}")
                        else:
                            logger.warning("⚠️ X平台标题为空或无效")
                    else:
                        logger.warning("⚠️ 无法获取X平台视频标题")
            else:
                # 其他平台：基于标题查找（如果还没有尝试过）
                if not expected_title:
                    logger.info("🔍 其他平台：尝试获取视频标题并查找")
                    info_opts = {
                        "quiet": True,
                        "no_warnings": True,
                        "socket_timeout": 15,
                        "retries": 2,
                    }
                    if downloader.youtube_cookies_path and os.path.exists(downloader.youtube_cookies_path):
                        info_opts["cookiefile"] = downloader.youtube_cookies_path
                    if downloader.douyin_cookies_path and os.path.exists(downloader.douyin_cookies_path):
                        info_opts["cookiefile"] = downloader.douyin_cookies_path

                    with yt_dlp.YoutubeDL(info_opts) as ydl:
                        info = ydl.extract_info(url, download=False)
                        if info and info.get('title'):
                            title = info.get('title')
                            safe_title = downloader._sanitize_filename(title)
                            if safe_title:
                                logger.info(f"🔍 其他平台标题: {safe_title}")
                                # 尝试不同的扩展名
                                possible_extensions = [".mp4", ".mkv", ".webm", ".avi", ".mov"]
                                for ext in possible_extensions:
                                    expected_file = download_path / f"{safe_title}{ext}"
                                    logger.info(f"🔍 尝试查找其他平台文件: {expected_file}")
                                    if os.path.exists(expected_file):
                                        logger.info(f"✅ 找到其他平台文件: {expected_file}")
                                        return str(expected_file)

                                logger.warning(f"⚠️ 未找到其他平台文件，标题: {safe_title}")
        except Exception as e:
            logger.warning(f"⚠️ 平台特定查找失败: {e}")

    # 4. 最后尝试：扫描下载目录中的所有视频文件
    logger.info("🔍 最后尝试：扫描下载目录中的所有视频文件")
    try:
        video_extensions = ['.mp4', '.mkv', '.webm', '.avi', '.mov', '.m4a', '.mp3']
        all_files = []

        for file_path in download_path.rglob('*'):
            if file_path.is_file() and file_path.suffix.lower() in video_extensions:
                # 获取文件的修改时间
                mtime = file_path.stat().st_mtime
                all_files.append((file_path, mtime))

        if all_files:
            # 按修改时间排序，最新的文件优先
            all_files.sort(key=lambda x: x[1], reverse=True)
            latest_file = all_files[0][0]
            logger.info(f"✅ 找到最新的视频文件: {latest_file}")
            return str(latest_file)
        else:
            logger.warning("⚠️ 下载目录中未找到任何视频文件")
    except Exception as e:
        logger.warning(f"⚠️ 扫描下载目录时出错: {e}")

    # 5. 如果都找不到，记录错误并返回None
    logger.error("❌ 无法找到预期的下载文件")
    return None
