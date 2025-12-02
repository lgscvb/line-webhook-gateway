# LINE 系統整合計畫

## 目標架構

```
[用戶發訊息]
      ↓
[LINE Platform]
      ↓ (Webhook)
[brain] ← 唯一入口，處理所有訊息
      ↓
      ├── 一般問題 → AI 回覆
      │
      └── 繳費/合約相關 → 呼叫 hourjungle API → 回覆用戶

[hourjungle]
      └── 催款通知 → 直接用 Push Message API（不經過 brain）
```

## 整合優點

- Webhook 只有 brain 一個入口，不會衝突
- Reply Token 由 brain 統一使用
- hourjungle 的催款通知繼續獨立運作
- 不需要中繼站

---

## 階段一：測試現有系統

- [ ] hourjungle 全部功能測試完成
- [ ] brain 全部功能測試完成
- [ ] 兩個系統都 commit 到 git

---

## 階段二：hourjungle 新增 API

### 需要新增的檔案

**檔案位置**: `hourjungle_backend/app/Http/Controllers/LineApiController.php`

```php
<?php

namespace App\Http\Controllers;

use Illuminate\Http\Request;
use App\Models\Customer;
use App\Models\Project;
use App\Models\PaymentHistory;

/**
 * LINE 外部 API
 * 提供給 brain 系統查詢客戶資料
 */
class LineApiController extends Controller
{
    /**
     * 查詢下次繳費
     * GET /api/line/customer/{line_id}/next-payment
     */
    public function nextPayment($lineId)
    {
        $customer = Customer::where('line_id', $lineId)->first();

        if (!$customer) {
            return response()->json([
                'success' => false,
                'message' => '查無客戶資料'
            ], 404);
        }

        $projects = Project::where('customer_id', $customer->id)
            ->where('status', 1)
            ->orderBy('next_pay_day', 'asc')
            ->get();

        if ($projects->isEmpty()) {
            return response()->json([
                'success' => true,
                'message' => '目前沒有有效合約',
                'data' => []
            ]);
        }

        $payments = $projects->map(function ($project) {
            return [
                'project_name' => $project->projectName,
                'next_pay_date' => date('Y-m-d', strtotime($project->next_pay_day)),
                'amount' => intval($project->current_payment)
            ];
        });

        return response()->json([
            'success' => true,
            'data' => $payments
        ]);
    }

    /**
     * 查詢繳費紀錄
     * GET /api/line/customer/{line_id}/payment-history
     */
    public function paymentHistory($lineId)
    {
        $customer = Customer::where('line_id', $lineId)->first();

        if (!$customer) {
            return response()->json([
                'success' => false,
                'message' => '查無客戶資料'
            ], 404);
        }

        $histories = PaymentHistory::where('customer_id', $customer->id)
            ->orderBy('created_at', 'desc')
            ->limit(10)
            ->get();

        if ($histories->isEmpty()) {
            return response()->json([
                'success' => true,
                'message' => '沒有繳費紀錄',
                'data' => []
            ]);
        }

        $records = $histories->map(function ($item) {
            $payTypeMap = [
                'credit' => '信用卡',
                'cash' => '現金',
                'transfer' => '轉帳'
            ];

            return [
                'pay_date' => date('Y-m-d', strtotime($item->pay_day)),
                'pay_type' => $payTypeMap[$item->pay_type] ?? '其他',
                'amount' => intval($item->amount)
            ];
        });

        return response()->json([
            'success' => true,
            'data' => $records
        ]);
    }

    /**
     * 查詢合約
     * GET /api/line/customer/{line_id}/contracts
     */
    public function contracts($lineId)
    {
        $customer = Customer::where('line_id', $lineId)->first();

        if (!$customer) {
            return response()->json([
                'success' => false,
                'message' => '查無客戶資料'
            ], 404);
        }

        $projects = Project::where('customer_id', $customer->id)
            ->where('status', 1)
            ->get();

        if ($projects->isEmpty()) {
            return response()->json([
                'success' => true,
                'message' => '目前沒有有效合約',
                'data' => []
            ]);
        }

        $contracts = $projects->map(function ($project) {
            $pdfUrl = null;
            if ($project->contract_path) {
                $pdfPublicPath = "storage/" . str_replace('public/', '', $project->contract_path);
                $pdfUrl = url($pdfPublicPath);
            }

            return [
                'project_name' => $project->projectName,
                'contract_url' => $pdfUrl
            ];
        });

        return response()->json([
            'success' => true,
            'data' => $contracts
        ]);
    }
}
```

