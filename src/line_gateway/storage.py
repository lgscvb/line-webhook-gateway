"""資料存儲模組 - 記錄所有對話，作為 AI 訓練的珍貴數據"""

import json
import logging
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import DatabaseType, get_settings

logger = logging.getLogger(__name__)


class ConversationStorage(ABC):
    """對話存儲抽象基類"""

    @abstractmethod
    async def save_event(
        self,
        user_id: str,
        event_type: str,
        message_type: str | None,
        message_text: str | None,
        reply_token: str | None,
        raw_event: dict,
        route_target: str | None = None,
        route_reason: str | None = None,
    ) -> str:
        """
        儲存事件

        Returns:
            str: 事件 ID
        """
        pass

    @abstractmethod
    async def get_user_history(
        self, user_id: str, limit: int = 50
    ) -> list[dict]:
        """取得使用者對話歷史"""
        pass


class SQLiteStorage(ConversationStorage):
    """SQLite 存儲實現 - 適合開發測試與小規模使用"""

    def __init__(self, db_path: str = "conversations.db"):
        # 從 sqlite:///./xxx.db 格式提取路徑
        if db_path.startswith("sqlite:///"):
            db_path = db_path.replace("sqlite:///", "")

        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self):
        """初始化資料庫表結構"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT UNIQUE,
                user_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                message_type TEXT,
                message_text TEXT,
                reply_token TEXT,
                route_target TEXT,
                route_reason TEXT,
                raw_event TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 建立索引加速查詢
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_id ON conversations(user_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_created_at ON conversations(created_at)
        """)

        conn.commit()
        conn.close()

        logger.info(f"SQLite 資料庫已初始化: {self.db_path}")

    async def save_event(
        self,
        user_id: str,
        event_type: str,
        message_type: str | None,
        message_text: str | None,
        reply_token: str | None,
        raw_event: dict,
        route_target: str | None = None,
        route_reason: str | None = None,
    ) -> str:
        """儲存事件到 SQLite"""
        event_id = f"{user_id}_{datetime.now().timestamp()}"

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO conversations
                (event_id, user_id, event_type, message_type, message_text,
                 reply_token, route_target, route_reason, raw_event)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    user_id,
                    event_type,
                    message_type,
                    message_text,
                    reply_token,
                    route_target,
                    route_reason,
                    json.dumps(raw_event, ensure_ascii=False),
                ),
            )
            conn.commit()
            logger.debug(f"已儲存事件: {event_id}")
            return event_id
        except sqlite3.IntegrityError:
            logger.warning(f"事件已存在: {event_id}")
            return event_id
        finally:
            conn.close()

    async def get_user_history(
        self, user_id: str, limit: int = 50
    ) -> list[dict]:
        """取得使用者對話歷史"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT * FROM conversations
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        )

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]


class FirestoreStorage(ConversationStorage):
    """Firestore 存儲實現 - 適合 GCP 生態系與大規模使用"""

    def __init__(self, project_id: str):
        try:
            from google.cloud import firestore
        except ImportError:
            raise ImportError(
                "請安裝 google-cloud-firestore: pip install google-cloud-firestore"
            )

        self.db = firestore.AsyncClient(project=project_id)
        self.collection = self.db.collection("line_conversations")
        logger.info(f"Firestore 已連接: project={project_id}")

    async def save_event(
        self,
        user_id: str,
        event_type: str,
        message_type: str | None,
        message_text: str | None,
        reply_token: str | None,
        raw_event: dict,
        route_target: str | None = None,
        route_reason: str | None = None,
    ) -> str:
        """儲存事件到 Firestore"""
        from google.cloud import firestore

        event_id = f"{user_id}_{datetime.now().timestamp()}"

        doc_ref = self.collection.document(event_id)
        await doc_ref.set(
            {
                "user_id": user_id,
                "event_type": event_type,
                "message_type": message_type,
                "message_text": message_text,
                "reply_token": reply_token,
                "route_target": route_target,
                "route_reason": route_reason,
                "raw_event": raw_event,
                "created_at": firestore.SERVER_TIMESTAMP,
            }
        )

        logger.debug(f"已儲存事件到 Firestore: {event_id}")
        return event_id

    async def get_user_history(
        self, user_id: str, limit: int = 50
    ) -> list[dict]:
        """取得使用者對話歷史"""
        query = (
            self.collection.where("user_id", "==", user_id)
            .order_by("created_at", direction="DESCENDING")
            .limit(limit)
        )

        docs = await query.get()
        return [doc.to_dict() for doc in docs]


# Storage 工廠函數
_storage: ConversationStorage | None = None


def get_storage() -> ConversationStorage:
    """取得存儲實例 (單例模式)"""
    global _storage
    if _storage is None:
        settings = get_settings()

        if settings.database_type == DatabaseType.SQLITE:
            _storage = SQLiteStorage(settings.database_url)
        elif settings.database_type == DatabaseType.FIRESTORE:
            if not settings.firestore_project_id:
                raise ValueError("使用 Firestore 需要設定 FIRESTORE_PROJECT_ID")
            _storage = FirestoreStorage(settings.firestore_project_id)
        else:
            # 預設使用 SQLite
            _storage = SQLiteStorage(settings.database_url)

    return _storage


async def save_conversation(
    user_id: str,
    event_type: str,
    message_type: str | None,
    message_text: str | None,
    reply_token: str | None,
    raw_event: dict,
    route_target: str | None = None,
    route_reason: str | None = None,
) -> str:
    """便捷函數 - 儲存對話"""
    storage = get_storage()
    return await storage.save_event(
        user_id=user_id,
        event_type=event_type,
        message_type=message_type,
        message_text=message_text,
        reply_token=reply_token,
        raw_event=raw_event,
        route_target=route_target,
        route_reason=route_reason,
    )
