# -*- coding: utf-8 -*-
"""
Flask Web UI 路由。
提供登录、任务页和基础任务 API。
"""

import os
import asyncio
import logging
import hashlib
import threading
from datetime import datetime, timedelta
from flask import (
    Blueprint,
    jsonify,
    request,
    send_from_directory,
    make_response,
    redirect,
    url_for,
)

from modules.web_task_manager import get_task_manager
from modules.task_persistence import get_persistence_manager, TaskPersistStatus

logger = logging.getLogger(__name__)

# ============ 配置 ============
SECRET_KEY = "savextube-secret-2026"
SESSION_EXPIRE_MINUTES = 60 * 24  # 24 小时

# ============ 默认用户 ============
DEFAULT_USERS = {
    "admin": {
        "username": "admin",
        "password": "savextube",
        "disabled": False,
        "role": "admin",
    }
}

# ============ 简单 Session 存储 ============
_sessions = {}


def generate_session_id(username: str) -> str:
    """生成 session ID。"""
    timestamp = datetime.now().isoformat()
    data = f"{username}:{timestamp}:{SECRET_KEY}"
    return hashlib.sha256(data.encode()).hexdigest()


def create_session(username: str) -> str:
    """创建 session。"""
    session_id = generate_session_id(username)
    expires = datetime.now() + timedelta(minutes=SESSION_EXPIRE_MINUTES)
    _sessions[session_id] = {"username": username, "expires": expires.isoformat()}
    logger.info("创建 session: %s", username)
    return session_id


def get_session(session_id: str) -> dict | None:
    """获取 session 信息。"""
    if not session_id or session_id not in _sessions:
        return None

    session_data = _sessions[session_id]
    expires = datetime.fromisoformat(session_data["expires"])
    if datetime.now() > expires:
        del _sessions[session_id]
        return None

    return session_data


def remove_session(session_id: str):
    """删除 session。"""
    if session_id in _sessions:
        del _sessions[session_id]


def get_current_user(session_id: str):
    """获取当前用户。"""
    session_data = get_session(session_id)
    if not session_data:
        return None

    username = session_data.get("username")
    if username and username in DEFAULT_USERS:
        return DEFAULT_USERS[username]
    return None


