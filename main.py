import sqlite3
import time
import math
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters

# --- 設定區域 ---
TOKEN = 'YOUR_BOT_TOKEN_HERE'  # 替換成你的 Bot Token
DB_NAME = 'chat_levels.db'
COOLDOWN_SECONDS = 30

# --- 資料庫初始化 ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER, chat_id INTEGER, level INTEGER, xp INTEGER, last_msg_time REAL,
                 PRIMARY KEY (user_id, chat_id))''')
    conn.commit()
    conn.close()

# --- 等級公式計算 ---
def get_required_xp(level):
    # 標準 RPG 二次模型: 5L^2 + 50L + 10
    return 5 * (level**2) + 50 * level + 10

def generate_progress_bar(current_xp, target_xp, bar_length=10):
    progress = current_xp / target_xp
    filled_length = int(bar_length * progress)
    bar = '█' * filled_length + '░' * (bar_length - filled_length)
    percentage = int(progress * 100)
    return f"`{bar}` {percentage}%"

# --- 核心邏輯 ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.is_bot:
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    now = time.time()
    message_thread_id = update.message.message_thread_id # 處理 Topic (分組論壇)

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT level, xp, last_msg_time FROM users WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
    result = c.fetchone()

    if result:
        level, xp, last_msg_time = result
        # 檢查冷卻
        if now - last_msg_time < COOLDOWN_SECONDS:
            conn.close()
            return

        # 增加經驗
        new_xp = xp + 1
        required_xp = get_required_xp(level)

        if new_xp >= required_xp:
            new_level = level + 1
            new_xp = 0 # 升級後進度重置（或扣除差額）
            
            # 升級文案
            username = update.effective_user.mention_html()
            congrats_text = (
                f"🎉 <b>LEVEL UP! 恭喜升級！</b>\n\n"
                f"{username}\n"
                f"🆙 等級提升: <b>Lv.{level} ➔ Lv.{new_level}</b>\n"
                f"Keep up the great work! 繼續保持活躍喔！"
            )
            await context.bot.send_message(
                chat_id=chat_id,
                text=congrats_text,
                parse_mode='HTML',
                message_thread_id=message_thread_id
            )
            c.execute("UPDATE users SET level = ?, xp = ?, last_msg_time = ? WHERE user_id = ? AND chat_id = ?",
                      (new_level, new_xp, now, user_id, chat_id))
        else:
            c.execute("UPDATE users SET xp = ?, last_msg_time = ? WHERE user_id = ? AND chat_id = ?",
                      (new_xp, now, user_id, chat_id))
    else:
        # 新用戶初始化
        c.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?)", (user_id, chat_id, 0, 1, now))

    conn.commit()
    conn.close()

# --- 查詢指令 ---
async def rank_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT level, xp FROM users WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
    result = c.fetchone()
    conn.close()

    if not result:
        await update.message.reply_text("你還沒有在資料庫中，發個訊息試試看！")
        return

    level, xp = result
    target_xp = get_required_xp(level)
    progress_bar = generate_progress_bar(xp, target_xp)
    username = update.effective_user.first_name

    rank_text = (
        f"📊 <b>{username} 的聊天等級報告</b>\n\n"
        f"🏅 當前等級: <b>Lv.{level}</b>\n"
        f"✨ 進度: {xp} / {target_xp} XP\n"
        f"{progress_bar}\n\n"
        f"距離下一級還差 <b>{target_xp - xp}</b> 次有效發言"
    )
    await update.message.reply_text(rank_text, parse_mode='HTML')

# --- 啟動入口 ---
if __name__ == '__main__':
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    # 監聽訊息
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    # 查詢等級指令
    app.add_handler(CommandHandler("rank", rank_command))
    app.add_handler(CommandHandler("level", rank_command))

    print("Bot 正在運行中...")
    app.run_polling()