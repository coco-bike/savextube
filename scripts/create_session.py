from telethon import TelegramClient
from telethon.sessions import StringSession
import os
import asyncio
from telethon.errors import FloodWaitError
import logging

# 配置日志
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def main():
    # 获取环境变量
    api_id = os.getenv('TELEGRAM_BOT_API_ID')
    api_hash = os.getenv('TELEGRAM_BOT_API_HASH')
    proxy = os.getenv('PROXY_URL')  # 例如: socks5://127.0.0.1:7890
    
    if not api_id or not api_hash:
        print("请设置环境变量：")
        print("export TELEGRAM_BOT_API_ID='你的API_ID'")
        print("export TELEGRAM_BOT_API_HASH='你的API_HASH'")
        return
    
    print(f"API ID: {api_id}")
    print("正在连接 Telegram 服务器...")
    
    # 代理配置
    proxy_dict = None
    if proxy:
        if proxy.startswith('socks5://'):
            from telethon import connection
            proxy_dict = {
                'proxy_type': 'socks5',
                'addr': proxy.split('://')[1].split(':')[0],
                'port': int(proxy.split(':')[-1]),
                'rdns': True
            }
            print(f"使用代理: {proxy}")
    
    # 创建客户端
    client = TelegramClient(
        StringSession(), 
        api_id, 
        api_hash,
        proxy=proxy_dict,
        connection_retries=None,  # 无限重试
        retry_delay=1  # 重试间隔1秒
    )
    
    try:
        print("正在启动客户端...")
        await client.connect()
        
        if not await client.is_user_authorized():
            print("\n需要登录，请按提示操作...")
            phone = input("请输入你的手机号 (格式如: +8613812345678): ")
            try:
                code = await client.send_code_request(phone)
                print("\n验证码已发送到你的 Telegram，请查收")
                signed_in = await client.sign_in(phone, input('请输入验证码: '))
            except FloodWaitError as e:
                print(f'发送验证码太频繁，请等待 {e.seconds} 秒后重试')
                return
            
        # 获取 session string
        session_string = client.session.save()
        print("\n登录成功！\n")
        print("你的 session string (请保存):")
        print("=" * 50)
        print(session_string)
        print("=" * 50)
        print("\n请将此字符串设置为环境变量 TELEGRAM_SESSION_STRING")
        
    except Exception as e:
        print(f"发生错误: {str(e)}")
        logger.error(f"详细错误: ", exc_info=True)
    finally:
        print("\n正在断开连接...")
        await client.disconnect()
        print("已完成")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n用户中断操作")
    except Exception as e:
        print(f"程序异常: {str(e)}")
