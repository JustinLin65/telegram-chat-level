import sqlite3
import time
import math
import logging
from telegram import Update, BotCommand
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters

# --- 設定區域 ---
TOKEN = '7991236877:AAHFm0KbSCmjxnhc7AgWY8rAF8u2Fddb39s'
DB_NAME = 'chat_levels.db'
COOLDOWN_SECONDS = 30
OWNER_ID = 0123456789  # 替換為實際擁有者的 Telegram ID

# 設定日誌
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- 資料庫初始化 ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER, chat_id INTEGER, level INTEGER, xp INTEGER, 
                  last_msg_time REAL, username TEXT, PRIMARY KEY (user_id, chat_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)''')
    c.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (OWNER_ID,))
    conn.commit()
    conn.close()

# --- 工具函數 ---
def get_required_xp(level):
    return 5 * (level**2) + 50 * level + 10

def generate_progress_bar(current_xp, target_xp, bar_length=10):
    progress = min(current_xp / target_xp, 1.0)
    filled_length = int(bar_length * progress)
    bar = '█' * filled_length + '░' * (bar_length - filled_length)
    percentage = int(progress * 100)
    return f"`{bar}` {percentage}%"

def check_db_admin(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result is not None

# --- 設定指令列表 (選單) ---
async def post_init(application):
    """機器人啟動後自動設定指令選單"""
    commands = [
        BotCommand("rank", "📊 查詢我的等級與進度"),
        BotCommand("addxp", "✍️ [管理員] 增加用戶經驗值"),
        BotCommand("addadmin", "➕ [管理員] 新增管理員名單"),
        BotCommand("deladmin", "➖ [擁有者] 移除管理員權限")
    ]
    await application.bot.set_my_commands(commands)
    print("✅ 已更新指令選單列表")

# --- 核心邏輯：處理訊息 (所有非指令訊息) ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 確保訊息來自使用者且不是機器人
    if not update.effective_user or update.effective_user.is_bot:
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    username = update.effective_user.username.lower() if update.effective_user.username else None
    now = time.time()
    
    # 處理 Topic ID (如果是在論壇群組)
    thread_id = None
    if update.message:
        thread_id = update.message.message_thread_id

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT level, xp, last_msg_time FROM users WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
    result = c.fetchone()

    if result:
        level, xp, last_msg_time = result
        # 更新最新 username
        c.execute("UPDATE users SET username = ? WHERE user_id = ? AND chat_id = ?", (username, user_id, chat_id))
        
        # 檢查冷卻時間
        if now - last_msg_time < COOLDOWN_SECONDS:
            conn.commit()
            conn.close()
            return

        new_xp = xp + 1
        req_xp = get_required_xp(level)

        if new_xp >= req_xp:
            level += 1
            new_xp = 0
            user_mention = update.effective_user.mention_html()
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🎉 <b>LEVEL UP! 恭喜升級！</b>\n\n{user_mention}\n🆙 等級提升: <b>Lv.{level-1} ➔ Lv.{level}</b>\n繼續加油！",
                parse_mode=ParseMode.HTML,
                message_thread_id=thread_id
            )
        c.execute("UPDATE users SET level = ?, xp = ?, last_msg_time = ? WHERE user_id = ? AND chat_id = ?",
                  (level, new_xp, now, user_id, chat_id))
    else:
        # 新使用者初始化
        c.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)", (user_id, chat_id, 0, 1, now, username))

    conn.commit()
    conn.close()

# --- 指令實作 ---
async def rank_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT level, xp FROM users WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
    result = c.fetchone()
    conn.close()
    if not result:
        await update.message.reply_text("查無資料，請先在群組發言！")
        return
    level, xp = result
    req_xp = get_required_xp(level)
    bar = generate_progress_bar(xp, req_xp)
    text = (f"📊 <b>{update.effective_user.first_name} 的等級報告</b>\n\n"
            f"🏅 當前等級: <b>Lv.{level}</b>\n"
            f"✨ 經驗進度: {xp} / {req_xp} XP\n"
            f"{bar}\n\n"
            f"距離下一級還差 <b>{req_xp - xp}</b> 次有效發言")
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def add_xp_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_db_admin(update.effective_user.id):
        await update.message.reply_text("❌ 權限不足。")
        return
    if len(context.args) < 2:
        await update.message.reply_text("💡 格式: `/addxp @username 數量`")
        return
    target_username = context.args[0].replace('@', '').lower()
    try:
        xp_to_add = int(context.args[1])
    except:
        await update.message.reply_text("❌ 經驗值必須是整數。")
        return
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT user_id, level, xp, chat_id FROM users WHERE username = ?", (target_username,))
    user_data = c.fetchone()
    if not user_data:
        await update.message.reply_text(f"❌ 找不到使用者 @{target_username}")
        conn.close()
        return
    t_id, t_lvl, t_xp, t_chat = user_data
    new_xp = t_xp + xp_to_add
    while True:
        req = get_required_xp(t_lvl)
        if new_xp >= req: new_xp -= req; t_lvl += 1
        else: break
    c.execute("UPDATE users SET level = ?, xp = ? WHERE user_id = ? AND chat_id = ?", (t_lvl, new_xp, t_id, t_chat))
    conn.commit(); conn.close()
    await update.message.reply_text(f"✅ 已為 @{target_username} 增加 {xp_to_add} XP。\n目前: <b>Lv.{t_lvl}</b>", parse_mode=ParseMode.HTML)

async def add_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_db_admin(update.effective_user.id):
        await update.message.reply_text("❌ 權限不足。")
        return
    if not context.args:
        await update.message.reply_text("💡 格式: `/addadmin @username`")
        return
    target = context.args[0].replace('@', '').lower()
    conn = sqlite3.connect(DB_NAME); c = conn.cursor()
    target_id = int(target) if target.isdigit() else None
    if not target_id:
        c.execute("SELECT user_id FROM users WHERE username = ?", (target,))
        res = c.fetchone()
        if res: target_id = res[0]
    if target_id:
        c.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (target_id,))
        conn.commit()
        await update.message.reply_text(f"✅ 已新增管理員 ID: `{target_id}`", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("❌ 找不到該使用者。")
    conn.close()

async def del_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ 只有擁有者可以刪除。")
        return
    if not context.args: return
    target = context.args[0].replace('@', '').lower()
    conn = sqlite3.connect(DB_NAME); c = conn.cursor()
    target_id = int(target) if target.isdigit() else None
    if not target_id:
        c.execute("SELECT user_id FROM users WHERE username = ?", (target,))
        res = c.fetchone()
        if res: target_id = res[0]
    if target_id and target_id != OWNER_ID:
        c.execute("DELETE FROM admins WHERE user_id = ?", (target_id,))
        conn.commit()
        await update.message.reply_text(f"🗑 已移除管理員 ID: `{target_id}`", parse_mode=ParseMode.MARKDOWN)
    conn.close()

if __name__ == '__main__':
    init_db()
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

    # 修正：將 filters.SERVICE 改為 filters.StatusUpdate.ALL
    # 這會過濾掉系統訊息（如成員加入、置頂訊息等），確保只有用戶發送的內容（文字、媒體、貼圖）會計入 XP
    app.add_handler(MessageHandler((~filters.COMMAND) & (~filters.StatusUpdate.ALL), handle_message))
    
    app.add_handler(CommandHandler("rank", rank_command))
    app.add_handler(CommandHandler("addxp", add_xp_admin))
    app.add_handler(CommandHandler("addadmin", add_admin_command))
    app.add_handler(CommandHandler("deladmin", del_admin_command))

    print("機器人正在啟動...")
    app.run_polling()