#!/usr/bin/env python3
"""
简化的Telegram会话生成器
直接处理验证码，没有任何复杂的会话管理
"""

import os
import json
import time
import logging
import tempfile
import subprocess
from pathlib import Path
from flask import Flask, Blueprint, jsonify, request, send_from_directory

# 导入配置读取器
from modules.config.toml_config import load_toml_config, get_proxy_config

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_proxy_from_config():
    """从TOML配置文件中读取代理设置"""
    try:
        # 尝试多个可能的配置文件路径
        config_paths = [
            "savextube.toml",
            "../savextube.toml", 
            "../../savextube.toml",
            "/app/config/savextube.toml"
        ]
        
        for config_path in config_paths:
            if os.path.exists(config_path):
                logger.info(f"找到配置文件: {config_path}")
                config = load_toml_config(config_path)
                if config:
                    proxy_config = get_proxy_config(config)
                    proxy_host = proxy_config.get('proxy_host')
                    logger.info(f"调试信息 - proxy_config: {proxy_config}")
                    logger.info(f"调试信息 - proxy_host: '{proxy_host}'")
                    if proxy_host:
                        logger.info(f"从TOML配置读取代理: {proxy_host}")
                        return proxy_host
                    else:
                        logger.info(f"TOML配置中未设置代理或代理被注释")
                        return None
                break
        else:
            logger.warning("未找到TOML配置文件")
    except Exception as e:
        logger.warning(f"读取TOML配置失败: {e}")
    
    # 如果TOML配置读取失败，回退到环境变量
    return os.getenv("PROXY_HOST")

