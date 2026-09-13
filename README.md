# Phone Info Bot – Railway + MongoDB

## Features
- Indian phone number lookup (any API format)
- Credit system (3 initial, 5 per referral)
- Daily free searches (default 3)
- Premium tiers (1 day at 15 referrals, unlimited at 70)
- Admin panel with full control
- Number protection (hide specific numbers)
- Mandatory channel join
- Unlimited free searches in official group
- Auto‑delete messages (configurable)
- Maintenance mode
- **No search data stored** – only user credits/premium/referrals saved in MongoDB

## Deployment on Railway

1. **Fork/Clone this repository** to GitHub.
2. **Create a MongoDB database** (Atlas free tier) and get the connection string.
3. **Create a Telegram bot** via @BotFather, copy token.
4. **On Railway**:
   - New Project → Deploy from GitHub → select your repo.
   - Add environment variables (copy `.env.example` content and replace placeholders):
     - `BOT_TOKEN`
     - `ADMIN_IDS` (comma‑separated)
     - `MONGO_URI`
     - `DB_NAME`
   - Railway will automatically detect `api/index.py` and run it as a web app.
5. **Set Telegram webhook**:
   After deployment, Railway gives you a URL (e.g., `https://your-app.up.railway.app`). Run:
