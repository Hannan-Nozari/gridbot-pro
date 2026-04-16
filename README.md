# GridBot Pro

A full-stack crypto grid trading platform with a luxury web dashboard.
Runs multiple strategies (Grid, Hybrid, Smart, V3) on Binance with paper
trading and live trading support.

## Features

- **4 Bot Types** — Grid, Hybrid (Grid + RSI + trailing stop), Smart
  (volatility-adaptive), V3 (10-layer full stack)
- **5 Backtestable Strategies** — Grid, DCA, Mean Reversion, Momentum,
  Combined
- **Web Dashboard** — Real-time portfolio value, active bots, recent
  trades, equity curves, strategy mix donut
- **Backtester UI** — Run backtests from the browser, visualise equity
  curves, Sharpe / Sortino / drawdown metrics
- **Multi-strategy Management** — Create, start, stop, delete bots from
  the UI
- **Alerts** — Email + Telegram notifications for trades, drawdowns,
  profit targets
- **Live Trading** — Binance integration via CCXT with both paper and
  live modes

## Architecture

```
crypto-grid-bot/
├── backend/              FastAPI + SQLite + the bot engine
│   ├── main.py           FastAPI app + WebSocket
│   ├── database.py       SQLite schema
│   ├── auth.py           Bearer-token auth
│   ├── routers/          REST endpoints
│   ├── services/         Bot manager, backtest, analytics, alerts
│   └── bots/             The 4 bot implementations + strategies.py
├── frontend/             Next.js 14 + Tailwind + shadcn/ui
│   └── src/app/          Dashboard, Bots, Backtester, Analytics,
│                         Trades, Alerts, Config
├── docker-compose.yml    Backend + Frontend + Caddy
├── Dockerfile.backend
├── Dockerfile.frontend
└── Caddyfile             Reverse proxy + HTTPS
```

## Local Development

### Prerequisites
- Python 3.11+
- Node.js 20+
- (Optional) Docker if you want to run the full stack locally

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run the API
AUTH_PASSWORD=admin uvicorn main:app --reload
# -> http://localhost:8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# -> http://localhost:3000
```

Log in with the password you set in `AUTH_PASSWORD`.

## Backtesting (CLI)

The original CLI tooling is still usable for fast parameter exploration:

```bash
# Optimize grid bounds and spacing on 90d of data
python optimize.py

# Full strategy comparison across pairs, 30 and 90 days
python all_strategies_backtest.py all

# Deep analysis with Sharpe, Sortino, drawdown, and parameter tuning
python deep_analysis.py 90
```

## Production Deploy

The repo ships with a Docker Compose stack ready to run behind Caddy
with automatic HTTPS.

### One-line deploy on a fresh Ubuntu server

```bash
# 1. Install Docker
curl -fsSL https://get.docker.com | sh

# 2. Clone and enter
git clone https://github.com/YOUR_USER/gridbot-pro.git /opt/gridbot
cd /opt/gridbot

# 3. Configure
cp .env.example .env
# edit .env: set AUTH_PASSWORD + BINANCE_API_KEY + BINANCE_API_SECRET

# 4. Launch
docker compose up -d
```

Caddy will obtain certificates automatically once DNS is pointed at the
server.  If you are behind Cloudflare, the included `Caddyfile` uses
`tls internal`, which is compatible with Cloudflare's **Full** SSL mode.

### Environment variables (`.env`)

| Variable | Purpose |
|----------|---------|
| `AUTH_PASSWORD` | Dashboard login password |
| `BINANCE_API_KEY` | Binance API key (leave blank for paper trading) |
| `BINANCE_API_SECRET` | Binance API secret |
| `DATABASE_PATH` | Default: `/app/data/trading.db` |
| `CORS_ORIGINS` | Comma-separated list of allowed origins |
| `ALERT_EMAIL_*` | SMTP settings for email alerts |
| `ALERT_TELEGRAM_*` | Telegram bot token + chat ID |

## Security

- **Never commit `.env`** — it is in `.gitignore` for a reason
- **Never enable withdrawals** on your Binance API key — the bot only
  needs Spot & Margin Trading
- **Restrict the API key to your server's IP** in the Binance settings
- Start with **paper trading** before going live
- **Change `AUTH_PASSWORD`** after the first login

## License

MIT
