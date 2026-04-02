# -*- coding: utf-8 -*-
"""下载 URL 预处理逻辑。"""

import asyncio
import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit


def _normalize_url_text(raw: str) -> str:
    """Normalize URL text from user input and strip invisible chars."""
    if not isinstance(raw, str):
        return raw

    text = unicodedata.normalize("NFKC", raw).strip()

    # Remove format/control chars (e.g. U+2060 word joiner from copied links).
    text = "".join(ch for ch in text if unicodedata.category(ch) not in {"Cf", "Cc"})

    # Trim punctuation commonly attached after copied URLs.
    text = text.rstrip('.,;!?，。；！？)]}>"\'')

    # Extract URL part if text contains extra words/newlines.
    if " " in text or "\n" in text or "\t" in text:
        m = re.search(r"https?://[^\s]+", text)
        if m:
            text = m.group(0).rstrip('.,;!?，。；！？)]}>"\'')
        else:
            text = text.split()[0]

    # Best-effort clean for accidental whitespace in parts.
    try:
        parts = urlsplit(text)
        if parts.scheme and parts.netloc:
            text = urlunsplit(
                (
                    parts.scheme,
                    parts.netloc,
                    parts.path.strip(),
                    parts.query.strip(),
                    parts.fragment.strip(),
                )
            )
    except Exception:
        pass

    return text


async def preprocess_download_url(downloader, url: str, message_updater, logger, yt_dlp_module):
    """执行下载前 URL 归一化、渠道开关检查与重定向处理。"""
    normalized_url = _normalize_url_text(url)
    if normalized_url != url:
        logger.info(f"🧹 URL输入清洗: {url} -> {normalized_url}")
    url = normalized_url

    if url.startswith("tp://"):
        logger.info("检测到 tp:// 协议，自动修正为 http://")
        url = "http://" + url[5:]
    elif url.startswith("tps://"):
        logger.info("检测到 tps:// 协议，自动修正为 https://")
        url = "https://" + url[6:]

    if downloader.is_weibo_url(url):
        logger.info(f"📳 检测到微博URL，开始展开短链接: {url}")
        expanded_url = downloader._expand_weibo_short_url(url)
        if expanded_url != url:
            logger.info(f"📧 短链接展开成功: {url} -> {expanded_url}")
            url = _normalize_url_text(expanded_url)
            logger.info(f"📧 使用展开后的微博链接: {url}")
        else:
            logger.info(f"ℹ️ URL无需展开或展开失败，继续使用原URL: {url}")

    original_url = url

    needs_cleanup = (
        " " in url
        or "(" in url
        or ")" in url
        or "。" in url
        or "，" in url
        or "@" in url
        or not url.startswith(("http://", "https://"))
    )

    if needs_cleanup:
        logger.info(f"🔡 检测到需要清理的URL，开始清理: {url}")

        clean_url = downloader._clean_netease_url_special(url)
        if clean_url and clean_url != url:
            logger.info(f"🔡 网易云音乐URL清理成功: {url} -> {clean_url}")
            url = _normalize_url_text(clean_url)
        else:
            clean_url = downloader._extract_clean_url_from_text(url)
            if clean_url and clean_url != url:
                logger.info(f"🔡 通用URL清理成功: {url} -> {clean_url}")
                url = _normalize_url_text(clean_url)
            else:
                if not url.startswith(("http://", "https://")):
                    logger.info(f"🔡 URL缺少协议前缀，尝试添加: {url}")
                    url = "https://" + url
                    logger.info(f"🔡 添加协议前缀后: {url}")
                else:
                    logger.warning(f"⚠️ URL清理失败，使用原始URL: {url}")

    if not downloader.is_netease_url(url):
        logger.info(f"📧 开始URL重定向检测: {url}")
        try:
            temp_opts = {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": True,
            }
            with yt_dlp_module.YoutubeDL(temp_opts) as ydl:
                temp_info = ydl.extract_info(url, download=False)

            if temp_info and temp_info.get("webpage_url") and temp_info["webpage_url"] != url:
                redirected_url = _normalize_url_text(temp_info["webpage_url"])
                logger.info(f"📧 检测到URL重定向: {url} -> {redirected_url}")

                if downloader.is_netease_url(redirected_url) and not downloader.is_netease_url(url):
                    logger.info(f"🎵 重定向后检测到网易云音乐链接，更新URL: {redirected_url}")
                    url = redirected_url
                elif downloader.is_apple_music_url(redirected_url) and not downloader.is_apple_music_url(url):
                    logger.info(f"🍎 重定向后检测到Apple Music链接，更新URL: {redirected_url}")
                    url = redirected_url
                elif downloader.is_youtube_url(redirected_url) and downloader.is_youtube_url(url):
                    logger.info(f"🎬 使用重定向后的YouTube标准链接: {redirected_url}")
                    url = redirected_url
        except Exception as e:
            logger.info(f"URL重定向检测失败: {e}")
    else:
        logger.info(f"🎵 检测到网易云音乐链接，完全跳过URL重定向检测: {url}")
        logger.info(f"🎵 网易云音乐链接将直接传递给网易云音乐下载器: {url}")
        if not url.startswith(("http://", "https://")):
            logger.warning(f"⚠️ 网易云音乐URL缺少协议前缀，自动添加: {url}")
            url = "https://" + url
            logger.info(f"🔡 修复后的URL: {url}")

    return {"ok": True, "url": url, "original_url": original_url}
