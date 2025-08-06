# 使用官方的 Python 3.11 slim 版本作为基础镜像
FROM python:3.11-slim

# 设置环境变量，防止生成 .pyc 文件并启用无缓冲输出
# 设置时区为亚洲/上海，以确保日志等时间正确显示
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV TZ=Asia/Shanghai
ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8

# 设置工作目录
WORKDIR /app

# 接收构建时参数，并设置默认值
ARG PUID=1000
ARG PGID=1000

# 安装系统依赖并创建用户
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    default-libmysqlclient-dev \
    tzdata \
    && addgroup --gid ${PGID} appgroup \
    && adduser --shell /bin/sh --disabled-password --uid ${PUID} --gid ${PGID} appuser \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY src/ ./src/
COPY static/ ./static/
COPY config/ ./config/

# 更改工作目录所有权为新创建的用户
RUN chown -R appuser:appgroup /app

# 暴露应用运行的端口
EXPOSE 7768

# 切换到非 root 用户
USER appuser

# 运行应用的默认命令
CMD ["python", "-m", "src.main"]
