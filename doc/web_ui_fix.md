# Web UI 登录和路由问题修复

## 问题描述

1. **无法显示登录页**：访问根路径 `/` 时无法正常显示登录页面
2. **404 错误**：登录后点击菜单项（仪表盘、任务、设置等）显示 404

## 问题原因

1. **架构问题**：
   - 项目使用 Flask 作为主框架（运行在 main.py，端口 8530）
   - FastAPI 应用（web/app.py）是独立的，未集成到主应用中
   - Flask 应用只注册了 `/setup` 蓝图，缺少登录和 Web UI 路由

2. **JWT 参数错误**：
   - `jwt.decode()` 参数顺序错误：`jwt.decode(SECRET_KEY, access_token, ...)` 应为 `jwt.decode(access_token, SECRET_KEY, ...)`

## 修复方案

### 1. 创建 Flask Web UI 蓝图 (`web/flask_web_ui.py`)

实现了以下路由：
- `/` - 根路径（检查登录状态，未登录显示登录页）
- `/dashboard` - 仪表盘
- `/tasks` - 下载任务
- `/settings` - 系统设置
- `/setup` - Telegram 会话生成
- `/api/token` - 登录接口

### 2. 在 main.py 中注册 Web UI 蓝图

在原有的 `/setup` 蓝图注册后，添加了 Web UI 蓝图注册：

```python
# 注册 Web UI 蓝图（登录、仪表盘、任务、设置等页面）
try:
    from web.flask_web_ui import create_web_ui_blueprint as _ui_create_bp
    _ui_static_dir = os.path.join(os.path.dirname(__file__), "web", "templates")
    app.register_blueprint(_ui_create_bp(static_dir=_ui_static_dir))
    logging.getLogger(__name__).info("✅ Web UI 已注册（登录、仪表盘、任务、设置）")
except Exception as _e2:
    logging.getLogger(__name__).warning(f"⚠️ 注册 Web UI 失败：{_e2}")
```

### 3. 修复 web/app.py 的 JWT 参数

修复了 `jwt.decode()` 的参数顺序错误。

## 使用方法

1. **启动机器人**：正常运行 main.py
   ```bash
   d:\MyProjects\savextube\.venv\Scripts\python.exe main.py
   ```

2. **访问 Web UI**：浏览器打开 http://localhost:8530

3. **登录**：
   - 用户名：`admin`
   - 密码：`savextube`

4. **使用菜单**：登录后点击侧边栏菜单访问各个页面

## 文件变更

| 文件 | 变更说明 |
|------|----------|
| `web/flask_web_ui.py` | 新增 - Flask Web UI 蓝图 |
| `main.py` | 修改 - 注册 Web UI 蓝图 |
| `web/app.py` | 修改 - 修复 JWT 参数顺序 |

## 注意事项

1. **端口占用**：Flask 应用使用 8530 端口，确保该端口未被占用
2. **依赖**：需要安装 `python-jose` 和 `passlib` 用于 JWT 和密码加密
3. **Cookie**：登录状态通过 Cookie 保存，有效期 24 小时
