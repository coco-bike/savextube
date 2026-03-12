# -*- coding: utf-8 -*-
"""网络与代理初始化工具。"""

import os


def configure_proxy_for_downloader(downloader, logger) -> None:
    """根据 proxy_host 配置代理环境并进行连通性检查。"""
    if downloader.proxy_host:
        if downloader._test_proxy_connection():
            logger.info(f"代理服务器已配置并连接成功: {downloader.proxy_host}")
            logger.info(f"yt-dlp 使用代理: {downloader.proxy_host}")
            os.environ["HTTP_PROXY"] = downloader.proxy_host
            os.environ["HTTPS_PROXY"] = downloader.proxy_host
            os.environ["NO_PROXY"] = "localhost,127.0.0.1"
        else:
            logger.warning(f"代理服务器已配置但连接失败: {downloader.proxy_host}")
            logger.info("yt-dlp 直接连接")
            downloader.proxy_host = None
            os.environ.pop("HTTP_PROXY", None)
            os.environ.pop("HTTPS_PROXY", None)
            os.environ.pop("NO_PROXY", None)
    else:
        logger.info("代理服务器未配置，将直接连接")
        logger.info("yt-dlp 直接连接")
