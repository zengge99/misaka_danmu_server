# 使用官方 Python 镜像作为基础镜像
FROM python:3.10-slim

# 设置环境变量，防止生成 .pyc 文件并启用无缓冲输出
# 设置时区为亚洲/上海，以确保日志等时间正确显示
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV TZ=Asia/Shanghai
# 设置容器的区域设置为 UTF-8。
# 这是解决 protobuf C++ 后端在某些精简版 Linux 环境中出现编码问题的关键。
# 它能确保底层库正确处理 UTF-8 字符串，从而修复 'invalid UTF-8 data' 或 'Couldn't parse file content!' 错误。
ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8

# 设置工作目录
WORKDIR /app

# 安装系统依赖
# build-essential 用于编译某些 Python 包 (如 cryptography)
# default-libmysqlclient-dev 是 aiomysql 所需的
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    default-libmysqlclient-dev \
    tzdata \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 为用户和组ID设置构建参数
ARG PUID=1000
ARG PGID=1000

# 创建一个非 root 用户和组
RUN groupadd -g ${PGID} appgroup && \
    useradd -u ${PUID} -g appgroup -s /bin/sh -m appuser

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 确保日志目录存在，并更改应用目录的所有权
# /app/config 目录是从源代码复制过来的
RUN mkdir -p /app/config/logs && \
    chown -R appuser:appgroup /app

# 切换到非 root 用户
USER appuser

# 暴露应用运行的端口
EXPOSE 7768

# 运行应用的命令
# host 在 docker-compose.yml 中通过环境变量设置为 0.0.0.0
CMD ["python", "-m", "src.main"]
