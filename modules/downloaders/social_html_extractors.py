# -*- coding: utf-8 -*-
"""社媒平台 HTML 视频直链提取工具。"""

import json
import re


async def extract_douyin_url_from_html(html: str, logger):
    """从抖音HTML源码中提取视频直链。"""
    try:
        logger.info(f"[extract] HTML长度: {len(html)} 字符")

        script_matches = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)

        for script_content in script_matches:
            if "aweme_id" in script_content and "status_code" in script_content:
                json_matches = re.findall(
                    r"({.*?\"errors\":\s*null\s*})", script_content, re.DOTALL
                )
                for json_str in json_matches:
                    try:
                        brace_count = 0
                        json_end = -1
                        for i, char in enumerate(json_str):
                            if char == "{":
                                brace_count += 1
                            elif char == "}":
                                brace_count -= 1
                                if brace_count == 0:
                                    json_end = i + 1
                                    break

                        if json_end > 0:
                            clean_json = json_str[:json_end]
                            data = json.loads(clean_json)

                            def find_video_url(obj):
                                if isinstance(obj, dict):
                                    for key, value in obj.items():
                                        if key == "video" and isinstance(value, dict):
                                            logger.info(f"[extract] 找到video字段: {list(value.keys())}")

                                            if "play_url" in value:
                                                play_url = value["play_url"]
                                                logger.info(f"[extract] play_url字段内容: {play_url}")
                                                logger.info(
                                                    f"[extract] play_url类型: {type(play_url)}"
                                                )
                                                if (
                                                    isinstance(play_url, dict)
                                                    and "url_list" in play_url
                                                ):
                                                    url_list = play_url["url_list"]
                                                    if isinstance(url_list, list) and url_list:
                                                        video_url = url_list[0]
                                                        if video_url.startswith("http"):
                                                            logger.info(
                                                                f"[extract] 从play_url.url_list找到无水印视频URL: {video_url}"
                                                            )
                                                            return video_url
                                                elif isinstance(play_url, str) and play_url.startswith(
                                                    "http"
                                                ):
                                                    if any(
                                                        ext in play_url.lower()
                                                        for ext in [
                                                            ".mp4",
                                                            ".m3u8",
                                                            ".ts",
                                                            "douyinvod.com",
                                                            "snssdk.com",
                                                        ]
                                                    ):
                                                        logger.info(
                                                            f"[extract] 找到无水印视频URL: {play_url}"
                                                        )
                                                        return play_url

                                            if "play_addr" in value:
                                                play_addr = value["play_addr"]
                                                logger.info(f"[extract] play_addr字段内容: {play_addr}")
                                                logger.info(
                                                    f"[extract] play_addr类型: {type(play_addr)}"
                                                )
                                                if (
                                                    isinstance(play_addr, dict)
                                                    and "url_list" in play_addr
                                                ):
                                                    url_list = play_addr["url_list"]
                                                    if isinstance(url_list, list) and url_list:
                                                        video_url = url_list[0]
                                                        if video_url.startswith("http"):
                                                            logger.info(
                                                                f"[extract] 从play_addr.url_list找到有水印视频URL: {video_url}"
                                                            )
                                                            return video_url
                                                if isinstance(play_addr, list) and play_addr:
                                                    video_url = play_addr[0]
                                                    if video_url.startswith("http") and any(
                                                        ext in video_url.lower()
                                                        for ext in [
                                                            ".mp4",
                                                            ".m3u8",
                                                            ".ts",
                                                            "douyinvod.com",
                                                            "snssdk.com",
                                                        ]
                                                    ):
                                                        logger.info(
                                                            f"[extract] 找到有水印视频URL: {video_url}"
                                                        )
                                                        return video_url
                                                elif isinstance(play_addr, str) and play_addr.startswith(
                                                    "http"
                                                ):
                                                    if any(
                                                        ext in play_addr.lower()
                                                        for ext in [
                                                            ".mp4",
                                                            ".m3u8",
                                                            ".ts",
                                                            "douyinvod.com",
                                                            "snssdk.com",
                                                        ]
                                                    ):
                                                        logger.info(
                                                            f"[extract] 找到有水印视频URL: {play_addr}"
                                                        )
                                                        return play_addr
                                        elif isinstance(value, (dict, list)):
                                            result = find_video_url(value)
                                            if result:
                                                return result
                                elif isinstance(obj, list):
                                    for item in obj:
                                        result = find_video_url(item)
                                        if result:
                                            return result
                                return None

                            video_url = find_video_url(data)
                            if video_url:
                                return video_url

                    except json.JSONDecodeError:
                        continue

        return None

    except Exception as e:
        logger.warning(f"抖音HTML正则提取失败: {str(e)}")
    return None


