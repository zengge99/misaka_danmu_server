# 使用官方 Python 镜像作为基础镜像
FROM python:3.10-slim

# 设置环境变量，防止生成 .pyc 文件并启用无缓冲输出
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 设置工作目录
WORKDIR /app

# 安装系统依赖
# build-essential 用于编译某些 Python 包 (如 cryptography)
# default-libmysqlclient-dev 是 aiomysql 所需的
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    default-libmysqlclient-dev \
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

# 更改应用目录的所有权
RUN chown -R appuser:appgroup /app

# 切换到非 root 用户
USER appuser

# 暴露应用运行的端口
EXPOSE 7768

# 运行应用的命令
# host 在 docker-compose.yml 中通过环境变量设置为 0.0.0.0
CMD ["python", "-m", "src.main"]
