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

# PUID/PGID 将由 entrypoint.sh 在运行时处理。
# 我们在这里用一个固定的默认ID创建用户。

# 安装系统依赖并创建用户
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    default-libmysqlclient-dev \
    curl \
    tzdata \
    && curl -o /usr/local/bin/su-exec -L "https://github.com/ncopa/su-exec/releases/download/v0.2/su-exec-amd64" \
    && chmod +x /usr/local/bin/su-exec \
    && addgroup --gid 1000 appgroup \
    && adduser --shell /bin/sh --disabled-password --uid 1000 --gid 1000 appuser \
    && apt-get purge -y --auto-remove curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY src/ ./src/
COPY static/ ./static/
COPY config/ ./config/
COPY exec.sh /exec.sh
COPY run.sh /run.sh
RUN chmod +x /exec.sh /run.sh

# 更改工作目录所有权为新创建的用户
RUN chown -R appuser:appgroup /app

# 暴露应用运行的端口
EXPOSE 7768

# 运行应用的默认命令
CMD ["/exec.sh"]