def _run_async(coro):
    """在 Flask 同步路由里执行异步持久化方法。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result_holder = {"value": None, "error": None}

    def _runner():
        try:
            result_holder["value"] = asyncio.run(coro)
        except Exception as e:  # pragma: no cover
            result_holder["error"] = e

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    t.join()

    if result_holder["error"] is not None:
        raise result_holder["error"]

    return result_holder["value"]


def _parse_iso_time(value: str | None) -> datetime | None:
    """解析 ISO 时间字符串。"""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _format_duration_seconds(seconds: float) -> str:
    """将秒数格式化为友好文本。"""
    if seconds < 0:
        seconds = 0
    if seconds < 60:
        return f"{seconds:.1f}s"
    if seconds < 3600:
        minutes = int(seconds // 60)
        sec = int(seconds % 60)
        return f"{minutes}m {sec}s"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    return f"{hours}h {minutes}m"


def _task_to_web_dict(task) -> dict:
    """将 PersistedTask 转换为前端任务结构。"""
    context = task.context or {}
    kind = context.get("kind", "single")
    created_dt = _parse_iso_time(task.created_at)
    updated_dt = _parse_iso_time(task.updated_at)
    completed_dt = _parse_iso_time(task.completed_at)

    start_dt = created_dt or updated_dt or datetime.now()
    end_dt = completed_dt or updated_dt or datetime.now()
    duration_text = _format_duration_seconds((end_dt - start_dt).total_seconds())

    return {
        "id": task.task_id,
        "title": task.title or task.url or task.task_id,
        "url": task.url,
        "type": "single" if kind in ("url", "media") else str(kind),
        "status": task.status.value,
        "progress": float(task.progress or 0),
        "progress_percent": float(task.progress or 0),
        "downloaded_bytes": int(task.downloaded_bytes or 0),
        "total_bytes": int(task.total_bytes or 0),
        "speed": 0,
        "eta": 0,
        "filename": context.get("file_name", ""),
        "error": task.error_message or "",
        "source": task.source or "telegram",
        "channel": str(task.chat_id) if task.chat_id is not None else "-",
        "message_id": task.message_id,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "created_at_text": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_text": duration_text,
        "speed_text": "-",
        "eta_text": "-",
        "extra": {
            "retry_count": int(task.retry_count or 0),
            "max_retries": int(task.max_retries or 0),
        },
    }


def create_web_ui_blueprint(static_dir: str = None):
    """创建 Web UI 蓝图。"""
    if static_dir is None:
        static_dir = os.path.join(os.path.dirname(__file__), "templates")

    bp = Blueprint("web_ui", __name__, static_folder=static_dir, static_url_path="")
    task_manager = get_task_manager()
    persistence = get_persistence_manager()

    @bp.route("/")
    def root():
        session_id = request.cookies.get("session_id")
        user = get_current_user(session_id)

        if user:
            return redirect(url_for("web_ui.tasks_page"))

        return send_from_directory(static_dir, "login.html")

    @bp.route("/tasks")
    def tasks_page():
        session_id = request.cookies.get("session_id")
        user = get_current_user(session_id)

        if not user:
            return redirect(url_for("web_ui.root"))

        return send_from_directory(static_dir, "tasks.html")

    @bp.route("/setup")
    def setup_page():
        session_id = request.cookies.get("session_id")
        user = get_current_user(session_id)

        if not user:
            return redirect(url_for("web_ui.root"))

        return send_from_directory(static_dir, "setup.html")

    @bp.route("/api/login", methods=["POST"])
    def login():
        try:
            data = request.get_json() or {}
            username = data.get("username")
            password = data.get("password")

            if not username or not password:
                return jsonify({"success": False, "message": "用户名或密码不能为空"}), 400

            user = DEFAULT_USERS.get(username)
            if not user or password != user["password"]:
                return jsonify({"success": False, "message": "用户名或密码错误"}), 401

            session_id = create_session(username)

            response = make_response(
                jsonify({"success": True, "message": "登录成功", "username": username})
            )
            response.set_cookie(
                key="session_id",
                value=session_id,
                max_age=int(SESSION_EXPIRE_MINUTES * 60),
                httponly=True,
                samesite="lax",
            )
            return response

        except Exception as e:
            logger.error("登录接口异常: %s", e)
            return jsonify({"success": False, "message": f"服务器错误: {e}"}), 500

    @bp.route("/api/logout", methods=["POST"])
    def logout():
        session_id = request.cookies.get("session_id")
        if session_id:
            remove_session(session_id)

        response = make_response(jsonify({"success": True, "message": "已退出"}))
        response.set_cookie(key="session_id", value="", expires=0)
        return response

    @bp.route("/api/status")
    def get_status():
        session_id = request.cookies.get("session_id")
        user = get_current_user(session_id)
        stats = task_manager.get_statistics()

        return jsonify(
            {
                "success": True,
                "username": user["username"] if user else "guest",
                "bot_status": "running" if user else "stopped",
                "active_tasks": stats.get("active_tasks", 0),
                "today_downloads": stats.get("today_downloads", 0),
            }
        )

    @bp.route("/api/tasks", methods=["GET"])
    def get_tasks():
        session_id = request.cookies.get("session_id")
        user = get_current_user(session_id)

        if not user:
            return jsonify({"success": False, "message": "未登录"}), 401

        status_filter = (request.args.get("status_filter", "all") or "all").strip().lower()

        try:
            limit = int(request.args.get("limit", "50"))
        except ValueError:
            limit = 50
        limit = max(1, min(limit, 500))

        all_tasks = list(persistence.tasks.values())

        if status_filter != "all":
            status_alias = {
                "processing": TaskPersistStatus.DOWNLOADING.value,
            }
            target_status = status_alias.get(status_filter, status_filter)
            all_tasks = [t for t in all_tasks if t.status.value == target_status]

        all_tasks.sort(key=lambda t: (t.updated_at or t.created_at or ""), reverse=True)
        sliced = all_tasks[:limit]
        task_items = [_task_to_web_dict(t) for t in sliced]

        return jsonify({"success": True, "tasks": task_items, "total": len(all_tasks)})

    @bp.route("/api/tasks/<task_id>/cancel", methods=["POST"])
    def cancel_task(task_id):
        session_id = request.cookies.get("session_id")
        user = get_current_user(session_id)

        if not user:
            return jsonify({"success": False, "message": "未登录"}), 401

        success = _run_async(persistence.cancel_task(task_id))
        if not success:
            return jsonify({"success": False, "message": "任务不存在或状态不可取消"}), 404

        return jsonify({"success": True, "message": "任务已取消"})

    @bp.route("/api/tasks/<task_id>/pause", methods=["POST"])
    def pause_task(task_id):
        session_id = request.cookies.get("session_id")
        user = get_current_user(session_id)

        if not user:
            return jsonify({"success": False, "message": "未登录"}), 401

        success = _run_async(persistence.pause_task(task_id))
        if not success:
            return jsonify({"success": False, "message": "任务不存在或状态不可暂停"}), 404

        return jsonify({"success": True, "message": "任务已暂停"})

    @bp.route("/api/tasks/<task_id>/resume", methods=["POST"])
    def resume_task(task_id):
        session_id = request.cookies.get("session_id")
        user = get_current_user(session_id)

        if not user:
            return jsonify({"success": False, "message": "未登录"}), 401

        success = _run_async(persistence.resume_task(task_id))
        if not success:
            return jsonify({"success": False, "message": "任务不存在或状态不可恢复"}), 404

        return jsonify({"success": True, "message": "任务已恢复"})

    @bp.route("/api/tasks/<task_id>/retry", methods=["POST"])
    def retry_task(task_id):
        session_id = request.cookies.get("session_id")
        user = get_current_user(session_id)

        if not user:
            return jsonify({"success": False, "message": "未登录"}), 401

        task = _run_async(persistence.get_task(task_id))
        if not task:
            return jsonify({"success": False, "message": "任务不存在"}), 404

        _run_async(persistence.update_status(task_id, TaskPersistStatus.PENDING, ""))
        return jsonify({"success": True, "message": "任务已重新排队"})

    @bp.route("/api/tasks/completed", methods=["DELETE"])
    def clear_completed_tasks():
        session_id = request.cookies.get("session_id")
        user = get_current_user(session_id)

        if not user:
            return jsonify({"success": False, "message": "未登录"}), 401

        cleared = _run_async(persistence.cleanup_completed(days=0))
        return jsonify({"success": True, "cleared": int(cleared)})

    return bp


if __name__ == "__main__":
    from flask import Flask

    app = Flask(__name__)
    static_dir = os.path.join(os.path.dirname(__file__), "templates")
    bp = create_web_ui_blueprint(static_dir)
    app.register_blueprint(bp)

    app.run(host="0.0.0.0", port=8531, debug=True)
