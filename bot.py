import logging
import time
import secrets
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ParseMode
from telegram.ext import CallbackContext
from html import escape

from config import *
from database import *
from utils import *

logger = logging.getLogger(__name__)

# ---------- Helper functions ----------
def is_premium(user_id):
    user = get_user(user_id)
    if not user:
        return False
    premium_until = user.get("premium_until")
    if premium_until:
        return datetime.now() < datetime.fromisoformat(premium_until)
    return False

def can_use_daily_free(user_id):
    daily_count, _ = get_daily_data(user_id)
    limit = get_daily_free_limit(user_id)
    return daily_count < limit

def deduct_credits(user_id, chat_id=None):
    if chat_id == OFFICIAL_GROUP_ID:
        return True
    if is_global_free_mode_active() or is_free_mode_active():
        return True
    if is_admin(user_id) or is_premium(user_id):
        return True
    user = get_user(user_id)
    if not user:
        return False
    if user.get("referral_count", 0) >= REFERRAL_TIER_2_COUNT:
        return True
    if user.get("credits", 0) >= SEARCH_COST:
        update_credits(user_id, -SEARCH_COST)
        return True
    return False

def get_info_footer(user_id, chat_id=None):
    if chat_id == OFFICIAL_GROUP_ID:
        return "\n\n🚀 <b>Official Group:</b> No credits used"
    if is_global_free_mode_active():
        return "\n\n🌍 <b>Global Free Mode ACTIVE!</b>"
    if is_free_mode_active():
        return "\n\n✨ <b>Free Mode ACTIVE!</b>"
    
    user = get_user(user_id)
    if not user:
        return "\n\n💰 Credits: 0\n📊 Referrals: 0\n🎁 Daily free used: 0/0"
    
    credits = user.get("credits", 0)
    referral_count = user.get("referral_count", 0)
    daily_used, _ = get_daily_data(user_id)
    daily_limit = get_daily_free_limit(user_id)
    
    created_at = user.get("created_at")
    is_first_day = False
    if created_at:
        today = datetime.now().date()
        if created_at.date() == today:
            is_first_day = True
    
    if is_first_day:
        daily_text = "Daily free search will provide you Tomorrow."
    else:
        daily_text = f"{daily_used}/{daily_limit}"
    
    footer = f"\n\n💰 Credits: {credits}\n📊 Referrals: {referral_count}\n🎁 Daily free used: {daily_text}"
    return footer

def check_membership(user_id, channel_id, context):
    try:
        member = context.bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False

def is_subscribed(user_id, context):
    return check_membership(user_id, REQUIRED_CHANNEL_1_ID, context) and \
           check_membership(user_id, REQUIRED_CHANNEL_2_ID, context)

def send_join_message(update, context):
    if update.callback_query:
        msg = update.callback_query.message
    else:
        msg = update.message
    keyboard = [
        [InlineKeyboardButton("➡️ Join Channel 1", url=CHANNEL_1_INVITE_LINK)],
        [InlineKeyboardButton("➡️ Join Channel 2", url=CHANNEL_2_INVITE_LINK)],
        [InlineKeyboardButton("✅ Verify", callback_data='verify_join')]
    ]
    msg.reply_text("❌ <b>You must join both channels to use this bot!</b>\n\nJoin and click Verify.",
                   reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)

def check_and_require_subscription(update, context, user_id):
    if not is_subscribed(user_id, context):
        send_join_message(update, context)
        return False
    return True

