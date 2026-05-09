# QR Code Generator

動態 QR Code 系統。使用者提交長網址，取得短網址 token 與 QR Code 圖片；掃描後 302 轉址至原始 URL，支援更新目標網址、軟刪除與過期設定。

## 系統架構

```
Client → API Gateway → QR Code Service → Cache (Redis / In-Memory)
                                       ↓
                                   Database (SQLite / PostgreSQL)
```

**短網址格式：** `http://localhost:8000/r/{qr_token}`

**Token 生成：** `hash(url + timestamp_ns)` → SHA-256 → Base62 `[A-Za-z0-9]` → 取前 7 碼

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

**流程：**

```
Client 送出 url
  │
  ├─ URL 驗證 + 正規化
  │     normalize("http://Example.com/") → "https://example.com/"
  │     檢查格式、scheme、blocklist
  │
  ├─ Token 生成
  │     hash(url + timestamp_ns) → SHA-256 → Base62 → 7 碼
  │     查 DB 確認唯一（碰撞最多重試 5 次）
  │
  ├─ 寫入 DB
  │     INSERT INTO qr_codes (qr_token, original_url, ...)
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
  "expires_at": null,
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
  ├─ DB 查 qr_token = "kmCwDoO"
  │     → is_deleted? → 410 Gone
  │     → expires_at < now? → 410 Gone
  │     → 找不到? → 404 Not Found
  │
  ├─ Cache 更新
  │     cache.set("kmCwDoO", original_url)
  │
  ├─ 記錄掃描
  │     INSERT INTO scan_logs (qr_token, ip_address)
  │     qr_codes.scan_count += 1
  │
  └─ HTTP 302 Location: https://example.com/
        → 瀏覽器自動跳至原始 URL
```

> 用 302 不用 301：瀏覽器不快取，URL 更新後掃描立即反映新目標。

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
  └─ 回傳 token metadata（含 short_url、qr_code_url、is_deleted、expires_at）
```

---

### PATCH /api/qr/{token} — 更新目標 URL

```bash
curl -X PATCH http://localhost:8000/api/qr/kmCwDoO \
  -H "Content-Type: application/json" \
  -d '{"url": "https://new-url.com"}'
```

**流程：**

```
  ├─ DB 查 token，確認存在且未刪除
  │
  ├─ 新 URL 驗證 + 正規化
  │
  ├─ 更新 DB
  │     UPDATE qr_codes SET original_url=..., updated_at=... WHERE qr_token=...
  │
  ├─ Cache Invalidate
  │     cache.delete("kmCwDoO")
  │     → 下次掃描強制回 DB 拿新 URL
  │
  └─ 回傳更新後的 metadata
```

> QR Code 圖片不需要重產，因為圖片只編碼短網址 `/r/{token}`，目標 URL 存在 DB。

---

### DELETE /api/qr/{token} — 軟刪除

```bash
curl -X DELETE http://localhost:8000/api/qr/kmCwDoO
```

**流程：**

```
  ├─ DB 查 token，確認存在且尚未刪除
  │
  ├─ 軟刪除（不真的移除資料）
  │     UPDATE qr_codes SET is_deleted=True WHERE qr_token=...
  │
  ├─ Cache Invalidate
  │     cache.delete("kmCwDoO")
  │
  └─ 之後掃描 /r/kmCwDoO → 410 Gone
```

> 軟刪除保留紀錄，方便 audit log 與還原。

---

### GET /api/qr/{token}/image — 取得 QR Code 圖片

```bash
curl -o qr.png http://localhost:8000/api/qr/kmCwDoO/image
```

**流程：**

```
  ├─ DB 查 token 存在
  │
  ├─ 即時產生圖片（不落地，不存檔）
  │     short_url = "http://localhost:8000/r/kmCwDoO"
  │     generate_qr_png(short_url)
  │       → qrcode.QRCode.add_data(url)
  │       → PIL Image → io.BytesIO → PNG bytes
  │
  └─ HTTP 200  Content-Type: image/png
        → bytes 直接寫進 response，記憶體釋放
```

> 圖片不存在磁碟，每次請求即時 render。目標 URL 改了也不需要重產圖，因為圖片編碼的是短網址。

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
  │     FROM scan_logs WHERE qr_token = "kmCwDoO"
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

**Token 碰撞處理**
生成時加入 `timestamp_ns` 確保隨機性，插入前查 DB 確認唯一，最多重試 5 次。

**Cache 設計**
`qr_token → original_url` 快取 5 分鐘（模擬 Redis）。更新或刪除時主動 invalidate，確保資料一致。

---

## 專案結構

```
qr_code_generator/
├── main.py                  # FastAPI 入口，建立 DB 資料表
├── database.py              # SQLAlchemy session
├── models.py                # QRCode、ScanLog 資料表
├── schemas.py               # Pydantic 請求/回應 schema
├── services/
│   ├── token_generator.py   # Base62 token 生成
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
