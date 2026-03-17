# -*- coding: utf-8 -*-
"""
Flask Web UI 路由
提供登录、仪表盘、任务、设置等页面
简化版 - 使用简单 session，不使用 JWT
"""

import os
import json
import logging
import hashlib
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request, send_from_directory, make_response, redirect, url_for, session
from pathlib import Path

logger = logging.getLogger(__name__)

# ============ 配置 ============
SECRET_KEY = "savextube-secret-2026"
SESSION_EXPIRE_MINUTES = 60 * 24  # 24 小时

# ============ 默认用户 ============
DEFAULT_USERS = {
    "admin": {
        "username": "admin",
        "password": "savextube",  # 简单明文密码
        "disabled": False,
        "role": "admin"
    }
}

# ============ 简单 Session 存储 ============
# 内存存储 session：{session_id: {"username": xxx, "expires": xxx}}
_sessions = {}


def generate_session_id(username: str) -> str:
    """生成 session ID"""
    timestamp = datetime.now().isoformat()
    data = f"{username}:{timestamp}:{SECRET_KEY}"
    return hashlib.sha256(data.encode()).hexdigest()


def create_session(username: str) -> str:
    """创建 session"""
    session_id = generate_session_id(username)
    expires = datetime.now() + timedelta(minutes=SESSION_EXPIRE_MINUTES)
    _sessions[session_id] = {
        "username": username,
        "expires": expires.isoformat()
    }
    logger.info(f"✅ 创建 session: {username}")
    return session_id


def get_session(session_id: str) -> dict:
    """获取 session 信息"""
    if not session_id or session_id not in _sessions:
        return None
    
    session_data = _sessions[session_id]
    expires = datetime.fromisoformat(session_data["expires"])
    
    # 检查是否过期
    if datetime.now() > expires:
        del _sessions[session_id]
        return None
    
    return session_data


def remove_session(session_id: str):
    """删除 session"""
    if session_id in _sessions:
        del _sessions[session_id]


def verify_password(plain_password: str, stored_password: str) -> bool:
    """验证密码（简单比较）"""
    return plain_password == stored_password


def get_current_user(session_id: str):
    """获取当前用户"""
    session_data = get_session(session_id)
    if not session_data:
        return None
    
    username = session_data.get("username")
    if username and username in DEFAULT_USERS:
        return DEFAULT_USERS[username]
    return None