# ---------- Admin Notification Helper ----------
def notify_admins_new_user(context, user):
    from config import ADMIN_IDS
    admin_ids = set(ADMIN_IDS)
    for doc in admins.find():
        admin_ids.add(doc["_id"])
    
    user_name = user.first_name or "Unknown"
    user_username = f"@{user.username}" if user.username else "No username"
    
    for admin_id in admin_ids:
        try:
            context.bot.send_message(
                chat_id=admin_id,
                text=(
                    f"🆕 <b>New User Verified!</b>\n\n"
                    f"👤 <b>User:</b> {user_name}\n"
                    f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
                    f"📛 <b>Username:</b> {user_username}\n"
                    f"⏰ <b>Time:</b> {datetime.now()}"
                ),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
            logger.info(f"📩 New user notification sent to admin {admin_id}")
        except Exception as e:
            logger.error(f"❌ Failed to notify admin {admin_id}: {e}")

# ---------- Search Log (with Owner Privacy) ----------
def log_search_to_channel(context, user, search_type, query, result="", success=True, chat_id=None):
    from config import OWNER_USER_IDS
    if user.id in OWNER_USER_IDS:
        logger.info(f"🔒 Skipping log for owner user {user.id}")
        return
    try:
        user_name = escape(user.first_name or "Unknown")
        user_username = f"@{escape(user.username)}" if user.username else "No username"
        status = "✅" if success else "❌"
        
        log_text = f"{status} <b>Search Log</b>\n\n"
        log_text += f"<b>👤 User:</b> {user_name}\n"
        log_text += f"<b>🆔 ID:</b> <code>{user.id}</code>\n"
        log_text += f"<b>📛 Username:</b> {user_username}\n"
        log_text += f"<b>🔍 Type:</b> {search_type}\n"
        log_text += f"<b>📝 Query:</b> <code>{escape(query)}</code>\n"
        log_text += f"<b>⏰ Time:</b> {datetime.now()}\n"
        
        if chat_id and chat_id == OFFICIAL_GROUP_ID:
            log_text += "<b>🌐 Location:</b> Official Group\n"
        else:
            log_text += "<b>🌐 Location:</b> Private Chat\n"
        
        if result:
            log_text += f"\n<b>📄 Result:</b>\n{result}\n"
        
        log_text += "\n💞<b>Developer: @ll_VIPIN_ll</b>"
        
        context.bot.send_message(
            chat_id=LOG_CHANNEL_ID,
            text=log_text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        logger.info(f"✅ Log sent for user {user.id}")
    except Exception as e:
        logger.error(f"❌ Log error for user {user.id}: {e}")

# ---------- Broadcast Background Task (FAST) ----------
def broadcast_task(context):
    """Background task to send broadcast quickly with flood-wait handling."""
    job = context.job
    message = job.context['message']
    admin_chat_id = job.context['admin_chat_id']
    
    success = 0
    fail = 0
    total = 0
    banned_users_set = set()
    for doc in banned_users.find():
        banned_users_set.add(doc["_id"])
    
    for user in users.find():
        total += 1
        uid = user["_id"]
        if uid in banned_users_set:
            continue
        try:
            context.bot.send_message(chat_id=uid, text=message, parse_mode=ParseMode.HTML)
            success += 1
        except Exception as e:
            fail += 1
            if hasattr(e, 'retry_after'):
                wait = e.retry_after
                logger.warning(f"Rate limited for {uid}, waiting {wait}s")
                time.sleep(wait)
                try:
                    context.bot.send_message(chat_id=uid, text=message, parse_mode=ParseMode.HTML)
                    success += 1
                    fail -= 1
                except:
                    pass
            else:
                logger.warning(f"Broadcast failed for {uid}: {e}")
    
    report = (
        f"📢 <b>Broadcast completed!</b>\n"
        f"👥 Total users: {total}\n"
        f"✅ Success: {success}\n"
        f"❌ Failed: {fail}"
    )
    try:
        context.bot.send_message(chat_id=admin_chat_id, text=report, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Could not send broadcast report to admin: {e}")

def delete_message(context):
    job = context.job
    try:
        context.bot.delete_message(chat_id=job.context['chat_id'], message_id=job.context['message_id'])
        logger.info(f"✅ Message {job.context['message_id']} deleted successfully")
    except Exception as e:
        logger.warning(f"⚠️ Delete message error (already deleted or not found): {e}")

# ---------- Ensure User Exists ----------
def ensure_user(user_id):
    if not get_user(user_id):
        create_user(user_id)

# ---------- Keyboards ----------
def get_main_keyboard(user_id):
    keyboard = [
        ["India Number 🇮🇳"],
        ["Check Credit 💰", "Get Referral Link 🔗"],
        ["Redeem Code 🎁", "Buy Premium & Credits 💎"],
        ["Support 👨‍💻", "Official Group 🚀"],
        ["Privacy Policy 🔒", "Protection 🛡️"]
    ]
    if is_admin(user_id):
        keyboard.append(["Admin Panel 👑"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_protection_keyboard():
    return ReplyKeyboardMarkup([
        ["Protect Number ➕🛡️", "Unprotect Number ➖🛡️"],
        ["My Protected 📋"],
        ["Back to Main 🔙"]
    ], resize_keyboard=True)

def get_admin_keyboard():
    return ReplyKeyboardMarkup([
        ["Add Credits ➕", "Remove Credits ➖"],
        ["Add Premium ⭐", "Remove Premium ⭐➖"],
        ["Add Credits to All 💰👥", "User History 📝"],
        ["Broadcast 📢", "Premium List 📋"],
        ["Block User 🚫", "Unblock User ✅"],
        ["Blocked List 📋🚫", "Bot Stats 📊"],
        ["Generate Code 🎁", "Toggle Group Free 🎯"],
        ["Toggle Global Free 🌍", "Set Daily Limit 🔢"],
        ["Referral Stats 📈", "Number Protection 🛡️"],
        ["Admin Management 👨‍💼", "Toggle Public Protection 🔄"],
        ["Auto-Delete Time ⏱️", "Maintenance Mode ⚠️"],
        ["Back to Main 🔙"]
    ], resize_keyboard=True)

def get_number_protection_keyboard():
    return ReplyKeyboardMarkup([
        ["Protect Number ➕🛡️", "Unprotect Number ➖🛡️"],
        ["Protected List 📋🛡️"],
        ["Back to Admin 🔙"]
    ], resize_keyboard=True)

def get_admin_management_keyboard():
    return ReplyKeyboardMarkup([
        ["Add Admin ➕👨‍💼", "Remove Admin ➖👨‍💼"],
        ["Admin List 📋👨‍💼"],
        ["Back to Admin 🔙"]
    ], resize_keyboard=True)

def get_buy_keyboard():
    return ReplyKeyboardMarkup([
        ["Premium Plans ⭐", "Credit Packages 💰"],
        ["Back to Main 🔙"]
    ], resize_keyboard=True)

# ---------- Command Handlers ----------
def start(update: Update, context: CallbackContext):
    user = update.effective_user
    chat = update.effective_chat
    ensure_user(user.id)
    
    if is_maintenance_mode_active() and not is_admin(user.id):
    update.message.reply_text(
        "⚠️ 🤖 Bot is currently under maintenance. 🛠️\n\n"
        "⚠️ Please try again after some time.\n"
        "We will notify you when the bot runs properly.\n\n"
        "🙏 Thank you for your patience and understanding! 💙",
        parse_mode=ParseMode.HTML
    )
    return
    
    if is_banned(user.id):
        return
    if chat.type != 'private' and chat.id != OFFICIAL_GROUP_ID:
        update.message.reply_text("❌ This bot works only in private chat or official group.")
        return
    if chat.type == 'private' and not check_and_require_subscription(update, context, user.id):
        return

    daily_limit = get_daily_free_limit(user.id)
    if daily_limit == 0:
        daily_text = "No daily free on first day (use credits)"
    else:
        daily_text = f"{daily_limit} free searches daily"
    
    text = f"<b>🎉 Welcome, {user.first_name}!</b>\n\n🔍 India Number Lookup\n💰 {daily_text}\n🔗 Referrals: 5 credits each, premium at {REFERRAL_TIER_1_COUNT}, unlimited at {REFERRAL_TIER_2_COUNT}\n\nUse buttons below."
    update.message.reply_text(text, reply_markup=get_main_keyboard(user.id), parse_mode=ParseMode.HTML)

def help_command(update: Update, context: CallbackContext):
    user = update.effective_user
    chat = update.effective_chat
    ensure_user(user.id)
    
    if chat.type != 'private' and chat.id != OFFICIAL_GROUP_ID:
        update.message.reply_text("❌ Not allowed here.")
        return
    if is_banned(user.id):
        return
    if chat.type == 'private' and not check_and_require_subscription(update, context, user.id):
        return
    if chat.id == OFFICIAL_GROUP_ID:
        text = "🚀 <b>Official Group</b>\nUse /phone 9876543210\nUnlimited free searches!"
    else:
        text = "🤖 <b>Help</b>\n/phone <number>\n/redeem <code>\nUse buttons for more."
    update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard(user.id))

def phone_command(update: Update, context: CallbackContext):
    user = update.effective_user
    chat = update.effective_chat
    ensure_user(user.id)
    
    if is_maintenance_mode_active() and not is_admin(user.id):
        update.message.reply_text("⚠️ Maintenance mode.")
        return
    if is_banned(user.id):
        return
    if chat.type != 'private' and chat.id != OFFICIAL_GROUP_ID:
        update.message.reply_text("❌ Not allowed here.")
        return
    if chat.type == 'private' and not check_and_require_subscription(update, context, user.id):
        return
    if not context.args:
        update.message.reply_text("Usage: /phone 9876543210")
        return
    raw = context.args[0].strip()
    normalized = normalize_phone_number(raw)
    if not normalized:
        update.message.reply_text("❌ Invalid Indian phone number.")
        return
    perform_phone_lookup(update, context, normalized, raw)

# ---------- UPDATED: perform_phone_lookup with refund logic ----------
def perform_phone_lookup(update, context, phone, raw):
    user = update.effective_user
    chat = update.effective_chat

    # Check if number is protected
    if is_number_protected(phone):
        protected = get_all_protected_numbers()
        for p in protected:
            if p["_id"] == phone:
                update.message.reply_text(p.get("message", "❌ No data."), parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='back_to_main')]]))
                log_search_to_channel(context, user, "Phone", raw, "Protected", False, chat.id)
                return

    use_daily = False
    credit_used = False   # <-- NEW: track if a credit was spent

    # Credit / daily logic
    if chat.type == 'private':
        if not (is_global_free_mode_active() or is_free_mode_active() or is_admin(user.id) or is_premium(user.id)):
            if can_use_daily_free(user.id):
                use_daily = True
                increment_daily_searches(user.id)
            else:
                if not deduct_credits(user.id, chat.id):
                    update.message.reply_text("❌ Insufficient credits. Use referrals or daily free.")
                    return
                credit_used = True   # <-- we deducted a credit

    msg = update.message.reply_text("🔍 Searching...", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='back_to_main')]]))
    records = fetch_phone_info(phone)

    # ================== NO DATA FOUND ==================
    if not records:
        # If a credit was used and the user has admin‑gifted credits, refund it
        if credit_used and is_admin_credit_protected(user.id):
            update_credits(user.id, 1)   # refund
            log_user_action(user.id, "Refunded Credit (No Data)", phone)
            msg.edit_text(
                f"❌ No data found for {phone}.\n\n💡 Your credit has been refunded because you have admin‑gifted credits.",
                parse_mode=ParseMode.HTML
            )
        else:
            msg.edit_text(f"❌ No data found for {phone}.", parse_mode=ParseMode.HTML)
        log_search_to_channel(context, user, "Phone", raw, "No data", False, chat.id)
        return
    # ===================================================

    result = f"🔍 <b>Phone Lookup Results for {phone}</b>\n\n"

    FIELD_LABELS = {
        'name': '👤 Name',
        'father_name': '👨‍👦 Father',
        'address': '📍 Address',
        'mobile': '📱 Mobile',
        'circle': '📡 Circle',
        'id': '🆔 ID Number',
        'id_number': '🆔 ID Number',
        'email': '📧 Email',
        'alternate_number': '📞 Alternate'
    }
    EXCLUDED_KEYS = {'dev', 'developer', 'owner', 'api_owner', 'dev_id'}

    for i, rec in enumerate(records[:10], 1):
        result += f"✅ <b>Result {i}:</b>\n\n"
        for key, value in rec.items():
            if key in EXCLUDED_KEYS:
                continue
            if not value or str(value).strip() in ['', 'N/A', 'null', 'None']:
                continue
            label = FIELD_LABELS.get(key, f"🔹 {key.replace('_', ' ').title()}")
            if key == 'address':
                value = format_address(str(value))
            result += f"<b>{label}:</b> {value}\n"
        result += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    result += "\n💞<b>Developer: @ll_VIPIN_ll</b>"
    result += get_info_footer(user.id, chat.id)

    auto_del = get_auto_delete_time()
    if auto_del > 0:
        if auto_del >= 3600:
            hours = auto_del // 3600
            time_str = f"{hours} hour{'s' if hours > 1 else ''}"
        elif auto_del >= 60:
            minutes = auto_del // 60
            time_str = f"{minutes} minute{'s' if minutes > 1 else ''}"
        else:
            time_str = f"{auto_del} second{'s' if auto_del > 1 else ''}"
        result += f"\n\n⏰ This message will be deleted in {time_str}."

    context.user_data['last_search_result'] = result
    context.user_data['last_search_query'] = phone
    context.user_data['last_search_type'] = 'phone'
    keyboard = [
        [InlineKeyboardButton("📥 Download", callback_data='download_info')],
        [InlineKeyboardButton("🔙 Back", callback_data='back_to_main')]
    ]
    msg.edit_text(result, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

    if auto_del > 0 and context.job_queue:
        context.job_queue.run_once(
            delete_message,
            auto_del,
            context={'chat_id': msg.chat_id, 'message_id': msg.message_id}
        )
        logger.info(f"⏰ Message {msg.message_id} scheduled for deletion in {auto_del} seconds")
    else:
        logger.warning(f"⚠️ Auto-delete not scheduled: auto_del={auto_del}, job_queue_exists={context.job_queue is not None}")

    log_search_to_channel(context, user, "Phone", raw, result, True, chat.id)
# -----------------------------------------------------------------

def redeem_command(update: Update, context: CallbackContext):
    user = update.effective_user
    ensure_user(user.id)
    if is_banned(user.id):
        return
    if not context.args:
        context.user_data['state'] = 'awaiting_redeem'
        update.message.reply_text("🎁 Send your redeem code:", reply_markup=get_main_keyboard(user.id))
        return
    code = context.args[0].strip().upper()
    credits = use_redeem_code(code, user.id)
    if credits is None:
        update.message.reply_text("❌ Invalid, used, or on cooldown.", reply_markup=get_main_keyboard(user.id))
    else:
        update.message.reply_text(f"✅ {credits} credits added!", reply_markup=get_main_keyboard(user.id))

def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    user = query.from_user
    query.answer()
    data = query.data
    if data == 'back_to_main':
        query.message.delete()
        query.message.reply_text("Main Menu", reply_markup=get_main_keyboard(user.id))
    elif data == 'verify_join':
        if is_subscribed(user.id, context):
            query.edit_message_text("✅ Verified! You can use the bot.")
            if not get_user(user.id):
                create_user(user.id)
                notify_admins_new_user(context, user)
        else:
            query.edit_message_text("❌ Not subscribed to both channels.")
    elif data == 'download_info':
        if 'last_search_result' not in context.user_data:
            query.answer("No result to download.", show_alert=True)
            return
        bot_username = context.bot.get_me().username
        file = create_search_result_file(context.user_data['last_search_result'], context.user_data['last_search_query'], context.user_data['last_search_type'], bot_username)
        context.bot.send_document(chat_id=query.message.chat_id, document=file, caption="✅ Download complete.")
        query.answer("File sent!")

# ---------- Message Handler (with smart menu fallback) ----------
def handle_message(update: Update, context: CallbackContext):
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    text = update.message.text.strip()
    chat = update.effective_chat
    ensure_user(user.id)
    
    if is_maintenance_mode_active() and not is_admin(user.id):
        update.message.reply_text("⚠️ Maintenance mode.")
        return
    if is_banned(user.id):
        return
    if chat.type != 'private' and chat.id != OFFICIAL_GROUP_ID:
        update.message.reply_text("❌ Not allowed.")
        return
    if chat.type == 'private' and not check_and_require_subscription(update, context, user.id):
        return

    # ---- Smart Menu Fallback: If user is in a submenu but presses a main menu button ----
    main_menu_buttons = [
        "India Number 🇮🇳",
        "Check Credit 💰",
        "Get Referral Link 🔗",
        "Redeem Code 🎁",
        "Buy Premium & Credits 💎",
        "Support 👨‍💻",
        "Official Group 🚀",
        "Privacy Policy 🔒",
        "Protection 🛡️",
        "Admin Panel 👑"
    ]
    current_menu = context.user_data.get('menu_level', 'main')
    if current_menu != 'main' and text in main_menu_buttons:
        context.user_data['menu_level'] = 'main'
    # ---------------------------------------------------------------------------------

    if is_admin(user.id) and context.user_data.get('admin_action'):
        handle_admin_action(update, context, text)
        return

    if context.user_data.get('state') == 'awaiting_redeem':
        context.user_data['state'] = None
        credits = use_redeem_code(text.upper(), user.id)
        update.message.reply_text(f"✅ {credits} credits added!" if credits else "❌ Invalid code.", reply_markup=get_main_keyboard(user.id))
        return

    if context.user_data.get('state') == 'awaiting_protect_number':
        context.user_data['state'] = None
        parts = text.split(maxsplit=1)
        if not parts:
            update.message.reply_text("❌ Please send a valid number.", reply_markup=get_main_keyboard(user.id))
            return
        number = parts[0].strip()
        message = parts[1] if len(parts) > 1 else None
        norm = normalize_phone_number(number)
        if not norm:
            update.message.reply_text("❌ Invalid Indian phone number. Please send a 10-digit number.", reply_markup=get_main_keyboard(user.id))
            return
        if protect_number(norm, user.id, message, first_name=user.first_name, username=user.username):
            update.message.reply_text(f"✅ Number {norm} protected successfully!", reply_markup=get_main_keyboard(user.id))
            log_user_action(user.id, "Protected Number (User)", norm)
        else:
            update.message.reply_text(f"❌ Number {norm} is already protected.", reply_markup=get_main_keyboard(user.id))
        return

    if context.user_data.get('state') == 'awaiting_unprotect_number':
        context.user_data['state'] = None
        number = text.strip()
        norm = normalize_phone_number(number)
        if not norm:
            update.message.reply_text("❌ Invalid Indian phone number. Please send a 10-digit number.", reply_markup=get_main_keyboard(user.id))
            return
        if unprotect_number(norm, user.id):
            update.message.reply_text(f"✅ Number {norm} unprotected successfully!", reply_markup=get_main_keyboard(user.id))
            log_user_action(user.id, "Unprotected Number (User Menu)", norm)
        else:
            update.message.reply_text(f"❌ Could not unprotect {norm}. It may not be protected or you are not the protector.", reply_markup=get_main_keyboard(user.id))
        return

    norm = normalize_phone_number(text)
    if norm:
        perform_phone_lookup(update, context, norm, text)
        return

    menu = context.user_data.get('menu_level', 'main')
    if menu == 'main':
        handle_main_menu(update, context, text)
    elif menu == 'admin':
        handle_admin_menu(update, context, text)
    elif menu == 'buy':
        handle_buy_menu(update, context, text)
    elif menu == 'admin_number_protection':
        handle_number_protection_menu(update, context, text)
    elif menu == 'admin_management':
        handle_admin_management_menu(update, context, text)
    elif menu == 'protection':
        handle_protection_menu(update, context, text)
    else:
        context.user_data['menu_level'] = 'main'
        update.message.reply_text("Main menu", reply_markup=get_main_keyboard(user.id))

# ---------- Menu Handlers ----------
def handle_main_menu(update, context, text):
    user = update.effective_user
    if text == "India Number 🇮🇳":
        context.user_data['state'] = 'awaiting_search'
        update.message.reply_text("🔍 Send 10-digit Indian mobile number:", reply_markup=get_main_keyboard(user.id))
    elif text == "Check Credit 💰":
        user_data = get_user(user.id)
        credits = user_data["credits"] if user_data else 0
        referral_count = user_data["referral_count"] if user_data else 0
        daily_used, _ = get_daily_data(user.id)
        daily_limit = get_daily_free_limit(user.id)
        created_at = user_data.get("created_at") if user_data else None
        is_first_day = False
        if created_at:
            today = datetime.now().date()
            if created_at.date() == today:
                is_first_day = True
        if is_first_day:
            daily_text = "Daily free search will provide you Tomorrow."
        else:
            daily_text = f"{daily_used}/{daily_limit}"
        msg = f"💰 Credits: {credits}\n📊 Referrals: {referral_count}\n🎁 Daily free used: {daily_text}"
        update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard(user.id))
    elif text == "Get Referral Link 🔗":
        bot_username = context.bot.get_me().username
        link = f"https://t.me/{bot_username}?start={user.id}"
        update.message.reply_text(f"🔗 Your referral link:\n<code>{link}</code>\n\nYou get 5 credits per referral, 1-day premium at {REFERRAL_TIER_1_COUNT} referrals, unlimited at {REFERRAL_TIER_2_COUNT}!", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Share", url=f"https://t.me/share/url?url={link}")]]))
    elif text == "Redeem Code 🎁":
        context.user_data['state'] = 'awaiting_redeem'
        update.message.reply_text("🎁 Send your redeem code:", reply_markup=get_main_keyboard(user.id))
    elif text == "Buy Premium & Credits 💎":
        context.user_data['menu_level'] = 'buy'
        update.message.reply_text("💎 Choose an option:", reply_markup=get_buy_keyboard())
    elif text == "Support 👨‍💻":
        update.message.reply_text(f"👨‍💻 Contact @{SUPPORT_USERNAME}", parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard(user.id))
    elif text == "Official Group 🚀":
        update.message.reply_text(f"🚀 Official Group: {OFFICIAL_GROUP_LINK}\n\nJoin for unlimited free searches!", parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard(user.id))
    elif text == "Privacy Policy 🔒":
        update.message.reply_text("🔒 We do not store any personal data. Only credits and referral counts are kept.", parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard(user.id))
    elif text == "Protection 🛡️":
        if not is_public_protection_enabled():
            update.message.reply_text("❌ Public protection feature is currently disabled by admin.", reply_markup=get_main_keyboard(user.id))
            return
        context.user_data['menu_level'] = 'protection'
        update.message.reply_text("🛡️ <b>Number Protection</b>\nChoose an option below:", parse_mode=ParseMode.HTML, reply_markup=get_protection_keyboard())
    elif text == "Admin Panel 👑" and is_admin(user.id):
        context.user_data['menu_level'] = 'admin'
        update.message.reply_text("👑 Admin Panel", reply_markup=get_admin_keyboard())

def handle_protection_menu(update, context, text):
    user = update.effective_user
    if text == "Back to Main 🔙":
        context.user_data['menu_level'] = 'main'
        update.message.reply_text("Main menu", reply_markup=get_main_keyboard(user.id))
    elif text == "Protect Number ➕🛡️":
        context.user_data['state'] = 'awaiting_protect_number'
        update.message.reply_text("🛡️ Send the 10-digit Indian mobile number you want to protect.\nYou can also add an optional custom message (separate with space after number).\n\nExample: `9876543210 This number is private.`", parse_mode=ParseMode.HTML, reply_markup=get_protection_keyboard())
    elif text == "Unprotect Number ➖🛡️":
        context.user_data['state'] = 'awaiting_unprotect_number'
        update.message.reply_text("🔓 Send the 10-digit Indian mobile number you want to unprotect.", reply_markup=get_protection_keyboard())
    elif text == "My Protected 📋":
        protected_list = get_user_protected_numbers(user.id)
        if not protected_list:
            update.message.reply_text("📋 You haven't protected any numbers yet.", reply_markup=get_protection_keyboard())
            return
        msg = "📋 <b>Your Protected Numbers</b>\n\n"
        for p in protected_list:
            number = p["_id"]
            protected_at = p.get("protected_at", "Unknown date")
            if isinstance(protected_at, datetime):
                protected_at = protected_at.strftime("%Y-%m-%d %H:%M")
            msg += f"📱 <code>{number}</code>\n🕒 {protected_at}\n\n"
        update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=get_protection_keyboard())
    else:
        update.message.reply_text("Please use the buttons below.", reply_markup=get_protection_keyboard())

