# -*- coding: utf-8 -*-
"""配置模块包。"""

from .toml_config import (
    load_toml_config,
    get_telegram_config,
    get_proxy_config,
    get_netease_config,
    get_apple_music_config,
    get_bilibili_config,
    get_paths_config,
    get_qbittorrent_config,
    get_logging_config,
    get_youtube_config,
    get_config_with_fallback,
    validate_telegram_config,
    print_config_summary,
)
