# WW3 Risk Model — Cloudflare + GitHub Actions 動態架構文檔 (v0.4.0)

## 一、架構圖與組件拓撲 (Architecture Diagram)

本系統以「GitHub（代碼與排程）+ Cloudflare（邊緣計算、儲存與托管）」之全免費 Serverless 架構運作，取代傳統獨立虛擬機或常駐伺服器：

```
+-----------------------------------------------------------------------------------------+
|                                    GitHub Ecosystem                                     |
|                                                                                         |
|  +--------------------+        +---------------------+        +----------------------+  |
|  | git repo (codebase)| -----> | GitHub Actions cron | -----> |  scripts/fetchers/   |  |
|  | - baseline_2026    |        | (00:00 UTC / 08:00  |        |  - World Bank API v2 |  |
|  | - 34 indicators    |        |  Asia/Macau 每日計算)|       |  - Publication check |  |
|  +--------------------+        +----------+----------+        +----------+-----------+  |
+-------------------------------------------|------------------------------|--------------+
                                            |                              | Writes candidates
                                            | Generates & Pushes           v (Human-in-the-loop)
                                            | Snapshot (push_snapshot.py)  data/candidates/
                                            v
+-----------------------------------------------------------------------------------------+
|                                  Cloudflare Ecosystem                                   |
|                                                                                         |
|   +------------------------------------+                                                |
|   | Cloudflare D1 Database             |                                                |
|   | (database_name: ww3-risk)          |                                                |
|   | - index_snapshots                  |                                                |
|   | - indicator_observations           |                                                |
|   +-----------------+------------------+                                                |
|                     |                                                                   |
|                     | SQL Query (DB Binding)                                            |
|                     v                                                                   |
|   +------------------------------------+                                                |
|   | Cloudflare Worker API              |                                                |
|   | (ww3-risk-api)                     |                                                |
|   | - GET /api/risk/latest             |                                                |
|   | - GET /api/risk/history            |                                                |
|   | - GET /api/risk/layers             |                                                |
|   | - GET /api/data-status             |                                                |
|   | (Cache-Control: public, max-age=60)|                                                |
|   +-----------------+------------------+                                                |
|                     |                                                                   |
|                     | Fetch API (AbortController 3s timeout)                            |
|                     v                                                                   |
|   +------------------------------------+        Fallback (if offline / timeout)         |
|   | Cloudflare Pages                   | --------------------------------------------+  |
|   | (ww3-risk-model)                   |                                             |  |
|   | - Standalone Dashboard UI          |                                             v  |
|   | - Live Badge: [即時 API · 2026...] |                                   +-------------------+
|   +------------------------------------+                                   | Embedded JSON     |
|                                                                            | [離線快照(內嵌數據)]|
|                                                                            +-------------------+
+-----------------------------------------------------------------------------------------+
```

---

## 二、數據流向 (Data Flow)

1. **日常數據採集與發布審計 (Data Collection)**：
   - GitHub Actions 每日（00:00 UTC / 澳門時間 08:00）自動觸發。
   - `scripts/fetchers/worldbank.py` 查詢 World Bank v2 API，對齊 5 項宏觀統計系列（軍費佔 GDP、總失業率、青年失業率、化石能源佔比、Gini 指數）。
   - `scripts/fetchers/publication_checker.py` 透過 HTTP HEAD/GET 監測 SIPRI、IMF、ILO、FAO、IEA 等機構出版發布。
   - **嚴格紀律**：抓取產物僅寫入 `data/candidates/` 作為候選與差異報告，**絕不自動覆寫 `data/baseline_2026.json`**。模型基準與評分權重保持專家審核與人工校準紀律。

2. **模型計算與快照寫入 (Recalculation & Snapshot Export)**：
   - Python 模型核心執行 baseline 運算（總指數 83.1、五層結構分、和平閘門、三項非線性共振增益、情境帶、34 指標觀測）。
   - CLI 參數 `--export-snapshot current_snapshot.json` 導出符合 D1 schema 的 JSON 快照。
   - `scripts/push_snapshot.py` 經 Cloudflare D1 REST API 寫入 `index_snapshots` 及 `indicator_observations`（參數化 SQL，杜絕注入）。

3. **邊緣 API 服務 (Edge Worker API)**：
   - Cloudflare Worker (`worker/src/index.js`) 綁定 D1 `DB`，以零依賴微秒級冷啟動響應四個唯讀 REST 端點。
   - 包含短快取 (`max-age=60`) 與全開放 CORS (`Access-Control-Allow-Origin: *`)。
   - 歷史案例標記 `retrospective_estimate: true`。

4. **動態渲染與離線回退 (Frontend Dynamic Hydration & Fallback)**：
   - 靜態頁面生成時內嵌當前模型完整數據（`<script id="ww3-model-data">`）。
   - 帶 `--api-base` 生成之頁面載入後發起 3 秒超時之非同步 fetch。
   - 成功：更新 Gauge 指針、維度橫條、推動因素與品質卡，頂欄顯示 `● 即時 API · [時間]` 綠色徽章。
   - 失敗或超時：無縫回退至內嵌數據，頂欄顯示 `● 離線快照（內嵌數據）`，零白屏、零崩潰。