def handle_admin_menu(update, context, text):
    user = update.effective_user
    if text == "Back to Main 🔙":
        context.user_data['menu_level'] = 'main'
        update.message.reply_text("Main menu", reply_markup=get_main_keyboard(user.id))
    elif text == "Number Protection 🛡️":
        context.user_data['menu_level'] = 'admin_number_protection'
        update.message.reply_text("🛡️ Number Protection", reply_markup=get_number_protection_keyboard())
    elif text == "Admin Management 👨‍💼":
        if not user.id in ADMIN_IDS:
            update.message.reply_text("❌ Only owners can manage admins.", reply_markup=get_admin_keyboard())
            return
        context.user_data['menu_level'] = 'admin_management'
        update.message.reply_text("👨‍💼 Admin Management", reply_markup=get_admin_management_keyboard())
    elif text == "Auto-Delete Time ⏱️":
        context.user_data['admin_action'] = 'set_auto_delete'
        update.message.reply_text(f"Current auto-delete: {get_auto_delete_time()} seconds.\nSend new time (0 = off):", reply_markup=get_admin_keyboard())
    elif text == "Maintenance Mode ⚠️":
        new = not is_maintenance_mode_active()
        set_maintenance_mode(new)
        update.message.reply_text(f"⚠️ Maintenance mode is {'ON' if new else 'OFF'}.", reply_markup=get_admin_keyboard())
        log_user_action(user.id, "Toggled Maintenance Mode", str(new))
    elif text == "Add Credits ➕":
        context.user_data['admin_action'] = 'add_credits'
        update.message.reply_text("💰 Send: user_id credits", reply_markup=get_admin_keyboard())
    elif text == "Remove Credits ➖":
        context.user_data['admin_action'] = 'remove_credits'
        update.message.reply_text("💰 Send: user_id credits", reply_markup=get_admin_keyboard())
    elif text == "Add Premium ⭐":
        context.user_data['admin_action'] = 'add_premium'
        update.message.reply_text("⭐ Send: user_id [days]", reply_markup=get_admin_keyboard())
    elif text == "Remove Premium ⭐➖":
        context.user_data['admin_action'] = 'remove_premium'
        update.message.reply_text("⭐ Send user_id", reply_markup=get_admin_keyboard())
    elif text == "Add Credits to All 💰👥":
        context.user_data['admin_action'] = 'add_credits_all'
        update.message.reply_text("💰 Enter number of credits for every user:", reply_markup=get_admin_keyboard())
    elif text == "User History 📝":
        update.message.reply_text("Use /history <user_id>", reply_markup=get_admin_keyboard())
    elif text == "Broadcast 📢":
        context.user_data['admin_action'] = 'broadcast'
        update.message.reply_text("📢 Send the broadcast message:", reply_markup=get_admin_keyboard())
    elif text == "Premium List 📋":
        premium_users = [u["_id"] for u in users.find({"premium_until": {"$ne": None}})]
        if not premium_users:
            update.message.reply_text("No premium users.", reply_markup=get_admin_keyboard())
        else:
            msg = "⭐ Premium users:\n" + "\n".join(f"<code>{uid}</code>" for uid in premium_users[:50])
            update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=get_admin_keyboard())
    elif text == "Block User 🚫":
        context.user_data['admin_action'] = 'block_user'
        update.message.reply_text("🚫 Send user ID to block:", reply_markup=get_admin_keyboard())
    elif text == "Unblock User ✅":
        context.user_data['admin_action'] = 'unblock_user'
        update.message.reply_text("✅ Send user ID to unblock:", reply_markup=get_admin_keyboard())
    elif text == "Blocked List 📋🚫":
        blocked = [doc["_id"] for doc in banned_users.find()]
        if not blocked:
            update.message.reply_text("No blocked users.", reply_markup=get_admin_keyboard())
        else:
            update.message.reply_text("🚫 Blocked users:\n" + "\n".join(f"<code>{uid}</code>" for uid in blocked), parse_mode=ParseMode.HTML, reply_markup=get_admin_keyboard())
    elif text == "Bot Stats 📊":
        total_users = users.count_documents({})
        total_credits = sum(u.get("credits",0) for u in users.find())
        premium_count = users.count_documents({"premium_until": {"$ne": None}})
        banned_count = banned_users.count_documents({})
        protected_count = protected_numbers.count_documents({})
        admin_count = len(get_all_admins())
        update.message.reply_text(f"📊 Stats:\n👥 Users: {total_users}\n💰 Credits: {total_credits}\n⭐ Premium: {premium_count}\n🚫 Banned: {banned_count}\n🛡️ Protected: {protected_count}\n👑 Admins: {admin_count}", parse_mode=ParseMode.HTML, reply_markup=get_admin_keyboard())
    elif text == "Generate Code 🎁":
        update.message.reply_text("Use /gencode <credits> <uses>", reply_markup=get_admin_keyboard())
    elif text == "Toggle Group Free 🎯":
        new = not is_free_mode_active()
        set_free_mode(new)
        update.message.reply_text(f"🎯 Group Free Mode is {'ON' if new else 'OFF'}.", reply_markup=get_admin_keyboard())
    elif text == "Toggle Global Free 🌍":
        new = not is_global_free_mode_active()
        set_global_free_mode(new)
        update.message.reply_text(f"🌍 Global Free Mode is {'ON' if new else 'OFF'}. Notifying users...", reply_markup=get_admin_keyboard())
        for u in users.find():
            try:
                context.bot.send_message(chat_id=u["_id"], text=f"🌍 Global free mode {'activated' if new else 'deactivated'}.", parse_mode=ParseMode.HTML)
            except:
                pass
        log_user_action(user.id, "Toggled Global Free Mode", str(new))
    elif text == "Set Daily Limit 🔢":
        context.user_data['admin_action'] = 'set_daily_limit'
        update.message.reply_text("🔢 Enter new daily free limit:", reply_markup=get_admin_keyboard())
    elif text == "Referral Stats 📈":
        top = list(users.find({"referral_count": {"$gt": 0}}).sort("referral_count", -1).limit(10))
        if top:
            msg = "📈 Top referrers:\n" + "\n".join(f"<code>{u['_id']}</code> - {u['referral_count']}" for u in top)
        else:
            msg = "No referrals yet."
        update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=get_admin_keyboard())
    elif text == "Toggle Public Protection 🔄":
        current = is_public_protection_enabled()
        new_status = not current
        set_public_protection_status(new_status)
        status_text = "ON" if new_status else "OFF"
        update.message.reply_text(f"🔄 Public Protection is now <b>{status_text}</b>. Users can {'now' if new_status else 'no longer'} protect numbers.", parse_mode=ParseMode.HTML, reply_markup=get_admin_keyboard())
        log_user_action(user.id, "Toggled Public Protection", status_text)
    else:
        update.message.reply_text("Please use the admin panel buttons.", reply_markup=get_admin_keyboard())

