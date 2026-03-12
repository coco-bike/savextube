#!/usr/bin/env python3
"""
模块功能测试脚本
测试 URL 提取、批量下载等核心功能
"""

import sys
import re
import os

# 添加项目根目录到 Python 路径（脚本已迁移到 test/）
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
sys.path.insert(0, PROJECT_ROOT)

def test_url_extractor():
    """测试 URL 提取功能"""
    print("="*60)
    print("🧪 测试 1: URL 提取功能")
    print("="*60)
    
    from modules.url_extractor import URLExtractor
    
    # 测试文本
    test_text = """
    这里有几个链接：
    1. https://youtube.com/watch?v=abc123
    2. https://bilibili.com/video/BV123
    3. magnet:?xt=urn:btih:1234567890abcdef1234567890abcdef12345678
    4. https://music.163.com/#/song?id=123456
    """
    
    urls = URLExtractor.extract_all_urls(test_text)
    
    print(f"输入文本：{test_text[:100]}...")
    print(f"提取到 {len(urls)} 个链接:")
    for i, url in enumerate(urls, 1):
        print(f"  {i}. {url}")
    
    # 验证
    assert len(urls) >= 3, "应该至少提取到 3 个链接"
    assert any('youtube.com' in u for u in urls), "应该包含 YouTube 链接"
    assert any('bilibili.com' in u for u in urls), "应该包含 B 站链接"
    assert any('magnet:' in u for u in urls), "应该包含磁力链接"
    
    print("✅ URL 提取测试通过\n")
    return True

def test_url_types():
    """测试 URL 类型识别"""
    print("="*60)
    print("🧪 测试 2: URL 类型识别")
    print("="*60)
    
    from modules.url_extractor import URLExtractor
    
    test_cases = [
        ("https://youtube.com/watch?v=abc", "YouTube", URLExtractor.is_youtube_url),
        ("https://bilibili.com/video/BV123", "B 站", URLExtractor.is_bilibili_url),
        ("https://music.163.com/song?id=123", "音乐", URLExtractor.is_music_url),
    ]
    
    for url, expected, func in test_cases:
        result = func(url)
        status = "✅" if result else "❌"
        print(f"{status} {expected} URL 识别：{url[:50]}... -> {result}")
        assert result == True, f"应该识别为{expected}URL"
    
    print("✅ URL 类型识别测试通过\n")
    return True

def test_batch_downloader_init():
    """测试批量下载器初始化"""
    print("="*60)
    print("🧪 测试 3: 批量下载器初始化")
    print("="*60)
    
    try:
        from modules.batch_downloader import BatchDownloadProcessor
        
        # 模拟下载器
        class MockDownloader:
            def get_yt_dlp_options(self, opts):
                return opts
        
        mock = MockDownloader()
        processor = BatchDownloadProcessor(mock, max_concurrent=3)
        
        print(f"✅ 批量下载器初始化成功")
        print(f"   最大并发数：{processor.max_concurrent}")
        print(f"   信号量：{processor.semaphore}")
        
        assert processor.max_concurrent == 3, "最大并发数应为 3"
        
        print("✅ 批量下载器初始化测试通过\n")
        return True
        
    except Exception as e:
        print(f"❌ 批量下载器初始化失败：{e}")
        return False

def test_file_utils():
    """测试文件工具"""
    print("="*60)
    print("🧪 测试 4: 文件工具")
    print("="*60)
    
    from modules.utils.file_utils import (
        clean_filename,
        format_file_size,
        format_speed,
        create_progress_bar
    )
    
    # 测试文件名清理
    dirty_name = 'Test<Video>: "Best" Movie?.mkv'
    clean = clean_filename(dirty_name)
    print(f"文件名清理：{dirty_name} -> {clean}")
    assert '<' not in clean and '>' not in clean, "应移除非法字符"
    
    # 测试文件大小格式化
    size = 1234567890
    formatted = format_file_size(size)
    print(f"文件大小：{size} bytes -> {formatted}")
    assert 'GB' in formatted or 'MB' in formatted, "应格式化为 MB 或 GB"
    
    # 测试速度格式化
    speed = 1024000
    formatted_speed = format_speed(speed)
    print(f"速度：{speed} B/s -> {formatted_speed}")
    
    # 测试进度条
    bar = create_progress_bar(50, length=20)
    print(f"进度条：50% -> {bar}")
    assert len(bar) == 20, "进度条长度应为 20"
    assert '█' in bar and '░' in bar, "进度条应包含填充和空白"
    
    print("✅ 文件工具测试通过\n")
    return True

def test_main_imports():
    """测试 main.py 导入"""
    print("="*60)
    print("🧪 测试 5: main.py 模块导入")
    print("="*60)
    
    try:
        # 测试模块导入（不导入 telegram 依赖）
        from modules.url_extractor import URLExtractor
        from modules.batch_downloader import BatchDownloadProcessor
        
        print("✅ 核心模块导入成功")
        
        # 验证模块可用
        assert hasattr(URLExtractor, 'extract_all_urls'), "URLExtractor 应有 extract_all_urls 方法"
        assert hasattr(BatchDownloadProcessor, 'download_batch'), "BatchDownloadProcessor 应有 download_batch 方法"
        
        print("✅ main.py 模块导入测试通过\n")
        return True
        
    except Exception as e:
        print(f"❌ main.py 模块导入失败：{e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("\n" + "="*60)
    print("🚀 SaveXTube 模块化功能测试")
    print("="*60 + "\n")
    
    tests = [
        ("URL 提取功能", test_url_extractor),
        ("URL 类型识别", test_url_types),
        ("批量下载器初始化", test_batch_downloader_init),
        ("文件工具", test_file_utils),
        ("main.py 模块导入", test_main_imports),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ 测试 '{name}' 异常：{e}\n")
            results.append((name, False))
    
    # 汇总结果
    print("="*60)
    print("📊 测试结果汇总")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status} - {name}")
    
    print("\n" + "="*60)
    print(f"总计：{passed}/{total} 个测试通过")
    print("="*60)
    
    if passed == total:
        print("\n🎉 所有测试通过！模块化功能已就绪")
        return 0
    else:
        print(f"\n⚠️  {total - passed} 个测试失败")
        return 1

if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
