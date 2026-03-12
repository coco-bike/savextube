# -*- coding: utf-8 -*-
"""渠道开关配置读取与保存。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

from modules.config.toml_config import load_toml_config

logger = logging.getLogger(__name__)

DEFAULT_CHANNEL_SWITCHES: Dict[str, bool] = {
    "x": True,
    "youtube": True,
    "xvideos": True,
    "pornhub": True,
    "bilibili": True,
    "music": True,
    "telegram": True,
    "telegraph": True,
    "douyin": True,
    "kuaishou": True,
    "toutiao": True,
    "facebook": True,
    "xiaohongshu": True,
    "weibo": True,
    "instagram": True,
    "tiktok": True,
    "netease": True,
    "qqmusic": True,
    "youtubemusic": True,
    "apple_music": True,
}

CHANNEL_SWITCHES_FILE = Path("config/channel_switches.json")


def _normalize_switches(raw: Dict[str, Any]) -> Dict[str, bool]:
    normalized: Dict[str, bool] = DEFAULT_CHANNEL_SWITCHES.copy()
    if not isinstance(raw, dict):
        return normalized

    for key in normalized.keys():
        if key in raw:
            normalized[key] = bool(raw[key])

    return normalized


def load_channel_switches() -> Dict[str, bool]:
    """读取渠道开关（优先 JSON，回退 TOML，最终默认全开）。"""
    switches = DEFAULT_CHANNEL_SWITCHES.copy()

    try:
        if CHANNEL_SWITCHES_FILE.exists():
            with open(CHANNEL_SWITCHES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            switches = _normalize_switches(data)
            return switches
    except Exception as e:
        logger.warning(f"读取渠道开关 JSON 失败，将尝试 TOML: {e}")

    try:
        toml_config = load_toml_config("savextube.toml")
        channels = toml_config.get("channels", {}) if isinstance(toml_config, dict) else {}
        switches = _normalize_switches(channels)
    except Exception as e:
        logger.warning(f"读取渠道开关 TOML 失败，使用默认值: {e}")

    return switches


def save_channel_switches(switches: Dict[str, Any]) -> Dict[str, bool]:
    """保存渠道开关到 JSON 文件。"""
    normalized = _normalize_switches(switches)
    CHANNEL_SWITCHES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CHANNEL_SWITCHES_FILE, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)
    return normalized
