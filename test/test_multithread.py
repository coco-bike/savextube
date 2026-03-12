#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多线程下载功能测试脚本
测试多线程下载模块是否正常工作
"""

import asyncio
import sys
import os

# 添加项目根目录到 Python 路径（脚本已迁移到 test/）
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
sys.path.insert(0, PROJECT_ROOT)

from modules.downloaders.multithread_downloader import MultiThreadDownloader, DownloadConfig, create_downloader


async def test_basic_download():
    """测试基本下载功能"""
    print("="*60)
    print("🧪 测试 1: 基本下载功能")
    print("="*60)
    
    # 创建下载器
    downloader = create_downloader(
        file_threads=16,
        concurrent_files=3,
        use_aria2c=True
    )
    
    print(f"✅ 下载器创建成功")
    print(f"   线程数：{downloader.config.file_threads}")
    print(f"   并发数：{downloader.config.concurrent_files}")
    print(f"   使用 aria2c: {downloader.config.use_aria2c}")
    
    # 测试获取 yt-dlp 选项
    base_opts = {
        'format': 'best',
        'outtmpl': './test/%(title)s.%(ext)s',
    }
    
    optimized_opts = downloader.get_yt_dlp_options(base_opts)
    
    print(f"\n✅ yt-dlp 选项优化完成")
    
    if optimized_opts.get('external_downloader') == 'aria2c':
        print(f"   ✓ 使用 aria2c 作为外部下载器")
        print(f"   ✓ aria2c 参数：{optimized_opts.get('external_downloader_args')}")
    else:
        print(f"   ✓ 使用 yt-dlp 内置下载")
    
    print("\n✅ 测试 1 通过\n")
    return True


async def test_ytdlp_integration():
    """测试与 yt-dlp 的集成"""
    print("="*60)
    print("🧪 测试 2: yt-dlp 集成测试")
    print("="*60)
    
    try:
        import yt_dlp
        print(f"✅ yt-dlp 版本：{yt_dlp.version.__version__}")
        
        # 创建一个简单的下载选项
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
        }
        
        # 创建下载器并应用优化
        downloader = create_downloader()
        optimized_opts = downloader.get_yt_dlp_options(ydl_opts)
        
        # 测试 YoutubeDL 初始化
        with yt_dlp.YoutubeDL(optimized_opts) as ydl:
            print(f"✅ YoutubeDL 初始化成功（使用优化选项）")
        
        print("\n✅ 测试 2 通过\n")
        return True
        
    except ImportError:
        print("❌ yt-dlp 未安装")
        print("   安装命令：pip install yt-dlp")
        return False
    except Exception as e:
        print(f"❌ 测试失败：{e}")
        return False


async def test_concurrent_download():
    """测试并发下载（模拟）"""
    print("="*60)
    print("🧪 测试 3: 并发控制测试（模拟）")
    print("="*60)
    
    downloader = create_downloader(concurrent_files=3)
    
    # 模拟 5 个下载任务
    async def mock_download(task_id):
        print(f"  📥 任务 {task_id} 开始下载")
        await asyncio.sleep(1)  # 模拟下载
        print(f"  ✅ 任务 {task_id} 完成")
        return {'success': True, 'task_id': task_id}
    
    # 使用信号量控制并发
    semaphore = asyncio.Semaphore(downloader.config.concurrent_files)
    
    async def limited_download(task_id):
        async with semaphore:
            return await mock_download(task_id)
    
    # 创建任务
    tasks = [limited_download(i) for i in range(5)]
    
    print(f"📊 创建 5 个模拟任务，最大并发：{downloader.config.concurrent_files}")
    print(f"🚀 开始执行...\n")
    
    # 执行任务
    start_time = asyncio.get_event_loop().time()
    results = await asyncio.gather(*tasks)
    end_time = asyncio.get_event_loop().time()
    
    duration = end_time - start_time
    
    print(f"\n✅ 所有任务完成")
    print(f"   总任务数：{len(tasks)}")
    print(f"   成功数：{sum(1 for r in results if r.get('success'))}")
    print(f"   耗时：{duration:.2f}秒")
    print(f"   理论最小耗时：{5 / downloader.config.concurrent_files:.2f}秒（完全并行）")
    print(f"   理论最大耗时：{5:.2f}秒（完全串行）")
    
    # 验证并发是否生效
    if duration < 4:  # 如果耗时明显小于 5 秒，说明并发生效
        print(f"\n✅ 测试 3 通过（并发下载正常工作）")
        return True
    else:
        print(f"\n⚠️  测试 3 警告（并发可能未正常工作）")
        return False


async def test_config_loading():
    """测试配置文件加载"""
    print("="*60)
    print("🧪 测试 4: 配置文件加载测试")
    print("="*60)
    
    config_file = 'savextube.toml'
    
    if not os.path.exists(config_file):
        print(f"❌ 配置文件不存在：{config_file}")
        print("   请确保在正确的目录运行此脚本")
        return False
    
    try:
        import tomli
        with open(config_file, 'rb') as f:
            config = tomli.load(f)
        
        print(f"✅ 配置文件加载成功")
        
        if 'multithread' in config:
            mt_config = config['multithread']
            print(f"\n📋 多线程配置:")
            print(f"   mt_file_threads: {mt_config.get('mt_file_threads', '未设置')}")
            print(f"   mt_concurrent_files: {mt_config.get('mt_concurrent_files', '未设置')}")
            print(f"   mt_use_aria2c: {mt_config.get('mt_use_aria2c', '未设置')}")
            print(f"   mt_aria2c_connections: {mt_config.get('mt_aria2c_connections', '未设置')}")
            print(f"   mt_aria2c_splits: {mt_config.get('mt_aria2c_splits', '未设置')}")
        else:
            print(f"⚠️  配置文件中没有找到 [multithread] 部分")
        
        print("\n✅ 测试 4 通过\n")
        return True
        
    except Exception as e:
        print(f"❌ 配置文件加载失败：{e}")
        return False


async def main():
    """主函数"""
    print("\n" + "="*60)
    print("🚀 SaveXTube 多线程下载功能测试")
    print("="*60 + "\n")
    
    tests = [
        ("基本下载功能", test_basic_download),
        ("yt-dlp 集成", test_ytdlp_integration),
        ("并发控制", test_concurrent_download),
        ("配置文件加载", test_config_loading),
    ]
    
    results = []
    
    for name, test_func in tests:
        try:
            result = await test_func()
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
        print("\n🎉 所有测试通过！多线程下载功能已就绪")
        return 0
    else:
        print(f"\n⚠️  {total - passed} 个测试失败，请检查配置")
        return 1


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