def create_blueprint(static_dir: str) -> Blueprint:
    """创建简化的蓝图"""
    bp = Blueprint("tg_setup", __name__, url_prefix="")

    @bp.get("/setup")
    def serve_setup_page():
        """提供前端页面"""
        return send_from_directory(static_dir, "setup.html")
    
    @bp.get("/<filename>")
    def serve_static_files(filename):
        """提供静态文件服务"""
        return send_from_directory(static_dir, filename)

    # 兼容前端使用 ./web/xxx 的相对路径
    @bp.get("/web/<path:filename>")
    def serve_static_files_with_web_prefix(filename):
        return send_from_directory(static_dir, filename)

    @bp.post("/start_code")
    def start_code():
        """发送验证码 - 简化版本"""
        try:
            data = request.get_json() or {}
            api_id = data.get("api_id")
            api_hash = data.get("api_hash")
            phone = data.get("phone")
            proxy_url = get_proxy_from_config()

            if not all([api_id, api_hash, phone]):
                return jsonify({"ok": False, "error": "缺少必要参数"}), 400

            logger.info(f"🔍 发送验证码到: {phone}")

            # 创建临时Python脚本
            script_content = f'''import asyncio
import json
import sys
from telethon import TelegramClient
from telethon.sessions import StringSession
from urllib.parse import urlparse

async def send_code():
    try:
        # 配置代理
        proxy_config = None
        proxy_url = "{proxy_url}"
        if proxy_url and proxy_url.strip() and proxy_url != "None":
            try:
                p_url = urlparse(proxy_url.strip())
                if p_url.scheme and p_url.hostname and p_url.port:
                    proxy_config = (p_url.scheme, p_url.hostname, p_url.port)
                    print(f"# 使用代理: {{proxy_config}}")
                else:
                    print("# 代理URL格式不正确，使用直连")
                    proxy_config = None
            except Exception as e:
                print("# 代理配置错误，使用直连")
                proxy_config = None
        else:
            print("# 未设置代理，使用直连")
        
        # 创建客户端
        client = TelegramClient(
            StringSession(),
            {int(api_id)},
            "{api_hash}",
            proxy=proxy_config,
            connection_retries=3,
            retry_delay=2
        )
        
        # 连接客户端，增加超时时间
        await client.connect()
        
        # 发送验证码
        code_result = await client.send_code_request("{phone}")
        # 保存临时会话字符串，供后续确认验证码时复用
        session_string = client.session.save()
        
        # 获取结果
        result = {{
            "ok": True,
            "phone": "{phone}",
            "api_id": {int(api_id)},
            "api_hash": "{api_hash}",
            "phone_code_hash": code_result.phone_code_hash,
            "temp_session_string": session_string
        }}
        
        # 断开连接
        await client.disconnect()
        
        # 输出JSON结果
        print(json.dumps(result))
        
    except Exception as e:
        error_result = {{
            "ok": False,
            "error": str(e)
        }}
        print(json.dumps(error_result))

# 运行
asyncio.run(send_code())
'''
            
            # 写入临时文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(script_content)
                script_path = f.name
            
            try:
                # 运行子进程
                result = subprocess.run(
                    [sys.executable, script_path],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                
                if result.returncode == 0:
                    output = result.stdout.strip()
                    stderr_output = result.stderr.strip()
                    
                    # 添加调试日志
                    logger.info(f"子进程标准输出: {output}")
                    if stderr_output:
                        logger.info(f"子进程错误输出: {stderr_output}")
                    
                    if output:
                        try:
                            # 找到JSON行（以{开头的行）
                            lines = output.split('\n')
                            json_line = None
                            for line in lines:
                                if line.strip().startswith('{'):
                                    json_line = line.strip()
                                    break
                            
                            if json_line:
                                data = json.loads(json_line)
                                if data.get("ok"):
                                    return jsonify({
                                        "ok": True,
                                        "message": f"验证码已发送到 {phone}，请查收 Telegram 消息",
                                        "phone": phone,
                                        "phone_code_hash": data.get("phone_code_hash"),  # 返回phone_code_hash
                                        "temp_session_string": data.get("temp_session_string")
                                    })
                                else:
                                    return jsonify(data)
                            else:
                                logger.error(f"未找到有效的JSON输出: {output}")
                                return jsonify({"ok": False, "error": f"子进程输出格式错误: {output}"})
                        except json.JSONDecodeError as e:
                            logger.error(f"JSON解析失败: {e}, 输出内容: {output}")
                            return jsonify({"ok": False, "error": f"子进程输出格式错误: {output}"})
                    else:
                        logger.error(f"子进程无标准输出，错误输出: {stderr_output}")
                        return jsonify({"ok": False, "error": f"子进程无输出，错误: {stderr_output}"})
                else:
                    error_msg = result.stderr.strip() or "子进程执行失败"
                    logger.error(f"子进程执行失败，返回码: {result.returncode}, 错误: {error_msg}")
                    return jsonify({"ok": False, "error": error_msg})
                    
            finally:
                # 清理临时文件
                try:
                    os.unlink(script_path)
                except:
                    pass
                        
        except Exception as e:
            logger.error(f"❌ 发送验证码失败: {e}")
            return jsonify({"ok": False, "error": str(e)})

    @bp.post("/confirm_code")
    def confirm_code():
        """确认验证码 - 简化版本"""
        try:
            data = request.get_json() or {}
            api_id = data.get("api_id")
            api_hash = data.get("api_hash")
            phone = data.get("phone")
            code = data.get("code")
            phone_code_hash = data.get("phone_code_hash")  # 添加phone_code_hash
            proxy_url = get_proxy_from_config()

            if not all([api_id, api_hash, phone, code, phone_code_hash]):
                return jsonify({"ok": False, "error": "缺少必要参数，包括phone_code_hash"}), 400

            logger.info(f"🔍 确认验证码: {phone} -> {code}")
            logger.info(f"🔍 phone_code_hash: {phone_code_hash}")

            # 创建临时Python脚本
            script_content = f'''import asyncio
import json
import sys
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import PhoneCodeInvalidError, FloodWaitError
from urllib.parse import urlparse

async def confirm_code():
    try:
        # 配置代理
        proxy_config = None
        proxy_url = "{proxy_url}"
        if proxy_url and proxy_url.strip() and proxy_url != "None":
            try:
                p_url = urlparse(proxy_url.strip())
                if p_url.scheme and p_url.hostname and p_url.port:
                    proxy_config = (p_url.scheme, p_url.hostname, p_url.port)
                    print(f"# 使用代理: {{proxy_config}}")
                else:
                    print("# 代理URL格式不正确，使用直连")
                    proxy_config = None
            except Exception as e:
                print("# 代理配置错误，使用直连")
                proxy_config = None
        else:
            print("# 未设置代理，使用直连")
        
        # 创建客户端（复用发送验证码时的同一会话）
        client = TelegramClient(
            StringSession("{data.get('temp_session_string','')}") ,
            {int(api_id)},
            "{api_hash}",
            proxy=proxy_config
        )
        
        # 连接客户端
        await client.connect()
        
        # 使用验证码登录（需要phone_code_hash）
        hash_value = {json.dumps(phone_code_hash)}
        signed_in = await client.sign_in("{phone}", "{code}", phone_code_hash=hash_value)
        
        # 获取会话字符串
        session_string = client.session.save()
        
        # 断开连接
        await client.disconnect()
        
        # 输出成功结果
        result = {{"ok": True, "session_string": session_string, "message": "登录成功！Telethon 会话已生成", "phone": "{phone}"}}
        print(json.dumps(result))
        
    except PhoneCodeInvalidError:
        error_result = {{"ok": False, "error": "验证码错误，请重新输入"}}
        print(json.dumps(error_result))
    except FloodWaitError as e:
        error_result = {{"ok": False, "error": f"操作过于频繁，请等待 {{e.seconds}} 秒后重试"}}
        print(json.dumps(error_result))
    except Exception as e:
        error_result = {{"ok": False, "error": f"验证码确认失败: {{str(e)}}"}}
        print(json.dumps(error_result))

# 运行
asyncio.run(confirm_code())
'''
            
            # 写入临时文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(script_content)
                script_path = f.name
            
            try:
                # 运行子进程
                result = subprocess.run(
                    [sys.executable, script_path],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                
                if result.returncode == 0:
                    output = result.stdout.strip()
                    stderr_output = result.stderr.strip()
                    
                    # 添加调试日志
                    logger.info(f"确认验证码子进程标准输出: {output}")
                    if stderr_output:
                        logger.info(f"确认验证码子进程错误输出: {stderr_output}")
                    
                    if output:
                        try:
                            # 找到JSON行（以{开头的行）
                            lines = output.split('\n')
                            json_line = None
                            for line in lines:
                                if line.strip().startswith('{'):
                                    json_line = line.strip()
                                    break
                            
                            if json_line:
                                data = json.loads(json_line)
                                return jsonify(data)
                            else:
                                logger.error(f"确认验证码未找到有效的JSON输出: {output}")
                                return jsonify({"ok": False, "error": f"子进程输出格式错误: {output}"})
                        except json.JSONDecodeError as e:
                            logger.error(f"确认验证码JSON解析失败: {e}, 输出内容: {output}")
                            return jsonify({"ok": False, "error": f"子进程输出格式错误: {output}"})
                    else:
                        logger.error(f"确认验证码子进程无标准输出，错误输出: {stderr_output}")
                        return jsonify({"ok": False, "error": f"子进程无输出，错误: {stderr_output}"})
                else:
                    error_msg = result.stderr.strip() or "子进程执行失败"
                    logger.error(f"确认验证码子进程执行失败，返回码: {result.returncode}, 错误: {error_msg}")
                    return jsonify({"ok": False, "error": error_msg})
                    
            finally:
                # 清理临时文件
                try:
                    os.unlink(script_path)
                except:
                    pass
                        
        except Exception as e:
            logger.error(f"❌ 确认验证码失败: {e}")
            return jsonify({"ok": False, "error": str(e)})

    @bp.post("/save_session")
    def save_session():
        """保存会话"""
        try:
            data = request.get_json() or {}
            session_string = data.get("session_string")
            
            if not session_string:
                return jsonify({"ok": False, "error": "missing session_string"}), 400

            # 硬编码session文件保存路径到/app/cookies目录
            session_dir = "/app/cookies"
            session_file_path = os.path.join(session_dir, "telethon_session.txt")
            
            # 确保目录存在
            os.makedirs(session_dir, exist_ok=True)
            
            with open(session_file_path, "w") as f:
                f.write(session_string.strip())

            return jsonify({"ok": True, "saved_to": session_file_path})
            
        except Exception as e:
            logger.error(f"❌ 保存会话失败: {e}")
            return jsonify({"ok": False, "error": str(e)})

    return bp

if __name__ == "__main__":
    app = Flask(__name__)
    
    # 注册蓝图
    static_dir = os.path.join(os.path.dirname(__file__))
    bp = create_blueprint(static_dir)
    app.register_blueprint(bp)
    
    # 单独运行时使用固定端口；被 main.py 托管时忽略
    setup_port = 8530
    app.run(host='0.0.0.0', port=setup_port, debug=False, use_reloader=False)


