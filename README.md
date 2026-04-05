# Telegram Chat Level System Bot

一個為 Telegram 群組設計的等級系統，透過訊息互動（文字、媒體、貼圖）自動累積經驗並提升等級，增加群組活躍度。

## 核心功能

- **全方位互動計分**：支援文字、圖片、影片、檔案與貼圖。自動排除「指令」與「系統訊息」，確保數據公平。
- **RPG 等級模型**：採用標準二次公式（`5L^2 + 50L + 10`），隨著等級提升挑戰性隨之增加。
- **高效效能優化**：啟用 SQLite **WAL 模式**與長連接，大幅提升訊息湧入時的處理速度。
- **自動指令選單**：啟動後自動設定 Bot Menu，使用者可輕鬆查詢指令。
- **權限管理系統**：支援「初始擁有者（Owner）」與「資料庫管理員（Admin）」雙層權限。
- **資源安全管理**：支援程式停止時自動安全存檔與關閉資料庫，防止資料毀損。
- **防止惡意刷等**：內建冷卻機制（預設 30 秒），冷卻期內不重複計算 XP。
- **視覺化進度**：美觀的 HTML 升級公告與 Unicode 視覺化進度條。
- **本地化存儲**：使用 SQLite 儲存資料，輕量且易於備份。

## 安裝與準備

1. **環境需求**：Python 3.9+
2. **安裝依賴**：

```bash
pip install -r requirements.txt
```

3. **配置參數**：
   編輯 `main.py` 中的變數：

   ```python
   TOKEN = 'YOUR_BOT_TOKEN_HERE' # 替換成你的機器人 Token
   OWNER_ID = 7716734928        # 你的 Telegram ID
   ```

## 指令說明

### 使用者指令

- `/rank`：查詢個人等級報告（包含等級、XP 進度與視覺條）。

### 管理員指令 (需具備 Admin 權限)

- `/addxp @username 數量`：調整使用者 XP（支援負值進行扣除，會自動處理降級）。
- `/addrank @username 等級數`：直接調整使用者等級（支援負值，最低為 Lv.0）。
- `/addadmin @username/ID`：將使用者加入管理員名單。

### 擁有者指令 (僅限 OWNER_ID 使用)

- `/deladmin @username/ID`：將使用者從管理員名單移除。


## 資料庫結構 (SQLite)

機器人會自動建立 `chat_levels.db`，包含以下兩個資料表：

### `users` (用戶等級資料)

- `user_id`：Telegram 使用者唯一 ID
- `chat_id`：Telegram 群組/對話 ID
- `level`：當前等級
- `xp`：目前累積的經驗值
- `last_msg_time`：最後一次獲得 XP 的時間戳
- `username`：使用者帳號（用於管理操作）

### `admins` (管理員名單)

- `user_id`：具備管理權限的使用者 ID

## 啟動

執行主程式：

```bash
python main.py
```

## 注意事項

- 本機器人預設處理所有非指令、非系統訊息的內容。
- 機器人必須在群組中具備「發送訊息」與「回覆訊息」的權限。
- 若需要調整冷卻時間或等級難度，可直接修改 `main.py` 中的 `COOLDOWN_SECONDS` 或 `get_required_xp` 函數。

## 貢獻與反饋

如果您有任何建議或發現 Bug，歡迎隨時進行調整或提出反饋！
