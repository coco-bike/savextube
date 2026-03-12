# -*- coding: utf-8 -*-
"""小红书 Playwright 下载运行时。"""

import asyncio
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from modules.downloaders.playwright_runtime_common import (
    build_playwright_download_error_result,
    build_playwright_unavailable_result,
    safe_delete_start_message,
)
from modules.downloaders.playwright_context_profiles import (
    get_xiaohongshu_context_options,
)
from modules.url_extractor import URLExtractor


@dataclass
class VideoInfo:
    video_id: str
    platform: str
    share_url: str
    download_url: Optional[str] = None
    title: Optional[str] = None
    author: Optional[str] = None
    create_time: Optional[str] = None
    quality: Optional[str] = None
    thumbnail_url: Optional[str] = None


async def prepare_xiaohongshu_playwright_context(
    downloader,
    *,
    url: str,
    message,
    logger,
    playwright_available: bool,
):
    """准备小红书 Playwright 下载上下文。"""
    real_url = URLExtractor.extract_xiaohongshu_url(url)
    if real_url:
        url = real_url
    else:
        logger.warning("未检测到小红书链接，原样使用参数")

    if not playwright_available:
        return {
            "handled": True,
            "result": build_playwright_unavailable_result("小红书", "Xiaohongshu"),
        }

    platform = downloader.Platform.XIAOHONGSHU
    start_message = None

    if (
        hasattr(downloader, "bot")
        and downloader.bot
        and message
        and hasattr(message, "chat")
        and hasattr(message.chat, "id")
    ):
        try:
            start_message = await downloader.bot.send_message(
                message.chat.id,
                f"🎬 开始下载{platform.value}视频...",
            )
        except Exception as e:
            logger.warning(f"⚠️ 发送开始消息失败: {e}")
    else:
        logger.info(f"🎬 开始下载{platform.value}视频...")

    download_dir = str(downloader.xiaohongshu_download_path)
    os.makedirs(download_dir, exist_ok=True)

    return {
        "handled": False,
        "url": url,
        "platform": platform,
        "start_message": start_message,
        "download_dir": download_dir,
    }