### 需要新增的路由

**檔案位置**: `hourjungle_backend/routes/api.php`

在檔案中新增：

```php
// LINE 外部 API（給 brain 系統用）
Route::prefix('line/customer/{line_id}')->group(function () {
    Route::get('/next-payment', [LineApiController::class, 'nextPayment']);
    Route::get('/payment-history', [LineApiController::class, 'paymentHistory']);
    Route::get('/contracts', [LineApiController::class, 'contracts']);
});
```

### API 規格

| 端點 | 方法 | 說明 |
|------|------|------|
| `/api/line/customer/{line_id}/next-payment` | GET | 查詢下次繳費 |
| `/api/line/customer/{line_id}/payment-history` | GET | 查詢繳費紀錄 |
| `/api/line/customer/{line_id}/contracts` | GET | 查詢合約列表 |

### 回傳格式範例

**下次繳費**
```json
{
  "success": true,
  "data": [
    {
      "project_name": "A區辦公室",
      "next_pay_date": "2025-01-15",
      "amount": 15000
    }
  ]
}
```

**繳費紀錄**
```json
{
  "success": true,
  "data": [
    {
      "pay_date": "2024-12-15",
      "pay_type": "轉帳",
      "amount": 15000
    }
  ]
}
```

**合約列表**
```json
{
  "success": true,
  "data": [
    {
      "project_name": "A區辦公室",
      "contract_url": "https://example.com/storage/contracts/xxx.pdf"
    }
  ]
}
```

---

## 階段三：brain 新增整合邏輯

### 需要新增的檔案

**檔案位置**: `brain/backend/services/hourjungle_client.py`

```python
"""Hour Jungle API 客戶端 - 查詢繳費/合約資料"""

import httpx
from typing import Optional
import os


class HourJungleClient:
    """Hour Jungle API 客戶端"""

    def __init__(self):
        self.base_url = os.getenv("HOURJUNGLE_API_URL", "https://your-hourjungle-domain.com")
        self.client = httpx.AsyncClient(timeout=10.0)

    async def get_next_payment(self, line_id: str) -> dict:
        """查詢下次繳費"""
        try:
            response = await self.client.get(
                f"{self.base_url}/api/line/customer/{line_id}/next-payment"
            )
            return response.json()
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def get_payment_history(self, line_id: str) -> dict:
        """查詢繳費紀錄"""
        try:
            response = await self.client.get(
                f"{self.base_url}/api/line/customer/{line_id}/payment-history"
            )
            return response.json()
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def get_contracts(self, line_id: str) -> dict:
        """查詢合約"""
        try:
            response = await self.client.get(
                f"{self.base_url}/api/line/customer/{line_id}/contracts"
            )
            return response.json()
        except Exception as e:
            return {"success": False, "message": str(e)}

    def format_next_payment(self, data: dict) -> str:
        """格式化下次繳費資訊"""
        if not data.get("success"):
            return data.get("message", "查詢失敗")

        payments = data.get("data", [])
        if not payments:
            return "目前沒有待繳費用"

        lines = []
        for p in payments:
            lines.append(
                f"合約：{p['project_name']}\n"
                f"下次繳費日：{p['next_pay_date']}\n"
                f"金額：${p['amount']:,}"
            )
        return "\n\n".join(lines)

    def format_payment_history(self, data: dict) -> str:
        """格式化繳費紀錄"""
        if not data.get("success"):
            return data.get("message", "查詢失敗")

        records = data.get("data", [])
        if not records:
            return "沒有繳費紀錄"

        lines = ["最近 10 筆繳費紀錄："]
        for r in records:
            lines.append(f"• {r['pay_date']} | {r['pay_type']} | ${r['amount']:,}")
        return "\n".join(lines)

    def format_contracts(self, data: dict) -> str:
        """格式化合約資訊"""
        if not data.get("success"):
            return data.get("message", "查詢失敗")

        contracts = data.get("data", [])
        if not contracts:
            return "目前沒有有效合約"

        lines = []
        for c in contracts:
            text = f"合約：{c['project_name']}"
            if c.get("contract_url"):
                text += f"\n查看合約：{c['contract_url']}"
            lines.append(text)
        return "\n\n".join(lines)

    async def close(self):
        await self.client.aclose()
```

