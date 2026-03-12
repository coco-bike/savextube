# main.py 精简计划 - 阶段 3

## 当前状态

- **main.py 行数**: 20,897 行
- **VideoDownloader 类**: ~12,400 行
- **TelegramBot 类**: ~6,300 行
- **其他代码**: ~2,200 行

## 已完成工作

### 阶段 1：基础模块 ✅
- url_extractor.py - URL 提取
- batch_downloader.py - 批量下载
- message_handler.py - 消息处理

### 阶段 2：平台下载器 ✅
- bilibili_downloader.py - B 站下载器
- youtube_downloader.py - YouTube 下载器
- music_downloader.py - 音乐下载器
- social_media_downloader.py - 社交媒体下载器
- utils/file_utils.py - 文件工具

### 阶段 3：main.py 精简 ⏳（进行中）

## 精简策略

### 方案 A：渐进式精简（推荐）

1. **保留原有代码** - 确保功能正常
2. **添加模块委托** - 新代码使用模块
3. **逐步替换** - 测试一个替换一个
4. **最终删除** - 确认无误后删除旧代码

### 方案 B：激进式精简

1. **直接替换** - 用模块调用替换大函数
2. **保留兼容** - 保留旧方法作为 fallback
3. **一次性重构** - 风险较高

## 已完成的精简

### 1. 导入模块下载器

```python
# 已添加到 main.py
from modules.downloaders.bilibili_downloader import BilibiliDownloader
from modules.downloaders.youtube_downloader import YouTubeDownloader
from modules.downloaders.music_downloader import MusicDownloader
from modules.downloaders.social_media_downloader import SocialMediaDownloader
```

### 2. 初始化下载器

```python
# 已添加到 VideoDownloader.__init__
if MODULES_ENABLED:
    self.bilibili_downloader = BilibiliDownloader(self)
    self.youtube_downloader = YouTubeDownloader(self)
    self.music_downloader = MusicDownloader(self)
    self.social_downloader = SocialMediaDownloader(self)
```

### 3. 简化 download_video 方法

```python
async def download_video(self, url, ...):
    """委托给模块化下载器"""
    url = self._preprocess_url(url)
    
    if MODULES_ENABLED:
        return await self._download_with_modules(url, ...)
    else:
        return await self._download_video_legacy(url, ...)  # 兼容
```

## 预期精简效果

| 阶段 | 精简前 | 精简后 | 减少 |
|------|--------|--------|------|
| 当前 | 20,897 行 | 20,897 行 | 0% |
| 阶段 3A | 20,897 行 | ~15,000 行 | -28% |
| 阶段 3B | 15,000 行 | ~8,000 行 | -62% |
| 最终目标 | 20,897 行 | ~5,000 行 | -76% |

## 下一步行动

### 立即执行
1. 简化 `download_video` 方法
2. 简化 `_download_with_ytdlp_unified` 方法
3. 添加 `_download_with_modules` 方法

### 后续执行
1. 删除已迁移到模块的旧代码
2. 删除未使用的辅助函数
3. 精简 TelegramBot 类

## 风险提示

⚠️ **大规模重构风险**：
- 可能引入 bug
- 需要全面测试
- 建议分步执行

✅ **缓解措施**：
- 保留兼容模式
- 逐步替换
- 充分测试

---

*创建时间：2026 年 3 月 10 日*
