# Telegram Chat Level System Bot

*本專案為 Telegram 聊天群組設計，透過記錄成員活動、提升等級來增加群組互動性。*

一個簡單且高效的 Telegram 等級系統機器人，支援：

- 自動累積經驗值（XP）與等級晉升
- 管理員手動調整使用者經驗值
- 靈活的管理員權限管理系統
- 設定訊息冷卻時間，防止洗版刷等級
- 支援 Telegram Topic（分組論壇）
- 視覺化等級進度條
- 使用 SQLite 本地資料庫儲存資料

## 核心功能

- **經驗值系統**：每發送一則有效文字訊息（非指令）可獲得 1 XP。
- **等級公式**：採用標準 RPG 二次模型（`5L^2 + 50L + 10`），隨等級提升所需經驗。
- **管理員系統**：支援多級權限管理，包含「初始擁有者（Owner）」與「資料庫管理員（Admin）」。
- **防止洗版**：內建 `COOLDOWN_SECONDS`（預設 30 秒）冷卻機制，冷卻期內不重複計算 XP。
- **升級公告**：當使用者達到升級門檻，機器人會自動發送 HTML 格式的慶祝訊息。
- **Topic 支援**：完美支援 Telegram 超群組中的 Topic 功能，訊息會正確回覆在原 Topic 中。
- **本地存儲**：所有等級資料儲存在 `chat_levels.db` SQLite 資料庫中。

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
   OWNER_ID = 7716734928        # 你的 Telegram ID（初始管理員）
   ```

## 指令說明

### 使用者指令

- `/rank` 或 `/level`：查詢當前群組中的個人等級報告，包含等級、XP 進度與視覺化進度條。

### 管理員指令 (需在管理員名單中)

- `/addxp @username 數量`：手動為指定使用者增加經驗值。
- `/addadmin @username/ID`：將指定使用者加入管理員清單。

### 擁有者指令 (僅限 OWNER_ID 使用)

- `/deladmin @username/ID`：將指定使用者從管理員清單移除。

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

- 本機器人預設僅處理文字訊息 (`filters.TEXT`)。
- 機器人必須在群組中具備「發送訊息」與「回覆訊息」的權限。
- 若需要調整冷卻時間或等級難度，可直接修改 `main.py` 中的 `COOLDOWN_SECONDS` 或 `get_required_xp` 函數。

## 貢獻與反饋

如果您有任何建議或發現 Bug，歡迎隨時進行調整或提出反饋！