### brain 的 webhook 處理邏輯修改

在處理訊息時，加入關鍵字判斷：

```python
# 在 webhooks.py 中

from services.hourjungle_client import HourJungleClient

hourjungle = HourJungleClient()

async def process_message(user_id: str, message_text: str) -> str:
    """處理訊息，判斷是否需要查詢 hourjungle"""

    # 繳費/合約相關關鍵字
    if message_text == "下次繳費":
        data = await hourjungle.get_next_payment(user_id)
        return hourjungle.format_next_payment(data)

    elif message_text == "繳費紀錄":
        data = await hourjungle.get_payment_history(user_id)
        return hourjungle.format_payment_history(data)

    elif message_text == "查看合約":
        data = await hourjungle.get_contracts(user_id)
        return hourjungle.format_contracts(data)

    else:
        # 其他訊息交給 AI 處理
        return await generate_ai_response(message_text, user_id)
```

### brain 需要新增的環境變數

```env
# Hour Jungle API
HOURJUNGLE_API_URL=https://your-hourjungle-domain.com
```

---

## 階段四：LINE 後台設定

1. 登入 LINE Developers Console
2. 找到你的 Channel
3. 將 Webhook URL 改為 brain 的網址：
   ```
   https://your-brain-domain.com/webhook/line
   ```
4. 確認 Webhook 已啟用

---

## 階段五：測試驗證

- [ ] 測試「下次繳費」→ brain 呼叫 hourjungle API → 正確回覆
- [ ] 測試「繳費紀錄」→ brain 呼叫 hourjungle API → 正確回覆
- [ ] 測試「查看合約」→ brain 呼叫 hourjungle API → 正確回覆
- [ ] 測試一般問題 → brain AI 回覆
- [ ] 測試 hourjungle 催款通知 → Push Message 正常發送

---

## 注意事項

1. **API 安全性**：建議為 hourjungle 的 API 加上驗證機制（API Key 或 IP 白名單）
2. **錯誤處理**：brain 呼叫 API 失敗時，要有友善的錯誤訊息
3. **日誌記錄**：兩邊都要記錄 API 呼叫日誌，方便除錯

---

## 檔案清單

### 需要新增的檔案

| 系統 | 檔案路徑 | 說明 |
|------|---------|------|
| hourjungle | `app/Http/Controllers/LineApiController.php` | 新的 API Controller |
| brain | `backend/services/hourjungle_client.py` | API 客戶端 |

### 需要修改的檔案

| 系統 | 檔案路徑 | 修改內容 |
|------|---------|---------|
| hourjungle | `routes/api.php` | 新增 API 路由 |
| brain | `backend/api/routes/webhooks.py` | 加入關鍵字判斷邏輯 |
| brain | `.env` | 新增 HOURJUNGLE_API_URL |

---

## 時程預估

| 階段 | 工作項目 | 預估時間 |
|------|---------|---------|
| 1 | 測試現有系統 | - |
| 2 | hourjungle 新增 API | 30 分鐘 |
| 3 | brain 新增整合邏輯 | 1 小時 |
| 4 | LINE 後台設定 | 5 分鐘 |
| 5 | 整合測試 | 30 分鐘 |

---

## 階段六：AI 費用監控系統（未來規劃）

### 目標

追蹤每次 AI 呼叫的 Token 使用量和費用，當費用超過預算時發出警報。
未來可根據數據決定是否切換到 OpenRouter 使用更便宜的模型。

### 資料庫模型

**檔案位置**: `brain/backend/db/models.py`

新增 `AIUsageLog` 表：

