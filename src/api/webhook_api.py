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

    # 1. 读取请求体
    raw_body = await request.body()

    if not raw_body:
        logger.warning(f"Webhook '{webhook_type}' 收到了一个空的请求体，无法处理。")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请求体为空 (Request body is empty)。"
        )

    # 2. 参考 Jellyfin 插件，根据 Content-Type 解析负载
    content_type = request.headers.get("content-type", "").lower()
    payload = None

    try:
        if "application/x-www-form-urlencoded" in content_type:
            from urllib.parse import parse_qs
            form_data = parse_qs(raw_body.decode())
            if 'payload' in form_data:
                payload_str = form_data['payload'][0]
                logger.info(f"检测到表单数据，正在解析 'payload' 字段...")
                payload = json.loads(payload_str)
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="表单数据中不包含 'payload' 字段。"
                )
        else: # Default to JSON, covers 'application/json' and cases with no/wrong content-type
            if "application/json" not in content_type:
                 logger.warning(f"未知的 Content-Type: '{content_type}'，将尝试直接解析为 JSON。")
            payload = json.loads(raw_body)

    except json.JSONDecodeError:
        logger.error(f"无法将请求体解析为 JSON。Content-Type: '{content_type}'")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请求体不是有效的JSON格式。")
    except Exception as e:
        logger.error(f"解析 Webhook 负载时发生未知错误: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"无法解析请求体。错误: {e}")

    # 3. 处理解析后的负载
    logger.info(f"Webhook '{webhook_type}' 解析后的负载:\n{json.dumps(payload, indent=2, ensure_ascii=False)}")
    try:
        handler = webhook_manager.get_handler(webhook_type)
        await handler.handle(payload)
    except ValueError as e:
        # 捕获在 get_handler 中当 webhook_type 无效时抛出的 ValueError
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return {"message": "Webhook received and is being processed."}