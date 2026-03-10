#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
系统依赖检查脚本
检查多线程下载所需的系统依赖是否已安装
"""

import subprocess
import sys
import os


def check_aria2c():
    """检查 aria2c 是否已安装"""
    print("🔍 检查 aria2c...")
    try:
        result = subprocess.run(
            ['aria2c', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            version = result.stdout.split()[0]
            print(f"✅ aria2c 已安装：{version}")
            print(f"   位置：{subprocess.run(['which', 'aria2c'], capture_output=True, text=True).stdout.strip()}")
            return True
        else:
            print("❌ aria2c 未安装或不可用")
            return False
    except FileNotFoundError:
        print("❌ aria2c 未安装")
        return False
    except subprocess.TimeoutExpired:
        print("❌ aria2c 检查超时")
        return False


def check_python_version():
    """检查 Python 版本"""
    print("\n🔍 检查 Python 版本...")
    version = sys.version_info
    print(f"✅ Python 版本：{version.major}.{version.minor}.{version.micro}")
    
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("⚠️  警告：Python 3.8+ 推荐用于最佳性能")
        return False
    return True


def check_required_packages():
    """检查必需的 Python 包"""
    print("\n🔍 检查 Python 包...")
    
    required = {
        'yt_dlp': 'yt-dlp',
        'aiohttp': 'aiohttp',
        'asyncio': 'asyncio',
    }
    
    missing = []
    
    for package, pip_name in required.items():
        try:
            __import__(package)
            print(f"✅ {pip_name} 已安装")
        except ImportError:
            print(f"❌ {pip_name} 未安装")
            missing.append(pip_name)
    
    if missing:
        print(f"\n💡 安装缺失的包：pip install {' '.join(missing)}")
        return False
    
    return True


def check_system_resources():
    """检查系统资源"""
    print("\n🔍 检查系统资源...")
    
    # 检查 CPU 核心数
    cpu_count = os.cpu_count()
    print(f"✅ CPU 核心数：{cpu_count}")
    
    # 检查内存（粗略估计）
    try:
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                if line.startswith('MemTotal:'):
                    mem_kb = int(line.split()[1])
                    mem_gb = mem_kb / 1024 / 1024
                    print(f"✅ 物理内存：{mem_gb:.2f} GB")
                    break
    except:
        print("⚠️  无法读取内存信息")
    
    # 检查磁盘空间
    import shutil
    total, used, free = shutil.disk_usage('/')
    free_gb = free / (1024 ** 3)
    print(f"✅ 可用磁盘空间：{free_gb:.2f} GB")
    
    if free_gb < 1:
        print("⚠️  警告：磁盘空间不足 1GB")
        return False
    
    return True


def print_install_guide():
    """打印安装指南"""
    print("\n" + "="*60)
    print("📦 安装指南")
    print("="*60)
    
    print("\n1️⃣  安装 aria2c:")
    print("   Ubuntu/Debian:")
    print("   sudo apt update && sudo apt install aria2")
    print("\n   CentOS/RHEL:")
    print("   sudo yum install aria2")
    print("\n   macOS:")
    print("   brew install aria2")
    print("\n   Docker:")
    print("   RUN apt-get update && apt-get install -y aria2")
    
    print("\n2️⃣  安装 Python 依赖:")
    print("   pip install -r requirements.txt")
    
    print("\n3️⃣  配置多线程下载:")
    print("   编辑 savextube.toml，在 [multithread] 部分配置:")
    print("   mt_file_threads = 16")
    print("   mt_concurrent_files = 3")
    print("   mt_use_aria2c = true")


def main():
    """主函数"""
    print("="*60)
    print("🔍 SaveXTube 系统依赖检查")
    print("="*60)
    
    results = {
        'python': check_python_version(),
        'packages': check_required_packages(),
        'aria2c': check_aria2c(),
        'resources': check_system_resources(),
    }
    
    print("\n" + "="*60)
    print("📊 检查结果汇总")
    print("="*60)
    
    all_passed = True
    
    for check, passed in results.items():
        status = "✅" if passed else "❌"
        print(f"{status} {check}: {'通过' if passed else '未通过'}")
        if not passed:
            all_passed = False
    
    print("\n" + "="*60)
    
    if all_passed:
        print("✅ 所有检查通过！可以开始使用多线程下载")
    else:
        print("⚠️  部分检查未通过，建议修复以获得最佳性能")
        print_install_guide()
    
    print("="*60)
    
    return 0 if all_passed else 1


if __name__ == '__main__':
    sys.exit(main())
