# Web UI 登录问题修复

## 问题描述
点击登录时显示 "token 生成失败"，POST `/api/token` 返回 500 错误。

## 修复内容

### 1. 增强错误处理 (`web/flask_web_ui.py`)
- 添加了 `JWT_AVAILABLE` 和 `PASSLIB_AVAILABLE` 标志
- 改进了密码验证的降级处理
- 在 `create_access_token` 函数中添加了详细的错误日志
- 在登录接口中添加了完整的 try-catch 和日志输出
- 添加了控制台日志处理器，确保错误信息输出

### 2. 测试结果
```
测试登录请求 (正确的密码):
   状态码：200
   响应数据：{'access_token': 'eyJhbGci...', 'token_type': 'bearer'}
   
测试登录请求 (错误的密码):
   状态码：401
   响应数据：{'detail': '用户名或密码错误'}
```

## 使用方法

### 1. 清除浏览器缓存
如果之前登录失败，请先清除浏览器缓存：
- Chrome/Edge: `Ctrl+Shift+Delete` → 清除缓存和 Cookie
- 或使用无痕模式访问

### 2. 访问登录页
打开浏览器访问：http://localhost:8530

### 3. 登录
- 用户名：`admin`
- 密码：`savextube`

### 4. 查看日志
如果登录仍然失败，查看控制台日志输出：
```
🔐 收到登录请求：用户名=admin
✅ JWT Token 生成成功
✅ 登录成功：admin
```

## 常见错误

### 1. "用户名或密码错误" (401)
- 检查用户名和密码是否正确
- 默认密码是 `savextube`

### 2. "Token 生成失败" (500)
- 检查 `python-jose` 是否安装：`pip show python-jose`
- 查看控制台日志获取详细错误信息

### 3. 页面加载失败
- 检查 Flask 应用是否启动
- 确认 8530 端口未被占用

## 依赖检查

确保以下依赖已安装：
```bash
pip show python-jose
pip show passlib
pip show flask
```

如果缺少依赖，安装：
```bash
pip install python-jose passlib flask
```
