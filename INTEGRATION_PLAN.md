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

## 更新紀錄

- 2025-12-02：建立整合計畫