```python
class AIUsageLog(Base):
    """AI 使用紀錄"""
    __tablename__ = "ai_usage_logs"

    id = Column(Integer, primary_key=True, index=True)

    # 關聯
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=True)

    # 模型資訊
    model = Column(String(100), nullable=False)  # claude-3-5-sonnet-20241022
    provider = Column(String(50), default="anthropic")  # anthropic, openrouter

    # Token 統計
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)

    # 費用（美元，小數點後 6 位）
    input_cost = Column(Float, default=0.0)
    output_cost = Column(Float, default=0.0)
    total_cost = Column(Float, default=0.0)

    # 時間
    created_at = Column(DateTime, default=datetime.utcnow)
```

### 費用計算服務

**檔案位置**: `brain/backend/services/usage_tracker.py`

```python
"""AI 使用量追蹤服務"""

from datetime import datetime, timedelta
from sqlalchemy import func
from db.models import AIUsageLog
from db.database import get_db

# 模型費用表（每 1M tokens 的美元價格）
MODEL_PRICING = {
    "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-opus-4-20250514": {"input": 15.00, "output": 75.00},
    # OpenRouter 模型（未來）
    "deepseek/deepseek-chat": {"input": 0.14, "output": 0.28},
    "google/gemini-flash-1.5": {"input": 0.075, "output": 0.30},
}


class UsageTracker:
    """使用量追蹤器"""

    def calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> dict:
        """計算費用"""
        pricing = MODEL_PRICING.get(model, {"input": 3.0, "output": 15.0})

        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]

        return {
            "input_cost": round(input_cost, 6),
            "output_cost": round(output_cost, 6),
            "total_cost": round(input_cost + output_cost, 6)
        }

    async def log_usage(
        self,
        db,
        model: str,
        input_tokens: int,
        output_tokens: int,
        message_id: int = None,
        provider: str = "anthropic"
    ):
        """記錄使用量"""
        costs = self.calculate_cost(model, input_tokens, output_tokens)

        log = AIUsageLog(
            message_id=message_id,
            model=model,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            **costs
        )
        db.add(log)
        await db.commit()
        return log

    async def get_daily_stats(self, db, date: datetime = None) -> dict:
        """取得每日統計"""
        if date is None:
            date = datetime.utcnow().date()

        start = datetime.combine(date, datetime.min.time())
        end = start + timedelta(days=1)

        result = await db.execute(
            select(
                func.sum(AIUsageLog.input_tokens).label("total_input"),
                func.sum(AIUsageLog.output_tokens).label("total_output"),
                func.sum(AIUsageLog.total_cost).label("total_cost"),
                func.count(AIUsageLog.id).label("request_count")
            ).where(
                AIUsageLog.created_at >= start,
                AIUsageLog.created_at < end
            )
        )
        row = result.first()

        return {
            "date": date.isoformat(),
            "total_input_tokens": row.total_input or 0,
            "total_output_tokens": row.total_output or 0,
            "total_cost_usd": round(row.total_cost or 0, 4),
            "request_count": row.request_count or 0
        }

    async def get_monthly_stats(self, db, year: int = None, month: int = None) -> dict:
        """取得每月統計"""
        now = datetime.utcnow()
        if year is None:
            year = now.year
        if month is None:
            month = now.month

        start = datetime(year, month, 1)
        if month == 12:
            end = datetime(year + 1, 1, 1)
        else:
            end = datetime(year, month + 1, 1)

        result = await db.execute(
            select(
                func.sum(AIUsageLog.total_cost).label("total_cost"),
                func.count(AIUsageLog.id).label("request_count")
            ).where(
                AIUsageLog.created_at >= start,
                AIUsageLog.created_at < end
            )
        )
        row = result.first()

        return {
            "year": year,
            "month": month,
            "total_cost_usd": round(row.total_cost or 0, 2),
            "request_count": row.request_count or 0
        }

    async def get_model_breakdown(self, db, days: int = 30) -> list:
        """取得各模型使用佔比"""
        start = datetime.utcnow() - timedelta(days=days)

        result = await db.execute(
            select(
                AIUsageLog.model,
                func.count(AIUsageLog.id).label("count"),
                func.sum(AIUsageLog.total_cost).label("cost")
            ).where(
                AIUsageLog.created_at >= start
            ).group_by(AIUsageLog.model)
        )

        return [
            {
                "model": row.model,
                "request_count": row.count,
                "total_cost_usd": round(row.cost or 0, 4)
            }
            for row in result.fetchall()
        ]
```

