# SaveXTube Web UI 配置

## 端口配置
- **主端口**: 8530 (Web UI + Setup)
- **API 端口**: 8530/api (FastAPI)

## 默认账户
- **用户名**: admin
- **密码**: savextube (首次登录后修改)

## 功能模块
1. 仪表盘
2. 歌单管理
3. TG 频道搜索
4. 下载任务
5. 系统设置
6. Setup (集成)

## 技术栈
- **后端**: FastAPI
- **前端**: Vue 3 + Element Plus
- **认证**: JWT Token
- **数据库**: SQLite (复用现有)
