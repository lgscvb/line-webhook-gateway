"""轉發服務 - 處理 Webhook 轉發邏輯"""

import logging
from dataclasses import dataclass

import httpx

from .config import ReplyMode, get_settings
from .router import RouteResult, RouteTarget

logger = logging.getLogger(__name__)


@dataclass
class ForwardResult:
    """轉發結果"""

    success: bool
    target: str  # "old_system" or "new_system"
    status_code: int | None = None
    response_body: dict | str | None = None
    error: str | None = None


class WebhookForwarder:
    """Webhook 轉發器"""

    def __init__(self):
        self.settings = get_settings()
        self.client = httpx.AsyncClient(timeout=30.0)

    async def forward_to_old_system(
        self,
        body: bytes,
        headers: dict,
        include_reply_token: bool = False,
    ) -> ForwardResult:
        """
        轉發 Webhook 到舊系統

        Args:
            body: 原始 Request body
            headers: 原始 Headers (會過濾掉 host 等不需要的 header)
            include_reply_token: 是否保留 reply_token (如果要讓舊系統回覆)

        Returns:
            ForwardResult: 轉發結果
        """
        if not self.settings.old_system_webhook_url:
            return ForwardResult(
                success=False,
                target="old_system",
                error="未設定 OLD_SYSTEM_WEBHOOK_URL",
            )

        return await self._forward(
            url=self.settings.old_system_webhook_url,
            body=body,
            headers=headers,
            target="old_system",
        )

    async def forward_to_new_system(
        self,
        body: bytes,
        headers: dict,
    ) -> ForwardResult:
        """
        轉發 Webhook 到新系統

        Args:
            body: 原始 Request body
            headers: 原始 Headers

        Returns:
            ForwardResult: 轉發結果
        """
        if not self.settings.new_system_webhook_url:
            return ForwardResult(
                success=False,
                target="new_system",
                error="未設定 NEW_SYSTEM_WEBHOOK_URL",
            )

        return await self._forward(
            url=self.settings.new_system_webhook_url,
            body=body,
            headers=headers,
            target="new_system",
        )

    async def forward_by_route(
        self,
        route_result: RouteResult,
        body: bytes,
        headers: dict,
    ) -> list[ForwardResult]:
        """
        根據路由結果轉發 Webhook

        Args:
            route_result: 路由判斷結果
            body: 原始 Request body
            headers: 原始 Headers

        Returns:
            list[ForwardResult]: 轉發結果列表
        """
        results = []

        # 決定是否讓目標系統自己回覆
        reply_mode = self.settings.reply_mode

        if route_result.target == RouteTarget.OLD_SYSTEM:
            # 轉發給舊系統
            # 如果是 delegate_old 模式，讓舊系統自己回覆
            include_reply = reply_mode == ReplyMode.DELEGATE_OLD
            result = await self.forward_to_old_system(
                body, headers, include_reply_token=include_reply
            )
            results.append(result)

        elif route_result.target == RouteTarget.NEW_SYSTEM:
            # 轉發給新系統
            result = await self.forward_to_new_system(body, headers)
            results.append(result)

        elif route_result.target == RouteTarget.BOTH:
            # 兩邊都轉發
            old_result = await self.forward_to_old_system(
                body, headers, include_reply_token=False
            )
            new_result = await self.forward_to_new_system(body, headers)
            results.extend([old_result, new_result])

        return results

    async def _forward(
        self,
        url: str,
        body: bytes,
        headers: dict,
        target: str,
    ) -> ForwardResult:
        """內部轉發方法"""
        # 過濾掉不需要轉發的 headers
        forward_headers = self._filter_headers(headers)

        try:
            response = await self.client.post(
                url,
                content=body,
                headers=forward_headers,
            )

            # 嘗試解析 JSON 回應
            try:
                response_body = response.json()
            except Exception:
                response_body = response.text

            success = 200 <= response.status_code < 300

            if not success:
                logger.warning(
                    f"轉發到 {target} 失敗: status={response.status_code}, body={response_body}"
                )

            return ForwardResult(
                success=success,
                target=target,
                status_code=response.status_code,
                response_body=response_body,
            )

        except httpx.TimeoutException:
            logger.error(f"轉發到 {target} 超時: {url}")
            return ForwardResult(
                success=False,
                target=target,
                error="請求超時",
            )
        except httpx.RequestError as e:
            logger.error(f"轉發到 {target} 失敗: {e}")
            return ForwardResult(
                success=False,
                target=target,
                error=str(e),
            )

    def _filter_headers(self, headers: dict) -> dict:
        """過濾 Headers，移除不該轉發的"""
        # 這些 header 不應該轉發
        skip_headers = {
            "host",
            "content-length",  # httpx 會自動計算
            "transfer-encoding",
            "connection",
        }

        return {
            k: v
            for k, v in headers.items()
            if k.lower() not in skip_headers
        }

    async def close(self):
        """關閉 HTTP client"""
        await self.client.aclose()


# 模組層級實例
_forwarder: WebhookForwarder | None = None


def get_forwarder() -> WebhookForwarder:
    """取得轉發器實例"""
    global _forwarder
    if _forwarder is None:
        _forwarder = WebhookForwarder()
    return _forwarder
