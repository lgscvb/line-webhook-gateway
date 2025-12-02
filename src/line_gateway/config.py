"""設定模組 - 從環境變數載入所有配置"""

from enum import Enum
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class ReplyMode(str, Enum):
    """回覆模式"""

    UNIFIED = "unified"  # 中繼站統一回覆 (建議)
    DELEGATE_OLD = "delegate_old"  # 委託舊系統回覆
    DELEGATE_NEW = "delegate_new"  # 委託新系統回覆


class DatabaseType(str, Enum):
    """資料庫類型"""

    SQLITE = "sqlite"
    FIRESTORE = "firestore"
    POSTGRESQL = "postgresql"


class Settings(BaseSettings):
    """應用程式設定"""

    # LINE Channel 設定
    line_channel_access_token: str = Field(default="")
    line_channel_secret: str = Field(default="")

    # 後端系統 Webhook URLs
    old_system_webhook_url: str = Field(default="")
    new_system_webhook_url: str = Field(default="")

    # 回覆模式
    reply_mode: ReplyMode = Field(default=ReplyMode.UNIFIED)

    # 路由規則 - 舊系統關鍵字
    old_system_keywords: str = Field(default="開發票,地址,預約,轉帳,繳費")

    # 資料庫設定
    database_type: DatabaseType = Field(default=DatabaseType.SQLITE)
    database_url: str = Field(default="sqlite:///./conversations.db")

    # Firestore 設定
    firestore_project_id: str = Field(default="")

    # 伺服器設定
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    debug: bool = Field(default=False)

    # 通知設定 (高價值關鍵字)
    notify_webhook_url: str = Field(default="")
    high_value_keywords: str = Field(default="設立公司,開公司,創業")

    @property
    def old_keywords_list(self) -> list[str]:
        """取得舊系統關鍵字列表"""
        if not self.old_system_keywords:
            return []
        return [k.strip() for k in self.old_system_keywords.split(",") if k.strip()]

    @property
    def high_value_keywords_list(self) -> list[str]:
        """取得高價值關鍵字列表"""
        if not self.high_value_keywords:
            return []
        return [k.strip() for k in self.high_value_keywords.split(",") if k.strip()]

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> Settings:
    """取得設定 (使用快取避免重複讀取)"""
    return Settings()
