# 简化版登录认证

## 变更说明

已移除复杂的 JWT 认证，改用简单的 Session 认证方式。

## 主要变更

### 1. 认证方式
- **之前**: JWT Token（需要 python-jose 库）
- **现在**: 简单 Session（内存存储，无需额外依赖）

### 2. API 端点
- **之前**: `POST /api/token` (form-data)
- **现在**: `POST /api/login` (JSON)

### 3. Cookie 名称
- **之前**: `access_token`
- **现在**: `session_id`

### 4. 用户配置
```python
DEFAULT_USERS = {
    "admin": {
        "username": "admin",
        "password": "savextube",  # 明文密码
        "disabled": False,
        "role": "admin"
    }
}
```

## 登录流程

1. 访问 http://localhost:8530
2. 输入用户名和密码
3. 前端发送 JSON 请求：`POST /api/login`
   ```json
   {
     "username": "admin",
     "password": "savextube"
   }
   ```
4. 后端验证密码（简单字符串比较）
5. 创建 Session 并返回 session_id
6. 浏览器保存 session_id 到 Cookie
7. 后续请求自动携带 Cookie 进行认证

## Session 管理

### Session 存储
```python
# 内存存储
_sessions = {
    "session_id": {
        "username": "admin",
        "expires": "2026-03-18T16:32:20.818526"
    }
}
```

### Session 过期
- 默认过期时间：24 小时
- 每次访问自动检查是否过期
- 过期后自动删除并重定向到登录页

## 新增 API

### 登出接口
```
POST /api/logout
```
响应：
```json
{
  "success": true,
  "message": "已退出"
}
```

### 状态接口
```
GET /api/status
```
响应：
```json
{
  "success": true,
  "username": "admin",
  "bot_status": "running",
  "active_tasks": 0,
  "today_downloads": 0
}
```

## 优点

1. **简单**: 无需 JWT 库，代码更少
2. **快速**: 密码直接比较，无需哈希计算
3. **易调试**: Session 存储在内存中，可随时查看
4. **低依赖**: 不需要 `python-jose` 和 `passlib`

## 缺点

1. **重启失效**: 程序重启后所有 Session 清空
2. **单机限制**: Session 存储在内存，不支持分布式
3. **安全性**: 明文密码比较（仅适用于内部使用）

## 使用建议

- ✅ 内部测试环境
- ✅ 个人使用
- ✅ 开发环境
- ❌ 生产环境（需要更强的安全措施）

## 登录凭据

- **用户名**: `admin`
- **密码**: `savextube`

## 故障排除

### 登录失败
1. 检查用户名和密码是否正确
2. 清除浏览器 Cookie
3. 查看控制台日志

### 日志示例
```
🔐 收到登录请求：用户名=admin
✅ 创建 session: admin
✅ 登录成功：admin
```
