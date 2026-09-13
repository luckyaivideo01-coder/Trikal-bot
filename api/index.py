import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request
from telegram import Update, Bot
from telegram.ext import Dispatcher, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, JobQueue
from bot import *
from config import BOT_TOKEN
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

app = Flask(__name__)

if not BOT_TOKEN:
    raise Exception("BOT_TOKEN missing")

bot = Bot(token=BOT_TOKEN)

# Create dispatcher with job_queue
dispatcher = Dispatcher(bot, None, workers=4)

# 🔥 JobQueue for auto-delete - MUST be started before adding handlers
job_queue = JobQueue()
job_queue.set_dispatcher(dispatcher)
dispatcher.job_queue = job_queue
job_queue.start()

# ---------- Premium Reminder Scheduler ----------
def schedule_daily_reminders():
    """Schedule 2 daily premium reminders at 12:00 AM IST and 9:00 AM IST."""
    now = datetime.now()
    
    # Reminder 1: 12:00 AM IST = 6:30 PM UTC (previous day)
    target_1 = now.replace(hour=18, minute=30, second=0, microsecond=0)
    if now >= target_1:
        target_1 = target_1 + timedelta(days=1)
    
    # Reminder 2: 9:00 AM IST = 3:30 AM UTC
    target_2 = now.replace(hour=3, minute=30, second=0, microsecond=0)
    if now >= target_2:
        target_2 = target_2 + timedelta(days=1)
    
    seconds_1 = (target_1 - now).total_seconds()
    seconds_2 = (target_2 - now).total_seconds()
    
    # Schedule first reminder (12:00 AM IST)
    job_queue.run_once(
        run_daily_reminder,
        seconds_1,
        context={'bot': bot, 'reminder_type': 'midnight'}
    )
    logger.info(f"⏰ 1st Reminder (12:00 AM IST) scheduled for: {target_1} UTC ({seconds_1} seconds from now)")
    
    # Schedule second reminder (9:00 AM IST)
    job_queue.run_once(
        run_daily_reminder,
        seconds_2,
        context={'bot': bot, 'reminder_type': 'morning'}
    )
    logger.info(f"⏰ 2nd Reminder (9:00 AM IST) scheduled for: {target_2} UTC ({seconds_2} seconds from now)")

def run_daily_reminder(context):
    """Run the premium reminder and reschedule for next day."""
    try:
        reminder_type = context.job.context.get('reminder_type', 'morning')
        logger.info(f"🔍 Running premium reminder ({reminder_type})...")
        send_premium_reminders(context.bot)
        logger.info(f"✅ Premium reminder ({reminder_type}) completed.")
    except Exception as e:
        logger.error(f"❌ Error in daily reminder: {e}")
    finally:
        # Reschedule this specific reminder for tomorrow at the same time
        now = datetime.now()
        reminder_type = context.job.context.get('reminder_type', 'morning')
        
        if reminder_type == 'midnight':
            next_time = now.replace(hour=18, minute=30, second=0, microsecond=0)
        else:
            next_time = now.replace(hour=3, minute=30, second=0, microsecond=0)
        
        if now >= next_time:
            next_time = next_time + timedelta(days=1)
        
        seconds_until = (next_time - now).total_seconds()
        
        context.job_queue.run_once(
            run_daily_reminder,
            seconds_until,
            context={'bot': context.bot, 'reminder_type': reminder_type}
        )
        logger.info(f"🔄 Next {reminder_type} reminder scheduled for: {next_time} UTC")

# Schedule the reminders
schedule_daily_reminders()

# Register all handlers
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("help", help_command))
dispatcher.add_handler(CommandHandler("phone", phone_command))
dispatcher.add_handler(CommandHandler("redeem", redeem_command))
dispatcher.add_handler(CommandHandler("admin", admin_command))
dispatcher.add_handler(CommandHandler("addadmin", addadmin_command))
dispatcher.add_handler(CommandHandler("removeadmin", removeadmin_command))
dispatcher.add_handler(CommandHandler("admins", admins_command))
dispatcher.add_handler(CommandHandler("gencode", gencode))
dispatcher.add_handler(CommandHandler("history", history_command))
dispatcher.add_handler(CommandHandler("protect", protect_command))
dispatcher.add_handler(CommandHandler("unprotect", unprotect_command))
dispatcher.add_handler(CommandHandler("protected", protected_command))
dispatcher.add_handler(CallbackQueryHandler(button_handler))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

@app.route("/", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        return "Bot is running! Webhook is active.", 200
    try:
        json_data = request.get_json(force=True)
        if not json_data:
            return "No JSON received", 400
        update = Update.de_json(json_data, bot)
        dispatcher.process_update(update)
        return "OK", 200
    except Exception as e:
        print(f"Webhook error: {e}")
        return "ERROR", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
