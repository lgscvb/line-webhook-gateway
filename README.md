# LINE 系統整合專案

這個倉庫包含 LINE 系統整合的規劃文件和工具程式碼。

## 最終決定的架構

經過評估，決定**不使用中繼站**，改用更簡潔的 API 整合方式：

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

## 整合計畫

詳見 [INTEGRATION_PLAN.md](./INTEGRATION_PLAN.md)

### 整合步驟摘要

1. **hourjungle** 新增 3 個 GET API：
   - `GET /api/line/customer/{line_id}/next-payment`
   - `GET /api/line/customer/{line_id}/payment-history`
   - `GET /api/line/customer/{line_id}/contracts`

2. **brain** 新增整合邏輯：
   - 判斷關鍵字（下次繳費、繳費紀錄、查看合約）
   - 呼叫 hourjungle API 取得資料
   - 格式化後回覆用戶

3. **LINE 後台**：
   - Webhook URL 改指向 brain

---

## 備用方案：中繼站（如果未來需要）

如果未來有更複雜的分流需求，這個倉庫也包含一個完整的中繼站實作。

### 中繼站架構圖

```
[使用者]
   ⬇ (傳送訊息)
[LINE Platform]
   ⬇ (Webhook)
[【中繼站】] ⬅ 這是唯一的接收口
   ⬇ (解析訊息內容)
   ╠══ 1. 儲存對話紀錄 (Data Asset) ➜ AI 訓練數據
   ╠══ 2. 路由判斷 (Router)
   ║     ╠══ 關鍵字 A (開發票/地址) ➜ 舊系統
   ║     ╚══ 其他問題 ➜ 新系統 (AI Agent)
   ╚══ 3. 統一回覆 ➜ 避免 Reply Token 衝突
```

## 快速開始

### 1. 安裝依賴

```bash
# 建立虛擬環境
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

# 安裝依賴
pip install -e .
```

### 2. 設定環境變數

```bash
cp .env.example .env
# 編輯 .env 填入你的設定
```

### 3. 啟動服務

```bash
# 開發模式 (熱重載)
python run.py

# 或使用 Docker
docker-compose up -d
```

### 4. 設定 LINE Webhook URL

在 LINE Developers Console 將 Webhook URL 設為：
```
https://你的網域/webhook
```

## 環境變數說明

| 變數名稱 | 說明 | 預設值 |
|---------|------|--------|
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Channel Access Token | - |
| `LINE_CHANNEL_SECRET` | LINE Channel Secret | - |
| `OLD_SYSTEM_WEBHOOK_URL` | 舊系統的 Webhook URL | - |
| `NEW_SYSTEM_WEBHOOK_URL` | 新系統的 Webhook URL | - |
| `REPLY_MODE` | 回覆模式 | `unified` |
| `OLD_SYSTEM_KEYWORDS` | 觸發舊系統的關鍵字 (逗號分隔) | `開發票,地址,預約,轉帳,繳費` |
| `HIGH_VALUE_KEYWORDS` | 高價值關鍵字 (觸發通知) | `設立公司,開公司,創業` |
| `DATABASE_TYPE` | 資料庫類型 | `sqlite` |

## 回覆模式

### `unified` (建議)
中繼站統一回覆。後端系統只負責產生回應內容，由中繼站呼叫 LINE API 回覆。

### `delegate_old`
委託舊系統回覆。當路由到舊系統時，原封不動轉發 Request，讓舊系統自己回覆。

### `delegate_new`
委託新系統回覆。當路由到新系統時，讓新系統自己回覆。

## 後端系統接入指南

如果使用 `unified` 模式，後端系統需要回傳以下格式：

```json
{
  "reply_text": "這是要回覆給使用者的訊息"
}
```

如果使用 `delegate_*` 模式，後端系統會收到完整的 LINE Webhook Request，
需自行處理回覆。

## 部署建議

### GCP Cloud Run (推薦)

```bash
# 建置並推送 Docker image
gcloud builds submit --tag gcr.io/YOUR_PROJECT/line-gateway

# 部署到 Cloud Run
gcloud run deploy line-gateway \
  --image gcr.io/YOUR_PROJECT/line-gateway \
  --platform managed \
  --region asia-east1 \
  --allow-unauthenticated \
  --set-env-vars LINE_CHANNEL_ACCESS_TOKEN=xxx,LINE_CHANNEL_SECRET=xxx
```

### 其他平台
- Render
- Fly.io
- AWS Lambda (需使用 Mangum adapter)

## 專案結構

```
line-webhook-gateway/
├── src/line_gateway/
│   ├── __init__.py
│   ├── main.py          # FastAPI 主程式
│   ├── config.py        # 設定模組
│   ├── router.py        # 路由判斷邏輯
│   ├── forwarder.py     # Webhook 轉發服務
│   ├── storage.py       # 對話儲存
│   └── line_reply.py    # LINE 回覆服務
├── .env.example
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── run.py               # 開發模式啟動腳本
└── README.md
```
