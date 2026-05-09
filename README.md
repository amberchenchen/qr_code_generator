# QR Code Generator

動態 QR Code 系統。使用者提交長網址，取得短網址 token 與 QR Code 圖片；掃描後 302 轉址至原始 URL，支援更新目標網址與軟刪除。QR Code 建立後自動 3 分鐘過期。

## 系統架構

```
Client → API Gateway → QR Code Service → Cache (Redis / In-Memory)
                                       ↓
                                   Database (SQLite / PostgreSQL)
```

**短網址格式：** `http://localhost:8000/r/{qr_token}`

**Token 生成：** `SHA-256(url + nonce)` → 取前 8 bytes → Base62 `[A-Za-z0-9]` → 取前 7 碼

## 快速開始

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

API 文件：http://localhost:8000/docs

---

## API 流程

### POST /api/qr/create — 建立 QR Code

```bash
curl -X POST http://localhost:8000/api/qr/create \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
```

**Request：** 只需傳 `url`，過期時間由後端自動設為 3 分鐘後。

**流程：**

```
Client 送出 url
  │
  ├─ URL 驗證 + 正規化
  │     normalize("http://Example.com/") → "https://example.com/"
  │     檢查格式、scheme、blocklist
  │
  ├─ Token 生成（SHA-256 + nonce）
  │     nonce = os.urandom(16)        ← 密碼學安全亂數
  │     SHA-256(url + nonce) → 32 bytes
  │     取前 8 bytes → int → Base62 → 7 碼
  │     查 DB 確認唯一（碰撞最多重試 5 次）
  │
  ├─ 寫入 DB
  │     INSERT INTO qr_codes (qr_token, original_url, expires_at=now+3min, ...)
  │
  ├─ 寫入 Cache
  │     cache.set("kmCwDoO", "https://example.com/")  TTL=5min
  │
  └─ 回傳
```

```json
{
  "token": "kmCwDoO",
  "short_url": "http://localhost:8000/r/kmCwDoO",
  "qr_code_url": "http://localhost:8000/api/qr/kmCwDoO/image",
  "original_url": "https://example.com/",
  "created_at": "2026-05-09T08:39:04",
  "updated_at": "2026-05-09T08:39:04",
  "expires_at": "2026-05-09T08:42:04",
  "is_deleted": false
}
```

---

### GET /r/{token} — 302 轉址（掃 QR Code）

```bash
curl -L http://localhost:8000/r/kmCwDoO
```

**流程：**

```
掃 QR → 開啟 http://localhost:8000/r/kmCwDoO
  │
  ├─ cache.get(token)
  │     hit  → 直接 302，略過 DB（高頻熱路徑）
  │     miss ↓
  │
  ├─ DB 查 qr_token = "kmCwDoO"
  │     → 找不到           → 404 Not Found
  │     → is_deleted=True  → 410 Gone
  │     → expires_at < now → 410 Gone
  │
  ├─ cache.set(token, url)  ← 暖快取，下次 hit
  │
  ├─ 記錄掃描
  │     INSERT INTO scan_logs (qr_token, ip_address)
  │     qr_codes.scan_count += 1
  │
  └─ HTTP 302 Location: https://example.com/
```

> 用 302 不用 301：瀏覽器不快取，URL 更新或刪除後掃描立即生效。

---

### GET /api/qr/{token} — 查詢 QR Code 資訊

```bash
curl http://localhost:8000/api/qr/kmCwDoO
```

**流程：**

```
  ├─ DB 查 qr_token = "kmCwDoO"
  │     → 找不到 → 404
  │
  └─ 回傳 token metadata（short_url、qr_code_url、expires_at、is_deleted）
```

---

### PATCH /api/qr/{token} — 更新目標 URL

```bash
curl -X PATCH http://localhost:8000/api/qr/kmCwDoO \
  -H "Content-Type: application/json" \
  -d '{"url": "https://new-url.com"}'
```

**Request：** 只需傳新的 `url`，過期時間自動重設為 3 分鐘後。

**流程：**

