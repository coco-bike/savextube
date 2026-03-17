# WebSocket 禁用说明

## 问题原因

WebSocket 连接失败是因为 **Flask 应用不支持 WebSocket 协议**。

### 技术背景

| 框架 | WebSocket 支持 |
|------|---------------|
| Flask | ❌ 需要扩展（flask-socketio） |
| FastAPI | ✅ 原生支持 |

当前项目使用的是 Flask 框架，没有集成 WebSocket 扩展，因此 WebSocket 连接会失败。

## 解决方案

### 当前方案：定期刷新（已实现）

- **刷新间隔**：10 秒
- **实现方式**：`setInterval` 定时器
- **优点**：简单可靠，无需额外依赖
- **缺点**：实时性稍差

### 状态指示器

页面头部显示当前状态：
```
🔄 ⚠️ WebSocket 暂不支持，每 10 秒自动刷新
```

## 代码变更

### tasks.html

#### 1. 禁用 WebSocket 连接
```javascript
// 检查 TG 配置
const checkConfig = async () => {
  const response = await fetch("/api/status");
  const data = await response.json();
  wsConfigured.value = data.bot_status === "running";
  
  // 目前 Flask 应用不支持 WebSocket，直接禁用
  console.log("ℹ️ Flask 应用不支持 WebSocket，实时推送已禁用");
  console.log("📋 任务列表将定期刷新");
};
```

#### 2. 添加定期刷新
```javascript
onMounted(() => {
  checkConfig();
  loadTasks();
  
  // 定期刷新任务列表（每 10 秒）
  const refreshInterval = setInterval(() => {
    loadTasks();
  }, 10000);
  
  onUnmounted(() => {
    if (refreshInterval) {
      clearInterval(refreshInterval);
    }
  });
});
```

#### 3. 更新状态指示器
```javascript
const wsStatusText = computed(() => {
  return "⚠️ WebSocket 暂不支持，每 10 秒自动刷新";
});

const wsStatusIcon = computed(() => {
  return "🔄";
});
```

## 控制台日志

### 正常日志
```
ℹ️ Flask 应用不支持 WebSocket，实时推送已禁用
📋 任务列表将定期刷新
📋 获取任务列表：filter=all, limit=50
```

### 不再有
```
❌ WebSocket connection failed
⏳ 5 秒后重连 WebSocket...
```

## 未来扩展

如果需要真正的实时推送功能，可以考虑：

### 方案 1：集成 flask-socketio
```bash
pip install flask-socketio
```

优点：
- 真正的实时推送
- 与 Flask 集成良好

缺点：
- 需要额外的服务器配置
- 可能需要 Redis 等消息队列

### 方案 2：迁移到 FastAPI
FastAPI 原生支持 WebSocket，但需要重构整个 Web 应用。

### 方案 3：保持当前方案
对于个人使用或小规模部署，10 秒刷新间隔已经足够。

## 功能对比

| 功能 | WebSocket | 定期刷新 |
|------|-----------|----------|
| 实时性 | 即时 | 最多 10 秒延迟 |
| 服务器负载 | 低（长连接） | 中（频繁请求） |
| 实现复杂度 | 高 | 低 |
| 可靠性 | 中（需要心跳） | 高 |
| 当前状态 | ❌ 禁用 | ✅ 启用 |

## 总结

- ✅ 任务页面正常工作
- ✅ 定期刷新任务列表
- ✅ 不再有 WebSocket 错误
- ⚠️ 实时性稍差（10 秒延迟）

对于当前使用场景（个人使用，任务数量有限），定期刷新方案完全够用。
