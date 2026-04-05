import sqlite3
import time
import math
import logging
import os
from dotenv import load_dotenv
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, CallbackQueryHandler, filters
from telegram.request import HTTPXRequest

# --- 設定區域 ---
load_dotenv()
TOKEN = os.getenv('TG_BOT_TOKEN')
DB_NAME = 'chat_levels.db'
COOLDOWN_SECONDS = 30
OWNER_ID = 7716734928  # 初始管理員 ID
ITEMS_PER_PAGE = 10     # 每頁顯示人數
AUTO_DELETE_SECONDS = 60 # 自動刪除訊息的秒數

# 設定日誌
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# 全域資料庫連接變數
db_conn = None

# --- 資料庫初始化與優化 ---
def init_db():
    global db_conn
    db_conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    db_conn.execute("PRAGMA journal_mode=WAL;")
    db_conn.execute("PRAGMA synchronous=NORMAL;")
    
    c = db_conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER, chat_id INTEGER, level INTEGER, xp INTEGER, 
                  last_msg_time REAL, username TEXT, display_name TEXT,
                  PRIMARY KEY (user_id, chat_id))''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)''')
    c.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (OWNER_ID,))
    db_conn.commit()
    print("✅ 資料庫已連接並開啟 WAL 模式")

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
    c = db_conn.cursor()
    c.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
    return c.fetchone() is not None

# --- 自動刪除訊息邏輯 ---
async def delete_message_job(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.data['chat_id']
    message_ids = job.data['message_ids']
    for msg_id in message_ids:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except:
            pass

def schedule_deletion(context: ContextTypes.DEFAULT_TYPE, chat_id, message_ids):
    if not isinstance(message_ids, list):
        message_ids = [message_ids]
    context.job_queue.run_once(
        delete_message_job, 
        when=AUTO_DELETE_SECONDS, 
        data={'chat_id': chat_id, 'message_ids': message_ids}
    )

# --- 排行榜數據生成器 ---
def get_leaderboard_page(chat_id, page=1):
    c = db_conn.cursor()
    offset = (page - 1) * ITEMS_PER_PAGE
    c.execute("SELECT COUNT(*) FROM users WHERE chat_id = ?", (chat_id,))
    total_users = c.fetchone()[0]
    total_pages = math.ceil(total_users / ITEMS_PER_PAGE) if total_users > 0 else 1
    
    c.execute("""SELECT user_id, username, display_name, level, xp FROM users 
                 WHERE chat_id = ? 
                 ORDER BY level DESC, xp DESC LIMIT ? OFFSET ?""", (chat_id, ITEMS_PER_PAGE, offset))
    results = c.fetchall()
    
    text = f"🏆 <b>群組等級排行榜 (第 {page}/{total_pages} 頁)</b>\n\n"
    if not results:
        text += "目前排行榜空空如也..."
        return text, total_pages

    for i, (uid, uname, dname, level, xp) in enumerate(results, 1):
        rank_num = offset + i
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank_num, f"<code>{rank_num:2}.</code>")
        final_name = f"@{uname}" if uname else (dname if dname else f"ID:{uid}")
        text += f"{medal} {final_name} — <b>Lv.{level}</b>\n"
    
    text += f"\n共有 {total_users} 名成員，訊息將在 {AUTO_DELETE_SECONDS} 秒後自動刪除。"
    return text, total_pages

# --- 設定指令選單 ---
async def post_init(application):
    commands = [
        BotCommand("rank", "📊 查詢我的等級與進度"),
        BotCommand("top", "🏆 查看群組等級排行榜"),
        BotCommand("addxp", "✍️ [管理員] 增加經驗值 (可回覆訊息)"),
        BotCommand("addrank", "🆙 [管理員] 直接增加等級 (可回覆訊息)"),
        BotCommand("addadmin", "➕ [管理員] 新增管理員名單"),
        BotCommand("deladmin", "➖ [擁有者] 移除管理員權限")
    ]
    await application.bot.set_my_commands(commands)

# --- 核心邏輯：處理訊息 ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.is_bot:
        return
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    username = update.effective_user.username
    display_name = update.effective_user.first_name
    now = time.time()
    thread_id = update.message.message_thread_id if update.message else None

    c = db_conn.cursor()
    c.execute("SELECT level, xp, last_msg_time FROM users WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
    result = c.fetchone()

    if result:
        level, xp, last_msg_time = result
        c.execute("UPDATE users SET username = ?, display_name = ? WHERE user_id = ? AND chat_id = ?", 
                  (username, display_name, user_id, chat_id))
        if now - last_msg_time < COOLDOWN_SECONDS:
            db_conn.commit()
            return
        new_xp = xp + 1
        req_xp = get_required_xp(level)
        if new_xp >= req_xp:
            level += 1
            new_xp = 0
            user_mention = update.effective_user.mention_html()
            bot_msg = await context.bot.send_message(
                chat_id=chat_id,
                text=f"🎉 <b>LEVEL UP! 恭喜升級！</b>\n\n{user_mention}\n🆙 等級提升: <b>Lv.{level-1} ➔ Lv.{level}</b>\n此訊息將在一分鐘後消失。",
                parse_mode=ParseMode.HTML,
                message_thread_id=thread_id
            )
            schedule_deletion(context, chat_id, [bot_msg.message_id])

        c.execute("UPDATE users SET level = ?, xp = ?, last_msg_time = ? WHERE user_id = ? AND chat_id = ?",
                  (level, new_xp, now, user_id, chat_id))
    else:
        c.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?)", (user_id, chat_id, 0, 1, now, username, display_name))
    db_conn.commit()

async def rank_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    c = db_conn.cursor()
    c.execute("SELECT level, xp FROM users WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
    result = c.fetchone()
    if not result:
        bot_msg = await update.message.reply_text("查無資料，請先在群組發言！")
        schedule_deletion(context, chat_id, [update.message.message_id, bot_msg.message_id])
        return
    level, xp = result
    req_xp = get_required_xp(level)
    bar = generate_progress_bar(xp, req_xp)
    text = (f"📊 <b>{update.effective_user.first_name} 的等級報告</b>\n\n"
            f"🏅 當前等級: <b>Lv.{level}</b>\n"
            f"✨ 經驗進度: {xp} / {req_xp} XP\n"
            f"{bar}\n\n"
            f"距離下一級還差 <b>{req_xp - xp}</b> 次發言。\n"
            f"<i>此訊息與指令將在 60 秒後刪除</i>")
    bot_msg = await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    schedule_deletion(context, chat_id, [update.message.message_id, bot_msg.message_id])

async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    page = 1
    text, total_pages = get_leaderboard_page(chat_id, page)
    keyboard = []
    nav_row = []
    if page > 1: nav_row.append(InlineKeyboardButton("⬅️ 上一頁", callback_data=f"top_{page-1}"))
    if page < total_pages: nav_row.append(InlineKeyboardButton("下一頁 ➡️", callback_data=f"top_{page+1}"))
    if nav_row: keyboard.append(nav_row)
    reply_markup = InlineKeyboardMarkup(keyboard)
    bot_msg = await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    schedule_deletion(context, chat_id, [update.message.message_id, bot_msg.message_id])

async def top_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    page = int(query.data.split('_')[1])
    text, total_pages = get_leaderboard_page(chat_id, page)
    keyboard = []
    nav_row = []
    if page > 1: nav_row.append(InlineKeyboardButton("⬅️ 上一頁", callback_data=f"top_{page-1}"))
    if page < total_pages: nav_row.append(InlineKeyboardButton("下一頁 ➡️", callback_data=f"top_{page+1}"))
    if nav_row: keyboard.append(nav_row)
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

async def admin_response_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    bot_msg = await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    schedule_deletion(context, update.effective_chat.id, [update.message.message_id, bot_msg.message_id])

# --- 修復後的管理指令 ---
async def add_xp_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_db_admin(update.effective_user.id):
        await admin_response_handler(update, context, "❌ 權限不足。")
        return
    
    target_id = None
    xp_to_add = 0
    chat_id = update.effective_chat.id

    # 判斷是否回覆訊息
    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
        if context.args:
            try: xp_to_add = int(context.args[0])
            except: pass
    elif len(context.args) >= 2:
        target_username = context.args[0].replace('@', '').lower()
        try: xp_to_add = int(context.args[1])
        except: pass
        c = db_conn.cursor()
        # 關鍵修正：加上 chat_id = ? 確保更新當前群組數據
        c.execute("SELECT user_id FROM users WHERE LOWER(username) = ? AND chat_id = ?", (target_username, chat_id))
        res = c.fetchone()
        if res: target_id = res[0]
    
    if target_id is None or xp_to_add == 0:
        await admin_response_handler(update, context, "💡 格式: `/addxp @username 數量` 或回覆訊息輸入 `/addxp 數量`")
        return

    c = db_conn.cursor()
    c.execute("SELECT level, xp FROM users WHERE user_id = ? AND chat_id = ?", (target_id, chat_id))
    user_data = c.fetchone()
    
    if not user_data:
        await admin_response_handler(update, context, "❌ 該使用者在當前群組尚無數據。")
        return

    t_lvl, t_xp = user_data
    new_xp = t_xp + xp_to_add
    
    # 重新計算等級升降
    while new_xp >= get_required_xp(t_lvl):
        new_xp -= get_required_xp(t_lvl)
        t_lvl += 1
    while new_xp < 0 and t_lvl > 0:
        t_lvl -= 1
        new_xp += get_required_xp(t_lvl)
    if t_lvl == 0 and new_xp < 0: new_xp = 0

    c.execute("UPDATE users SET level = ?, xp = ? WHERE user_id = ? AND chat_id = ?", (t_lvl, new_xp, target_id, chat_id))
    db_conn.commit()
    await admin_response_handler(update, context, f"✅ 已成功為 ID:{target_id} 調整經驗值 (當前: Lv.{t_lvl})。")

async def add_rank_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_db_admin(update.effective_user.id):
        await admin_response_handler(update, context, "❌ 權限不足。")
        return

    target_id = None
    ranks_to_add = 0
    chat_id = update.effective_chat.id

    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
        if context.args:
            try: ranks_to_add = int(context.args[0])
            except: pass
    elif len(context.args) >= 2:
        target_username = context.args[0].replace('@', '').lower()
        try: ranks_to_add = int(context.args[1])
        except: pass
        c = db_conn.cursor()
        # 關鍵修正：加上 chat_id = ?
        c.execute("SELECT user_id FROM users WHERE LOWER(username) = ? AND chat_id = ?", (target_username, chat_id))
        res = c.fetchone()
        if res: target_id = res[0]

    if target_id is None or ranks_to_add == 0:
        await admin_response_handler(update, context, "💡 格式: `/addrank @username 數量` 或回覆訊息輸入 `/addrank 數量`")
        return

    c = db_conn.cursor()
    c.execute("SELECT level, xp FROM users WHERE user_id = ? AND chat_id = ?", (target_id, chat_id))
    user_data = c.fetchone()
    
    if not user_data:
        await admin_response_handler(update, context, "❌ 該使用者在當前群組尚無數據。")
        return

    t_lvl, t_xp = user_data
    new_lvl = max(0, t_lvl + ranks_to_add)
    if new_lvl == 0: t_xp = 0
    
    c.execute("UPDATE users SET level = ?, xp = ? WHERE user_id = ? AND chat_id = ?", (new_lvl, t_xp, target_id, chat_id))
    db_conn.commit()
    await admin_response_handler(update, context, f"✅ 已成功將 ID:{target_id} 調整為 Lv.{new_lvl}。")

async def add_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_db_admin(update.effective_user.id):
        await admin_response_handler(update, context, "❌ 權限不足。")
        return
    if not context.args:
        await admin_response_handler(update, context, "💡 格式: `/addadmin @username` 或 `/addadmin ID`")
        return
    target = context.args[0].replace('@', '').lower()
    c = db_conn.cursor()
    target_id = int(target) if target.isdigit() else None
    if not target_id:
        c.execute("SELECT user_id FROM users WHERE LOWER(username) = ? AND chat_id = ?", (target, update.effective_chat.id))
        res = c.fetchone()
        if res: target_id = res[0]
    if target_id:
        c.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (target_id,))
        db_conn.commit()
        await admin_response_handler(update, context, f"✅ 已新增管理員 ID: <code>{target_id}</code>")
    else:
        await admin_response_handler(update, context, "❌ 找不到該使用者數據。")

async def del_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await admin_response_handler(update, context, "❌ 只有擁有者可以刪除。")
        return
    if not context.args: return
    target = context.args[0].replace('@', '').lower()
    c = db_conn.cursor()
    target_id = int(target) if target.isdigit() else None
    if not target_id:
        c.execute("SELECT user_id FROM users WHERE LOWER(username) = ? AND chat_id = ?", (target, update.effective_chat.id))
        res = c.fetchone()
        if res: target_id = res[0]
    if target_id and target_id != OWNER_ID:
        c.execute("DELETE FROM admins WHERE user_id = ?", (target_id,))
        db_conn.commit()
        await admin_response_handler(update, context, f"🗑 已移除管理員 ID: <code>{target_id}</code>")

if __name__ == '__main__':
    init_db()
    request_config = HTTPXRequest(connect_timeout=20.0, read_timeout=20.0)
    app = ApplicationBuilder().token(TOKEN).request(request_config).post_init(post_init).build()

    app.add_handler(MessageHandler((~filters.COMMAND) & (~filters.StatusUpdate.ALL), handle_message))
    app.add_handler(CommandHandler("rank", rank_command))
    app.add_handler(CommandHandler("top", top_command))
    app.add_handler(CommandHandler("addxp", add_xp_admin))
    app.add_handler(CommandHandler("addrank", add_rank_admin))
    app.add_handler(CommandHandler("addadmin", add_admin_command))
    app.add_handler(CommandHandler("deladmin", del_admin_command))
    app.add_handler(CallbackQueryHandler(top_callback, pattern="^top_"))

    print(f"機器人 V8.1 啟動 (修正管理指令問題)...")
    try:
        app.run_polling()
    finally:
        if db_conn:
            db_conn.close()