# ---------- UPDATED: handle_number_protection_menu (adds admin credit protection) ----------
def handle_number_protection_menu(update, context, text):
    user = update.effective_user
    if text == "Back to Admin 🔙":
        context.user_data['menu_level'] = 'admin'
        update.message.reply_text("Admin Panel", reply_markup=get_admin_keyboard())
    elif text == "Protect Number ➕🛡️":
        context.user_data['admin_action'] = 'protect_number'
        update.message.reply_text("🛡️ Send number and optional message:", reply_markup=get_number_protection_keyboard())
    elif text == "Unprotect Number ➖🛡️":
        context.user_data['admin_action'] = 'unprotect_number'
        update.message.reply_text("🛡️ Send number to unprotect:", reply_markup=get_number_protection_keyboard())
    elif text == "Protected List 📋🛡️":
        protected = get_all_protected_numbers_with_user_info()
        if not protected:
            update.message.reply_text("No protected numbers.", reply_markup=get_number_protection_keyboard())
            return
        
        from config import OWNER_USER_IDS
        protected = [p for p in protected if p.get("user_id") not in OWNER_USER_IDS]
        
        if not protected:
            update.message.reply_text("No protected numbers (owner IDs hidden).", reply_markup=get_number_protection_keyboard())
            return
        msg = "🛡️ <b>Protected Numbers (with User Info)</b>\n\n"
        for p in protected[:20]:
            number = p["_id"]
            user_id = p.get("user_id", "Unknown")
            display_name = p.get("display_name", "Unknown")
            protected_at = p.get("protected_at")
            if isinstance(protected_at, datetime):
                protected_at = protected_at.strftime("%Y-%m-%d %H:%M")
            else:
                protected_at = str(protected_at) if protected_at else "Unknown"
            msg += f"📱 <code>{number}</code>\n👤 User: <code>{user_id}</code> ({display_name})\n🕒 {protected_at}\n"
            if p.get("message"):
                msg += f"📝 Message: {p['message']}\n"
            msg += "\n"
        if len(protected) > 20:
            msg += f"\n... and {len(protected)-20} more."
        update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=get_number_protection_keyboard())
    else:
        update.message.reply_text("Please use the number protection menu buttons.", reply_markup=get_number_protection_keyboard())