async def extract_kuaishou_url_from_html(html: str, logger):
    """从快手HTML源码中提取视频直链。"""
    try:
        logger.info(f"[extract] 快手HTML长度: {len(html)} 字符")

        try:
            debug_path = "/tmp/kuaishou_debug.html"
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(html)
            logger.info(f"[extract] 已保存HTML到 {debug_path} 用于调试")
            logger.info(f"[extract] HTML开头内容: {html[:500]}")

            keywords = ["video", "mp4", "src", "url", "play", "kwai"]
            for keyword in keywords:
                count = html.lower().count(keyword)
                if count > 0:
                    logger.info(f"[extract] HTML中包含 '{keyword}': {count} 次")

        except Exception as e:
            logger.warning(f"[extract] 保存HTML调试文件失败: {e}")

        patterns = [
            r'"srcNoMark":"(https://[^"]+\.mp4[^"]*)"',
            r'"playUrl":"(https://[^"]+\.mp4[^"]*)"',
            r'"videoUrl":"(https://[^"]+\.mp4[^"]*)"',
            r'"src":"(https://[^"]+\.mp4[^"]*)"',
            r'"url":"(https://[^"]+\.mp4[^"]*)"',
            r"(https://[^\"']+\.kwaicdn\.com/[^\"']+\.mp4[^\"']*)",
            r"(https://[^\"']+\.kuaishou\.com/[^\"']+\.mp4[^\"']*)",
            r"(https://[^\"']+\.ksapisrv\.com/[^\"']+\.mp4[^\"']*)",
            r'"photoUrl":"(https://[^"]+\.mp4[^"]*)"',
            r'"manifest":"(https://[^"]+\.mp4[^"]*)"',
            r"(https://[^\"'>\s]+\.mp4[^\"'>\s]*)",
            r'"[^"]*[Vv]ideo[^"]*":"(https://[^"]+)"',
            r'"[^"]*[Pp]lay[^"]*":"(https://[^"]+\.mp4[^"]*)"',
        ]

        for i, pattern in enumerate(patterns):
            matches = re.findall(pattern, html)
            if matches:
                for match in matches:
                    video_url = (
                        match.replace("\\u002F", "/")
                        .replace("\\u0026", "&")
                        .replace("\\/", "/")
                        .replace("\\", "")
                    )
                    if (
                        video_url.startswith("http")
                        and (
                            ".mp4" in video_url
                            or "kwaicdn.com" in video_url
                            or "kuaishou.com" in video_url
                        )
                        and len(video_url) > 20
                    ):
                        logger.info(f"[extract] 快手模式{i+1}找到视频URL: {video_url}")
                        return video_url

        logger.info("[extract] 正则模式失败，尝试解析script标签中的JSON")
        script_matches = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
        for script_content in script_matches:
            if "mp4" in script_content or "video" in script_content.lower():
                video_patterns = [
                    r'"(https://[^"]+\.mp4[^"]*)"',
                    r"'(https://[^']+\.mp4[^']*)'",
                    r"(https://[^\s\"']+\.mp4[^\s\"']*)",
                ]
                for pattern in video_patterns:
                    matches = re.findall(pattern, script_content)
                    for match in matches:
                        video_url = (
                            match.replace("\\u002F", "/")
                            .replace("\\u0026", "&")
                            .replace("\\/", "/")
                            .replace("\\", "")
                        )
                        if (
                            video_url.startswith("http")
                            and (
                                ".mp4" in video_url or "kwaicdn.com" in video_url
                            )
                            and len(video_url) > 20
                        ):
                            logger.info(f"[extract] 从script标签找到视频URL: {video_url}")
                            return video_url

        logger.warning("[extract] 所有快手正则模式都未匹配到视频URL")

        if "mp4" in html:
            mp4_contexts = []
            for match in re.finditer(r".{0,50}mp4.{0,50}", html, re.IGNORECASE):
                mp4_contexts.append(match.group())
            logger.info(f"[extract] HTML中包含mp4的上下文: {mp4_contexts[:3]}")

        return None

    except Exception as e:
        logger.warning(f"快手HTML正则提取失败: {str(e)}")
    return None
