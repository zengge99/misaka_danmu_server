import logging
from typing import Dict
import json

import aiomysql
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from .. import crud
from ..database import get_db_pool
from ..webhook_manager import WebhookManager

logger = logging.getLogger(__name__)
router = APIRouter()


async def get_webhook_manager(request: Request) -> WebhookManager:
    """依赖项：从应用状态获取 Webhook 管理器"""
    return request.app.state.webhook_manager


@router.post("/{webhook_type}", status_code=status.HTTP_202_ACCEPTED, summary="接收外部服务的Webhook通知")
async def handle_webhook(
    webhook_type: str,
    request: Request,
    api_key: str = Query(..., description="Webhook安全密钥"),
    pool: aiomysql.Pool = Depends(get_db_pool),
    webhook_manager: WebhookManager = Depends(get_webhook_manager),
):
    """统一的Webhook入口，用于接收来自Sonarr, Radarr等服务的通知。"""
    stored_key = await crud.get_config_value(pool, "webhook_api_key", "")
    if not stored_key or api_key != stored_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的Webhook API Key")

    # 新增：先读取原始请求体并记录日志，再尝试解析
    raw_body = await request.body()
    decoded_body = raw_body.decode(errors='ignore')
    log_body = decoded_body if decoded_body.strip() else "[请求体为空]"
    logger.info(f"收到来自 '{webhook_type}' 的 Webhook 原始请求体 (长度: {len(raw_body)} bytes):\n---\n{log_body}\n---")

    if not raw_body:
        logger.warning(f"Webhook '{webhook_type}' 收到了一个空的请求体，无法处理。")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请求体为空 (Request body is empty)。"
        )
    try:
        # 尝试将原始请求体直接解析为JSON
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        # 如果直接解析JSON失败，尝试将其作为表单数据处理（这是Jellyfin的常见情况）
        try:
            from urllib.parse import parse_qs
            form_data = parse_qs(raw_body.decode())
            if 'payload' in form_data:
                # 实际的JSON数据在名为'payload'的表单字段中
                payload_str = form_data['payload'][0]
                logger.info(f"检测到表单数据，正在解析 'payload' 字段:\n{payload_str}")
                payload = json.loads(payload_str)
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="请求体既不是有效的JSON，也不是包含'payload'字段的表单。"
                )
        except Exception as form_e:
            logger.error(f"解析 Webhook 表单数据失败: {form_e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无法解析请求体。它必须是JSON或包含'payload'字段的表单。"
            )
    logger.info(f"Webhook '{webhook_type}' 解析后的负载:\n{json.dumps(payload, indent=2, ensure_ascii=False)}")
    try:
        handler = webhook_manager.get_handler(webhook_type)
        await handler.handle(payload)
    except ValueError as e:
        # 捕获在 get_handler 中当 webhook_type 无效时抛出的 ValueError
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return {"message": "Webhook received and is being processed."}