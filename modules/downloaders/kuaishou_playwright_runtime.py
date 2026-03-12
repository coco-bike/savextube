# -*- coding: utf-8 -*-
"""快手 Playwright 下载运行时。"""

import asyncio
import os
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from modules.downloaders.playwright_runtime_common import (
    build_playwright_download_error_result,
    build_playwright_unavailable_result,
)
from modules.downloaders.playwright_context_profiles import (
    get_kuaishou_context_options,
)


@dataclass
class VideoInfo:
    video_id: str
    title: str
    author: str
    download_url: str
    platform: str = "kuaishou"
    create_time: Optional[str] = None
    quality: Optional[str] = None
    thumbnail_url: Optional[str] = None


class Platform(str, Enum):
    KUAISHOU = "kuaishou"
    DOUYIN = "douyin"
    XIAOHONGSHU = "xiaohongshu"
    UNKNOWN = "unknown"


async def run_kuaishou_playwright_download(
    downloader,
    *,
    url: str,
    message,
    message_updater,
    logger,
    playwright_available: bool,
):
    """执行快手 Playwright 下载流程。"""
    _ = message

    if not playwright_available:
        return build_playwright_unavailable_result("快手", "Kuaishou")

    try:
        from playwright.async_api import async_playwright

        clean_url = downloader._extract_clean_url_from_text(url)
        if not clean_url:
            return build_playwright_download_error_result(
                "Kuaishou", "无法从文本中提取有效的快手链接"
            )

        logger.info(f"⚡ 开始下载快手视频: {clean_url}")
        if clean_url != url:
            logger.info(f"🔧 URL已清理: {url} -> {clean_url}")

        url = clean_url
        total_start = time.time()
        _ = total_start
        platform = Platform.KUAISHOU

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)

            context = await browser.new_context(**get_kuaishou_context_options())

            page = await context.new_page()

            if downloader.kuaishou_cookies_path and os.path.exists(downloader.kuaishou_cookies_path):
                try:
                    cookies_dict = downloader._parse_kuaishou_cookies_file(downloader.kuaishou_cookies_path)
                    cookies = []
                    for name, value in cookies_dict.items():
                        cookies.append(
                            {
                                "name": name,
                                "value": value,
                                "domain": ".kuaishou.com",
                                "path": "/",
                            }
                        )
                    await context.add_cookies(cookies)
                    logger.info(f"[extract] 成功加载{len(cookies)}个快手cookies")
                except Exception as e:
                    logger.warning(f"[extract] 加载快手cookies失败: {e}")

            video_id_holder = {"id": None}
            video_url_holder = {"url": None}

            def handle_video_id(request):
                req_url = request.url
                matched = re.search(r"photoId[=:]([a-zA-Z0-9_-]+)", req_url)
                if matched and not video_id_holder["id"]:
                    video_id_holder["id"] = matched.group(1)
                    logger.info(f"[extract] 网络请求中捕获到快手 photo_id: {matched.group(1)}")

                if not video_url_holder["url"]:
                    exclude_patterns = [
                        "log",
                        "collect",
                        "radar",
                        "stat",
                        "track",
                        "analytics",
                        "api",
                        "rest",
                        "sdk",
                        "report",
                        "beacon",
                        "ping",
                    ]

                    is_video_request = False
                    if ".mp4" in req_url and any(
                        domain in req_url
                        for domain in ["kwaicdn.com", "ksapisrv.com", "kuaishou.com"]
                    ):
                        if not any(pattern in req_url.lower() for pattern in exclude_patterns):
                            is_video_request = True
                    elif any(domain in req_url for domain in ["kwaicdn.com"]) and any(
                        ext in req_url for ext in [".mp4", ".m3u8", ".ts"]
                    ):
                        if not any(pattern in req_url.lower() for pattern in exclude_patterns):
                            is_video_request = True

                    if is_video_request:
                        video_url_holder["url"] = req_url
                        logger.info(f"[extract] 网络请求中捕获到快手视频URL: {req_url}")
                    elif any(pattern in req_url.lower() for pattern in exclude_patterns):
                        logger.debug(f"[extract] 跳过非视频请求: {req_url}")

            page.on("request", handle_video_id)

            try:
                await downloader._set_platform_headers(page, platform)

                logger.info(f"[extract] 开始访问快手页面: {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                logger.info("[extract] 页面访问完成")

                logger.info("[extract] 等待页面JavaScript执行...")
                await asyncio.sleep(5)

                try:
                    await page.wait_for_selector(
                        "video, [data-testid*='video'], .video-player", timeout=10000
                    )
                    logger.info("[extract] 检测到视频元素")
                except Exception:
                    logger.warning("[extract] 未检测到视频元素，继续处理")

                try:
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(1)
                    await page.evaluate("window.scrollTo(0, 0)")
                    await asyncio.sleep(1)

                    play_selectors = [
                        ".play-button",
                        ".video-play",
                        "[data-testid='play']",
                        ".player-play",
                        "button[aria-label*='play']",
                        ".play-icon",
                    ]
                    for selector in play_selectors:
                        try:
                            play_button = await page.query_selector(selector)
                            if play_button:
                                await play_button.click()
                                logger.info(f"[extract] 点击了播放按钮: {selector}")
                                await asyncio.sleep(2)
                                break
                        except Exception:
                            continue

                    try:
                        video_area = await page.query_selector(
                            "video, .video-container, .player-container"
                        )
                        if video_area:
                            await video_area.hover()
                            await asyncio.sleep(1)
                    except Exception:
                        pass

                except Exception as e:
                    logger.warning(f"[extract] 页面交互失败: {e}")

                await asyncio.sleep(3)

                if not video_id_holder["id"]:
                    photo_id_match = re.search(r"/short-video/([a-zA-Z0-9_-]+)", url)
                    if photo_id_match:
                        video_id_holder["id"] = photo_id_match.group(1)
                        logger.info(
                            f"[extract] 从URL提取到快手 photo_id: {video_id_holder['id']}"
                        )

                video_url = video_url_holder["url"]

                if not video_url:
                    logger.info("[extract] 网络监听未捕获到视频URL，尝试从HTML提取")
                    html = await page.content()
                    video_url = await downloader._extract_kuaishou_url_from_html(html)
                    logger.info(f"[extract] 快手HTML提取结果: {video_url}")
                else:
                    logger.info(f"[extract] 使用网络监听捕获的视频URL: {video_url}")

                if video_url:
                    title = await downloader._get_video_title(page, platform)
                    author = await downloader._get_video_author(page, platform)

                    video_info = VideoInfo(
                        video_id=video_id_holder["id"] or str(int(time.time())),
                        title=title or f"快手视频_{int(time.time())}",
                        author=author or "未知作者",
                        download_url=video_url,
                        platform="kuaishou",
                    )

                    logger.info(
                        f"[extract] 快手视频信息: 标题={video_info.title}, 作者={video_info.author}"
                    )
                    logger.info("[extract] 正则流程完成")

                    download_result = await downloader._download_video_file(
                        video_info,
                        str(downloader.kuaishou_download_path),
                        message_updater,
                        None,
                    )

                    await page.close()
                    await context.close()
                    return download_result

                logger.error("[extract] 未能提取到快手视频直链")
                await page.close()
                await context.close()
                return build_playwright_download_error_result(
                    "Kuaishou", "未能提取到快手视频直链"
                )

            except Exception as e:
                logger.error(f"[extract] 快手页面处理异常: {str(e)}")
                try:
                    await page.close()
                    await context.close()
                except Exception:
                    pass
                logger.info("[extract] 关闭 page/context 后")

            await browser.close()

    except Exception as e:
        logger.error(f"快手下载异常: {str(e)}")
        return build_playwright_download_error_result("Kuaishou", f"下载失败: {str(e)}")
