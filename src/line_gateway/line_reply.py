"""LINE 回覆服務 - 統一處理 LINE 訊息回覆"""

import logging

import httpx

from .config import get_settings

logger = logging.getLogger(__name__)

# LINE Messaging API 端點
LINE_API_BASE = "https://api.line.me/v2/bot"


class LineReplyService:
    """LINE 回覆服務 - 用於中繼站統一回覆模式"""

    def __init__(self):
        self.settings = get_settings()
        self.client = httpx.AsyncClient(timeout=30.0)

    @property
    def _headers(self) -> dict:
        """取得 API 請求 Headers"""
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.settings.line_channel_access_token}",
        }

    async def reply_text(self, reply_token: str, text: str) -> bool:
        """
        使用 reply_token 回覆文字訊息

        注意: reply_token 只能使用一次，且有時效性 (約 1 分鐘)

        Args:
            reply_token: LINE 提供的 reply token
            text: 要回覆的文字內容

        Returns:
            bool: 是否成功
        """
        return await self.reply_messages(
            reply_token,
            [{"type": "text", "text": text}],
        )

    async def reply_messages(
        self, reply_token: str, messages: list[dict]
    ) -> bool:
        """
        使用 reply_token 回覆多則訊息

        Args:
            reply_token: LINE 提供的 reply token
            messages: 訊息列表 (最多 5 則)

        Returns:
            bool: 是否成功
        """
        if not self.settings.line_channel_access_token:
            logger.error("未設定 LINE_CHANNEL_ACCESS_TOKEN")
            return False

        if len(messages) > 5:
            logger.warning("LINE API 最多只能一次回覆 5 則訊息，超過的會被截斷")
            messages = messages[:5]

        try:
            response = await self.client.post(
                f"{LINE_API_BASE}/message/reply",
                headers=self._headers,
                json={
                    "replyToken": reply_token,
                    "messages": messages,
                },
            )

            if response.status_code == 200:
                logger.debug(f"回覆成功: token={reply_token[:20]}...")
                return True
            else:
                logger.error(
                    f"回覆失敗: status={response.status_code}, body={response.text}"
                )
                return False

        except httpx.RequestError as e:
            logger.error(f"回覆請求失敗: {e}")
            return False

    async def push_text(self, user_id: str, text: str) -> bool:
        """
        主動推送文字訊息給使用者

        注意: Push Message 會消耗訊息配額

        Args:
            user_id: 使用者 ID
            text: 要推送的文字內容

        Returns:
            bool: 是否成功
        """
        return await self.push_messages(
            user_id,
            [{"type": "text", "text": text}],
        )

    async def push_messages(
        self, user_id: str, messages: list[dict]
    ) -> bool:
        """
        主動推送多則訊息給使用者

        Args:
            user_id: 使用者 ID
            messages: 訊息列表 (最多 5 則)

        Returns:
            bool: 是否成功
        """
        if not self.settings.line_channel_access_token:
            logger.error("未設定 LINE_CHANNEL_ACCESS_TOKEN")
            return False

        try:
            response = await self.client.post(
                f"{LINE_API_BASE}/message/push",
                headers=self._headers,
                json={
                    "to": user_id,
                    "messages": messages[:5],
                },
            )

            if response.status_code == 200:
                logger.debug(f"推送成功: user_id={user_id}")
                return True
            else:
                logger.error(
                    f"推送失敗: status={response.status_code}, body={response.text}"
                )
                return False

        except httpx.RequestError as e:
            logger.error(f"推送請求失敗: {e}")
            return False

    async def close(self):
        """關閉 HTTP client"""
        await self.client.aclose()


# 通知服務 - 用於高價值關鍵字觸發
class NotifyService:
    """通知服務 - 當偵測到高價值關鍵字時發送通知"""

    def __init__(self):
        self.settings = get_settings()
        self.client = httpx.AsyncClient(timeout=10.0)

    async def send_notification(
        self,
        user_id: str,
        message_text: str,
        keyword: str,
    ) -> bool:
        """
        發送高價值客戶通知

        Args:
            user_id: 使用者 ID
            message_text: 使用者發送的訊息
            keyword: 觸發的關鍵字

        Returns:
            bool: 是否成功
        """
        if not self.settings.notify_webhook_url:
            return False

        try:
            # 支援 Slack / Discord / 自訂 Webhook 格式
            payload = {
                "text": f"🎯 高價值客戶警報!\n"
                f"關鍵字: {keyword}\n"
                f"用戶ID: {user_id}\n"
                f"訊息: {message_text}",
                # Slack 格式
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*🎯 高價值客戶警報!*\n"
                            f"• 關鍵字: `{keyword}`\n"
                            f"• 用戶ID: `{user_id}`\n"
                            f"• 訊息: {message_text}",
                        },
                    }
                ],
            }

            response = await self.client.post(
                self.settings.notify_webhook_url,
                json=payload,
            )

            return response.status_code == 200

        except httpx.RequestError as e:
            logger.error(f"發送通知失敗: {e}")
            return False

    async def close(self):
        """關閉 HTTP client"""
        await self.client.aclose()


# 模組層級實例
_line_reply: LineReplyService | None = None
_notify: NotifyService | None = None


def get_line_reply_service() -> LineReplyService:
    """取得 LINE 回覆服務實例"""
    global _line_reply
    if _line_reply is None:
        _line_reply = LineReplyService()
    return _line_reply


def get_notify_service() -> NotifyService:
    """取得通知服務實例"""
    global _notify
    if _notify is None:
        _notify = NotifyService()
    return _notify
