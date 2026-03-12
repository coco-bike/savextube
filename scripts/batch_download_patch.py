#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量并发下载补丁
修改 main.py 中的 handle_message 方法以支持批量链接处理
"""

import re

# 要添加的新方法
NEW_METHOD = '''
    def extract_all_urls(self, text: str) -> list:
        """从文本中提取所有 URL 链接（包括磁力链接）"""
        urls = []
        
        # 提取 HTTP/HTTPS 链接
        http_urls = re.findall(r'https?://[^\s]+', text)
        urls.extend(http_urls)
        
        # 提取磁力链接
        magnet_urls = re.findall(r'magnet:\\?xt=urn:btih:[a-fA-F0-9]{32,40}[^\\s]*', text)
        urls.extend(magnet_urls)
        
        # 提取 torrent 链接
        torrent_urls = re.findall(r'https?://[^\\s]*\\.torrent[^\\s]*', text)
        urls.extend(torrent_urls)
        
        # 去重
        urls = list(dict.fromkeys(urls))
        
        return urls
'''

print("批量下载补丁已生成")
print("需要在 main.py 的 handle_message 方法前添加 extract_all_urls 方法")
print("并修改 handle_message 方法以支持批量链接处理")