def handle_admin_management_menu(update, context, text):
    user = update.effective_user
    if text == "Back to Admin 🔙":
        context.user_data['menu_level'] = 'admin'
        update.message.reply_text("Admin Panel", reply_markup=get_admin_keyboard())
    elif text == "Add Admin ➕👨‍💼":
        if not user.id in ADMIN_IDS:
            update.message.reply_text("❌ Only owners can add admins.", reply_markup=get_admin_management_keyboard())
        else:
            context.user_data['admin_action'] = 'add_admin'
            update.message.reply_text("👨‍💼 Send user ID to make admin:", reply_markup=get_admin_management_keyboard())
    elif text == "Remove Admin ➖👨‍💼":
        if not user.id in ADMIN_IDS:
            update.message.reply_text("❌ Only owners can remove admins.", reply_markup=get_admin_management_keyboard())
        else:
            context.user_data['admin_action'] = 'remove_admin'
            update.message.reply_text("👨‍💼 Send user ID to remove admin:", reply_markup=get_admin_management_keyboard())
    elif text == "Admin List 📋👨‍💼":
        admins_list = get_all_admins()
        msg = "👑 Owners:\n" + "\n".join(f"<code>{uid}</code>" for uid in ADMIN_IDS) + "\n\n👨‍💼 Sub-admins:\n"
        sub_admins = [doc["_id"] for doc in admins.find()]
        msg += "\n".join(f"<code>{uid}</code>" for uid in sub_admins) if sub_admins else "None"
        update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=get_admin_management_keyboard())
    else:
        update.message.reply_text("Please use the admin management buttons.", reply_markup=get_admin_management_keyboard())