### Dashboard API

**檔案位置**: `brain/backend/api/routes/stats.py`

新增以下 API：

```python
@router.get("/stats/ai-usage/today")
async def get_today_usage(db: AsyncSession = Depends(get_db)):
    """取得今日 AI 使用統計"""
    tracker = UsageTracker()
    return await tracker.get_daily_stats(db)

@router.get("/stats/ai-usage/monthly")
async def get_monthly_usage(
    year: int = None,
    month: int = None,
    db: AsyncSession = Depends(get_db)
):
    """取得每月 AI 使用統計"""
    tracker = UsageTracker()
    return await tracker.get_monthly_stats(db, year, month)

@router.get("/stats/ai-usage/by-model")
async def get_usage_by_model(
    days: int = 30,
    db: AsyncSession = Depends(get_db)
):
    """取得各模型使用佔比"""
    tracker = UsageTracker()
    return await tracker.get_model_breakdown(db, days)

@router.get("/stats/ai-usage/budget-alert")
async def check_budget(
    monthly_budget_usd: float = 50.0,
    db: AsyncSession = Depends(get_db)
):
    """檢查是否超過預算"""
    tracker = UsageTracker()
    stats = await tracker.get_monthly_stats(db)

    usage_percent = (stats["total_cost_usd"] / monthly_budget_usd) * 100

    return {
        **stats,
        "budget_usd": monthly_budget_usd,
        "usage_percent": round(usage_percent, 1),
        "is_over_budget": stats["total_cost_usd"] > monthly_budget_usd,
        "alert_level": "critical" if usage_percent > 100 else "warning" if usage_percent > 80 else "ok"
    }
```

### 前端 Dashboard 顯示

在前端新增一個「AI 費用」頁面，顯示：

1. **今日統計卡片**
   - 今日花費 $X.XX
   - 今日請求數 XXX 次
   - Input/Output tokens

2. **月度統計**
   - 本月花費 vs 預算
   - 進度條（綠色/黃色/紅色）

3. **模型使用佔比**
   - 圓餅圖顯示各模型佔比
   - 費用 vs 請求數

4. **費用趨勢**
   - 過去 30 天每日費用折線圖

### 預算警報

當費用超過設定閾值時：
- 80%：Dashboard 顯示黃色警告
- 100%：Dashboard 顯示紅色警告 + 發送通知

### 未來優化：Router + Worker 模式

當有足夠數據後，可以實作智慧路由：

```python
class IntentRouter:
    """用便宜的模型判斷意圖，再分派給對應的模型"""

    async def route(self, message: str) -> str:
        """
        用 Haiku 快速分類，然後選擇模型：
        - 簡單問候 → Haiku (最便宜)
        - 一般問題 → Sonnet (中等)
        - 複雜諮詢 → Opus (最強)
        - 繳費查詢 → 直接查 API（不用 AI）
        """
        pass
```

### 未來優化：OpenRouter 整合

如果 Claude 太貴，可以切換到 OpenRouter 使用便宜模型：

| 模型 | Input/1M | Output/1M | 用途 |
|------|----------|-----------|------|
| DeepSeek Chat | $0.14 | $0.28 | 一般問題 |
| Gemini Flash | $0.075 | $0.30 | 快速回覆 |
| Claude Haiku | $0.80 | $4.00 | 分類路由 |

---

## 階段七：AI 自我進化系統（未來規劃）

### 目標

讓 AI 從人工修改中學習，逐漸提升草稿品質，減少人工修改次數。

### 進化架構

```
生成草稿
     ↓
人工回饋（並行收集）
├── 快速回饋：👍 / 👎
├── 評分：1-5 星
└── 修改原因：文字描述
     ↓
累積數據
     ↓
定期分析 → 更新 Prompt / 規則
     ↓
AI 生成更好的草稿
```

### 資料庫模型修改

**檔案位置**: `brain/backend/db/models.py`

在 `Draft` 模型新增欄位：

