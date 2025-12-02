"""
LINE Webhook Gateway - 中繼站主程式

這是唯一的 Webhook 接收口，負責：
1. 接收所有 LINE Webhook 事件
2. 儲存對話紀錄 (Data Asset)
3. 根據規則路由到不同後端系統
4. 統一回覆訊息 (避免 Reply Token 衝突)
"""

import hashlib
import hmac
import base64
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse

from .config import ReplyMode, get_settings
from .forwarder import get_forwarder
from .line_reply import get_line_reply_service, get_notify_service
from .router import RouteTarget, route_message
from .storage import save_conversation

# 設定 logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """應用程式生命週期管理"""
    # 啟動時
    settings = get_settings()
    logger.info("=" * 50)
    logger.info("LINE Webhook Gateway 啟動中...")
    logger.info(f"回覆模式: {settings.reply_mode.value}")
    logger.info(f"舊系統關鍵字: {settings.old_keywords_list}")
    logger.info(f"高價值關鍵字: {settings.high_value_keywords_list}")
    logger.info("=" * 50)

    yield

    # 關閉時
    logger.info("正在關閉服務...")
    forwarder = get_forwarder()
    await forwarder.close()
    line_reply = get_line_reply_service()
    await line_reply.close()
    notify = get_notify_service()
    await notify.close()


app = FastAPI(
    title="LINE Webhook Gateway",
    description="LINE Webhook 中繼站 - 統一接收並分流至多個後端系統",
    version="0.1.0",
    lifespan=lifespan,
)


def verify_signature(body: bytes, signature: str, channel_secret: str) -> bool:
    """驗證 LINE Webhook 簽名"""
    hash_value = hmac.new(
        channel_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()
    expected_signature = base64.b64encode(hash_value).decode("utf-8")
    return hmac.compare_digest(signature, expected_signature)


@app.get("/")
async def root():
    """健康檢查端點"""
    return {"status": "ok", "service": "LINE Webhook Gateway"}


@app.get("/health")
async def health():
    """健康檢查端點 (GCP/AWS 用)"""
    return {"status": "healthy"}


@app.post("/webhook")
async def webhook(
    request: Request,
    x_line_signature: str = Header(None, alias="X-Line-Signature"),
):
    """
    LINE Webhook 主要端點

    這是所有 LINE 事件的唯一入口
    """
    settings = get_settings()

    # 取得原始 body
    body = await request.body()

    # 驗證簽名 (如果有設定 channel secret)
    if settings.line_channel_secret and x_line_signature:
        if not verify_signature(body, x_line_signature, settings.line_channel_secret):
            logger.warning("Webhook 簽名驗證失敗")
            raise HTTPException(status_code=403, detail="Invalid signature")

    # 解析 JSON
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        logger.error("無法解析 Webhook JSON")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # 處理每個事件
    events = data.get("events", [])

    for event in events:
        await process_event(event, body, dict(request.headers))

    # LINE 要求回傳 200 OK
    return JSONResponse(content={"status": "ok"}, status_code=200)


async def process_event(event: dict, raw_body: bytes, headers: dict):
    """處理單一事件"""
    settings = get_settings()

    event_type = event.get("type", "unknown")
    reply_token = event.get("replyToken")

    # 取得使用者資訊
    source = event.get("source", {})
    user_id = source.get("userId", "unknown")

    # 取得訊息內容
    message = event.get("message", {})
    message_type = message.get("type", "unknown")
    message_text = message.get("text") if message_type == "text" else None

    logger.info(
        f"收到事件: type={event_type}, user={user_id[:10]}..., "
        f"msg_type={message_type}, text={message_text[:20] if message_text else 'N/A'}..."
    )

    # 第一步：路由判斷
    route_result = route_message(message_text, message_type)
    logger.info(f"路由結果: target={route_result.target.value}, reason={route_result.reason}")

    # 第二步：儲存對話紀錄 (非常重要！這是訓練 AI 的珍貴數據)
    try:
        await save_conversation(
            user_id=user_id,
            event_type=event_type,
            message_type=message_type,
            message_text=message_text,
            reply_token=reply_token,
            raw_event=event,
            route_target=route_result.target.value,
            route_reason=route_result.reason,
        )
    except Exception as e:
        logger.error(f"儲存對話失敗: {e}")
        # 不要因為儲存失敗而影響主流程

    # 第三步：如果是高價值關鍵字，發送通知
    if route_result.is_high_value and route_result.matched_keyword:
        try:
            notify = get_notify_service()
            await notify.send_notification(
                user_id=user_id,
                message_text=message_text or "",
                keyword=route_result.matched_keyword,
            )
        except Exception as e:
            logger.error(f"發送通知失敗: {e}")

    # 第四步：根據回覆模式處理
    forwarder = get_forwarder()

    if settings.reply_mode == ReplyMode.UNIFIED:
        # 統一回覆模式：中繼站負責回覆
        # 轉發給目標系統，等待其回應，然後由中繼站回覆
        results = await forwarder.forward_by_route(route_result, raw_body, headers)

        for result in results:
            if result.success and isinstance(result.response_body, dict):
                # 如果後端系統回傳了要回覆的訊息
                response_text = result.response_body.get("reply_text")
                if response_text and reply_token:
                    line_reply = get_line_reply_service()
                    await line_reply.reply_text(reply_token, response_text)
                    break  # Reply token 只能用一次

    elif settings.reply_mode == ReplyMode.DELEGATE_OLD:
        # 委託舊系統回覆模式
        if route_result.target == RouteTarget.OLD_SYSTEM:
            # 原封不動轉發，讓舊系統自己回覆
            await forwarder.forward_to_old_system(raw_body, headers, include_reply_token=True)
        else:
            # 轉發給新系統，由中繼站回覆
            results = await forwarder.forward_to_new_system(raw_body, headers)
            # 處理回覆...

    elif settings.reply_mode == ReplyMode.DELEGATE_NEW:
        # 委託新系統回覆模式
        if route_result.target == RouteTarget.NEW_SYSTEM:
            await forwarder.forward_to_new_system(raw_body, headers)
        else:
            await forwarder.forward_to_old_system(raw_body, headers, include_reply_token=False)


# 開發模式入口
if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "line_gateway.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