def handle_buy_menu(update, context, text):
    user = update.effective_user
    if text == "Back to Main 🔙":
        context.user_data['menu_level'] = 'main'
        update.message.reply_text("Main menu", reply_markup=get_main_keyboard(user.id))
    elif text == "Premium Plans ⭐":
        update.message.reply_text("⭐ Premium Plans:\n1 Week - ₹99\n15 Day's - ₹199\n1 Month - ₹299\nLifetime - ₹999\n\nContact @ll_VIPIN_ll or @Stampedk", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Contact Support", url=f"https://t.me/{SUPPORT_USERNAME}")]]))
    elif text == "Credit Packages 💰":
        update.message.reply_text("💰 Credit Packages:\n10 Credits - ₹15\n30 Credits - ₹45\n50 Credits - ₹75\n100 Credits - ₹150\n200 Credits - ₹300\n\nContact @ll_VIPIN_ll or @Stampedk", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Contact Support", url=f"https://t.me/{SUPPORT_USERNAME}")]]))
    else:
        update.message.reply_text("Please use the buy menu buttons.", reply_markup=get_buy_keyboard())

# ---------- UPDATED: handle_admin_action (adds admin_credit_protected flag) ----------
def handle_admin_action(update, context, text):
    user = update.effective_user
    action = context.user_data['admin_action']
    if text in ["Back to Main 🔙", "Back to Admin 🔙"]:
        context.user_data['admin_action'] = None
        if text == "Back to Main 🔙":
            context.user_data['menu_level'] = 'main'
            update.message.reply_text("Main menu", reply_markup=get_main_keyboard(user.id))
        else:
            context.user_data['menu_level'] = 'admin'
            update.message.reply_text("Admin Panel", reply_markup=get_admin_keyboard())
        return

    if action == 'add_credits':
        parts = text.split()
        if len(parts) != 2:
            update.message.reply_text("❌ Usage: user_id credits", reply_markup=get_admin_keyboard())
        else:
            try:
                uid = int(parts[0])
                credits = int(parts[1])
                update_credits(uid, credits)
                set_admin_credit_protected(uid, True)   # <-- NEW
                context.bot.send_message(chat_id=uid, text=f"💰 Admin added {credits} credits to your account.", parse_mode=ParseMode.HTML)
                update.message.reply_text(f"✅ Added {credits} credits to {uid}", reply_markup=get_admin_keyboard())
                log_user_action(user.id, "Added Credits", f"To: {uid}, Amount: {credits}")
            except:
                update.message.reply_text("❌ Invalid input.", reply_markup=get_admin_keyboard())
        context.user_data['admin_action'] = None

    elif action == 'remove_credits':
        parts = text.split()
        if len(parts) != 2:
            update.message.reply_text("❌ Usage: user_id credits", reply_markup=get_admin_keyboard())
        else:
            try:
                uid = int(parts[0])
                credits = int(parts[1])
                update_credits(uid, -credits)
                context.bot.send_message(chat_id=uid, text=f"💰 Admin removed {credits} credits from your account.", parse_mode=ParseMode.HTML)
                update.message.reply_text(f"✅ Removed {credits} credits from {uid}", reply_markup=get_admin_keyboard())
                log_user_action(user.id, "Removed Credits", f"From: {uid}, Amount: {credits}")
            except:
                update.message.reply_text("❌ Invalid input.", reply_markup=get_admin_keyboard())
        context.user_data['admin_action'] = None

    elif action == 'add_premium':
        parts = text.split()
        try:
            uid = int(parts[0])
            days = int(parts[1]) if len(parts) > 1 else None
            set_premium_until(uid, days)
            context.bot.send_message(chat_id=uid, text=f"🎉🎊 Congratulations! you got premium {'for '+str(days)+' days' if days else 'permanently'}!", parse_mode=ParseMode.HTML)
            update.message.reply_text(f"✅ Premium added to {uid}", reply_markup=get_admin_keyboard())
            log_user_action(user.id, "Added Premium", f"To: {uid}, Days: {days}")
        except:
            update.message.reply_text("❌ Usage: user_id [days]", reply_markup=get_admin_keyboard())
        context.user_data['admin_action'] = None

    elif action == 'remove_premium':
        try:
            uid = int(text)
            remove_premium(uid)
            context.bot.send_message(chat_id=uid, text="⚠️ Your premium access has been removed by admin.", parse_mode=ParseMode.HTML)
            update.message.reply_text(f"✅ Premium removed from {uid}", reply_markup=get_admin_keyboard())
            log_user_action(user.id, "Removed Premium", f"From: {uid}")
        except:
            update.message.reply_text("❌ Invalid user ID.", reply_markup=get_admin_keyboard())
        context.user_data['admin_action'] = None

    elif action == 'add_credits_all':
        try:
            credits = int(text)
            count = 0
            for u in users.find():
                uid = u["_id"]
                update_credits(uid, credits)
                set_admin_credit_protected(uid, True)   # <-- NEW
                try:
                    context.bot.send_message(chat_id=uid, text=f"💰 Admin gave {credits} credits to all users!", parse_mode=ParseMode.HTML)
                except:
                    pass
                count += 1
            update.message.reply_text(f"✅ Added {credits} credits to {count} users.", reply_markup=get_admin_keyboard())
            log_user_action(user.id, "Added Credits to All", f"Credits: {credits}")
        except:
            update.message.reply_text("❌ Invalid number.", reply_markup=get_admin_keyboard())
        context.user_data['admin_action'] = None

    elif action == 'broadcast':
        if context.job_queue:
            context.job_queue.run_once(
                broadcast_task,
                0,
                context={'message': text, 'admin_chat_id': update.effective_chat.id}
            )
            update.message.reply_text("📢 Broadcast started! You will receive a report when it's done.", reply_markup=get_admin_keyboard())
            log_user_action(user.id, "Broadcast", text[:50])
        else:
            update.message.reply_text("❌ Job queue not available.", reply_markup=get_admin_keyboard())
        context.user_data['admin_action'] = None

    elif action == 'block_user':
        try:
            uid = int(text)
            ban_user(uid)
            context.bot.send_message(chat_id=uid, text="🚫 You have been blocked from using this bot.", parse_mode=ParseMode.HTML)
            update.message.reply_text(f"✅ Blocked {uid}", reply_markup=get_admin_keyboard())
            log_user_action(user.id, "Blocked User", str(uid))
        except:
            update.message.reply_text("❌ Invalid ID.", reply_markup=get_admin_keyboard())
        context.user_data['admin_action'] = None

    elif action == 'unblock_user':
        try:
            uid = int(text)
            unban_user(uid)
            context.bot.send_message(chat_id=uid, text="✅ You have been unblocked. You can use the bot again.", parse_mode=ParseMode.HTML)
            update.message.reply_text(f"✅ Unblocked {uid}", reply_markup=get_admin_keyboard())
            log_user_action(user.id, "Unblocked User", str(uid))
        except:
            update.message.reply_text("❌ Invalid ID.", reply_markup=get_admin_keyboard())
        context.user_data['admin_action'] = None

    elif action == 'set_daily_limit':
        try:
            limit = int(text)
            set_daily_free_limit(limit)
            update.message.reply_text(f"✅ Daily free limit set to {limit}.", reply_markup=get_admin_keyboard())
            log_user_action(user.id, "Set Daily Limit", str(limit))
        except:
            update.message.reply_text("❌ Enter a number.", reply_markup=get_admin_keyboard())
        context.user_data['admin_action'] = None

    elif action == 'set_auto_delete':
        try:
            sec = int(text)
            set_auto_delete_time(sec)
            update.message.reply_text(f"✅ Auto-delete time set to {sec} seconds.", reply_markup=get_admin_keyboard())
        except:
            update.message.reply_text("❌ Invalid number.", reply_markup=get_admin_keyboard())
        context.user_data['admin_action'] = None

    elif action == 'protect_number':
        parts = text.split(maxsplit=1)
        if not parts:
            update.message.reply_text("❌ Usage: number [message]", reply_markup=get_number_protection_keyboard())
        else:
            num = parts[0]
            msg = parts[1] if len(parts) > 1 else None
            if protect_number(num, user.id, msg, first_name=user.first_name, username=user.username):
                update.message.reply_text(f"✅ Number {num} protected.", reply_markup=get_number_protection_keyboard())
                log_user_action(user.id, "Protected Number (Admin)", num)
            else:
                update.message.reply_text("❌ Already protected.", reply_markup=get_number_protection_keyboard())
        context.user_data['admin_action'] = None

    elif action == 'unprotect_number':
        num = text.strip()
        if unprotect_number(num, user.id):
            update.message.reply_text(f"✅ Number {num} unprotected.", reply_markup=get_number_protection_keyboard())
            log_user_action(user.id, "Unprotected Number (Admin)", num)
        else:
            update.message.reply_text("❌ Not protected or not authorized.", reply_markup=get_number_protection_keyboard())
        context.user_data['admin_action'] = None

    elif action == 'add_admin':
        try:
            uid = int(text)
            add_admin(uid)
            context.bot.send_message(chat_id=uid, text="👑 You have been promoted to admin! Use /admin to access panel.", parse_mode=ParseMode.HTML)
            update.message.reply_text(f"✅ Admin {uid} added.", reply_markup=get_admin_management_keyboard())
            log_user_action(user.id, "Added Admin", str(uid))
        except:
            update.message.reply_text("❌ Invalid ID.", reply_markup=get_admin_management_keyboard())
        context.user_data['admin_action'] = None

    elif action == 'remove_admin':
        try:
            uid = int(text)
            if uid in ADMIN_IDS:
                update.message.reply_text("❌ Cannot remove owner.", reply_markup=get_admin_management_keyboard())
            else:
                remove_admin(uid)
                context.bot.send_message(chat_id=uid, text="⚠️ Your admin privileges have been removed.", parse_mode=ParseMode.HTML)
                update.message.reply_text(f"✅ Admin {uid} removed.", reply_markup=get_admin_management_keyboard())
                log_user_action(user.id, "Removed Admin", str(uid))
        except:
            update.message.reply_text("❌ Invalid ID.", reply_markup=get_admin_management_keyboard())
        context.user_data['admin_action'] = None

    else:
        context.user_data['admin_action'] = None

# ---------- Additional Admin Commands ----------
def admin_command(update: Update, context: CallbackContext):
    if is_admin(update.effective_user.id):
        context.user_data['menu_level'] = 'admin'
        update.message.reply_text("👑 Admin Panel", reply_markup=get_admin_keyboard())
    else:
        update.message.reply_text("❌ Not admin.")

def gencode(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        update.message.reply_text("❌ Admin only.")
        return
    if len(context.args) != 2:
        update.message.reply_text("Usage: /gencode <credits> <uses>")
        return
    try:
        credits = int(context.args[0])
        uses = int(context.args[1])
        code = generate_redeem_code(credits, uses, update.effective_user.id)
        update.message.reply_text(f"✅ Code: <code>{code}</code>\nCredits: {credits}\nUses: {uses}", parse_mode=ParseMode.HTML)
        log_user_action(update.effective_user.id, "Generated Code", f"Code: {code}")
    except:
        update.message.reply_text("❌ Invalid numbers.")

def history_command(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        update.message.reply_text("❌ Admin only.")
        return
    if not context.args:
        update.message.reply_text("Usage: /history <user_id>")
        return
    try:
        uid = int(context.args[0])
        from config import OWNER_USER_IDS
        if uid in OWNER_USER_IDS:
            update.message.reply_text("❌ No history available for this user.")
            return
        hist = list(user_history.find({"user_id": uid}).sort("timestamp", -1).limit(10))
        if not hist:
            update.message.reply_text(f"No history for {uid}.")
            return
        msg = f"History for {uid}:\n"
        for h in hist:
            msg += f"{h['timestamp']} - {h['action']} - {h['details']}\n"
        update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    except:
        update.message.reply_text("Invalid user ID.")

def protect_command(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        update.message.reply_text("❌ Admin only.")
        return
    if len(context.args) < 1:
        update.message.reply_text("Usage: /protect <number> [message]")
        return
    num = context.args[0]
    msg = ' '.join(context.args[1:]) if len(context.args) > 1 else None
    if protect_number(num, update.effective_user.id, msg, first_name=update.effective_user.first_name, username=update.effective_user.username):
        update.message.reply_text(f"✅ Number {num} protected.")
    else:
        update.message.reply_text("❌ Already protected.")

def unprotect_command(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        update.message.reply_text("❌ Admin only.")
        return
    if not context.args:
        update.message.reply_text("Usage: /unprotect <number>")
        return
    num = context.args[0]
    if unprotect_number(num, update.effective_user.id):
        update.message.reply_text(f"✅ Number {num} unprotected.")
    else:
        update.message.reply_text("❌ Not protected or not authorized.")

def protected_command(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        update.message.reply_text("❌ Admin only.")
        return
    protected = get_all_protected_numbers_with_user_info()
    if not protected:
        update.message.reply_text("No protected numbers.")
        return
    from config import OWNER_USER_IDS
    protected = [p for p in protected if p.get("user_id") not in OWNER_USER_IDS]
    if not protected:
        update.message.reply_text("No protected numbers (owner IDs hidden).")
        return
    msg = "🛡️ Protected numbers:\n"
    for p in protected[:20]:
        msg += f"{p['_id']} - protected by {p.get('user_id', 'Unknown')} at {p.get('protected_at', '')}\n"
    update.message.reply_text(msg, parse_mode=ParseMode.HTML)

def addadmin_command(update: Update, context: CallbackContext):
    if not update.effective_user.id in ADMIN_IDS:
        update.message.reply_text("❌ Only owners.")
        return
    if not context.args:
        update.message.reply_text("Usage: /addadmin <user_id>")
        return
    try:
        uid = int(context.args[0])
        add_admin(uid)
        update.message.reply_text(f"✅ Admin {uid} added.")
        context.bot.send_message(chat_id=uid, text="👑 You are now an admin.", parse_mode=ParseMode.HTML)
    except:
        update.message.reply_text("Invalid ID.")

def removeadmin_command(update: Update, context: CallbackContext):
    if not update.effective_user.id in ADMIN_IDS:
        update.message.reply_text("❌ Only owners.")
        return
    if not context.args:
        update.message.reply_text("Usage: /removeadmin <user_id>")
        return
    try:
        uid = int(context.args[0])
        if uid in ADMIN_IDS:
            update.message.reply_text("❌ Cannot remove owner.")
        else:
            remove_admin(uid)
            update.message.reply_text(f"✅ Admin {uid} removed.")
            context.bot.send_message(chat_id=uid, text="⚠️ Your admin privileges have been removed.", parse_mode=ParseMode.HTML)
    except:
        update.message.reply_text("Invalid ID.")

def admins_command(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        update.message.reply_text("❌ Admin only.")
        return
    admins_list = get_all_admins()
    msg = "Admins:\n" + "\n".join(f"<code>{uid}</code>" for uid in admins_list)
    update.message.reply_text(msg, parse_mode=ParseMode.HTML)

# ---------- Premium Reminder Sender ----------
def send_premium_reminders(bot):
    try:
        from config import PREMIUM_REMINDER_START_DAYS, PREMIUM_REMINDER_END_DAYS
        logger.info("🔍 Checking premium reminders...")

        for day_count in range(PREMIUM_REMINDER_START_DAYS, PREMIUM_REMINDER_END_DAYS - 1, -1):
            users_list = get_users_expiring_in_days(day_count)

            for user_data in users_list:
                user_id = user_data["_id"]
                premium_until = user_data.get("premium_until")
                reminders_sent = user_data.get("reminders_sent", [])

                if day_count in reminders_sent:
                    continue

                if premium_until:
                    try:
                        expiry_date = datetime.fromisoformat(premium_until)
                        
                        if day_count == 1:
                            text = (
                                f"⚠️ <b>Your Premium Expires TOMORROW!</b>\n\n"
                                f"📅 Expiry date: {expiry_date.strftime('%Y-%m-%d %H:%M')}\n\n"
                                f"Renew now to avoid losing premium benefits!\n"
                                f"Contact @{SUPPORT_USERNAME} for renewal."
                            )
                        else:
                            text = (
                                f"⚠️ <b>Premium Expiry Reminder</b>\n\n"
                                f"Your premium will expire in <b>{day_count} days</b>.\n"
                                f"📅 Expiry date: {expiry_date.strftime('%Y-%m-%d %H:%M')}\n\n"
                                f"Renew now to continue enjoying premium features!\n"
                                f"Contact @{SUPPORT_USERNAME} for renewal."
                            )

                        try:
                            bot.send_message(chat_id=user_id, text=text, parse_mode=ParseMode.HTML)
                            mark_reminder_sent(user_id, day_count)
                            logger.info(f"✅ Premium reminder sent to {user_id} ({day_count} days left)")
                        except Exception as e:
                            logger.error(f"❌ Failed to send reminder to {user_id}: {e}")

                    except Exception as e:
                        logger.error(f"❌ Error parsing premium_until for {user_id}: {e}")

        logger.info("✅ Premium reminders check completed.")
    except Exception as e:
        logger.error(f"❌ Error in send_premium_reminders: {e}")