---

## 三、GitHub Secrets 配置與權限要求 (Secrets & Permissions)

在 GitHub 倉庫 `whypuss/ww3-risk-model` 的 **Settings -> Secrets and variables -> Actions** 中配置以下 Secrets：

| Secret 名稱 | 來源與獲取路徑 | 必要權限 (Permissions) | 作用 |
|---|---|---|---|
| `CLOUDFLARE_API_TOKEN` | Cloudflare Dashboard -> My Profile -> API Tokens -> Create Custom Token | 1. **Account -> D1: Edit**<br>2. **Account -> Cloudflare Pages: Edit**<br>3. **Account -> Workers Scripts: Edit** | 允許 Actions 推送 D1 快照及發布 Pages |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare Dashboard 網址或首頁右側 Overview 欄位 | `cf2aa9a2ddd5a936933715000e4302fe` | 指定操作之 Cloudflare 帳戶 |

> [!NOTE]
> 工作流內建優雅降級邏輯：若未設定上述 Secrets，相關 D1 寫入與 Pages 部署步驟會乾淨跳過（Skip）並在 GitHub Actions 日誌中給出提示，測試與本機構建依舊保持全綠通過。

---

## 四、日常維運操作指南 (Operations Guide)

### 1. 手動觸發排程更新 (Manual Trigger)
- 前往 GitHub 倉儲 -> **Actions** 頁籤。
- 點選左側 **Daily Update & Model Recalculation Pipeline**。
- 點選右側 **Run workflow** -> 選擇 `main` 分支 -> 點擊執行。

### 2. 本地測試與 dry-run
```bash
# 1. 跑測試 (Python 45 項 + Worker 8 項)
python3 -m pytest
node --test worker/tests/index.test.js

# 2. 導出 D1 快照
python3 -m ww3_risk.cli --export-snapshot /tmp/snapshot.json

# 3. 預覽 D1 推送 SQL (不發起網絡請求)
python3 scripts/push_snapshot.py /tmp/snapshot.json --dry-run

# 4. 運行 World Bank 抓取與出版物檢查
python3 scripts/fetchers/worldbank.py --dry-run
python3 scripts/fetchers/publication_checker.py --dry-run
```

### 3. 查看運行日誌與監控
- **API 狀態**：直接 curl 生產 Worker 端點：
  `curl -s https://ww3-risk-api.whypuss.workers.dev/api/risk/latest`
  `curl -s https://ww3-risk-api.whypuss.workers.dev/api/data-status`
- **D1 數據審查**：使用 wrangler 查詢歷史快照：
  `npx wrangler d1 execute ww3-risk --command="SELECT id, computed_at, total_index, stage FROM index_snapshots ORDER BY computed_at DESC LIMIT 5;"`

### 4. 故障回滾 (Rollback)
- **前端回滾**：Cloudflare Pages 支援秒級 Instant Rollback，前往 Pages 控制台 `ww3-risk-model` -> Deployments -> 挑選上一穩定版本點擊 `Rollback to this deployment`。
- **快照回滾**：若某一快照數據有瑕疵，可直接執行 SQL 刪除該筆 `index_snapshots` 記錄，級聯外鍵（CASCADE）會自動清理對應的 `indicator_observations`。

---

## 五、Cloudflare 免費額度裕度分析 (Free Tier Limits)

本架構設計完全在 Cloudflare 免費方案（Free Plan）限制之內，且擁有極大餘量：

| 服務項目 | 免費方案額度上限 | 本模型預估消耗量 | 裕度安全倍數 |
|---|---|---|---|
| **D1 寫入** | 100,000 次 / 日 | 每日 1 次快照（~5 次 batch SQL） | **> 20,000 倍** |
| **D1 讀取** | 5,000,000 次 / 日 | 每次 API 調用 1–2 次讀取（配合 60 秒快取） | **> 100,000 倍** |
| **D1 儲存** | 5 GB | 每次快照約 30 KB，一年 365 份約 11 MB | **> 450 年** |
| **Workers 請求** | 100,000 次 / 日 | 邊緣快取 60s，一般訪問約 1,000–5,000 次/日 | **> 20 倍** |
| **Pages 部署** | 500 次 / 月 | 每日排程 1 次，每月約 30 次 | **> 16 倍** |

---

## 六、特此註明：社會動盪指數未實作說明 (Notice on Social Instability Index)

按照規格鐵律，**本版本（v0.4.0）嚴格未加入「社會動盪指數」或 `/api/social-instability` 端點**。

原因與背景：
1. 現有模型核心架構包含五層結構風險（L1 資源短缺、L2 分配不均、L3 勞工與AI自動化、L4 權力地緣、L5 未來焦慮）及和平機制閘門。
2. 社會動盪在現行架構中主要體現於 L2（分配裂痕）與 L3（就業結構）指標群組之綜合作用，尚未獨立定義經驗回測之數學公式與指標映射權重。
3. 為維持模型嚴謹性與可信度紀律，在用戶與防務分析團隊正式拍板社會動盪指數之量化定義前，API 僅提供正式已驗收之 4 個端點，保留未來延伸空間。