```python
class Draft(Base):
    """AI 草稿"""
    __tablename__ = "drafts"

    # ... 原有欄位 ...

    # 人工評分回饋
    is_good = Column(Boolean, nullable=True)          # 快速回饋：好/不好
    rating = Column(Integer, nullable=True)           # 評分：1-5 星
    feedback_reason = Column(Text, nullable=True)     # 人工填寫的修改/不好原因
    feedback_at = Column(DateTime, nullable=True)     # 回饋時間

    # AI 分析結果（自動填入）
    auto_analysis = Column(Text, nullable=True)       # AI 分析的修改原因
    improvement_tags = Column(JSON, nullable=True)    # 改進標籤 ["語氣", "專業度", "完整性"]
```

### API 端點

**檔案位置**: `brain/backend/api/routes/messages.py`

```python
from pydantic import BaseModel
from typing import Optional

class DraftFeedback(BaseModel):
    is_good: Optional[bool] = None      # 快速回饋
    rating: Optional[int] = None        # 1-5 星
    feedback_reason: Optional[str] = None  # 修改原因

@router.post("/drafts/{draft_id}/feedback")
async def submit_draft_feedback(
    draft_id: int,
    feedback: DraftFeedback,
    db: AsyncSession = Depends(get_db)
):
    """提交草稿回饋"""
    draft = await db.get(Draft, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    # 更新回饋
    if feedback.is_good is not None:
        draft.is_good = feedback.is_good
    if feedback.rating is not None:
        draft.rating = max(1, min(5, feedback.rating))  # 限制 1-5
    if feedback.feedback_reason:
        draft.feedback_reason = feedback.feedback_reason

    draft.feedback_at = datetime.utcnow()
    await db.commit()

    return {"success": True, "message": "回饋已記錄"}

@router.get("/stats/feedback-summary")
async def get_feedback_summary(
    days: int = 30,
    db: AsyncSession = Depends(get_db)
):
    """取得回饋統計摘要"""
    start = datetime.utcnow() - timedelta(days=days)

    # 統計好/不好比例
    result = await db.execute(
        select(
            func.count(Draft.id).label("total"),
            func.sum(case((Draft.is_good == True, 1), else_=0)).label("good_count"),
            func.sum(case((Draft.is_good == False, 1), else_=0)).label("bad_count"),
            func.avg(Draft.rating).label("avg_rating")
        ).where(
            Draft.feedback_at >= start,
            Draft.is_good.isnot(None)
        )
    )
    row = result.first()

    return {
        "period_days": days,
        "total_feedback": row.total or 0,
        "good_count": row.good_count or 0,
        "bad_count": row.bad_count or 0,
        "good_rate": round((row.good_count or 0) / max(row.total or 1, 1) * 100, 1),
        "avg_rating": round(row.avg_rating or 0, 2)
    }
```

### 前端 UI 設計

在草稿顯示區域新增回饋元件：

```jsx
// DraftFeedback.jsx
function DraftFeedback({ draftId, onFeedbackSubmit }) {
  const [isGood, setIsGood] = useState(null);
  const [rating, setRating] = useState(0);
  const [reason, setReason] = useState('');

  const handleSubmit = async () => {
    await api.post(`/drafts/${draftId}/feedback`, {
      is_good: isGood,
      rating: rating || null,
      feedback_reason: reason || null
    });
    onFeedbackSubmit();
  };

  return (
    <div className="draft-feedback">
      {/* 快速回饋 */}
      <div className="quick-feedback">
        <button
          className={isGood === true ? 'selected' : ''}
          onClick={() => setIsGood(true)}
        >
          👍 好
        </button>
        <button
          className={isGood === false ? 'selected' : ''}
          onClick={() => setIsGood(false)}
        >
          👎 不好
        </button>
      </div>

      {/* 星級評分 */}
      <div className="star-rating">
        {[1, 2, 3, 4, 5].map(star => (
          <span
            key={star}
            className={star <= rating ? 'filled' : ''}
            onClick={() => setRating(star)}
          >
            ⭐
          </span>
        ))}
      </div>

      {/* 修改原因（當選「不好」或有修改時顯示） */}
      {isGood === false && (
        <textarea
          placeholder="請說明不好的原因，幫助 AI 改進..."
          value={reason}
          onChange={e => setReason(e.target.value)}
        />
      )}

      <button onClick={handleSubmit}>送出回饋</button>
    </div>
  );
}
```

