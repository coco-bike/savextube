# -*- coding: utf-8 -*-
"""Bilibili 智能下载运行时逻辑。"""

import asyncio
import os
import re
import subprocess
import threading
from pathlib import Path

import requests
import yt_dlp

from modules.utils.progress_hooks import (
    create_single_video_progress_hook as single_video_progress_hook,
)

def smart_download_bilibili_runtime(downloader, url: str, download_path: str, progress_callback=None, auto_playlist=False, *, logger
):
    """智能下载B站视频，支持单视频、分集、合集"""
    import re
    import subprocess
    import os
    import threading
    import asyncio
    from pathlib import Path

    logger.info(f"🎬 开始智能下载B站视频: {url}")
    logger.info(f"📁 下载路径: {download_path}")
    logger.info(f"🔄 自动下载全集: {auto_playlist}")

    # 保存原始工作目录
    original_cwd = os.getcwd()
    logger.info(f"📁 原始工作目录: {original_cwd}")

    try:
        # 检查是否为B站用户列表URL
        is_list, uid, list_id = downloader.is_bilibili_list_url(url)
        if is_list:
            logger.info(f"📋 检测到B站用户列表: UID={uid}, ListID={list_id}")

            # 使用BV号循环法下载用户列表
            bv_list = downloader.get_bilibili_list_videos(uid, list_id)
            if not bv_list:
                return {"status": "failure", "error": "无法获取用户列表视频信息"}

            logger.info(f"📋 获取到 {len(bv_list)} 个视频")

            # 获取列表标题
            try:
                list_info = downloader.get_bilibili_list_info(uid, list_id)
                playlist_title = list_info.get("title", f"BilibiliList-{list_id}")
            except BaseException:
                playlist_title = f"BilibiliList-{list_id}"
            safe_playlist_title = re.sub(
                r'[\\/:*?"<>|]', "_", playlist_title
            ).strip()
            final_download_path = Path(download_path) / safe_playlist_title
            final_download_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"📁 为合集创建下载目录: {final_download_path}")
            # 使用yt-dlp print记录文件名的方案（与多P下载保持一致）
            success_count = 0
            downloaded_files = []  # 记录实际下载的文件信息

            for idx, (bv, title) in enumerate(bv_list, 1):
                safe_title = re.sub(r'[\\/:*?"<>|]', "", title)[:60]
                # 使用绝对路径构建输出模板
                outtmpl = str(
                    final_download_path / f"{idx:02d}. {safe_title}.%(ext)s"
                )

                # 更新下载进度显示
                if progress_callback:
                    progress_callback({
                        'status': 'downloading',
                        'filename': f'{idx:02d}. {safe_title}',
                        '_percent_str': f'{idx}/{len(bv_list)}',
                        '_eta_str': f'第{idx}个，共{len(bv_list)}个',
                        'info_dict': {'title': title}
                    })

                # 1. 先用yt-dlp print获取实际文件名
                video_url = f"https://www.bilibili.com/video/{bv}"
                cmd_print = [
                    "yt-dlp", "--print", "filename", "-o", outtmpl, video_url
                ]

                try:
                    print_result = subprocess.run(cmd_print, capture_output=True, text=True, cwd=str(final_download_path))
                    if print_result.returncode == 0:
                        full_expected_path = print_result.stdout.strip()
                        # 只保留文件名部分，不包含路径
                        expected_filename = os.path.basename(full_expected_path)
                        logger.info(f"📝 预期文件名: {expected_filename}")
                    else:
                        # 如果print失败，使用构造的文件名
                        expected_filename = f"{idx:02d}. {safe_title}.mp4"
                        logger.warning(f"⚠️ print文件名失败，使用构造文件名: {expected_filename}")
                except Exception as e:
                    expected_filename = f"{idx:02d}. {safe_title}.mp4"
                    logger.warning(f"⚠️ print文件名异常: {e}，使用构造文件名: {expected_filename}")

                # 2. 执行下载（使用yt-dlp Python API支持进度回调）
                # 创建安全的进度回调函数，避免 'NoneType' object is not callable 错误
                def safe_progress_hook(d):
                    try:
                        if progress_callback and callable(progress_callback):
                            if asyncio.iscoroutinefunction(progress_callback):
                                # 异步函数处理
                                try:
                                    loop = asyncio.get_running_loop()
                                    asyncio.run_coroutine_threadsafe(progress_callback(d), loop)
                                except RuntimeError:
                                    logger.warning("没有运行的事件循环，跳过异步进度回调")
                            else:
                                # 同步函数，直接调用
                                progress_callback(d)
                        # 如果progress_callback为None或不可调用，静默忽略
                    except Exception as e:
                        logger.error(f"B站下载进度回调错误: {e}")

                ydl_opts_single = {
                    'outtmpl': outtmpl,
                    'merge_output_format': 'mp4',
                    'quiet': False,
                    'no_warnings': False,
                    'progress_hooks': [safe_progress_hook],
                    # 🎯 B站4K支持：使用多策略格式选择，优先4K，回退到会员/非会员可用格式
                    'format': downloader._get_bilibili_best_format(),
                }

                # 添加代理和cookies配置
                if downloader.proxy_host:
                    ydl_opts_single['proxy'] = downloader.proxy_host
            if downloader.b_cookies_path and os.path.exists(downloader.b_cookies_path):
                ydl_opts_single['cookiefile'] = downloader.b_cookies_path

                logger.info(f"🚀 下载第{idx}个: {bv} - {title}")
                logger.info(f"📝 文件名模板: {outtmpl}")

                try:
                    # 使用yt-dlp Python API，支持进度回调
                    with yt_dlp.YoutubeDL(ydl_opts_single) as ydl:
                        ydl.download([video_url])
                    success_count += 1
                    logger.info(f"✅ 第{idx}个下载成功")

                    # 3. 根据预期文件名查找实际文件
                    expected_path = final_download_path / expected_filename
                    if expected_path.exists():
                        size_mb = os.path.getsize(expected_path) / (1024 * 1024)
                        media_info = downloader.get_media_info(str(expected_path))
                        downloaded_files.append({
                            'filename': expected_filename,
                            'size_mb': size_mb,
                            'resolution': media_info.get('resolution', '未知'),
                            'abr': media_info.get('bit_rate')
                        })
                        logger.info(f"📁 记录文件: {expected_filename} ({size_mb:.1f}MB)")
                    else:
                        logger.warning(f"⚠️ 预期文件不存在: {expected_filename}")
                except Exception as e:
                    logger.error(f"❌ 第{idx}个下载失败: {e}")

            logger.info(
                f"🎉 BV号循环法下载完成: {success_count}/{len(bv_list)} 个成功"
            )

            if success_count > 0:
                # 使用已记录的文件信息（不遍历目录）
                total_size_mb = sum(file_info['size_mb'] for file_info in downloaded_files)
                all_resolutions = {file_info['resolution'] for file_info in downloaded_files if file_info['resolution'] != '未知'}

                filename_list = [info['filename'] for info in downloaded_files]
                filename_display = '\n'.join([f"  {i+1:02d}. {name}" for i, name in enumerate(filename_list)])
                resolution_display = ', '.join(sorted(all_resolutions)) if all_resolutions else '未知'

                logger.info(f"📊 用户列表下载统计: {len(downloaded_files)}个文件, 总大小{total_size_mb:.1f}MB")

                return {
                    "status": "success",
                    "video_type": "playlist",
                    "count": success_count,
                    "playlist_title": safe_playlist_title,
                    "download_path": str(final_download_path),
                    # 使用预期文件信息，避免目录遍历
                    "is_playlist": True,
                    "file_count": len(downloaded_files),
                    "total_size_mb": total_size_mb,
                    "files": downloaded_files,
                    "platform": "bilibili",
                    "filename": filename_display,
                    "size_mb": total_size_mb,
                    "resolution": resolution_display,
                    "episode_count": len(downloaded_files)
                }
            else:
                return {"status": "failure", "error": "用户列表视频全部下载失败"}
        # 下面是原有的B站单视频/合集/分集下载逻辑
        logger.info(f"🔍 正在检查视频类型: {url}")

        # 处理短链接，提取BV号
        original_url = url
        if "b23.tv" in url or "b23.wtf" in url:
            logger.info("🔄 检测到B站短链接，尝试提取BV号...")
            try:
                # 先获取重定向后的URL
                temp_opts = {
                    "quiet": True,
                    "no_warnings": True,
                }
                with yt_dlp.YoutubeDL(temp_opts) as ydl:
                    temp_info = ydl.extract_info(url, download=False)

                if temp_info.get("webpage_url"):
                    redirected_url = temp_info["webpage_url"]
                    logger.info(f"🔄 短链接重定向到: {redirected_url}")

                    # 从重定向URL中提取BV号
                    bv_match = re.search(r"BV[0-9A-Za-z]+", redirected_url)
                    if bv_match:
                        bv_id = bv_match.group()
                        # 构造原始链接（不带分P标识）
                        original_url = f"https://www.bilibili.com/video/{bv_id}/"
                        logger.info(f"🔄 提取到BV号: {bv_id}")
                        logger.info(f"🔄 使用原始链接: {original_url}")
                    else:
                        logger.warning("⚠️ 无法从重定向URL中提取BV号")
                else:
                    logger.warning("⚠️ 短链接重定向失败")
            except Exception as e:
                logger.warning(f"⚠️ 处理短链接时出错: {e}")

        # 修改检测逻辑，确保能正确识别多P视频
        if auto_playlist:
            # 开启自动下载全集时，强制检测playlist
            check_opts = {
                "quiet": True,
                "flat_playlist": True,
                "extract_flat": True,
                "print": "%(id)s %(title)s",
                "noplaylist": False,  # 关键：不阻止playlist检测
                "yes_playlist": True,  # 关键：允许playlist检测
                "extract_flat": True,  # 确保提取所有条目
            }
        else:
            # 关闭自动下载全集时，阻止playlist检测
            check_opts = {
                "quiet": True,
                "flat_playlist": True,
                "extract_flat": True,
                "print": "%(id)s %(title)s",
                "noplaylist": True,  # 阻止playlist检测
            }

        # 使用处理后的URL进行检测
        with yt_dlp.YoutubeDL(check_opts) as ydl:
            info = ydl.extract_info(original_url, download=False)

        entries = info.get("entries", [])
        count = len(entries) if entries else 1
        logger.info(f"📋 检测到 {count} 个视频")

        # 如果只有一个视频，尝试anthology检测和强制playlist检测
        if count == 1:
            # 特殊检测：使用模拟下载检测anthology
            logger.info("🔍 使用模拟下载检测anthology...")
            anthology_detected = False
            try:
                # 捕获yt-dlp的输出来检测anthology
                cmd_simulate = ['yt-dlp', '--simulate', '--verbose', original_url]
                result = subprocess.run(cmd_simulate, capture_output=True, text=True)
                output = result.stdout + result.stderr

                if 'extracting videos in anthology' in output.lower():
                    anthology_detected = True
                    logger.info("✅ 检测到anthology关键词，这是一个合集")
                else:
                    logger.info("❌ 未检测到anthology关键词")

            except Exception as e:
                logger.warning(f"⚠️ anthology检测失败: {e}")

            # 如果检测到anthology或开启了auto_playlist，尝试强制检测playlist
            if anthology_detected or auto_playlist:
                if anthology_detected:
                    logger.info("🔄 检测到anthology，强制使用合集模式")
                else:
                    logger.info("🔄 开启自动下载全集，尝试强制检测playlist...")

                force_check_opts = {
                    "quiet": True,
                    "flat_playlist": True,
                    "extract_flat": True,
                    "print": "%(id)s %(title)s",
                    "noplaylist": False,
                    "yes_playlist": True,
                }

                try:
                    with yt_dlp.YoutubeDL(force_check_opts) as ydl:
                        force_info = ydl.extract_info(original_url, download=False)
                    force_entries = force_info.get("entries", [])
                    force_count = len(force_entries) if force_entries else 1

                    if force_count > count:
                        logger.info(f"🔄 强制检测成功！检测到 {force_count} 个视频")
                        entries = force_entries
                        count = force_count
                        info = force_info
                    elif anthology_detected:
                        # 检测到anthology，但需要进一步确认是否真的是多集
                        logger.info("🔄 anthology检测成功，但需要确认是否真的是多集")
                        # 不强制设置count，保持原有的检测结果
                        if count <= 1:
                            logger.info("🔍 anthology检测到，但实际只有1集，按单集处理")
                        else:
                            logger.info(f"🔍 anthology检测到，确认有{count}集，按合集处理")
                except Exception as e:
                    logger.warning(f"⚠️ 强制检测失败: {e}")
                    if anthology_detected:
                        # 如果anthology检测成功但强制检测失败，需要谨慎处理
                        logger.info("🔄 anthology检测成功，但强制检测失败，按实际检测结果处理")
                        # 不强制设置count，保持原有的检测结果
                        if count <= 1:
                            logger.info("🔍 anthology检测到但强制检测失败，且实际只有1集，按单集处理")
                        else:
                            logger.info(f"🔍 anthology检测到，实际有{count}集，按合集处理")
        playlist_title = info.get("title", "Unknown Playlist")
        safe_playlist_title = re.sub(r'[\\/:*?"<>|]', "_", playlist_title).strip()

        if count > 1 and auto_playlist:
            final_download_path = Path(download_path) / safe_playlist_title
            final_download_path.mkdir(parents=True, exist_ok=True)
            logger.info(
                f"📁 为合集 '{safe_playlist_title}' 创建下载目录: {final_download_path}"
            )
        else:
            final_download_path = Path(download_path)
            logger.info(f"📁 使用默认下载目录: {final_download_path}")
        # 移除 os.chdir() 调用，使用绝对路径

        if count == 1:
            video_type = "single"
            logger.info("🎬 检测到单视频")
        else:
            first_id = entries[0].get("id", "") if entries else ""
            all_same_id = all(
                entry.get("id", "") == first_id for entry in entries if entry
            )
            if all_same_id:
                video_type = "episodes"
                logger.info(f"📺 检测到分集视频，共 {count} 集")
                logger.info("📋 分集详情:")
                for i, entry in enumerate(entries, 1):
                    if entry:
                        episode_title = entry.get("title", "unknown")
                        episode_id = entry.get("id", "unknown")
                        logger.info(
                            f"  {i:02d}. {episode_title} (ID: {episode_id})"
                        )
            else:
                video_type = "playlist"
                logger.info(f"📚 检测到合集，共 {count} 个视频")
                logger.info("📋 合集详情:")
                for i, entry in enumerate(entries, 1):
                    if entry:
                        video_title = entry.get("title", "unknown")
                        video_id = entry.get("id", "unknown")
                        logger.info(f"  {i:02d}. {video_title} (ID: {video_id})")

        # 根据视频类型决定下载策略
        if video_type == "single":
            # smart_download_bilibili 专门处理多P和合集，单视频应该由通用下载器处理
            logger.info("⚠️ smart_download_bilibili 检测到单视频")
            if auto_playlist:
                logger.info("💡 虽然开启了自动下载全集，但这确实是单视频，建议使用通用下载器")
            else:
                logger.info("💡 这是单视频，建议使用通用下载器")

            # 返回特殊状态，让调用方知道这是单视频
            return {
                "status": "single_video",
                "message": "这是单视频，建议使用通用下载器",
                "video_type": "single"
            }
        elif video_type == "episodes":
            if auto_playlist:
                # 自动下载全集 - 直接使用完整标题，不做复杂处理
                output_template = str(
                    final_download_path / "%(title)s.%(ext)s"
                )
                # 添加明显的outtmpl日志
                logger.info(
                    f"🔧 [BILIBILI_EPISODES] outtmpl 使用完整标题: {output_template}"
                )

                # 创建简单的进度回调，不需要重命名
                def enhanced_progress_callback(d):
                    # 执行原有的进度回调逻辑（显示完整标题）
                    if progress_callback:
                        progress_callback(d)

                ydl_opts = {
                    "outtmpl": output_template,
                    "merge_output_format": "mp4",
                    "quiet": False,
                    "yes_playlist": True,
                    "extract_flat": False,
                    "progress_hooks": [enhanced_progress_callback],
                    # 🎯 B站4K支持：使用多策略格式选择，优先4K，回退到会员/非会员可用格式
                    "format": downloader._get_bilibili_best_format(),
                }
                logger.info("🔄 自动下载全集模式：将下载所有分P视频")
            else:
                # 只下载当前分P
                output_template = str(final_download_path / "%(title)s.%(ext)s")
                # 添加明显的outtmpl日志
                logger.info(
                    f"🔧 [BILIBILI_SINGLE_EPISODE] outtmpl 绝对路径: {output_template}"
                )
                ydl_opts = {
                    "outtmpl": output_template,
                    "merge_output_format": "mp4",
                    "quiet": False,
                    "noplaylist": True,
                    "progress_hooks": [
                        lambda d: (
                            progress_callback(d) if progress_callback else None
                        )
                    ],
                    # 🎯 B站4K支持：使用多策略格式选择，优先4K，回退到会员/非会员可用格式
                    "format": downloader._get_bilibili_best_format(),
                }
                logger.info("🔄 单P模式：只下载当前分P视频")
        else:  # playlist - 和多P下载一样简单
            # 对于合集，直接使用yt-dlp播放列表功能（和多P下载一样）
            logger.info(f"🔧 检测到合集，使用yt-dlp播放列表功能下载")
            logger.info(f"   - 视频数量: {count}")

            # 使用和多P下载完全相同的逻辑，B站不使用ID标签
            output_template = str(
                final_download_path / "%(playlist_index)s. %(title)s.%(ext)s"
            )
            logger.info(f"🔧 [BILIBILI_PLAYLIST] outtmpl 绝对路径: {output_template}")

            # 使用增强版进度回调来生成详细的进度显示格式
            progress_data = {
                "final_filename": None,
                "lock": threading.Lock(),
                "downloaded_files": [],  # 添加下载文件列表
                "expected_files": []     # 添加预期文件列表
            }

            # 检查 progress_callback 是否是增强版进度回调函数
            if callable(progress_callback) and progress_callback.__name__ == 'enhanced_progress_callback':
                # 如果是增强版进度回调，直接使用它返回的 progress_hook
                progress_hook = progress_callback(progress_data)
            else:
                # 否则使用标准的 single_video_progress_hook
                progress_hook = single_video_progress_hook(
                    message_updater=progress_callback,
                    progress_data=progress_data,
                    status_message=None,
                    context=None,
                )

            ydl_opts = {
                "outtmpl": output_template,
                "merge_output_format": "mp4",
                "quiet": False,
                "yes_playlist": True,
                "extract_flat": False,
                "progress_hooks": [progress_hook],
                # 🎯 B站4K支持：使用多策略格式选择，优先4K，回退到会员/非会员可用格式
                "format": downloader._get_bilibili_best_format(),
            }
            logger.info("🔄 合集模式：将下载所有合集视频")

        # 对于单视频和分集视频，使用yt-dlp下载
        if video_type in ["single", "episodes"]:
            # 添加代理和cookies配置
            if downloader.proxy_host:
                ydl_opts["proxy"] = downloader.proxy_host
            if downloader.b_cookies_path and os.path.exists(downloader.b_cookies_path):
                ydl_opts["cookiefile"] = downloader.b_cookies_path
                logger.info(f"🍪 使用B站cookies: {downloader.b_cookies_path}")
            else:
                logger.warning("⚠️ 未设置B站cookies，可能无法下载某些视频")
                logger.warning("💡 请设置BILIBILI_COOKIES环境变量指向cookies文件")

            # 为B站添加更强的重试和延迟机制
            if downloader.is_bilibili_url(url):
                ydl_opts.update({
                    "retries": 10,  # 增加重试次数
                    "fragment_retries": 10,
                    "socket_timeout": 60,  # 增加超时时间
                    "sleep_interval": 2,   # 添加请求间隔
                    "max_sleep_interval": 5,
                    # 添加更详细的错误处理
                    "ignoreerrors": False,  # 不忽略错误，便于调试
                })
                logger.info("🔧 为B站链接启用增强重试机制")

            # 添加弹幕下载选项
            ydl_opts = downloader._add_danmaku_options(ydl_opts, url)

            # 如果是B站链接且开启了封面下载，添加缩略图下载选项
            if hasattr(self, 'bot') and hasattr(downloader.bot, 'bilibili_thumbnail_download') and downloader.bot.bilibili_thumbnail_download:
                ydl_opts["writethumbnail"] = True
                # 添加缩略图格式转换后处理器：WebP -> JPG
                if "postprocessors" not in ydl_opts:
                    ydl_opts["postprocessors"] = []
                ydl_opts["postprocessors"].append({
                    'key': 'FFmpegThumbnailsConvertor',
                    'format': 'jpg',
                    'when': 'before_dl'
                })
                logger.info("🖼️ 开启B站封面下载（转换为JPG格式）")

            logger.info(f"🔧 [BILIBILI_DOWNLOAD] 最终ydl_opts: {ydl_opts}")
            logger.info(f"📝 最终输出模板: {output_template}")
            logger.info(f"📁 下载目录: {final_download_path}")

            # 执行下载
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([original_url])

            logger.info("✅ B站视频下载完成")
            logger.info("🎯 使用postprocessor智能文件名，无需重命名")

            # 简化：B站多P下载完成，直接返回成功，文件查找交给目录遍历
            logger.info("🎯 B站多P下载完成，使用目录遍历查找文件")

            return {
                "status": "success",
                "video_type": video_type,
                "count": count,
                "playlist_title": safe_playlist_title if count > 1 else None,
                "download_path": str(final_download_path),
                # 简化：不传递预期文件信息，使用目录遍历
            }

    except Exception as e:
        logger.error(f"❌ B站视频下载失败: {e}")
        return {"status": "failure", "error": str(e)}
    finally:
        # 恢复原始工作目录
        try:
            os.chdir(original_cwd)
            logger.info(f"📁 已恢复工作目录: {original_cwd}")
        except Exception as e:
            logger.warning(f"⚠️ 恢复工作目录失败: {e}")