async def extract_xiaohongshu_video_info(
    downloader,
    *,
    url: str,
    platform,
    logger,
):
    """通过 Playwright 提取小红书视频信息。"""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(**get_xiaohongshu_context_options())

        page = await context.new_page()
        video_url_holder = {"url": None}
        html = ""

        def handle_request(request):
            req_url = request.url
            if any(ext in req_url.lower() for ext in [".mp4", ".m3u8"]):
                if "xhscdn.com" in req_url or "xiaohongshu.com" in req_url:
                    if not video_url_holder["url"]:
                        video_url_holder["url"] = req_url
                        logger.info(f"[cat-catch] 嗅探到小红书视频流: {req_url}")

        page.on("request", handle_request)

        try:
            await downloader._set_platform_headers(page, platform)

            logger.info("[extract] goto 前")
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            logger.info("[extract] goto 后，开始极速嗅探")

            for _ in range(5):
                if video_url_holder["url"]:
                    logger.info(
                        f"[cat-catch][fast] 极速嗅探到小红书视频流: {video_url_holder['url']}"
                    )
                    title = await downloader._get_video_title(page, platform)
                    author = await downloader._get_video_author(page, platform)
                    logger.info("[cat-catch][fast] 极速嗅探流程完成")
                    return VideoInfo(
                        video_id=str(int(time.time())),
                        platform=platform.value,
                        share_url=url,
                        download_url=video_url_holder["url"],
                        title=title,
                        author=author,
                    )
                await asyncio.sleep(0.3)

            if not video_url_holder["url"]:
                logger.warning("⚠️ 网络嗅探未捕获到小红书视频流")
            else:
                logger.info(
                    f"✅ 网络嗅探成功捕获到小红书视频流: {video_url_holder['url']}"
                )

            if not video_url_holder["url"]:
                html = await page.content()
                logger.info("🔍 开始从HTML提取小红书视频直链...")

                patterns = [
                    r"(https://sns-[^\"']+\\.xhscdn\\.com/stream/[^\"']+\\.mp4)",
                    r"(https://ci[^\"']+\\.xhscdn\\.com/[^\"']+\\.mp4)",
                    r"(https://[^\"']+\\.xhscdn\\.com/[^\"']+\\.mp4)",
                    r'"videoUrl":"(https://[^"\\]+)"',
                    r'"video_url":"(https://[^"\\]+)"',
                    r'"url":"(https://[^"\\]+\\.mp4)"',
                ]

                for i, pattern in enumerate(patterns):
                    matched = re.search(pattern, html)
                    if matched:
                        candidate = matched.group(1).replace("\\u002F", "/").replace("\\u0026", "&")
                        if (
                            downloader._is_valid_xiaohongshu_url(candidate)
                            and not video_url_holder["url"]
                        ):
                            video_url_holder["url"] = candidate
                            logger.info(f"✅ 使用模式{i + 1}提取到小红书视频URL: {candidate}")
                            break
                        if (
                            downloader._is_valid_xiaohongshu_url(candidate)
                            and video_url_holder["url"]
                        ):
                            logger.info(
                                f"⚠️ 网络嗅探已捕获到URL，跳过HTML提取的URL: {candidate}"
                            )
                            break

            title = None
            author = None
            if video_url_holder["url"]:
                try:
                    title = await downloader._get_video_title(page, platform)
                    author = await downloader._get_video_author(page, platform)
                    logger.info(f"📝 获取到标题: {title}")
                    logger.info(f"👤 获取到作者: {author}")
                except Exception as e:
                    logger.warning(f"⚠️ 获取标题和作者失败: {e}")

            if not video_url_holder["url"]:
                raise Exception("无法提取小红书视频直链，请检查链接有效性")

            return VideoInfo(
                video_id=str(int(time.time())),
                platform=platform.value,
                share_url=url,
                download_url=video_url_holder["url"],
                title=title,
                author=author,
            )
        except Exception:
            if html:
                debug_html_path = str(
                    Path.cwd() / f"xiaohongshu_debug_{int(time.time())}.html"
                )
                try:
                    with open(debug_html_path, "w", encoding="utf-8") as f:
                        f.write(html)
                    logger.error(f"❌ 无法提取小红书视频直链，已保存调试HTML到: {debug_html_path}")
                except Exception as save_error:
                    logger.error(f"❌ 无法提取小红书视频直链，保存调试文件失败: {save_error}")
            raise
        finally:
            await page.close()
            await context.close()
            await browser.close()


async def run_xiaohongshu_playwright_download(
    downloader,
    *,
    url: str,
    message,
    message_updater,
    logger,
    playwright_available: bool,
):
    """运行小红书 Playwright 下载全流程。"""
    ctx = await prepare_xiaohongshu_playwright_context(
        downloader,
        url=url,
        message=message,
        logger=logger,
        playwright_available=playwright_available,
    )
    if ctx.get("handled"):
        return ctx["result"]

    platform = ctx["platform"]
    start_message = ctx["start_message"]
    download_dir = ctx["download_dir"]
    actual_url = ctx["url"]

    try:
        video_info = await extract_xiaohongshu_video_info(
            downloader,
            url=actual_url,
            platform=platform,
            logger=logger,
        )

        result = await downloader._download_video_file(
            video_info,
            download_dir,
            message_updater,
            start_message,
        )

        if not result.get("success"):
            raise Exception(result.get("error", "下载失败"))

        await safe_delete_start_message(
            downloader,
            message=message,
            start_message=start_message,
            logger=logger,
        )

        logger.info(f"✅ {platform.value}视频下载成功")
        return result

    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Playwright 下载小红书视频失败: {error_msg}")

        await safe_delete_start_message(
            downloader,
            message=message,
            start_message=start_message,
            logger=logger,
        )

        return build_playwright_download_error_result(
            "Xiaohongshu", f"Playwright 下载失败: {error_msg}"
        )
