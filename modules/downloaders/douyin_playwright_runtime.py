# -*- coding: utf-8 -*-
"""抖音 Playwright 下载运行时。"""

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
    get_douyin_context_options,
)


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


class Platform(str, Enum):
    DOUYIN = "douyin"
    XIAOHONGSHU = "xiaohongshu"
    UNKNOWN = "unknown"


async def run_douyin_playwright_download(
    downloader,
    *,
    url: str,
    message,
    message_updater,
    logger,
    playwright_available: bool,
):
    """执行抖音 Playwright 下载流程。"""
    _ = message

    if not playwright_available:
        return build_playwright_unavailable_result("抖音", "Douyin")

    try:
        from playwright.async_api import async_playwright

        logger.info(f"🎬 开始下载抖音视频: {url}")

        total_start = time.time()
        platform = Platform.DOUYIN

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)

            context = await browser.new_context(**get_douyin_context_options())

            page = await context.new_page()

            if downloader.douyin_cookies_path and os.path.exists(downloader.douyin_cookies_path):
                try:
                    cookies_dict = downloader._parse_douyin_cookies_file(downloader.douyin_cookies_path)
                    cookies = []
                    for name, value in cookies_dict.items():
                        cookies.append(
                            {
                                "name": name,
                                "value": value,
                                "domain": ".douyin.com",
                                "path": "/",
                            }
                        )
                    await context.add_cookies(cookies)
                    logger.info(f"[extract] 成功加载{len(cookies)}个cookies")
                except Exception as e:
                    logger.warning(f"[extract] cookies加载失败: {e}")

            video_id_holder = {"id": None}

            def handle_video_id(request):
                request_url = request.url
                if "video_id=" in request_url:
                    matched = re.search(r"video_id=([a-zA-Z0-9]+)", request_url)
                    if matched:
                        video_id_holder["id"] = matched.group(1)
                        logger.info(f"[extract] 网络请求中捕获到 video_id: {matched.group(1)}")

            page.on("request", handle_video_id)

            try:
                await downloader._set_platform_headers(page, platform)

                if "v.douyin.com" in url:
                    logger.info(f"[extract] 检测到短链接，先获取重定向: {url}")
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    real_url = page.url
                    logger.info(f"[extract] 短链接重定向到: {real_url}")

                    video_id_match = re.search(r"/video/(\d+)", real_url)
                    if video_id_match:
                        video_id = video_id_match.group(1)
                        standard_url = f"https://www.douyin.com/video/{video_id}"
                        logger.info(f"[extract] 转换为标准链接: {standard_url}")
                        await page.goto(standard_url, wait_until="domcontentloaded", timeout=30000)
                        logger.info("[extract] 访问标准链接完成")
                    elif real_url != url:
                        await page.goto(real_url, wait_until="domcontentloaded", timeout=30000)
                        logger.info("[extract] 重新访问真实URL完成")
                else:
                    logger.info("[extract] goto 前")
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    logger.info("[extract] goto 后，等待 video_id")

                page_title = await page.title()
                current_url = page.url
                logger.info(f"[debug] 页面标题: {repr(page_title)}")
                logger.info(f"[debug] 当前URL: {current_url}")

                video_id_match = re.search(r"/video/(\d+)", current_url)
                if video_id_match:
                    video_id_holder["id"] = video_id_match.group(1)
                    logger.info(
                        f"[extract] 从当前URL直接提取到 video_id: {video_id_holder['id']}"
                    )
                else:
                    video_id_match = re.search(r"/video/(\d+)", url)
                    if video_id_match:
                        video_id_holder["id"] = video_id_match.group(1)
                        logger.info(
                            f"[extract] 从原始URL提取到 video_id: {video_id_holder['id']}"
                        )

                await asyncio.sleep(2)

                wait_start = time.time()
                max_wait = 3
                while time.time() - wait_start < max_wait:
                    if video_id_holder["id"]:
                        break
                    await asyncio.sleep(0.1)
                logger.info(f"[extract] video_id 等待用时: {time.time() - wait_start:.2f}s")

                if not video_id_holder["id"]:
                    logger.info("[extract] 网络监听未捕获到video_id，尝试从URL直接提取")
                    for test_url in [current_url, url]:
                        video_id_match = re.search(r"/video/(\d+)", test_url)
                        if video_id_match:
                            video_id_holder["id"] = video_id_match.group(1)
                            logger.info(
                                "[extract] 从URL直接提取到 video_id: "
                                f"{video_id_holder['id']} (来源: {test_url})"
                            )
                            break

                logger.info("[extract] 进入HTML提取流程")
                html = await page.content()
                video_url = await downloader._extract_douyin_url_from_html(html)
                logger.info(f"[extract] 正则提取结果: {video_url}")

                if video_url:
                    if "playwm" in video_url:
                        logger.info("[extract] 检测到带水印URL，尝试转换为无水印URL")
                        video_url = video_url.replace("playwm", "play")
                        logger.info(f"[extract] 转换后的无水印URL: {video_url}")

                    def is_valid_video_url(u):
                        lowered = u.lower()
                        if any(domain in lowered for domain in ["aweme.snssdk.com", "douyinvod.com", "snssdk.com"]):
                            return True
                        if any(param in lowered for param in ["video_id", "play", "aweme"]):
                            return True
                        if any(
                            x in lowered
                            for x in [
                                "client.mp4",
                                "static",
                                "eden-cn",
                                "download/douyin_pc_client",
                                "douyin_pc_client.mp4",
                            ]
                        ):
                            return False
                        return True

                    if is_valid_video_url(video_url):
                        logger.info(f"[extract] 正则流程命中: {video_url}")
                        title = await downloader._get_video_title(page, platform)
                        author = await downloader._get_video_author(page, platform)
                        video_info = VideoInfo(
                            video_id=str(int(time.time())),
                            platform=platform,
                            share_url=url,
                            download_url=video_url,
                            title=title,
                            author=author,
                            thumbnail_url=None,
                        )
                        logger.info("[extract] 正则流程完成")

                        download_result = await downloader._download_video_file(
                            video_info,
                            str(downloader.douyin_download_path),
                            message_updater,
                            None,
                        )

                        await page.close()
                        await context.close()
                        await browser.close()
                        return download_result

                    logger.warning(f"[extract] 提取的URL无效: {video_url}")

                logger.info("[extract] 所有流程均未捕获到视频数据，抛出 TimeoutError")
                raise TimeoutError("未能捕获到视频数据")

            finally:
                logger.info("[extract] 关闭 page/context 前")
                await page.close()
                await context.close()
                logger.info("[extract] 关闭 page/context 后")

            await browser.close()

    except Exception as e:
        logger.error(f"抖音下载异常: {str(e)}")
        return build_playwright_download_error_result("Douyin", f"下载失败: {str(e)}")
