# -*- coding: utf-8 -*-
"""QQ 音乐下载运行时逻辑。"""

from modules.utils.text_utils import (
    clean_filename_for_display,
    create_progress_bar,
)

async def download_qqmusic_music_runtime(downloader, url: str, download_path: str, message_updater=None, status_message=None, context=None, *, logger) -> dict:
        """下载QQ音乐"""
        import threading
        try:
            if not downloader.qqmusic_downloader:
                # 尝试重新初始化QQ音乐下载器
                try:
                    # 动态导入qqmusic_downloader模块，避免全局导入失败的影响
                    import modules.downloaders.qqmusic_downloader as qqmusic_downloader
                    from modules.downloaders.qqmusic_downloader import QQMusicDownloader

                    # 直接使用QQMusicDownloader
                    downloader.qqmusic_downloader = QQMusicDownloader(bot=downloader)
                    logger.info(f"🎵 QQ音乐下载器重新初始化成功 (模块: {qqmusic_downloader.__file__})")
                except Exception as e:
                    logger.warning(f"QQ音乐下载器重新初始化失败: {e}")
                    return {
                        "success": False,
                        "error": "QQ音乐下载器不可用",
                        "platform": "QQMusic",
                        "content_type": "music"
                    }

            # 更新状态消息
            if message_updater:
                try:
                    message_updater("🎵 正在解析QQ音乐链接...")
                except Exception as e:
                    logger.warning(f"消息更新失败: {e}")

            # 创建进度回调
            progress_data = {"final_filename": None, "lock": threading.Lock()}

            if message_updater:
                # 添加速度计算所需的时间跟踪
                import time
                last_time = time.time()
                last_downloaded = 0
                last_update_time = time.time()

                def progress_callback(progress, downloaded, total, filename=None):
                    nonlocal last_time, last_downloaded, last_update_time
                    try:
                        with progress_data["lock"]:
                            if total > 0:
                                # 添加频率控制：每0.2秒更新一次（提高更新频率）
                                current_time = time.time()
                                if current_time - last_update_time < 0.2:
                                    return
                                last_update_time = current_time
                                progress_percent = (downloaded / total) * 100
                                total_mb = total / (1024 * 1024)
                                downloaded_mb = downloaded / (1024 * 1024)

                                # 计算真正的下载速度
                                time_diff = current_time - last_time
                                downloaded_diff = downloaded - last_downloaded

                                if time_diff > 0 and downloaded_diff > 0:
                                    speed_bytes_per_sec = downloaded_diff / time_diff
                                    speed_mb = speed_bytes_per_sec / (1024 * 1024)
                                elif progress_percent >= 100:
                                    # 下载完成时，显示"完成"
                                    speed_mb = "完成"
                                else:
                                    speed_mb = 0

                                # 更新时间和下载量
                                last_time = current_time
                                last_downloaded = downloaded

                                # 计算预计剩余时间
                                if isinstance(speed_mb, (int, float)) and speed_mb > 0 and total > downloaded:
                                    remaining = total - downloaded
                                    eta_seconds = int(remaining / (speed_bytes_per_sec))
                                    mins, secs = divmod(eta_seconds, 60)
                                    if mins > 0:
                                        eta_str = f"{mins:02d}:{secs:02d}"
                                    else:
                                        eta_str = f"00:{secs:02d}"
                                else:
                                    eta_str = "未知"

                                # 创建进度条（复用模块化工具）
                                progress_bar = create_progress_bar(progress_percent)

                                # 处理文件名显示
                                display_filename = "正在下载..."
                                if filename:
                                    display_filename = clean_filename_for_display(filename)

                                # 使用和网易云音乐相同的格式
                                if isinstance(speed_mb, str):
                                    speed_display = speed_mb
                                else:
                                    speed_display = f"{speed_mb:.2f}MB/s"

                                progress_text = (
                                    f"🎵 音乐: QQ音乐下载中...\n"
                                    f"📝 文件: {display_filename}\n"
                                    f"💾 大小: {downloaded_mb:.2f}MB / {total_mb:.2f}MB\n"
                                    f"⚡ 速度: {speed_display}\n"
                                    f"⏳ 预计剩余: {eta_str}\n"
                                    f"📊 进度: {progress_bar} ({progress_percent:.1f}%)"
                                )

                                # 处理异步函数
                                if asyncio.iscoroutinefunction(message_updater):
                                    # 异步函数，使用 run_coroutine_threadsafe
                                    try:
                                        loop = asyncio.get_running_loop()
                                        asyncio.run_coroutine_threadsafe(
                                            message_updater(progress_text), loop
                                        )
                                    except Exception as e:
                                        logger.warning(f"异步消息更新失败: {e}")
                                else:
                                    # 同步函数，直接调用
                                    message_updater(progress_text)
                    except Exception as e:
                        logger.warning(f"QQ音乐进度更新失败: {e}")
            else:
                progress_callback = None

            # 使用asyncio.run_in_executor在独立线程中运行同步的下载函数
            import asyncio
            loop = asyncio.get_event_loop()

            # 调用download_by_url方法
            result = await loop.run_in_executor(
                None,
                downloader.qqmusic_downloader.download_by_url,
                url,
                str(download_path),
                'best',  # 使用最高音质
                progress_callback
            )

            if result.get('success'):
                # 检查是否为歌单下载
                if result.get('playlist_name'):
                    # 歌单下载结果
                    return {
                        "success": True,
                        "platform": "QQMusic",
                        "content_type": "music",
                        "download_path": result.get('download_path', ''),
                        "playlist_name": result.get('playlist_name', ''),
                        "total_songs": result.get('total_songs', 0),
                        "downloaded_songs": result.get('downloaded_songs', 0),
                        "failed_songs": result.get('failed_songs', 0),
                        "total_size_mb": result.get('total_size_mb', 0),
                        "quality": result.get('quality', '未知'),
                        "downloaded_list": result.get('downloaded_list', []),
                        "failed_list": result.get('failed_list', []),
                        "url": url
                    }
                # 检查是否为专辑下载
                elif result.get('album_name'):
                    # 专辑下载结果
                    return {
                        "success": True,
                        "platform": "QQMusic",
                        "content_type": "music",
                        "download_path": result.get('download_path', ''),
                        "album_name": result.get('album_name', ''),
                        "singer_name": result.get('singer_name', ''),
                        "total_songs": result.get('total_songs', 0),
                        "downloaded_songs": result.get('downloaded_songs', 0),
                        "failed_songs": result.get('failed_songs', 0),
                        "downloaded_list": result.get('downloaded_list', []),
                        "failed_list": result.get('failed_list', []),
                        "url": url
                    }
                else:
                    # 单首歌曲下载结果
                    song_info = result.get('song_info', {})

                    # 正确提取歌手信息
                    song_artist = song_info.get('singer', '未知歌手')

                    # 正确提取专辑信息
                    album_name = song_info.get('album', '未知专辑')

                    return {
                        "success": True,
                        "platform": "QQMusic",
                        "content_type": "music",
                        "file_path": result.get('file_path', ''),
                        "song_title": song_info.get('title', '未知歌曲'),
                        "song_artist": song_artist,
                        "album": album_name,
                        "quality": song_info.get('quality', '未知音质'),
                        "format": song_info.get('format', '未知格式'),
                        "duration": song_info.get('interval', 0),
                        "url": url
                    }
            else:
                return {
                    "success": False,
                    "error": result.get('error', 'QQ音乐下载失败'),
                    "platform": "QQMusic",
                    "content_type": "music"
                }

        except Exception as e:
            logger.error(f"QQ音乐下载异常: {str(e)}")
            return {
                "success": False,
                "error": f"下载失败: {str(e)}",
                "platform": "QQMusic",
                "content_type": "music"
            }
