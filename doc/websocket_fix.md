# WebSocket 连接优化

## 问题描述

之前页面加载时会立即尝试连接 WebSocket，导致：
1. TG 机器人未配置时，WebSocket 连接失败
2. 控制台持续报错：`WebSocket connection failed`
3. 无限重连循环

## 修复方案

### 1. 配置检查
页面加载时先检查 TG 机器人是否已配置：
- 调用 `/api/status` 接口
- 根据 `bot_status` 判断是否连接 WebSocket
- 未配置时不建立 WebSocket 连接

### 2. 状态指示器
在页面头部添加 WebSocket 状态指示器：

| 图标 | 状态 | 说明 |
|------|------|------|
| ⚠️ | TG 未配置 | TG 机器人未配置，WebSocket 已禁用 |
| ✅ | 已连接 | WebSocket 正常连接 |
| ⏳ | 未连接 | WebSocket 未连接（可能正在重连） |

### 3. 静默错误处理
- WebSocket 错误不再显示控制台错误
- 只在未配置时停止重连
- 避免无限重连循环

## 代码变更

### tasks.html

#### 新增状态变量
```javascript
const wsConnected = ref(false);      // WebSocket 连接状态
const wsConfigured = ref(false);     // TG 是否已配置
```

#### 新增配置检查函数
```javascript
const checkConfig = async () => {
  const response = await fetch("/api/status");
  const data = await response.json();
  wsConfigured.value = data.bot_status === "running";
  
  if (wsConfigured.value) {
    connectWebSocket();  // 已配置才连接
  } else {
    console.log("⚠️ TG 机器人未配置，WebSocket 连接已禁用");
  }
};
```

#### 新增状态计算属性
```javascript
const wsStatusText = computed(() => {
  if (!wsConfigured.value) return "TG 未配置，WebSocket 已禁用";
  if (wsConnected.value) return "WebSocket 已连接";
  return "WebSocket 未连接";
});
```

### flask_web_ui.py

#### 修改 /api/status 接口
```python
@bp.route("/api/status")
def get_status():
    # 不需要登录也可以访问
    session_id = request.cookies.get("session_id")
    user = get_current_user(session_id)
    
    # 检查 bot 是否已配置
    bot_configured = user is not None
    
    return jsonify({
        "success": True,
        "username": user["username"] if user else "guest",
        "bot_status": "running" if bot_configured else "stopped",
        ...
    })
```

## 使用流程

### 未配置 TG 机器人
1. 访问 /tasks 页面
2. 调用 `/api/status` → `bot_status: "stopped"`
3. WebSocket 连接被禁用
4. 显示状态：⚠️ TG 未配置

### 已配置 TG 机器人
1. 访问 /tasks 页面
2. 调用 `/api/status` → `bot_status: "running"`
3. 建立 WebSocket 连接
4. 显示状态：✅ WebSocket 已连接

## 控制台日志

### 未配置时
```
⚠️ TG 机器人未配置，WebSocket 连接已禁用
```

### 已配置时
```
✅ WebSocket 已连接
```

### 连接断开时（已配置）
```
⏳ WebSocket 已断开，5 秒后重连...
```

### 连接断开时（未配置）
```
⏹️ WebSocket 已停止重连
```

## 优势

1. ✅ 避免无意义的 WebSocket 错误
2. ✅ 清晰的状态指示
3. ✅ 智能重连逻辑
4. ✅ 更好的用户体验
