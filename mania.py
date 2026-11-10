import asyncio
import logging
import os
import secrets
import sqlite3
from datetime import datetime
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# -------------------------------------------------------------------
# CONFIGURATION
# -------------------------------------------------------------------
BOT_TOKEN = "9247311280:AAHEZthVVtbRaFicW05m61XYCCOGfmzB83I"
ADMIN_ID = 8668542249
BOT_USERNAME = "ALL_VIRAL_VIDEO_Unlock_BOT"
DB_NAME = "video_manager.db"

# আপনার দেওয়া দুটি চ্যানেল লিংক এখানে যুক্ত করা হলো
CHANNEL_1_URL = "https://t.me/+wCXW6y4g3xE2Yjg1"
CHANNEL_2_URL = "https://t.me/+iu9kjptGlf80YmM9"

# -------------------------------------------------------------------
# LOGGING SETUP
# -------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# DATABASE LAYER
# -------------------------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT NOT NULL,
                file_unique_id TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                token TEXT UNIQUE NOT NULL,
                upload_date TEXT NOT NULL
            )
        """)
        conn.commit()

def save_video(file_id: str, file_unique_id: str, file_name: str, file_size: int) -> str:
    token = secrets.token_urlsafe(12)
    upload_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO videos (file_id, file_unique_id, file_name, file_size, token, upload_date)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (file_id, file_unique_id, file_name, file_size, token, upload_date)
        )
        conn.commit()
    return token

def get_video_by_token(token: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM videos WHERE token = ?", (token,))
        return cursor.fetchone()

def get_video_by_id(video_id: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM videos WHERE id = ?", (video_id,))
        return cursor.fetchone()

def get_all_videos(limit: int = 10, offset: int = 0):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM videos ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))
        return cursor.fetchall()

def get_total_videos_count() -> int:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM videos")
        return cursor.fetchone()[0]

def get_total_storage_bytes() -> int:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(file_size) FROM videos")
        res = cursor.fetchone()[0]
        return res if res else 0

def delete_video_by_id(video_id: int) -> bool:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM videos WHERE id = ?", (video_id,))
        conn.commit()
        return cursor.rowcount > 0

# -------------------------------------------------------------------
# HELPER FUNCTIONS
# -------------------------------------------------------------------
def format_bytes(size: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

# -------------------------------------------------------------------
# KEYBOARD BUILDERS
# -------------------------------------------------------------------
def get_force_subscribe_keyboard():
    keyboard = [
        [InlineKeyboardButton("📢 প্রথম চ্যানেল", url=CHANNEL_1_URL)],
        [InlineKeyboardButton("📢 দ্বিতীয় চ্যানেল", url=CHANNEL_2_URL)]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_admin_dashboard_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("📂 Manage Files", callback_data="manage_files_0"),
            InlineKeyboardButton("📊 Bot Statistics", callback_data="bot_stats")
        ],
        [
            InlineKeyboardButton("📤 Upload New Video", callback_data="upload_info")
        ],
        [
            InlineKeyboardButton("🔄 Refresh Dashboard", callback_data="admin_dashboard")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_file_manager_keyboard(videos, page: int, total_count: int, per_page: int = 5):
    keyboard = []
    for vid in videos:
        title = vid["file_name"]
        if len(title) > 25:
            title = title[:22] + "..."
        keyboard.append([InlineKeyboardButton(f"📹 {title}", callback_data=f"file_view_{vid['id']}_{page}")])
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"manage_files_{page - 1}"))
    if (page + 1) * per_page < total_count:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"manage_files_{page + 1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
        
    keyboard.append([InlineKeyboardButton("🔙 Back to Dashboard", callback_data="admin_dashboard")])
    return InlineKeyboardMarkup(keyboard)

def get_video_detail_keyboard(video_id: int, page: int, token: str):
    link = f"https://t.me/{BOT_USERNAME}?start={token}"
    keyboard = [
        [
            InlineKeyboardButton("▶️ Watch Video", callback_data=f"watch_{video_id}"),
            InlineKeyboardButton("🗑️ Delete Video", callback_data=f"delete_confirm_{video_id}_{page}")
        ],
        [
            InlineKeyboardButton("🔗 Direct Access Link", url=link)
        ],
        [
            InlineKeyboardButton("🔙 Back to Files", callback_data=f"manage_files_{page}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_delete_confirm_keyboard(video_id: int, page: int):
    keyboard = [
        [
            InlineKeyboardButton("⚠️ Confirm Delete", callback_data=f"delete_do_{video_id}_{page}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"file_view_{video_id}_{page}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# -------------------------------------------------------------------
# BACKGROUND TASK FOR AUTO-DELETION
# -------------------------------------------------------------------
async def delete_message_after_delay(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int, delay: int = 600):
    await asyncio.sleep(delay)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as e:
        logger.error(f"Could not auto-delete message: {e}")

# -------------------------------------------------------------------
# COMMAND HANDLERS
# -------------------------------------------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args

    # যদি কেউ ডাইরেক্ট ভিডিও লিংকে ক্লিক করে আসে
    if args:
        token = args[0]
        video = get_video_by_token(token)
        if video:
            try:
                sent_msg = await update.message.reply_video(
                    video=video["file_id"],
                    caption=f"🎥 <b>{video['file_name']}</b>\n📦 Size: {format_bytes(video['file_size'])}\n\n⚠️ <i>এই ভিডিওটি ১০ মিনিট পর স্বয়ংক্রিয়ভাবে মুছে যাবে।</i>",
                    parse_mode=ParseMode.HTML,
                    protect_content=True
                )
                context.application.create_task(
                    delete_message_after_delay(context, update.effective_chat.id, sent_msg.message_id, 600)
                )
            except Exception as e:
                logger.error(f"Error sending video: {e}")
                await update.message.reply_text("❌ Failed to deliver video. It may no longer be available.")
        else:
            await update.message.reply_text("⛔ <b>Access Denied</b>\n\nThis video link is invalid or has been revoked.", parse_mode=ParseMode.HTML)
        return

    # যদি অ্যাডমিন স্টার্ট করে
    if is_admin(user_id):
        await show_admin_dashboard(update, context)
    else:
        # সাধারণ ইউজার স্টার্ট করলে শুধু স্বাগতম বার্তা ও চ্যানেল জয়েন করার বাটন দেখাবে
        text = "👋 স্বাগতম! ভিডিও দেখতে বা ব্যবহার করতে নিচের চ্যানেলগুলোতে জয়েন করুন:"
        await update.message.reply_text(
            text,
            reply_markup=get_force_subscribe_keyboard(),
            parse_mode=ParseMode.HTML
        )

async def show_admin_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_vids = get_total_videos_count()
    total_size = format_bytes(get_total_storage_bytes())
    
    text = (
        "⚡ <b>ADMIN CONTROL DASHBOARD</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"📹 <b>Total Videos:</b> <code>{total_vids}</code>\n"
        f"💾 <b>Total Storage:</b> <code>{total_size}</code>\n"
        f"🔗 <b>Active Links:</b> <code>{total_vids}</code>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "💡 <i>Send any video directly to this chat to upload it instantly.</i>"
    )
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=get_admin_dashboard_keyboard(), parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(text, reply_markup=get_admin_dashboard_keyboard(), parse_mode=ParseMode.HTML)

# -------------------------------------------------------------------
# MEDIA HANDLERS
# -------------------------------------------------------------------
async def handle_video_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    message = update.message
    video = message.video or message.document

    if not video:
        return

    file_id = video.file_id
    file_unique_id = video.file_unique_id
    file_name = getattr(video, 'file_name', None) or f"Video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
    file_size = getattr(video, 'file_size', 0)

    token = save_video(file_id, file_unique_id, file_name, file_size)
    link = f"https://t.me/{BOT_USERNAME}?start={token}"

    text = (
        "✅ <b>Video Uploaded Successfully!</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"📛 <b>Name:</b> <code>{file_name}</code>\n"
        f"📦 <b>Size:</b> <code>{format_bytes(file_size)}</code>\n"
        f"🔑 <b>Token:</b> <code>{token}</code>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 <b>Access Link:</b>\n<code>{link}</code>"
    )
    await message.reply_text(text, parse_mode=ParseMode.HTML, protect_content=True)

# -------------------------------------------------------------------
# CALLBACK QUERY HANDLER
# -------------------------------------------------------------------
async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if not is_admin(user_id):
        await query.answer("⛔ Unauthorized access.", show_alert=True)
        return

    await query.answer()
    data = query.data

    if data == "admin_dashboard":
        await show_admin_dashboard(update, context)

    elif data.startswith("manage_files_"):
        page = int(data.split("_")[2])
        per_page = 5
        total_count = get_total_videos_count()
        videos = get_all_videos(limit=per_page, offset=page * per_page)
        
        if not videos and page > 0:
            page = 0
            videos = get_all_videos(limit=per_page, offset=0)

        text = (
            "📁 <b>FILE MANAGER</b>\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            f"Select a file to inspect details, get share links, or delete:\n"
            f"<i>Page {page + 1} of {max(1, (total_count + per_page - 1) // per_page)}</i>"
        )
        await query.edit_message_text(text, reply_markup=get_file_manager_keyboard(videos, page, total_count, per_page), parse_mode=ParseMode.HTML)

    elif data.startswith("file_view_"):
        parts = data.split("_")
        video_id = int(parts[2])
        page = int(parts[3])
        
        video = get_video_by_id(video_id)
        if not video:
            await query.edit_message_text("❌ File not found.", reply_markup=get_admin_dashboard_keyboard())
            return

        link = f"https://t.me/{BOT_USERNAME}?start={video['token']}"
        text = (
            "📄 <b>FILE DETAILS</b>\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 <b>ID:</b> <code>{video['id']}</code>\n"
            f"📛 <b>Name:</b> <code>{video['file_name']}</code>\n"
            f"📦 <b>Size:</b> <code>{format_bytes(video['file_size'])}</code>\n"
            f"📅 <b>Uploaded:</b> <code>{video['upload_date']}</code>\n"
            f"🔑 <b>Token:</b> <code>{video['token']}</code>\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            f"🔗 <b>Link:</b>\n<code>{link}</code>"
        )
        await query.edit_message_text(text, reply_markup=get_video_detail_keyboard(video_id, page, video['token']), parse_mode=ParseMode.HTML)

    elif data.startswith("watch_"):
        video_id = int(data.split("_")[1])
        video = get_video_by_id(video_id)
        if video:
            sent_msg = await context.bot.send_video(
                chat_id=query.message.chat_id,
                video=video["file_id"],
                caption=f"🎥 <b>Preview:</b> {video['file_name']}\n\n⚠️ <i>এই প্রিভিউ ভিডিওটি ১০ মিনিট পর মুছে যাবে।</i>",
                parse_mode=ParseMode.HTML,
                protect_content=True
            )
            context.application.create_task(
                delete_message_after_delay(context, query.message.chat_id, sent_msg.message_id, 600)
            )

    elif data.startswith("delete_confirm_"):
        parts = data.split("_")
        video_id = int(parts[2])
        page = int(parts[3])
        video = get_video_by_id(video_id)
        
        text = f"⚠️ <b>Are you sure you want to delete this file?</b>\n\n<b>Name:</b> {video['file_name'] if video else 'Unknown'}\n\n<i>This will immediately revoke its share link.</i>"
        await query.edit_message_text(text, reply_markup=get_delete_confirm_keyboard(video_id, page), parse_mode=ParseMode.HTML)

    elif data.startswith("delete_do_"):
        parts = data.split("_")
        video_id = int(parts[2])
        page = int(parts[3])
        
        success = delete_video_by_id(video_id)
        if success:
            await query.answer("🗑️ File deleted successfully.", show_alert=True)
        else:
            await query.answer("❌ File was already removed.", show_alert=True)
            
        total_count = get_total_videos_count()
        per_page = 5
        videos = get_all_videos(limit=per_page, offset=page * per_page)
        text = "📁 <b>FILE MANAGER</b>\n━━━━━━━━━━━━━━━━━━━\nSelect a file to manage:"
        await query.edit_message_text(text, reply_markup=get_file_manager_keyboard(videos, page, total_count, per_page), parse_mode=ParseMode.HTML)

    elif data == "bot_stats":
        total_vids = get_total_videos_count()
        total_size = format_bytes(get_total_storage_bytes())
        text = (
            "📊 <b>BOT SYSTEM STATISTICS</b>\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            f"📹 <b>Indexed Videos:</b> <code>{total_vids}</code>\n"
            f"💾 <b>Calculated Volume:</b> <code>{total_size}</code>\n"
            f"👑 <b>Admin ID:</b> <code>{ADMIN_ID}</code>\n"
            f"🤖 <b>Bot Engine:</b> <code>python-telegram-bot 22.8</code>\n"
            "━━━━━━━━━━━━━━━━━━━"
        )
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Dashboard", callback_data="admin_dashboard")]])
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)

    elif data == "upload_info":
        text = (
            "📤 <b>HOW TO UPLOAD</b>\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "Simply forward or upload any video or video document directly into this chat.\n\n"
            "The bot will automatically register it in SQLite and generate a protected deep link for distribution."
        )
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Dashboard", callback_data="admin_dashboard")]])
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)

# -------------------------------------------------------------------
# MAIN APPLICATION INITIALIZATION
# -------------------------------------------------------------------
def main():
    init_db()
    
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_video_upload))
    application.add_handler(CallbackQueryHandler(handle_callbacks))

    logger.info("Bot starting...")
    application.run_polling()

if __name__ == "__main__":
    main()