def create_web_ui_blueprint(static_dir: str = None):
    """创建 Web UI 蓝图"""
    if static_dir is None:
        static_dir = os.path.join(os.path.dirname(__file__), "templates")

    bp = Blueprint("web_ui", __name__, static_folder=static_dir, static_url_path="")

    @bp.route("/")
    def root():
        """根页面 - 检查登录状态"""
        session_id = request.cookies.get("session_id")
        user = get_current_user(session_id)

        if user:
            return redirect(url_for("web_ui.dashboard"))

        return send_from_directory(static_dir, "login.html")

    @bp.route("/dashboard")
    def dashboard():
        """仪表盘页面"""
        session_id = request.cookies.get("session_id")
        user = get_current_user(session_id)

        if not user:
            return redirect(url_for("web_ui.root"))

        return send_from_directory(static_dir, "dashboard.html")

    @bp.route("/tasks")
    def tasks_page():
        """下载任务页面"""
        session_id = request.cookies.get("session_id")
        user = get_current_user(session_id)

        if not user:
            return redirect(url_for("web_ui.root"))

        return send_from_directory(static_dir, "tasks.html")

    @bp.route("/api/login", methods=["POST"])
    def login():
        """登录接口"""
        try:
            data = request.get_json() or {}
            username = data.get("username")
            password = data.get("password")

            logger.info(f"🔐 收到登录请求：用户名={username}")

            if not username or not password:
                logger.warning("用户名或密码为空")
                return jsonify({"success": False, "message": "用户名或密码不能为空"}), 400

            user = DEFAULT_USERS.get(username)
            if not user:
                logger.warning(f"用户不存在：{username}")
                return jsonify({"success": False, "message": "用户名或密码错误"}), 401

            # 验证密码（简单比较）
            if password != user["password"]:
                logger.warning(f"密码错误：{username}")
                return jsonify({"success": False, "message": "用户名或密码错误"}), 401

            # 创建 session
            session_id = create_session(username)

            response = make_response(jsonify({
                "success": True,
                "message": "登录成功",
                "username": username
            }))
            response.set_cookie(
                key="session_id",
                value=session_id,
                max_age=int(SESSION_EXPIRE_MINUTES * 60),
                httponly=True,
                samesite="lax",
            )
            logger.info(f"✅ 登录成功：{username}")
            return response

        except Exception as e:
            logger.error(f"❌ 登录接口异常：{e}")
            return jsonify({"success": False, "message": f"服务器错误：{str(e)}"}), 500

    @bp.route("/api/logout", methods=["POST"])
    def logout():
        """登出接口"""
        session_id = request.cookies.get("session_id")
        if session_id:
            remove_session(session_id)

        response = make_response(jsonify({"success": True, "message": "已退出"}))
        response.set_cookie(
            key="session_id",
            value="",
            expires=0,
        )
        return response

    @bp.route("/api/status")
    def get_status():
        """获取系统状态"""
        # 不需要登录也可以访问，用于检查配置状态
        session_id = request.cookies.get("session_id")
        user = get_current_user(session_id)

        # 检查 bot 是否已配置（通过检查环境变量或配置文件）
        # 这里简单判断：如果有 session 说明已登录，bot 可能已配置
        bot_configured = user is not None
        
        return jsonify({
            "success": True,
            "username": user["username"] if user else "guest",
            "bot_status": "running" if bot_configured else "stopped",
            "active_tasks": 0,
            "today_downloads": 0,
        })

    # ============ 任务管理 API ============

    @bp.route("/api/tasks", methods=["GET"])
    def get_tasks():
        """获取任务列表"""
        session_id = request.cookies.get("session_id")
        user = get_current_user(session_id)

        if not user:
            return jsonify({"success": False, "message": "未登录"}), 401

        # 返回空任务列表（实际使用时需要从数据库或任务管理器读取）
        status_filter = request.args.get("status_filter", "all")
        limit = request.args.get("limit", "50")
        
        logger.info(f"📋 获取任务列表：filter={status_filter}, limit={limit}")
        
        return jsonify({
            "success": True,
            "tasks": [],  # 空任务列表
            "total": 0
        })

    @bp.route("/api/tasks/<task_id>/cancel", methods=["POST"])
    def cancel_task(task_id):
        """取消任务"""
        session_id = request.cookies.get("session_id")
        user = get_current_user(session_id)

        if not user:
            return jsonify({"success": False, "message": "未登录"}), 401

        logger.info(f"🚫 取消任务：{task_id}")
        
        return jsonify({
            "success": True,
            "message": "任务已取消"
        })

    @bp.route("/api/tasks/<task_id>/pause", methods=["POST"])
    def pause_task(task_id):
        """暂停任务"""
        session_id = request.cookies.get("session_id")
        user = get_current_user(session_id)

        if not user:
            return jsonify({"success": False, "message": "未登录"}), 401

        logger.info(f"⏸️ 暂停任务：{task_id}")
        
        return jsonify({
            "success": True,
            "message": "任务已暂停"
        })

    @bp.route("/api/tasks/<task_id>/resume", methods=["POST"])
    def resume_task(task_id):
        """恢复任务"""
        session_id = request.cookies.get("session_id")
        user = get_current_user(session_id)

        if not user:
            return jsonify({"success": False, "message": "未登录"}), 401

        logger.info(f"▶️ 恢复任务：{task_id}")
        
        return jsonify({
            "success": True,
            "message": "任务已恢复"
        })

    @bp.route("/api/tasks/<task_id>/retry", methods=["POST"])
    def retry_task(task_id):
        """重试任务"""
        session_id = request.cookies.get("session_id")
        user = get_current_user(session_id)

        if not user:
            return jsonify({"success": False, "message": "未登录"}), 401

        logger.info(f"🔄 重试任务：{task_id}")
        
        return jsonify({
            "success": True,
            "message": "任务已重新排队"
        })

    @bp.route("/api/tasks/completed", methods=["DELETE"])
    def clear_completed_tasks():
        """清除已完成的任务"""
        session_id = request.cookies.get("session_id")
        user = get_current_user(session_id)

        if not user:
            return jsonify({"success": False, "message": "未登录"}), 401

        logger.info("🧹 清除已完成任务")
        
        return jsonify({
            "success": True,
            "cleared": 0
        })

    return bp


if __name__ == "__main__":
    # 测试运行
    from flask import Flask
    app = Flask(__name__)
    
    static_dir = os.path.join(os.path.dirname(__file__), "templates")
    bp = create_web_ui_blueprint(static_dir)
    app.register_blueprint(bp)
    
    app.run(host="0.0.0.0", port=8531, debug=True)
