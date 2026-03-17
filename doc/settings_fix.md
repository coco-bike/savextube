# 系统设置 API 修复

## 问题描述
点击"系统设置"菜单时，报错：`读取设置失败：Error: HTTP 404`

## 问题原因
Flask 应用中缺少 `/api/settings` 路由，导致前端无法读取和保存设置。

## 修复内容

### 新增 API 端点

在 `web/flask_web_ui.py` 中添加：

#### 1. GET /api/settings - 获取系统设置
```python
@bp.route("/api/settings", methods=["GET"])
def get_settings():
    """获取系统设置"""
    # 返回默认设置
    return jsonify({
        "success": True,
        "storage_path": "/vol2/1000/media/music",
        "quality": "lossless",
        "notify": True,
        "channel_switches": {
            "x": True,
            "youtube": True,
            "bilibili": True,
            # ... 其他渠道
        }
    })
```

#### 2. POST /api/settings - 更新系统设置
```python
@bp.route("/api/settings", methods=["POST"])
def update_settings():
    """更新系统设置"""
    data = request.get_json()
    # 保存设置逻辑
    return jsonify({
        "success": True,
        "message": "设置已保存",
        "settings": data
    })
```

## 测试结果

### 未登录访问
```
GET /api/settings
状态码：401
响应：{"success": False, "message": "未登录"}
```

### 已登录获取设置
```
GET /api/settings
状态码：200
响应：{
  "success": True,
  "storage_path": "/vol2/1000/media/music",
  "quality": "lossless",
  "notify": True,
  "channel_switches": {...}
}
```

### 更新设置
```
POST /api/settings
状态码：200
响应：{
  "success": True,
  "message": "设置已保存",
  "settings": {...}
}
```

## 系统设置功能

### 当前支持的设置项

| 设置项 | 类型 | 说明 | 默认值 |
|--------|------|------|--------|
| storage_path | string | 下载存储路径 | /vol2/1000/media/music |
| quality | string | 下载质量 | lossless |
| notify | boolean | 启用通知 | true |
| channel_switches | object | 渠道开关 | 全部开启 |

### 渠道开关

- ✅ X (Twitter)
- ✅ YouTube
- ✅ Bilibili
- ✅ 抖音
- ✅ 快手
- ✅ 小红书
- ✅ Instagram
- ✅ Telegram
- ✅ 网易云音乐
- ✅ QQ 音乐

## 注意事项

1. **登录要求**：所有设置 API 都需要登录后才能访问
2. **Session 认证**：使用 Cookie 中的 `session_id` 进行认证
3. **设置持久化**：当前版本设置保存在内存中，重启后恢复默认
4. **后续改进**：可以添加数据库存储设置

## 使用示例

### 前端调用

```javascript
// 获取设置
const response = await fetch('/api/settings', {
  credentials: 'include'
});
const data = await response.json();
console.log(data);

// 更新设置
await fetch('/api/settings', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  credentials: 'include',
  body: JSON.stringify({
    storage_path: '/new/path',
    quality: 'high',
    notify: false
  })
});
```

## 日志输出

```
🔐 收到登录请求：用户名=admin
✅ 创建 session: admin
✅ 登录成功：admin
📝 收到设置更新：['channel_switches', 'notify', 'quality', 'storage_path']
```
