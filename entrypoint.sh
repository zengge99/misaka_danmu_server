#!/bin/sh
# 设置严格的错误检查，任何命令失败都会导致脚本退出
set -e

# 如果环境变量未设置，则默认 PUID 和 PGID 为 1000
PUID=${PUID:-1000}
PGID=${PGID:-1000}

# 更新 appuser 的 UID 和 appgroup 的 GID 以匹配宿主机用户，从而避免挂载卷的权限问题
echo "正在更新用户 'appuser' 的 UID 为 ${PUID}，GID 为 ${PGID}"
usermod -o -u "${PUID}" appuser >/dev/null 2>&1 || true
groupmod -o -g "${PGID}" appgroup >/dev/null 2>&1 || true

# 更改挂载的 /app/config 目录的所有权
echo "正在更新 /app/config 目录的所有权为 ${PUID}:${PGID}..."
chown -R "${PUID}:${PGID}" /app/config

# 降权并执行主命令 (例如：python -m src.main)
echo "正在以 appuser 用户身份执行命令: $@"
exec gosu appuser "$@"