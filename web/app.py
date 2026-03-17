# -*- coding: utf-8 -*-
"""
SaveXTube Web UI - FastAPI 应用
提供可视化管理界面和 API 接口
"""

import os
import sys
import json
import tempfile
import subprocess
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

# 添加父目录到路径（必须早于导入 modules.*）
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, Depends, status, Request, WebSocket, WebSocketDisconnect
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.websockets import WebSocketState
import uvicorn
from jose import JWTError, jwt
from passlib.context import CryptContext

from modules.config.channel_switches import (
    DEFAULT_CHANNEL_SWITCHES,
    load_channel_switches,
    save_channel_switches,
)
from modules.config.toml_config import load_toml_config, get_proxy_config
from modules.web_task_manager import task_manager, TaskStatus, get_task_manager

logger = __import__('logging').getLogger('savextube.web')

# ============ 配置 ============
SECRET_KEY = "savextube-secret-key-change-in-production-2026"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 小时

# ============ 密码加密 ============
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/token", auto_error=False)

# ============ 默认用户 ============
DEFAULT_USERS = {
    "admin": {
        "username": "admin",
        "hashed_password": pwd_context.hash("savextube"),  # 默认密码
        "disabled": False,
        "role": "admin"
    }
}

# ============ FastAPI 应用 ============
app = FastAPI(
    title="SaveXTube Web UI",
    description="SaveXTube 可视化管理界面",
    version="1.0.0"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件和模板
STATIC_DIR = Path(__file__).parent / "static"
TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.variable_start_string = "[["
templates.env.variable_end_string = "]]"

PROJECT_ROOT = Path(__file__).parent.parent

# ============ 工具函数 ============
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """密码哈希"""
    return pwd_context.hash(password)

def get_proxy_from_config():
    """从 TOML 配置文件中读取代理设置"""
    try:
        config_paths = [
            PROJECT_ROOT / "savextube.toml",
            Path("savextube.toml"),
            Path("/app/config/savextube.toml"),
        ]

        for config_path in config_paths:
            if config_path.exists():
                logger.info(f"找到配置文件: {config_path}")
                config = load_toml_config(str(config_path))
                if config:
                    proxy_config = get_proxy_config(config)
                    proxy_host = proxy_config.get("proxy_host")
                    if proxy_host:
                        logger.info(f"从 TOML 配置读取代理: {proxy_host}")
                        return proxy_host
                break
    except Exception as e:
        logger.warning(f"读取 TOML 配置失败: {e}")

    return os.getenv("PROXY_HOST")

def get_session_file_path() -> Path:
    """统一的 Telethon 会话文件路径"""
    return PROJECT_ROOT / "cookies" / "telethon_session.txt"

def _extract_json_line(output: str) -> Dict[str, Any]:
    """从子进程输出中提取 JSON 行"""
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise ValueError(f"未找到有效 JSON 输出: {output}")

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """创建 JWT Token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(request: Request, token: Optional[str] = Depends(oauth2_scheme)):
    """获取当前用户"""
    # 浏览器页面跳转通常不带 Authorization Header，回退读取 Cookie 中的 token
    access_token = token or request.cookies.get("access_token")
    
    if not access_token:
        # 未认证，重定向到登录页
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/")
    
    try:
        payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise JWTError("Invalid token")
    except JWTError:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/")
    
    user = DEFAULT_USERS.get(username)
    if user is None or user.get("disabled"):
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/")
    
    return user

# ============ 数据库引用 ============
# 复用现有的数据库和配置
def get_bot_instance():
    """获取 Bot 实例（从主程序）"""
    # 这里需要从主程序获取 bot 实例
    # 暂时返回 None，后续集成
    return None

# ============ API 路由 ============

@app.get("/")
async def root(request: Request):
    """根页面 - 检查登录状态"""
    # 检查是否有有效的 token
    access_token = request.cookies.get("access_token")

    if access_token:
        try:
            payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            if username and username in DEFAULT_USERS:
                # 已登录，重定向到仪表盘
                from fastapi.responses import RedirectResponse
                return RedirectResponse(url="/dashboard")
        except JWTError:
            pass

    # 未登录，显示登录页面
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/dashboard")
async def dashboard(request: Request, current_user: dict = Depends(get_current_user)):
    """仪表盘页面"""
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "username": current_user["username"]
    })

@app.get("/tasks")
async def tasks_page(request: Request, current_user: dict = Depends(get_current_user)):
    """下载任务页面"""
    return templates.TemplateResponse("tasks.html", {
        "request": request,
        "username": current_user["username"]
    })

@app.get("/setup")
async def setup_page(request: Request, current_user: dict = Depends(get_current_user)):
    """Setup 页面（融入当前 Web UI 布局）"""
    return templates.TemplateResponse("setup.html", {
        "request": request,
        "username": current_user["username"]
    })

@app.get("/check_session")
async def check_session(current_user: dict = Depends(get_current_user)):
    """检查会话文件是否存在"""
    session_file_path = get_session_file_path()

    if session_file_path.exists():
        try:
            content = session_file_path.read_text(encoding="utf-8").strip()
            if content and len(content) > 10:
                return {"exists": True, "message": "会话文件已存在"}
        except Exception as e:
            logger.error(f"检查会话文件失败: {e}")

    return {"exists": False, "message": "会话文件不存在"}

@app.post("/save_session")
async def save_session(payload: Dict[str, Any], current_user: dict = Depends(get_current_user)):
    """保存会话字符串到 cookies 目录"""
    session_string = (payload or {}).get("session_string", "").strip()
    if not session_string:
        raise HTTPException(status_code=400, detail="missing session_string")

    session_file_path = get_session_file_path()
    session_file_path.parent.mkdir(parents=True, exist_ok=True)
    session_file_path.write_text(session_string, encoding="utf-8")

    return {"ok": True, "saved_to": str(session_file_path), "auto_reloaded": False}

@app.post("/start_code")
async def start_code(payload: Dict[str, Any], current_user: dict = Depends(get_current_user)):
    """发送 Telegram 验证码"""
    api_id = (payload or {}).get("api_id")
    api_hash = (payload or {}).get("api_hash")
    phone = (payload or {}).get("phone")
    proxy_url = get_proxy_from_config()

    if not all([api_id, api_hash, phone]):
        raise HTTPException(status_code=400, detail="缺少必要参数")

    script_content = f'''import asyncio
import json
from telethon import TelegramClient
from telethon.sessions import StringSession
from urllib.parse import urlparse

async def send_code():
    try:
        proxy_config = None
        proxy_url = {json.dumps(proxy_url)}
        if proxy_url and str(proxy_url).strip() and str(proxy_url) != "None":
            try:
                p_url = urlparse(str(proxy_url).strip())
                if p_url.scheme and p_url.hostname and p_url.port:
                    proxy_config = (p_url.scheme, p_url.hostname, p_url.port)
                    print(f"# 使用代理: {{proxy_config}}")
            except Exception:
                proxy_config = None

        client = TelegramClient(StringSession(), {int(api_id)}, {json.dumps(str(api_hash))}, proxy=proxy_config, connection_retries=3, retry_delay=2)
        await client.connect()
        code_result = await client.send_code_request({json.dumps(str(phone))})
        session_string = client.session.save()
        await client.disconnect()
        print(json.dumps({{"ok": True, "phone_code_hash": code_result.phone_code_hash, "temp_session_string": session_string}}))
    except Exception as e:
        print(json.dumps({{"ok": False, "error": str(e)}}))

asyncio.run(send_code())
'''

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(script_content)
        script_path = f.name

    try:
        result = subprocess.run([sys.executable, script_path], capture_output=True, text=True, timeout=60)
        output = (result.stdout or "").strip()
        stderr_output = (result.stderr or "").strip()
        if result.returncode != 0:
            return JSONResponse({"ok": False, "error": stderr_output or "子进程执行失败"})

        data = _extract_json_line(output)
        if data.get("ok"):
            return {
                "ok": True,
                "message": f"验证码已发送到 {phone}，请查收 Telegram 消息",
                "phone": phone,
                "phone_code_hash": data.get("phone_code_hash"),
                "temp_session_string": data.get("temp_session_string"),
            }
        return data
    except Exception as e:
        logger.error(f"发送验证码失败: {e}")
        return JSONResponse({"ok": False, "error": str(e)})
    finally:
        try:
            os.unlink(script_path)
        except Exception:
            pass

@app.post("/confirm_code")
async def confirm_code(payload: Dict[str, Any], current_user: dict = Depends(get_current_user)):
    """确认验证码并生成 Telethon 会话"""
    data = payload or {}
    api_id = data.get("api_id")
    api_hash = data.get("api_hash")
    phone = data.get("phone")
    code = data.get("code")
    phone_code_hash = data.get("phone_code_hash")
    temp_session_string = data.get("temp_session_string", "")
    proxy_url = get_proxy_from_config()

    if not all([api_id, api_hash, phone, code, phone_code_hash]):
        raise HTTPException(status_code=400, detail="缺少必要参数，包括 phone_code_hash")

    script_content = f'''import asyncio
import json
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import PhoneCodeInvalidError, FloodWaitError
from urllib.parse import urlparse

async def confirm_code():
    try:
        proxy_config = None
        proxy_url = {json.dumps(proxy_url)}
        if proxy_url and str(proxy_url).strip() and str(proxy_url) != "None":
            try:
                p_url = urlparse(str(proxy_url).strip())
                if p_url.scheme and p_url.hostname and p_url.port:
                    proxy_config = (p_url.scheme, p_url.hostname, p_url.port)
            except Exception:
                proxy_config = None

        client = TelegramClient(StringSession({json.dumps(str(temp_session_string))}), {int(api_id)}, {json.dumps(str(api_hash))}, proxy=proxy_config)
        await client.connect()
        await client.sign_in({json.dumps(str(phone))}, {json.dumps(str(code))}, phone_code_hash={json.dumps(str(phone_code_hash))})
        session_string = client.session.save()
        await client.disconnect()
        print(json.dumps({{"ok": True, "session_string": session_string, "message": "登录成功！Telethon 会话已生成", "phone": {json.dumps(str(phone))}}}))
    except PhoneCodeInvalidError:
        print(json.dumps({"ok": False, "error": "验证码错误，请重新输入"}))
    except FloodWaitError as e:
        print(json.dumps({{"ok": False, "error": f"操作过于频繁，请等待 {{e.seconds}} 秒后重试"}}))
    except Exception as e:
        print(json.dumps({{"ok": False, "error": f"验证码确认失败: {{str(e)}}"}}))

asyncio.run(confirm_code())
'''

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(script_content)
        script_path = f.name

    try:
        result = subprocess.run([sys.executable, script_path], capture_output=True, text=True, timeout=60)
        output = (result.stdout or "").strip()
        stderr_output = (result.stderr or "").strip()
        if result.returncode != 0:
            return JSONResponse({"ok": False, "error": stderr_output or "子进程执行失败"})

        return _extract_json_line(output)
    except Exception as e:
        logger.error(f"确认验证码失败: {e}")
        return JSONResponse({"ok": False, "error": str(e)})
    finally:
        try:
            os.unlink(script_path)
        except Exception:
            pass

@app.post("/api/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """登录接口"""
    user = DEFAULT_USERS.get(form_data.username)
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"]},
        expires_delta=access_token_expires
    )

    response = JSONResponse({"access_token": access_token, "token_type": "bearer"})
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        samesite="lax",
    )
    return response

@app.get("/api/status")
async def get_status(current_user: dict = Depends(get_current_user)):
    """获取系统状态"""
    bot = get_bot_instance()
    
    return {
        "bot_status": "running" if bot else "stopped",
        "active_tasks": 0,
        "today_downloads": 0,
        "storage_used": "0 GB",
        "storage_total": "500 GB"
    }

@app.get("/api/tasks")
async def get_tasks(
    current_user: dict = Depends(get_current_user),
    status_filter: str = "all",
    limit: int = 50
):
    """获取下载任务列表"""
    if status_filter == "all":
        tasks = task_manager.get_all_tasks(limit=limit)
    elif status_filter == "active":
        tasks = task_manager.get_active_tasks()
    elif status_filter == "completed":
        tasks = task_manager.get_completed_tasks(limit=limit)
    else:
        tasks = task_manager.get_all_tasks(limit=limit)
    
    return {
        "tasks": tasks,
        "total": len(tasks),
    }

@app.get("/api/tasks/stats")
async def get_task_stats(current_user: dict = Depends(get_current_user)):
    """获取任务统计信息"""
    return task_manager.get_statistics()

@app.post("/api/tasks/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    current_user: dict = Depends(get_current_user)
):
    """取消任务"""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    task_manager.cancel_task(task_id)
    return {"success": True, "message": "任务已取消"}

@app.post("/api/tasks/{task_id}/pause")
async def pause_task(
    task_id: str,
    current_user: dict = Depends(get_current_user)
):
    """暂停任务"""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    if task.status not in (TaskStatus.DOWNLOADING, TaskStatus.QUEUED, TaskStatus.PROCESSING):
        raise HTTPException(status_code=400, detail="任务不在可暂停状态")
    
    task_manager.update_task(task_id, status=TaskStatus.PENDING)  # 暂时用 PENDING 表示暂停
    return {"success": True, "message": "任务已暂停"}

@app.post("/api/tasks/{task_id}/resume")
async def resume_task(
    task_id: str,
    current_user: dict = Depends(get_current_user)
):
    """恢复任务"""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    task_manager.update_task(task_id, status=TaskStatus.QUEUED, progress=task.progress)
    return {"success": True, "message": "任务已恢复"}

@app.post("/api/tasks/{task_id}/retry")
async def retry_task(
    task_id: str,
    current_user: dict = Depends(get_current_user)
):
    """重试任务"""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 重置任务状态
    task_manager.update_task(task_id, status=TaskStatus.QUEUED, progress=0)
    return {"success": True, "message": "任务已重新排队"}

@app.delete("/api/tasks/completed")
async def clear_completed_tasks(current_user: dict = Depends(get_current_user)):
    """清除已完成的任务"""
    completed = [
        tid for tid, t in task_manager.tasks.items()
        if t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
    ]
    for tid in completed:
        del task_manager.tasks[tid]
        if tid in task_manager.task_order:
            task_manager.task_order.remove(tid)
    return {"success": True, "cleared": len(completed)}

# ============ WebSocket 路由 ============

@app.websocket("/ws/tasks")
async def websocket_tasks(websocket: WebSocket):
    """WebSocket 连接，推送任务实时更新"""
    # 接受连接
    await websocket.accept()
    
    # 创建消息队列
    message_queue: asyncio.Queue = asyncio.Queue()
    
    # 注册到任务管理器
    await task_manager.register_websocket(message_queue)
    
    try:
        while True:
            # 等待新消息
            message = await message_queue.get()
            await websocket.send_json(message)
    except WebSocketDisconnect:
        logger.info("WebSocket 客户端断开连接")
    except Exception as e:
        logger.error(f"WebSocket 错误：{e}")
    finally:
        # 注销连接
        await task_manager.unregister_websocket(message_queue)
        if websocket.client_state != WebSocketState.DISCONNECTED:
            try:
                await websocket.close()
            except Exception:
                pass

@app.websocket("/ws/status")
async def websocket_status(websocket: WebSocket):
    """WebSocket 连接，推送系统状态"""
    await websocket.accept()
    
    message_queue: asyncio.Queue = asyncio.Queue()
    await task_manager.register_websocket(message_queue)
    
    try:
        while True:
            message = await message_queue.get()
            # 只推送统计信息
            stats = task_manager.get_statistics()
            await websocket.send_json({
                "type": "status_update",
                "data": stats,
                "timestamp": message.get("timestamp"),
            })
    except WebSocketDisconnect:
        logger.info("WebSocket 客户端断开连接")
    except Exception as e:
        logger.error(f"WebSocket 错误：{e}")
    finally:
        await task_manager.unregister_websocket(message_queue)
        if websocket.client_state != WebSocketState.DISCONNECTED:
            try:
                await websocket.close()
            except Exception:
                pass

# ============ 启动函数 ============
async def _start_background_tasks():
    """启动后台任务"""
    await task_manager.start()

def start_web_server(host: str = "0.0.0.0", port: int = 8530):
    """启动 Web 服务器"""
    logger.info(f"🌐 启动 Web UI 服务器：http://{host}:{port}")
    
    # 启动后台任务
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_start_background_tasks())
    
    uvicorn.run(app, host=host, port=port, log_level="info")

if __name__ == "__main__":
    start_web_server()
