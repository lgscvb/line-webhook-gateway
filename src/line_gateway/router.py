"""路由模組 - 判斷訊息該轉發給哪個後端系統"""

from dataclasses import dataclass
from enum import Enum

from .config import get_settings


class RouteTarget(str, Enum):
    """路由目標"""

    OLD_SYSTEM = "old_system"  # 舊系統 (例如：套裝軟體、行政功能)
    NEW_SYSTEM = "new_system"  # 新系統 (例如：AI Agent)
    BOTH = "both"  # 兩邊都轉發 (例如：需要紀錄但由新系統回覆)


@dataclass
class RouteResult:
    """路由結果"""

    target: RouteTarget
    reason: str
    is_high_value: bool = False  # 是否為高價值關鍵字 (觸發通知)
    matched_keyword: str | None = None


class MessageRouter:
    """訊息路由器 - 決定訊息該送往哪個系統"""

    def __init__(self):
        self.settings = get_settings()

    def route(self, message_text: str | None, message_type: str = "text") -> RouteResult:
        """
        判斷訊息應該路由到哪個系統

        Args:
            message_text: 訊息文字內容 (可能為 None，例如貼圖、圖片)
            message_type: 訊息類型 (text, image, sticker, etc.)

        Returns:
            RouteResult: 路由結果
        """
        # 非文字訊息 -> 預設轉發給新系統處理
        if message_type != "text" or message_text is None:
            return RouteResult(
                target=RouteTarget.NEW_SYSTEM,
                reason=f"非文字訊息 (type={message_type})，由新系統處理",
            )

        # 檢查是否包含舊系統關鍵字
        for keyword in self.settings.old_keywords_list:
            if keyword in message_text:
                return RouteResult(
                    target=RouteTarget.OLD_SYSTEM,
                    reason=f"包含舊系統關鍵字: {keyword}",
                    matched_keyword=keyword,
                )

        # 檢查是否為高價值關鍵字
        for keyword in self.settings.high_value_keywords_list:
            if keyword in message_text:
                return RouteResult(
                    target=RouteTarget.NEW_SYSTEM,
                    reason=f"包含高價值關鍵字: {keyword}",
                    is_high_value=True,
                    matched_keyword=keyword,
                )

        # 預設 -> 新系統
        return RouteResult(
            target=RouteTarget.NEW_SYSTEM,
            reason="一般訊息，由新系統 (AI Agent) 處理",
        )

    def should_forward_to_old(self, route_result: RouteResult) -> bool:
        """是否應該轉發給舊系統"""
        return route_result.target in (RouteTarget.OLD_SYSTEM, RouteTarget.BOTH)

    def should_forward_to_new(self, route_result: RouteResult) -> bool:
        """是否應該轉發給新系統"""
        return route_result.target in (RouteTarget.NEW_SYSTEM, RouteTarget.BOTH)


# 模組層級的便捷函數
_router: MessageRouter | None = None


def get_router() -> MessageRouter:
    """取得路由器實例 (單例模式)"""
    global _router
    if _router is None:
        _router = MessageRouter()
    return _router


def route_message(message_text: str | None, message_type: str = "text") -> RouteResult:
    """便捷函數 - 路由訊息"""
    return get_router().route(message_text, message_type)