### 自動學習機制

#### 方法 1：RAG + 修改歷史（即時參考）

生成草稿時，查詢過去類似問題的回饋：

```python
# brain/backend/brain/draft_generator.py

async def generate_draft_with_learning(user_message: str, db) -> str:
    """生成草稿，參考過去的修改經驗"""

    # 1. 搜尋類似問題的歷史回饋
    similar_feedbacks = await search_similar_feedbacks(user_message, db, limit=5)

    # 2. 篩選有價值的回饋（評分低 + 有修改原因）
    learning_examples = [
        f for f in similar_feedbacks
        if f.rating and f.rating <= 3 and f.feedback_reason
    ]

    # 3. 組成 Prompt
    learning_context = ""
    if learning_examples:
        learning_context = "\n## 過去類似問題的改進建議：\n"
        for ex in learning_examples:
            learning_context += f"- {ex.feedback_reason}\n"

    prompt = f"""你是專業客服助理。

{learning_context}

## 用戶問題：
{user_message}

請根據上述建議，生成一個高品質的回覆："""

    return await claude.generate(prompt)
```

#### 方法 2：定期 Prompt 優化（排程執行）

每週分析累積的回饋，自動更新 System Prompt：

```python
# brain/backend/brain/prompt_optimizer.py

async def analyze_and_optimize_prompt(db):
    """分析回饋並優化 Prompt"""

    # 1. 取得低評分的回饋
    low_rated = await db.execute(
        select(Draft)
        .where(Draft.rating <= 3, Draft.feedback_reason.isnot(None))
        .order_by(Draft.feedback_at.desc())
        .limit(50)
    )
    feedbacks = low_rated.scalars().all()

    if len(feedbacks) < 10:
        return None  # 數據不足

    # 2. 讓 AI 歸納改進規則
    feedback_text = "\n".join([
        f"- 原因：{f.feedback_reason}"
        for f in feedbacks
    ])

    analysis = await claude.generate(f"""
分析以下客服草稿的修改原因，歸納出 5 條具體的寫作改進規則：

{feedback_text}

請用以下格式輸出：
1. [規則一]
2. [規則二]
...
""")

    # 3. 儲存優化後的規則
    await save_prompt_rules(analysis, db)

    return analysis
```

#### 方法 3：自動標籤分析

自動為每個回饋加上標籤，便於統計分析：

```python
IMPROVEMENT_TAGS = [
    "語氣問題",      # 太生硬、不親切
    "專業度不足",    # 資訊不正確、不完整
    "太長/太短",     # 篇幅問題
    "格式問題",      # 排版、換行
    "用詞不當",      # 用語太官方、太口語
    "缺少關鍵資訊",  # 沒回答到重點
]

async def auto_tag_feedback(feedback_reason: str) -> list[str]:
    """自動為回饋原因加上標籤"""
    result = await claude.generate(f"""
分析以下回饋原因，選擇最相關的標籤（可多選）：

可用標籤：{IMPROVEMENT_TAGS}

回饋原因：{feedback_reason}

只輸出標籤名稱，用逗號分隔：""")

    return [tag.strip() for tag in result.split(",") if tag.strip() in IMPROVEMENT_TAGS]
```

### Dashboard 顯示

在前端新增「AI 學習進度」頁面：

1. **回饋統計**
   - 好評率趨勢圖
   - 平均評分趨勢圖
   - 本週 vs 上週比較

2. **改進標籤分佈**
   - 圓餅圖顯示各標籤佔比
   - 點擊標籤查看具體案例

3. **學習進度**
   - 目前的 Prompt 規則
   - 上次優化時間
   - 手動觸發優化按鈕

### 預期效果

| 指標 | 初期 | 1個月後 | 3個月後 |
|------|------|---------|---------|
| 好評率 | 60% | 75% | 85% |
| 平均評分 | 3.0 | 3.8 | 4.2 |
| 需人工修改比例 | 50% | 30% | 15% |

---

## 更新紀錄

- 2025-12-02：建立整合計畫
- 2025-12-02：新增 AI 費用監控系統規劃
- 2025-12-02：新增 AI 自我進化系統規劃（回饋收集 + 學習機制）
