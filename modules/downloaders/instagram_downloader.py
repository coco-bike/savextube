#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Instagram 图片下载器 - 简化版本
使用命令行方式调用 gallery-dl，确保 cookies 正确传递
"""

import os
import sys
import time
import asyncio
import json
import logging
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List
import requests
from urllib.parse import urlparse

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class InstagramPicDownloaderSimple:
    """Instagram 图片下载器 - 简化版本"""
    
    def __init__(self, cookies_path: str = "./instagram_cookies.txt"):
        """
        初始化下载器
        
        Args:
            cookies_path: Instagram cookies 文件路径
        """
        self.cookies_path = cookies_path
        self.session = requests.Session()
        self._setup_session()
        
        # 检查 gallery-dl 是否可用
        try:
            result = subprocess.run(['gallery-dl', '--version'], 
                                  capture_output=True, text=True, check=True)
            self.gallery_dl_available = True
            logger.info(f"✅ gallery-dl 可用，版本: {result.stdout.strip()}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.gallery_dl_available = False
            logger.error("❌ gallery-dl 未安装或不可用")
    
    def _setup_session(self):
        """设置会话和 cookies"""
        try:
            # 设置 User-Agent
            self.session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            })
            
            # 加载 cookies
            if os.path.exists(self.cookies_path):
                logger.info(f"📄 加载 Instagram cookies: {self.cookies_path}")
                self._load_cookies()
            else:
                logger.warning(f"⚠️ Instagram cookies 文件不存在: {self.cookies_path}")
                
        except Exception as e:
            logger.error(f"❌ 设置会话失败: {e}")
    
    def _load_cookies(self):
        """加载 cookies 文件"""
        try:
            with open(self.cookies_path, 'r', encoding='utf-8') as f:
                cookies_data = f.read().strip()
            
            # 解析 cookies 格式（假设是 Netscape 格式）
            for line in cookies_data.split('\n'):
                if line.strip() and not line.startswith('#'):
                    parts = line.split('\t')
                    if len(parts) >= 7:
                        domain = parts[0]
                        flag = parts[1]
                        path = parts[2]
                        secure = parts[3]
                        expiry = parts[4]
                        name = parts[5]
                        value = parts[6]
                        
                        if domain.endswith('instagram.com'):
                            self.session.cookies.set(name, value, domain=domain, path=path)
            
            logger.info(f"✅ 成功加载 Instagram cookies")
            
        except Exception as e:
            logger.error(f"❌ 加载 cookies 失败: {e}")
    
    def is_instagram_url(self, url: str) -> bool:
        """检查是否为 Instagram URL"""
        instagram_domains = [
            'instagram.com',
            'www.instagram.com',
            'm.instagram.com',
            'web.instagram.com'
        ]
        
        try:
            parsed = urlparse(url)
            return any(domain in parsed.netloc for domain in instagram_domains)
        except:
            return False
    
    def extract_post_id(self, url: str) -> Optional[str]:
        """从 Instagram URL 中提取帖子 ID"""
        try:
            # 支持多种 Instagram URL 格式
            if '/p/' in url:
                # 帖子格式: https://www.instagram.com/p/ABC123/
                post_id = url.split('/p/')[1].split('/')[0]
            elif '/reel/' in url:
                # Reel 格式: https://www.instagram.com/reel/ABC123/
                post_id = url.split('/reel/')[1].split('/')[0]
            elif '/tv/' in url:
                # IGTV 格式: https://www.instagram.com/tv/ABC123/
                post_id = url.split('/tv/')[1].split('/')[0]
            else:
                return None
            
            return post_id
        except:
            return None
    
    async def download_post(self, url: str, download_dir: str = "./downloads", progress_callback=None) -> Dict[str, Any]:
        """
        下载 Instagram 帖子
        
        Args:
            url: Instagram 帖子 URL
            download_dir: 下载目录
            progress_callback: 进度回调函数
            
        Returns:
            下载结果字典
        """
        try:
            if not self.gallery_dl_available:
                return {
                    "success": False,
                    "error": "gallery-dl 未安装或不可用"
                }
            
            # 检查 URL 格式
            if not self.is_instagram_url(url):
                return {
                    "success": False,
                    "error": "不是有效的 Instagram URL"
                }
            
            # 提取帖子 ID
            post_id = self.extract_post_id(url)
            if not post_id:
                return {
                    "success": False,
                    "error": "无法从 URL 中提取帖子 ID"
                }
            
            logger.info(f"📱 开始下载 Instagram 帖子: {post_id}")
            
            # 创建下载目录
            os.makedirs(download_dir, exist_ok=True)
            
            # 发送开始下载消息
            if progress_callback:
                start_text = (
                    f"🚀 开始下载 Instagram 帖子\n"
                    f"📝 帖子 ID: `{post_id}`\n"
                    f"📥 正在获取媒体信息..."
                )
                await self._safe_callback(progress_callback, start_text)
            
            # 使用命令行方式调用 gallery-dl
            result = await self._download_with_gallery_dl_cmd(url, download_dir, progress_callback, post_id)
            
            if result.get("success"):
                logger.info(f"✅ Instagram 帖子下载成功: {post_id}")
                return {
                    "success": True,
                    "post_id": post_id,
                    "url": url,
                    "platform": "Instagram",
                    "content_type": "image",
                    "download_path": result.get("download_path", download_dir),
                    "files": result.get("files", []),
                    "files_count": result.get("files_count", 0),
                    "total_size": result.get("total_size", 0),
                    "file_formats": result.get("file_formats", [])
                }
            else:
                logger.error(f"❌ Instagram 帖子下载失败: {result.get('error')}")
                return result
                
        except Exception as e:
            logger.error(f"❌ 下载 Instagram 帖子失败: {e}")
            return {
                "success": False,
                "error": f"下载失败: {str(e)}"
            }
    
    async def _download_with_gallery_dl_cmd(self, url: str, download_dir: str, progress_callback=None, post_id=None) -> Dict[str, Any]:
        """使用命令行方式调用 gallery-dl 下载"""
        try:
            # 记录下载前的文件
            before_files = set()
            download_path = Path(download_dir)
            if download_path.exists():
                for file_path in download_path.rglob("*"):
                    if file_path.is_file():
                        relative_path = str(file_path.relative_to(download_path))
                        before_files.add(relative_path)
            
            logger.info(f"📊 下载前文件数量: {len(before_files)}")
            
            # 创建进度监控任务
            progress_task = None
            if progress_callback:
                progress_task = asyncio.create_task(self._monitor_progress(
                    download_path, before_files, progress_callback
                ))
            
            # 构建 gallery-dl 命令
            cmd = [
                'gallery-dl',
                '--cookies', self.cookies_path,
                '--dest', download_dir,
                '--verbose',
                url
            ]
            
            logger.info(f"📸 执行命令: {' '.join(cmd)}")
            
            # 在异步执行器中运行命令
            def run_gallery_dl():
                return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            loop = asyncio.get_running_loop()
            process = await loop.run_in_executor(None, run_gallery_dl)
            
            logger.info(f"📸 gallery-dl 命令执行完成，返回码: {process.returncode}")
            
            if process.stdout:
                logger.info(f"📸 标准输出: {process.stdout[:500]}...")
            if process.stderr:
                logger.warning(f"📸 标准错误: {process.stderr[:500]}...")
            
            # 等待文件写入完成
            await asyncio.sleep(3)
            
            # 取消进度监控任务
            if progress_task:
                progress_task.cancel()
                try:
                    await progress_task
                except asyncio.CancelledError:
                    pass
            
            # 计算下载结果
            current_files = set()
            if download_path.exists():
                for file_path in download_path.rglob("*"):
                    if file_path.is_file():
                        relative_path = str(file_path.relative_to(download_path))
                        current_files.add(relative_path)
            
            new_files = current_files - before_files
            files_count = len(new_files)
            
            if files_count == 0:
                return {
                    "success": False,
                    "error": f"没有下载到任何文件 (命令返回码: {process.returncode})"
                }
            
            # 计算总大小和文件格式
            total_size = 0
            file_formats = set()
            files_info = []
            
            for file_path in new_files:
                full_path = download_path / file_path
                if full_path.exists():
                    file_size = full_path.stat().st_size
                    total_size += file_size
                    
                    # 提取文件格式
                    ext = full_path.suffix.lower().lstrip('.')
                    if ext:
                        file_formats.add(ext.upper())
                    
                    files_info.append({
                        'path': str(full_path),
                        'size': file_size,
                        'filename': full_path.name
                    })
            
            # 发送完成消息
            if progress_callback:
                final_text = (
                    f"✅ Instagram 帖子下载完成\n"
                    f"📝 帖子 ID: `{post_id}`\n"
                    f"🖼️ 文件数量: `{files_count} 个`\n"
                    f"💾 总大小: `{total_size / (1024*1024):.2f} MB`\n"
                    f"📄 文件格式: `{', '.join(file_formats)}`"
                )
                await self._safe_callback(progress_callback, final_text)
            
            return {
                "success": True,
                "files_count": files_count,
                "total_size": total_size,
                "file_formats": list(file_formats),
                "files": files_info,
                "download_path": str(download_path)
            }
            
        except Exception as e:
            logger.error(f"❌ gallery-dl 命令执行失败: {e}")
            return {
                "success": False,
                "error": f"gallery-dl 命令执行失败: {str(e)}"
            }
    
    async def _monitor_progress(self, download_path: Path, before_files: set, progress_callback):
        """监控下载进度"""
        try:
            last_count = 0
            last_update_time = time.time()
            update_interval = 2  # 每2秒更新一次进度
            
            logger.info(f"📊 开始监控 Instagram 下载进度")
            
            while True:
                await asyncio.sleep(1)  # 每1秒检查一次
                
                # 计算当前文件数量
                current_files = set()
                if download_path.exists():
                    for file_path in download_path.rglob("*"):
                        if file_path.is_file():
                            relative_path = str(file_path.relative_to(download_path))
                            current_files.add(relative_path)
                
                # 计算新文件数量
                new_files = current_files - before_files
                current_count = len(new_files)
                
                # 如果文件数量有变化或时间间隔到了，更新进度
                if current_count != last_count or time.time() - last_update_time > update_interval:
                    last_count = current_count
                    last_update_time = time.time()
                    
                    # 获取当前正在下载的文件路径
                    current_file_path = "准备中..."
                    if new_files:
                        latest_file = sorted(new_files)[-1]
                        current_file_path = latest_file
                    
                    progress_text = (
                        f"📱 **Instagram 图片下载中**\n"
                        f"📝 当前下载：`{current_file_path}`\n"
                        f"🖼️ 已完成：{current_count} 个"
                    )
                    
                    await self._safe_callback(progress_callback, progress_text)
                    
        except asyncio.CancelledError:
            logger.info("📊 进度监控任务已取消")
        except Exception as e:
            logger.error(f"❌ 进度监控任务错误: {e}")
    
    async def _safe_callback(self, callback, text):
        """安全调用回调函数"""
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(text)
            else:
                callback(text)
        except Exception as e:
            logger.warning(f"⚠️ 回调函数调用失败: {e}")

async def main():
    """主函数 - 用于测试"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Instagram 图片下载器 - 简化版本')
    parser.add_argument('urls', nargs='*', help='要下载的 Instagram 链接')
    parser.add_argument('-d', '--dir', default='./downloads', help='下载目录')
    parser.add_argument('-c', '--cookies', default='./instagram_cookies.txt', help='Instagram Cookies 文件路径')
    
    args = parser.parse_args()
    
    downloader = InstagramPicDownloaderSimple(cookies_path=args.cookies)
    
    # 如果没有通过命令行提供URL，使用交互式输入
    urls = args.urls
    if not urls:
        print("请输入 Instagram 链接（输入 'quit' 退出）:")
        while True:
            url = input("URL: ").strip()
            if url.lower() == 'quit':
                break
            if url:
                urls.append(url)
    
    if not urls:
        print("没有提供任何链接")
        return
    
    print(f"准备下载 {len(urls)} 个 Instagram 链接到目录: {args.dir}")
    
    # 创建简单的进度回调函数
    async def progress_callback(text):
        print(f"📱 进度: {text}")
    
    success_count = 0
    for i, url in enumerate(urls, 1):
        try:
            print(f"\n[{i}/{len(urls)}] 处理链接: {url}")
            
            result = await downloader.download_post(url, args.dir, progress_callback)
            if result.get("success"):
                success_count += 1
                print(f"✅ 下载成功: {result.get('post_id', '未知帖子')}")
            else:
                print(f"❌ 下载失败: {result.get('error', '未知错误')}")
            
            time.sleep(2)  # 避免请求过快
        except Exception as e:
            print(f"处理链接失败 {url}: {e}")
    
    print(f"\n完成！成功下载 {success_count}/{len(urls)} 个链接")

if __name__ == "__main__":
    asyncio.run(main())

