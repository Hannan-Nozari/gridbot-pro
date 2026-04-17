# Setting up Telegram Alerts

## Step 1 — Create a Telegram bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Give it a name (e.g. `My GridBot Alerts`)
4. Give it a username ending in `bot` (e.g. `my_gridbot_alerts_bot`)
5. Copy the **bot token** — looks like `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`

## Step 2 — Get your chat ID

1. Search for **@userinfobot** on Telegram
2. Send it `/start`
3. It replies with your chat ID (a number like `123456789`)

Or alternatively:
1. Send any message to your new bot (the one you created)
2. Visit `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
3. Look for `"chat":{"id":123456789`

## Step 3 — Add credentials to the server

SSH into the server and edit `.env`:

```bash
ssh root@144.172.65.228
nano /opt/gridbot/.env
```

Set these two variables:

```
ALERT_TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
ALERT_TELEGRAM_CHAT_ID=123456789
```

Save (`Ctrl+X`, `Y`, `Enter`) and restart:

```bash
cd /opt/gridbot
docker compose up -d --force-recreate backend
```

## Step 4 — Test it

You should immediately receive a "🟢 GridBot Pro started" message in Telegram.

You'll also get alerts for:
- 🔄 Trade executed
- ⚠️ Drawdown exceeded
- 🎯 Profit target reached
- 🚨 Kill switch activated
- ❌ Bot crashes
