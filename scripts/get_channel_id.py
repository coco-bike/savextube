#!/usr/bin/env python3
"""
获取 Telegram 频道 ID 的脚本
使用方法：
1. 安装依赖：pip install telethon
2. 运行脚本：python3 get_channel_id.py
3. 按提示输入 API 凭证
4. 转发一条频道消息给机器人，或输入频道用户名
"""

import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

# API 凭证（从 https://my.telegram.org 获取）
API_ID = 32838714  # 使用项目的 API ID
API_HASH = "1eadd0ce914f1deb3bf5d794f065133d"  # 使用项目的 API Hash

async def get_channel_id():
    """获取频道 ID"""
    
    print("=" * 50)
    print("Telegram 频道 ID 获取工具")
    print("=" * 50)
    print()
    
    # 创建客户端
    client = TelegramClient('get_channel_id_session', API_ID, API_HASH)
    
    await client.start()
    print("✅ 客户端已启动")
    print()
    
    # 获取当前用户信息
    me = await client.get_me()
    print(f"👤 当前登录账号：{me.first_name} (@{me.username or '无用户名'})")
    print()
    
    # 方法 1：通过用户名获取
    print("请选择获取方式：")
    print("1. 通过频道用户名获取（推荐）")
    print("2. 通过转发消息获取")
    print()
    
    choice = input("请输入选择 (1/2): ").strip()
    
    if choice == "1":
        # 通过用户名获取
        username = input("请输入频道用户名（例如 @lossless_music）: ").strip()
        
        # 去除 @ 符号
        if username.startswith('@'):
            username = username[1:]
        
        try:
            # 获取频道实体
            entity = await client.get_entity(username)
            
            print()
            print("=" * 50)
            print("✅ 获取成功！")
            print("=" * 50)
            print(f"频道名称：{entity.title}")
            print(f"频道用户名：@{username}")
            print(f"频道 ID: {entity.id}")
            print(f"完整 ID: -100{abs(entity.id)} (如果是超级群组)")
            print()
            
            # 判断类型
            from telethon.tl.types import Channel, Chat, User
            
            if isinstance(entity, Channel):
                if entity.broadcast:
                    print("📢 类型：频道 (Channel)")
                elif entity.megagroup:
                    print("👥 类型：超级群组 (Supergroup)")
                else:
                    print("📢 类型：频道")
            elif isinstance(entity, Chat):
                print("👥 类型：群组 (Chat)")
            
            print()
            print("📝 配置文件格式:")
            print(f"""
[[channels]]
name = "{entity.title}"
username = "@{username}"
chat_id = "{entity.id}"
enabled = true
priority = 1
""")
            
        except Exception as e:
            print(f"❌ 获取失败：{e}")
            print("可能原因：")
            print("  - 频道用户名错误")
            print("  - 频道是私有的，需要先加入")
            print("  - API 凭证无效")
    
    elif choice == "2":
        print()
        print("请转发一条频道消息给这个机器人（或发送给我）")
        print("按 Enter 键继续...")
        input()
        
        # 获取最近的对话
        async for dialog in client.iter_dialogs(limit=10):
            print(f"- {dialog.name} ({dialog.id})")
        
        print()
        print("提示：转发消息后，查看消息的 chat_id 即可")
    
    else:
        print("❌ 无效选择")
    
    await client.disconnect()
    print()
    print("👋 已断开连接")


if __name__ == '__main__':
    try:
        asyncio.run(get_channel_id())
    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断")
    except Exception as e:
        print(f"\n❌ 错误：{e}")
        print("\n请确保：")
        print("1. 已安装 telethon: pip install telethon")
        print("2. API 凭证正确")
        print("3. 网络连接正常")
