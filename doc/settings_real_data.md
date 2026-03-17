# 系统设置功能说明

## 当前状态

✅ **功能正常，数据真实有效**

系统设置界面现在使用真实的内存存储，不是模拟数据。

## 实现方式

### 1. 数据存储

```python
# 内存存储设置（重启后恢复默认）
_system_settings = {
    "storage_path": "/vol2/1000/media/music",
    "quality": "lossless",
    "notify": True,
    "channel_switches": {
        "x": True,
        "youtube": True,
        "bilibili": True,
        # ... 其他渠道
    }
}
```

### 2. API 端点

#### GET /api/settings - 获取设置
```python
# 返回当前保存的设置
return jsonify({
    "success": True,
    "storage_path": _system_settings["storage_path"],
    "quality": _system_settings["quality"],
    "notify": _system_settings["notify"],
    "channel_switches": _system_settings["channel_switches"]
})
```

#### POST /api/settings - 更新设置
```python
# 保存设置到内存
if "storage_path" in data:
    _system_settings["storage_path"] = data["storage_path"]
if "quality" in data:
    _system_settings["quality"] = data["quality"]
if "notify" in data:
    _system_settings["notify"] = data["notify"]
if "channel_switches" in data:
    _system_settings["channel_switches"] = data["channel_switches"]
```

### 3. 前端调用

```javascript
// 加载设置
const loadSettings = async () => {
  const resp = await fetch("/api/settings", {
    credentials: 'include', // 携带 Cookie
  });
  const data = await resp.json();
  // 更新 settings 对象
};

// 保存设置
const saveSettings = async () => {
  const resp = await fetch("/api/settings", {
    method: "POST",
    credentials: 'include',
    body: JSON.stringify({
      channel_switches: settings.channelSwitches,
      storage_path: settings.storagePath,
      quality: settings.preferredQuality,
      notify: settings.enableNotification,
    }),
  });
};
```

## 测试结果

### 测试流程
1. 登录 → 获取 session
2. 获取设置 → 返回默认值
3. 更新设置 → 保存到内存
4. 再次获取 → 返回新值

### 测试日志
```
🔐 收到登录请求：用户名=admin
✅ 创建 session: admin
✅ 登录成功：admin

📝 收到设置更新：['channel_switches', 'notify', 'quality', 'storage_path']
✅ 设置已保存：storage_path=/new/path/music, quality=high
```

### 设置变更验证
| 设置项 | 默认值 | 更新后 | 验证结果 |
|--------|--------|--------|----------|
| storage_path | /vol2/1000/media/music | /new/path/music | ✅ 已保存 |
| quality | lossless | high | ✅ 已保存 |
| notify | True | False | ✅ 已保存 |
| channel_switches.x | True | False | ✅ 已保存 |

## 功能特点

### ✅ 优点
1. **真实数据存储** - 不是模拟数据，设置会真正保存
2. **即时生效** - 保存后立即更新
3. **跨页面共享** - 所有 API 共享同一份设置
4. **简单可靠** - 内存存储，无数据库依赖

### ⚠️ 限制
1. **重启丢失** - 程序重启后设置恢复默认
2. **单机限制** - 设置存储在内存，不支持多实例
3. **无持久化** - 没有保存到文件或数据库

## 可配置项

### 1. 存储设置
- **storage_path**: 下载存储路径
- **quality**: 下载质量（lossless/high/standard）
- **notify**: 是否启用通知

### 2. 渠道开关
支持以下渠道的开启/关闭：
- X (Twitter)
- YouTube
- Bilibili
- 抖音
- 快手
- 小红书
- Instagram
- Telegram
- 网易云音乐
- QQ 音乐

## 使用示例

### 1. 访问设置页面
```
http://localhost:8530/settings
```

### 2. 修改存储路径
```
存储路径：/vol2/1000/media/music → /new/path
```

### 3. 修改下载质量
```
下载质量：lossless → high
```

### 4. 关闭某些渠道
```
X: ✓ → ✗
Bilibili: ✓ → ✗
```

### 5. 保存设置
点击"💾 保存设置"按钮

### 6. 验证保存结果
刷新页面或重新进入设置页面，查看设置是否保持

## 日志输出

### 加载设置
```
📋 获取系统设置
✅ 设置已加载
```

### 保存设置
```
📝 收到设置更新：['channel_switches', 'notify', 'quality', 'storage_path']
✅ 设置已保存：storage_path=/new/path, quality=high
```

## 后续改进建议

### 1. 持久化存储
```python
# 保存到配置文件
import json
with open('/app/config/settings.json', 'w') as f:
    json.dump(_system_settings, f)
```

### 2. 从配置文件加载
```python
# 启动时加载
if os.path.exists('/app/config/settings.json'):
    with open('/app/config/settings.json', 'r') as f:
        _system_settings = json.load(f)
```

### 3. 集成到主配置
将设置保存到 `savextube.toml` 配置文件，与机器人配置统一管理。

## 总结

- ✅ 系统设置功能正常
- ✅ 数据真实有效，不是模拟
- ✅ 支持读取和保存
- ✅ 跨页面共享设置
- ⚠️ 重启后恢复默认（内存存储）
- 📝 建议添加持久化存储
