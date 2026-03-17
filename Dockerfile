# ===== 阶段 1: 用 Go 构建可执行文件 =====
FROM golang:1.23 AS go-builder

WORKDIR /app

# 克隆并编译 apple-music-downloader
RUN git clone https://github.com/zhaarey/apple-music-downloader.git \
    && cd apple-music-downloader \
    && go mod download \
    && go build -o amd main.go \
    && chmod +x amd 

# ===== 阶段 2: Python 程序运行环境 =====

# 使用 ubuntu 作为基础镜像
FROM ubuntu:22.04

# 设置工作目录
WORKDIR /app

# 从第一阶段复制二进制到最终镜像
COPY --from=go-builder /app/apple-music-downloader/amd /app/amdp/

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    DOWNLOAD_PATH=/downloads

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    curl  \
    wget  \
    git   \
    python3  \
    python3-pip \
    xz-utils \
    unzip   \
    tzdata  \
    libnspr4 \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libxss1 \
    libasound2 \
    libdrm2 \
    libgtk-3-0 \
    libx11-xcb1 \
    libxcb-dri3-0 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxss1 \
    libxtst6 \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖并确保 yt-dlp 是最新版本
RUN pip3 install --no-cache-dir -r requirements.txt \
    && pip3 install --no-cache-dir -U yt-dlp

# 安装GPAC（包含MP4Box)

# 安装依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    tar \
    && rm -rf /var/lib/apt/lists/*

# 下载 GPAC 官方预编译二进制
RUN apt-get update && apt-get install -y --no-install-recommends \
    gpac \
    git \
    wget \
    ca-certificates \
    build-essential \
    && rm -rf /var/lib/apt/lists/*


# 下载并安装 Bento4 SDK (包含 mp4decrypt)
RUN wget -O /tmp/bento4.zip "https://www.bok.net/Bento4/binaries/Bento4-SDK-1-6-0-641.x86_64-unknown-linux.zip" \
    && unzip /tmp/bento4.zip -d /tmp/ \
    && cp /tmp/Bento4-SDK-*/bin/mp4decrypt /usr/local/bin/ \
    && chmod +x /usr/local/bin/mp4decrypt \
    && rm -rf /tmp/bento4.zip /tmp/Bento4-SDK-* \
    && echo "Bento4 SDK 安装成功"

# 安装 Playwright 浏览器
RUN playwright install chromium

# 安装最新版本 FFmpeg 7.x
ARG TARGETARCH

RUN cd /tmp && \
    if [ "$TARGETARCH" = "amd64" ]; then \
    wget https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz; \
    elif [ "$TARGETARCH" = "arm64" ]; then \
    wget https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz; \
    else \
    echo "Unsupported arch: $TARGETARCH" && exit 1; \
    fi && \
    tar -xf ffmpeg-release-${TARGETARCH}-static.tar.xz && \
    cp ffmpeg-*-static/ffmpeg /usr/local/bin/ && \
    cp ffmpeg-*-static/ffprobe /usr/local/bin/ && \
    chmod +x /usr/local/bin/ffmpeg /usr/local/bin/ffprobe && \
    rm -rf /tmp/ffmpeg-* && \
    ffmpeg -version && \
    ffprobe -version


# 复制应用代码
COPY . .

# 创建下载目录
RUN mkdir -p /downloads/x /downloads/youtube \
    && chmod -R 777 /downloads

# 设置健康检查（Flask 服务运行在 8530 端口）
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8530/ || exit 1

# 设置入口点
ENTRYPOINT ["python3", "main.py"]
