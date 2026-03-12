# -*- coding: utf-8 -*-
"""
SaveXTube Web UI - FastAPI 应用
提供可视化管理界面和 API 接口
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, HTTPException, Depends, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn
from jose import JWTError, jwt
from passlib.context import CryptContext
import asyncio

from modules.config.channel_switches import (
    DEFAULT_CHANNEL_SWITCHES,
    load_channel_switches,
    save_channel_switches,
)

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

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

# ============ 工具函数 ============
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """密码哈希"""
    return pwd_context.hash(password)

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
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    # 浏览器页面跳转通常不带 Authorization Header，回退读取 Cookie 中的 token
    access_token = token or request.cookies.get("access_token")
    if not access_token:
        raise credentials_exception

    try:
        payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = DEFAULT_USERS.get(username)
    if user is None or user.get("disabled"):
        raise credentials_exception
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
    """根页面 - 重定向到登录"""
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/dashboard")
async def dashboard(request: Request, current_user: dict = Depends(get_current_user)):
    """仪表盘页面"""
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "username": current_user["username"]
    })

@app.get("/playlists")
async def playlists_page(request: Request, current_user: dict = Depends(get_current_user)):
    """歌单管理页面"""
    return templates.TemplateResponse("playlists.html", {
        "request": request,
        "username": current_user["username"]
    })

@app.get("/search")
async def search_page(request: Request, current_user: dict = Depends(get_current_user)):
    """TG 频道搜索页面"""
    return templates.TemplateResponse("search.html", {
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

@app.get("/settings")
async def settings_page(request: Request, current_user: dict = Depends(get_current_user)):
    """系统设置页面"""
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "username": current_user["username"]
    })

@app.get("/setup")
async def setup_page(request: Request, current_user: dict = Depends(get_current_user)):
    """Setup 页面"""
    return templates.TemplateResponse("setup.html", {
        "request": request,
        "username": current_user["username"]
    })

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

@app.get("/api/playlists")
async def get_playlists(current_user: dict = Depends(get_current_user)):
    """获取歌单列表"""
    # TODO: 从数据库读取
    return {
        "playlists": []
    }

@app.post("/api/playlists")
async def add_playlist(
    name: str,
    url: str,
    platform: str,
    style: str,
    current_user: dict = Depends(get_current_user)
):
    """添加歌单"""
    # TODO: 实现添加逻辑
    return {"success": True, "message": "歌单已添加"}

@app.get("/api/channels")
async def get_channels(current_user: dict = Depends(get_current_user)):
    """获取 TG 频道列表"""
    # TODO: 从配置文件读取
    return {
        "channels": []
    }

@app.post("/api/search")
async def search_music(
    keyword: str,
    current_user: dict = Depends(get_current_user)
):
    """搜索音乐"""
    # TODO: 实现 TG 频道搜索
    return {
        "results": []
    }

@app.get("/api/tasks")
async def get_tasks(current_user: dict = Depends(get_current_user)):
    """获取下载任务列表"""
    # TODO: 从数据库读取
    return {
        "tasks": []
    }

@app.get("/api/settings")
async def get_settings(current_user: dict = Depends(get_current_user)):
    """获取系统设置"""
    channel_switches = load_channel_switches()
    return {
        "storage_path": "/vol2/1000/media/music",
        "quality": "lossless",
        "notify": True,
        "channel_switches": channel_switches,
    }

@app.post("/api/settings")
async def update_settings(
    settings: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
):
    """更新系统设置"""
    try:
        raw_switches = settings.get("channel_switches")
        if isinstance(raw_switches, dict):
            save_channel_switches(raw_switches)
        return {
            "success": True,
            "channel_switches": load_channel_switches(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存设置失败: {e}")

# ============ 启动函数 ============
def start_web_server(host: str = "0.0.0.0", port: int = 8530):
    """启动 Web 服务器"""
    logger.info(f"🌐 启动 Web UI 服务器：http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")

if __name__ == "__main__":
    start_web_server()
