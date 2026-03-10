# VideoDownloader 模块拆分计划

## 当前状态
- `VideoDownloader` 类：12,364 行
- `TelegramBot` 类：约 6,000 行
- 其他代码：约 2,500 行

## 拆分方案

### 1. 平台下载器模块 (modules/downloaders/)

#### video_downloader.py (约 3000 行)
- `_download_with_ytdlp_unified` - 通用 yt-dlp 下载
- `_download_single_video` - 单视频下载
- `_download_video_file` - 视频文件下载

#### bilibili_downloader.py (约 2500 行)
- `_download_bilibili_video`
- `_download_bilibili_ugc_season`
- `_download_bilibili_user_all_videos`
- `_download_bilibili_list`

#### youtube_downloader.py (约 2000 行)
- `_download_youtube_channel_playlists`
- `_download_youtube_playlist_with_progress`

#### social_media_downloader.py (约 2000 行)
- `_download_x_video_with_ytdlp` (Twitter/X)
- `_download_x_playlist`
- `_download_x_image_with_gallerydl`
- `_download_xiaohongshu_*`
- `_download_douyin_*`
- `_download_kuaishou_*`

#### music_downloader.py (约 1500 行)
- `_download_apple_music`
- `_download_netease_music`
- `_download_qqmusic_music`
- `_download_youtubemusic_music`

### 2. 工具模块 (modules/)

#### progress_utils.py (约 1000 行)
- 进度回调函数
- 消息更新函数
- 格式化函数

#### file_utils.py (约 500 行)
- 文件名清理
- 路径处理
- 文件查找

### 3. 重构后的 main.py

精简到约 500 行，只包含：
- 导入模块
- 初始化逻辑
- 主入口函数
- 简单的协调逻辑

## 优势

1. **易于维护** - 每个模块职责单一
2. **便于测试** - 可以单独测试每个下载器
3. **代码复用** - 通用逻辑提取为工具函数
4. **新人友好** - 快速定位功能代码

## 执行步骤

1. 提取工具函数到 modules/utils/
2. 拆分平台下载器到 modules/downloaders/
3. 精简 VideoDownloader 类为协调器
4. 更新导入和调用关系
5. 测试验证

---

*创建时间：2026 年 3 月 10 日*
