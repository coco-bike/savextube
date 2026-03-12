# -*- coding: utf-8 -*-
"""gallery-dl 图片下载运行时逻辑。"""

import asyncio
import json
from pathlib import Path

from modules.downloaders.image_download_common import (
    build_gallery_download_success_result,
    collect_relative_files,
    discover_new_media_files,
)


async def monitor_gallery_dl_progress(download_path: Path, before_files, message_updater, logger):
    """监控 gallery-dl 下载进度。"""
    try:
        last_count = 0
        last_update_time = 0
        update_interval = 3

        logger.info("📊 开始监控 gallery-dl 进度")
        logger.info(f"📊 监控目录: {download_path}")
        logger.info(f"📊 下载前文件数量: {len(before_files)}")
        if before_files:
            logger.info(f"📊 下载前文件示例: {list(before_files)[:3]}")

        while True:
            await asyncio.sleep(2)

            current_files = collect_relative_files(download_path)
            new_files = current_files - before_files
            current_count = len(new_files)

            logger.info(f"📊 当前文件数量: {len(current_files)}, 新文件数量: {current_count}")
            if new_files:
                logger.info(f"📊 新文件示例: {list(new_files)[:3]}")

            now = asyncio.get_running_loop().time()
            if current_count != last_count or now - last_update_time > update_interval:
                last_count = current_count
                last_update_time = now

                current_file_path = sorted(new_files)[-1] if new_files else "准备中..."
                progress_text = (
                    "🖼️ **图片下载中**\n"
                    f"📝 当前下载：{current_file_path}\n"
                    f"🖼️ 已完成：{current_count} 张"
                )

                try:
                    if message_updater is None:
                        logger.warning("⚠️ message_updater为None，跳过进度更新")
                        continue

                    if asyncio.iscoroutinefunction(message_updater):
                        await message_updater(progress_text)
                    else:
                        message_updater(progress_text)
                    logger.info(
                        f"📊 gallery-dl 进度更新: {current_count} 张图片, 当前文件: {current_file_path}"
                    )
                except Exception as e:
                    logger.warning(f"⚠️ 更新进度消息失败: {e}")
                    continue

    except asyncio.CancelledError:
        logger.info("📊 进度监控任务已取消")
    except Exception as e:
        logger.error(f"❌ 进度监控任务错误: {e}")


async def run_gallery_dl_image_download(
    downloader,
    *,
    url: str,
    download_path: Path,
    message_updater,
    logger,
    gallery_dl_module,
):
    """执行 gallery-dl 图片下载。"""
    download_path.mkdir(parents=True, exist_ok=True)

    config_path = Path(downloader.download_path / "gallery-dl.conf")
    if not config_path.exists():
        logger.warning(f"⚠️ gallery-dl.conf 配置文件不存在: {config_path}")
        return {"success": False, "error": "gallery-dl.conf 配置文件不存在"}

    logger.info(f"📄 使用 gallery-dl.conf 配置文件: {config_path}")
    gallery_dl_module.config.load([str(config_path)])

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)
        actual_download_dir = config_data.get("base-directory", str(download_path))
        logger.info(f"🎯 gallery-dl 实际下载目录: {actual_download_dir}")
    except Exception as e:
        logger.warning(f"⚠️ 无法从配置文件读取下载目录: {e}")
        actual_download_dir = str(download_path)
        logger.info(f"🎯 使用默认下载目录: {actual_download_dir}")

    actual_download_path = Path(actual_download_dir)
    before_files = collect_relative_files(actual_download_path)
    logger.info(f"📊 下载前文件数量: {len(before_files)}")
    if before_files:
        logger.info(f"📊 下载前文件示例: {list(before_files)[:5]}")

    if message_updater:
        try:
            start_text = "🖼️ **图片下载中**\n📝 当前下载：准备中...\n🖼️ 已完成：0 张"
            if asyncio.iscoroutinefunction(message_updater):
                await message_updater(start_text)
            else:
                message_updater(start_text)
        except Exception as e:
            logger.warning(f"⚠️ 发送开始消息失败: {e}")

    progress_task = None
    if message_updater:
        progress_task = asyncio.create_task(
            monitor_gallery_dl_progress(actual_download_path, before_files, message_updater, logger)
        )

    job = gallery_dl_module.job.DownloadJob(url, None)
    logger.info("📸 gallery-dl 开始下载...")

    try:
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                run_loop = asyncio.get_running_loop()
                await run_loop.run_in_executor(None, job.run)
                logger.info("📸 gallery-dl 下载任务完成")
                break
            except Exception as e:
                retry_count += 1
                error_str = str(e).lower()
                if ("403" in error_str or "forbidden" in error_str) and retry_count < max_retries:
                    logger.warning(f"⚠️ 遇到 403 错误，第 {retry_count} 次重试...")
                    await asyncio.sleep(10)
                    continue
                raise

        await asyncio.sleep(3)
    finally:
        if progress_task:
            progress_task.cancel()
            try:
                await progress_task
            except asyncio.CancelledError:
                logger.info("📊 进度监控任务已取消")

    downloaded_files, total_size_bytes, file_formats = discover_new_media_files(
        actual_download_path, before_files, logger
    )

    logger.info(f"🔍 最终找到的下载文件数量: {len(downloaded_files)}")
    if not downloaded_files:
        logger.warning(f"⚠️ 未找到新下载的文件，查找目录: {actual_download_dir}")
        logger.warning(f"⚠️ 下载前文件数量: {len(before_files)}")
        return {"success": False, "error": "未找到下载的文件"}

    result = build_gallery_download_success_result(
        downloaded_files,
        total_size_bytes,
        file_formats,
        actual_download_dir,
    )
    logger.info(
        f"✅ gallery-dl 下载成功: {result.get('files_count', 0)} 个文件, 总大小: {result.get('size_mb', 0):.1f} MB"
    )
    return result
