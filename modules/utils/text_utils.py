# -*- coding: utf-8 -*-
"""
文本与展示工具函数
用于下载进度文案、文件名展示与 Markdown 转义。
"""

import os
import re


def clean_filename_for_display(filename: str, max_length: int = 35) -> str:
    """清理并截断用于消息显示的文件名。"""
    try:
        if filename and re.match(r"^\d{10}_", filename):
            display_name = filename[11:]
        else:
            display_name = filename or ""

        if len(display_name) > max_length:
            name, ext = os.path.splitext(display_name)
            keep = max(1, max_length - 5)
            display_name = name[:keep] + "..." + ext
        return display_name
    except Exception:
        filename = filename or ""
        if len(filename) <= max_length:
            return filename
        return filename[: max_length - 3] + "..."


def create_progress_bar(percent: float, length: int = 20) -> str:
    """创建下载进度条字符串。"""
    filled_length = int(length * percent / 100)
    return "█" * filled_length + "░" * (length - filled_length)


def escape_markdown_v2(text: str) -> str:
    """对 MarkdownV2 特殊字符进行转义。"""
    if not text:
        return text

    escaped_text = text.replace("\\", "\\\\")
    special_chars = [
        "_", "*", "[", "]", "(", ")", "~", "`", ">", "#",
        "+", "-", "=", "|", "{", "}", ".", "!",
    ]
    for char in special_chars:
        escaped_text = escaped_text.replace(char, f"\\{char}")
    return escaped_text
