# -*- coding: utf-8 -*-
"""单视频下载运行时辅助逻辑。"""

import asyncio
import copy
import os
import threading
import time

YOUTUBE_COOKIE_BYPASS_SECONDS = 30 * 60


def prepare_single_video_progress(
    *,
    message_updater,
    status_message,
    context,
    single_video_progress_hook,
    logger,
):
    """准备单视频进度状态与回调。"""
    logger.info("🔍 步骤3: 设置进度回调...")
    progress_data = {"final_filename": None, "lock": threading.Lock()}

    logger.info(f"🔍 [PROGRESS_SETUP] message_updater类型: {type(message_updater)}")
    logger.info(f"🔍 [PROGRESS_SETUP] status_message: {status_message}")
    logger.info(f"🔍 [PROGRESS_SETUP] context: {context}")

    if (
        callable(message_updater)
        and hasattr(message_updater, "__name__")
        and message_updater.__name__ == "enhanced_progress_callback"
    ):
        logger.info("🔍 [PROGRESS_SETUP] 使用增强版进度回调")
        try:
            progress_hook = message_updater(progress_data)
        except Exception as e:
            logger.error(f"调用增强版进度回调失败: {e}")
            progress_hook = single_video_progress_hook(
                message_updater, progress_data, status_message, context
            )
    else:
        logger.info("🔍 [PROGRESS_SETUP] 使用标准进度回调")
        progress_hook = single_video_progress_hook(
            message_updater, progress_data, status_message, context
        )

    return progress_data, progress_hook


async def run_single_video_download(
    *,
    url: str,
    ydl_opts: dict,
    progress_data: dict,
    yt_dlp_module,
    logger,
):
    """执行单视频下载并返回成功状态。"""
    logger.info("✅ 进度回调已设置")
    logger.info("🔍 步骤4: 开始下载视频（设置60秒超时）...")

    def _run_with_opts(run_opts: dict):
        with yt_dlp_module.YoutubeDL(run_opts) as ydl:
            logger.info("🚀 开始下载视频...")

            try:
                info = ydl.extract_info(url, download=False)
                if info and isinstance(info, dict):
                    title = info.get("title", "未知标题")
                else:
                    title = "未知标题"
                    logger.warning(
                        "⚠️ yt-dlp 未返回有效的视频信息(info=None 或类型无效)，继续执行下载以尝试获取文件"
                    )
                logger.info(f"📺 视频标题: {title}")
            except Exception as e:
                logger.warning(f"⚠️ 获取视频信息失败: {e}")

            retcode = ydl.download([url])
            if retcode not in (0, None):
                raise RuntimeError(f"yt-dlp download failed with code: {retcode}")

    def run_download():
        try:
            _run_with_opts(ydl_opts)
            if progress_data and isinstance(progress_data, dict):
                progress_data["download_strategy"] = "default"
            return True
        except KeyboardInterrupt:
            logger.info("🛇 下载被用户取消")
            if progress_data and isinstance(progress_data, dict):
                progress_data["error"] = "下载已被用户取消"
            return False
        except Exception as e:
            error_message = str(e)
            logger.error(f"❌ 下载失败: {error_message}")

            lowered = error_message.lower()
            should_retry = (
                "requested format is not available" in lowered
                or "only images are available" in lowered
            )

            if should_retry:
                logger.warning("⚠️ 触发YouTube格式回退：改用 format=best 重试一次")
                retry_opts = copy.deepcopy(ydl_opts)
                retry_opts["format"] = "best"
                retry_opts["extractor_args"] = {
                    "youtube": {
                        "player_client": ["android", "ios", "web", "mweb"],
                        "player_skip": ["configs", "webpage"],
                        "formats": ["missing_pot"],
                    }
                }
                try:
                    _run_with_opts(retry_opts)
                    logger.info("✅ YouTube格式回退重试成功")
                    if progress_data and isinstance(progress_data, dict):
                        progress_data["download_strategy"] = "format_best_fallback"
                    return True
                except Exception as retry_error:
                    retry_message = str(retry_error)
                    logger.error(f"❌ YouTube格式回退重试仍失败: {retry_message}")
                    retry_lowered = retry_message.lower()
                    need_no_cookie_retry = (
                        "data sync id" in retry_lowered
                        or "gvs po token" in retry_lowered
                        or "only images are available" in retry_lowered
                        or "requested format is not available" in retry_lowered
                    )
                    if need_no_cookie_retry and ("cookiefile" in ydl_opts or "cookiefile" in retry_opts):
                        logger.warning("⚠️ 检测到YouTube登录态令牌问题，移除 cookies 后再重试一次")
                        no_cookie_opts = copy.deepcopy(retry_opts)
                        no_cookie_opts.pop("cookiefile", None)
                        no_cookie_opts["extractor_args"] = {
                            "youtube": {
                                "player_client": ["android", "web", "mweb"],
                                "player_skip": ["configs", "webpage"],
                            }
                        }
                        try:
                            _run_with_opts(no_cookie_opts)
                            logger.info("✅ 去 cookies 回退重试成功")
                            if progress_data and isinstance(progress_data, dict):
                                progress_data["download_strategy"] = "no_cookie_fallback"
                                progress_data[
                                    "youtube_cookie_bypass_recommended_until"
                                ] = time.time() + YOUTUBE_COOKIE_BYPASS_SECONDS
                            return True
                        except Exception as final_retry_error:
                            retry_message = str(final_retry_error)
                            logger.error(f"❌ 去 cookies 回退重试仍失败: {retry_message}")

                    if progress_data and isinstance(progress_data, dict):
                        progress_data["error"] = retry_message
                    return False

            if progress_data and isinstance(progress_data, dict):
                progress_data["error"] = error_message
            return False

    loop = asyncio.get_running_loop()
    try:
        success = await asyncio.wait_for(
            loop.run_in_executor(None, run_download), timeout=600.0
        )
    except asyncio.TimeoutError:
        logger.error("❌ 视频下载超时（10分钟）")
        return {
            "success": False,
            "error": "视频下载超时，请检查网络连接或稍后重试。",
        }

    if not success:
        error = (
            progress_data.get("error", "下载器在执行时发生未知错误")
            if progress_data and isinstance(progress_data, dict)
            else "下载器在执行时发生未知错误"
        )
        return {"success": False, "error": error}

    return {"success": True, "error": ""}


def build_single_video_download_result(
    downloader,
    *,
    download_path,
    progress_data: dict,
    title: str,
    url: str,
    logger,
):
    """定位下载文件并构建返回结果。"""
    logger.info("🔍 步骤5: 查找下载的文件...")
    time.sleep(1)

    final_file_path = downloader.single_video_find_downloaded_file(
        download_path, progress_data, title, url
    )

    if not final_file_path or not os.path.exists(final_file_path):
        return {
            "success": False,
            "error": "下载完成但无法在文件系统中找到最终文件。",
        }

    logger.info("🔍 步骤6: 获取媒体信息...")
    media_info = downloader.get_media_info(final_file_path)

    try:
        file_size_bytes = os.path.getsize(final_file_path)
        size_mb = file_size_bytes / (1024 * 1024)
    except (OSError, TypeError):
        size_mb = 0.0

    logger.info("🎉 视频下载任务完成!")
    return {
        "success": True,
        "filename": os.path.basename(final_file_path),
        "full_path": final_file_path,
        "size_mb": size_mb,
        "platform": downloader.get_platform_name(url),
        "download_path": str(download_path),
        "resolution": media_info.get("resolution", "未知"),
        "abr": media_info.get("bit_rate"),
        "title": title,
    }
