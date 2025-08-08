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

    try:
        payload = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效的请求体。Webhook 必须使用 'json' 类型发送。"
        )
    logger.info(f"收到来自 '{webhook_type}' 的 Webhook 原始负载:\n{json.dumps(payload, indent=2, ensure_ascii=False)}")
    try:
        handler = webhook_manager.get_handler(webhook_type)
        await handler.handle(payload)
    except ValueError as e:
        # 捕获在 get_handler 中当 webhook_type 无效时抛出的 ValueError
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return {"message": "Webhook received and is being processed."}