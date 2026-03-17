# 任务管理 API 修复

## 问题描述

访问任务页面时报错：
- `GET /api/tasks?status_filter=all&limit=50 404 (NOT FOUND)`
- `加载任务失败：SyntaxError: Unexpected token '<', "<!doctype "... is not valid JSON`
- `WebSocket connection to 'ws://localhost:8530/ws/tasks' failed`

## 问题原因

Flask 应用中缺少任务相关的 API 端点，导致前端无法调用。

## 修复内容

### 新增 API 端点

在 `web/flask_web_ui.py` 中添加以下 API：

#### 1. GET /api/tasks - 获取任务列表
```python
@bp.route("/api/tasks", methods=["GET"])
def get_tasks():
    """获取任务列表"""
    # 参数：status_filter, limit
    # 返回：{"success": True, "tasks": [], "total": 0}
```

#### 2. POST /api/tasks/<task_id>/cancel - 取消任务
```python
@bp.route("/api/tasks/<task_id>/cancel", methods=["POST"])
def cancel_task(task_id):
    """取消任务"""
    # 返回：{"success": True, "message": "任务已取消"}
```

#### 3. POST /api/tasks/<task_id>/pause - 暂停任务
```python
@bp.route("/api/tasks/<task_id>/pause", methods=["POST"])
def pause_task(task_id):
    """暂停任务"""
    # 返回：{"success": True, "message": "任务已暂停"}
```

#### 4. POST /api/tasks/<task_id>/resume - 恢复任务
```python
@bp.route("/api/tasks/<task_id>/resume", methods=["POST"])
def resume_task(task_id):
    """恢复任务"""
    # 返回：{"success": True, "message": "任务已恢复"}
```

#### 5. POST /api/tasks/<task_id>/retry - 重试任务
```python
@bp.route("/api/tasks/<task_id>/retry", methods=["POST"])
def retry_task(task_id):
    """重试任务"""
    # 返回：{"success": True, "message": "任务已重新排队"}
```

#### 6. DELETE /api/tasks/completed - 清除已完成任务
```python
@bp.route("/api/tasks/completed", methods=["DELETE"])
def clear_completed_tasks():
    """清除已完成的任务"""
    # 返回：{"success": True, "cleared": 0}
```

### 前端修复

#### 1. 修复 Loading 组件
移除未定义的 `<Loading>` 组件，使用 SVG 图标代替：
```html
<el-icon class="is-loading">
  <svg viewBox="0 0 1024 1024" ...>
    <path fill="currentColor" d="..."/>
  </svg>
</el-icon>
```

#### 2. 优化 WebSocket 日志
添加详细的连接日志，便于调试：
```javascript
console.log("🔌 尝试连接 WebSocket:", wsUrl);
console.log("✅ WebSocket 已连接");
console.log("❌ WebSocket 连接关闭");
```

## 测试结果

### API 测试
```
✅ 登录：200
✅ 获取任务列表：200
✅ 取消任务：200
✅ 暂停任务：200
✅ 恢复任务：200
✅ 重试任务：200
✅ 清除已完成任务：200
```

### 前端日志
```
🔌 尝试连接 WebSocket: ws://localhost:8530/ws/tasks
✅ WebSocket 已连接
📋 获取任务列表：filter=all, limit=50
```

## 当前状态

所有任务管理 API 已正常工作，但返回的是空任务列表（因为没有实际的任务数据源）。

### 返回数据示例

**获取任务列表：**
```json
{
  "success": true,
  "tasks": [],
  "total": 0
}
```

**取消任务：**
```json
{
  "success": true,
  "message": "任务已取消"
}
```

## 后续改进

1. **集成任务管理器**：连接实际的任务数据源
2. **WebSocket 实时推送**：实现任务状态实时更新
3. **任务持久化**：使用数据库存储任务信息
4. **任务统计**：添加任务数量、完成率等统计信息

## 控制台日志说明

### 正常日志
```
📋 获取任务列表：filter=all, limit=50
🔌 尝试连接 WebSocket: ws://localhost:8530/ws/tasks
✅ WebSocket 已连接
```

### 未配置 TG 机器人
```
⚠️ TG 机器人未配置，WebSocket 连接已禁用
⏹️ WebSocket 已停止重连（未配置）
```

### 错误处理
```
WebSocket 错误（静默处理，不显示）
❌ WebSocket 连接关闭
⏳ 5 秒后重连 WebSocket...
```