```
  ├─ DB 查 token，確認存在且 is_deleted=False
  │
  ├─ 新 URL 驗證 + 正規化
  │
  ├─ 更新 DB
  │     UPDATE qr_codes
  │     SET original_url=..., expires_at=now+3min, updated_at=...
  │     WHERE qr_token=...
  │
  ├─ cache.delete(token)  ← invalidate，強制下次掃描回 DB 拿新 URL
  │
  └─ 回傳更新後的 metadata
```

> QR Code 圖片不需重產，因為圖片只編碼短網址 `/r/{token}`，目標 URL 存在 DB。

---

### DELETE /api/qr/{token} — 軟刪除

```bash
curl -X DELETE http://localhost:8000/api/qr/kmCwDoO
```

**流程：**

```
  ├─ DB 查 token，確認存在且尚未刪除
  │
  ├─ 軟刪除（不移除資料）
  │     UPDATE qr_codes SET is_deleted=True, updated_at=... WHERE qr_token=...
  │
  ├─ cache.delete(token)  ← invalidate
  │
  └─ 之後掃描 /r/kmCwDoO → 410 Gone
```

---

### GET /api/qr/{token}/image — 取得 QR Code 圖片

```bash
curl -o qr.png http://localhost:8000/api/qr/kmCwDoO/image
# Content-Type: image/png
```

**流程：**

```
  ├─ DB 查 token 存在
  │
  ├─ 即時產生圖片（不落地，不存檔）
  │     short_url = "{base_url}/r/kmCwDoO"
  │     SHA-256 + qrcode lib → PIL Image → io.BytesIO → PNG bytes
  │
  └─ HTTP 200  Content-Type: image/png
```

> 圖片不存磁碟，每次 render。目標 URL 改了也不需重產圖，圖片只編碼短網址。

---

### GET /api/qr/{token}/analytics — 查詢掃描數據

```bash
curl http://localhost:8000/api/qr/kmCwDoO/analytics
```

**流程：**

```
  ├─ DB 查 token 存在
  │
  ├─ 撈 scan_logs
  │     SELECT strftime('%Y-%m-%d', scanned_at), COUNT(*)
  │     FROM scan_logs WHERE qr_token="kmCwDoO"
  │     GROUP BY date ORDER BY date
  │
  └─ 回傳
```

```json
{
  "token": "kmCwDoO",
  "total_scans": 42,
  "scans_by_day": [
    {"date": "2026-05-09", "count": 42}
  ]
}
```

---

## 設計重點

**為什麼用動態 QR Code？**
QR Code 本身只編碼短網址（`/r/{token}`），圖片永遠不變。目標 URL 存在 DB，隨時可更新，掃描自動反映新網址。

**為什麼用 302 不用 301？**
301 瀏覽器會永久快取，之後更新目標 URL 無效。302 每次都重新查詢，支援即時更新。

**Token 生成：SHA-256 + nonce**
`os.urandom(16)` 提供密碼學安全亂數，避免高併發下 timestamp-based 方法的碰撞問題。碰撞時由呼叫端 retry，最多 5 次。

**Cache 設計**
`qr_token → original_url` 快取（模擬 Redis）。Cache hit 直接 302，不查 DB。更新或刪除時主動 invalidate，確保資料一致。

**過期時間**
建立與更新時自動設為 3 分鐘後（UTC），使用者不需手動輸入。

---

## 專案結構

```
qr_code_generator/
├── main.py                  # FastAPI 入口，建立 DB 資料表
├── database.py              # SQLAlchemy session
├── models.py                # QRCode、ScanLog 資料表
├── schemas.py               # Pydantic 請求/回應 schema
├── services/
│   ├── token_generator.py   # SHA-256 + nonce + Base62 token 生成
│   ├── url_validator.py     # URL 正規化 + 驗證
│   ├── cache.py             # In-memory cache（可換 Redis）
│   └── qr_image.py          # 產生 QR Code PNG
├── routers/
│   ├── qr_router.py         # CRUD API 路由
│   └── redirect_router.py   # 302 轉址路由
└── test_api.py              # Smoke test
```

## 執行測試

```bash
# 先啟動 server，再執行
python test_api.py
```
