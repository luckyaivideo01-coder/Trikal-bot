import os
from dotenv import load_dotenv
load_dotenv()

# ---------- Telegram ----------
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    print("⚠️ WARNING: BOT_TOKEN not set. Bot will not work.")

ADMIN_IDS = [int(id) for id in os.getenv("ADMIN_IDS", "").split(",") if id]
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "InfoHelpLineBot")
REFERRAL_NOTIFICATION_GROUP = os.getenv("REFERRAL_NOTIFICATION_GROUP", "https://t.me/+tIwH7ctrekc1YThl")
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "-1003472844347"))

# ---------- Unlimited Group ----------
OFFICIAL_GROUP_ID = int(os.getenv("OFFICIAL_GROUP_ID", "-1003490016636"))
OFFICIAL_GROUP_LINK = os.getenv("OFFICIAL_GROUP_LINK", "https://t.me/+OdNjwHMDXZtiNzA1")

# ---------- Mandatory Channels ----------
CHANNEL_1_INVITE_LINK = os.getenv("CHANNEL_1_INVITE_LINK", "https://t.me/SecretBotsTelegram")
REQUIRED_CHANNEL_1_ID = int(os.getenv("REQUIRED_CHANNEL_1_ID", "-1003411597042"))
CHANNEL_2_INVITE_LINK = os.getenv("CHANNEL_2_INVITE_LINK", "https://t.me/+EnHwtMwircJkNzk1")
REQUIRED_CHANNEL_2_ID = int(os.getenv("REQUIRED_CHANNEL_2_ID", "-1003227457437"))

# ---------- Phone API ----------
PHONE_API_NEW = os.getenv("PHONE_API_NEW", "https://numinfo-1m.hcjffjggjf.workers.dev/?number={num}")

# ---------- MongoDB ----------
MONGO_URI = os.getenv("MONGO_URI", "your_mongodb_uri_here")
DB_NAME = os.getenv("DB_NAME", "mybotdb")

# ---------- Credits & Referrals ----------
INITIAL_CREDITS = 3
REFERRAL_CREDITS = 5
NEW_USER_REFERRAL_CREDITS = 2
SEARCH_COST = 1
REDEEM_COOLDOWN_SECONDS = 3600
REFERRAL_PREMIUM_DAYS = 1
REFERRAL_TIER_1_COUNT = 15
REFERRAL_TIER_2_COUNT = 70
DEFAULT_DAILY_LIMIT = 3
DEFAULT_AUTO_DELETE_TIME = 60

if not ADMIN_IDS:
    ADMIN_IDS = [8262107211]

# ---------- Premium Reminder Settings ----------
PREMIUM_REMINDER_START_DAYS = 2
PREMIUM_REMINDER_END_DAYS = 1

# ---------- Owner User IDs (hide activity from all admins) ----------
# Add your user ID(s) here to keep your activity completely hidden.
# Example: OWNER_USER_IDS = [8262107211, 123456789]
OWNER_USER_IDS = [8262107211]   # <-- YOUR ID (bot owner)
