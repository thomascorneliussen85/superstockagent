# Super Stock Discovery Agent

CLI tool that screens high-growth stocks using a growth/position trading model (Connor Bates style):

1. **Scanner** (`scanner.py`) – filters on 20-day average dollar volume, ATR %, base range and trend vs. the 50/200-day SMAs.
2. **Setup detector** (`setup_detector.py`) – flags base breakouts (tight bases only), high-tight flags, 50-SMA pullbacks, undercut & rally, and episodic pivots.
3. **Catalyst agent** (`catalyst_agent.py`) – searches recent news via DuckDuckGo and asks an OpenAI model to score the catalyst and theme.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # add your OPENAI_API_KEY
python main.py
```

Without an API key, the scan still runs and the catalyst step is skipped. Tune thresholds and the ticker universe in `config.py`.

*Not financial advice.*

## Daily morning alert (GitHub Actions)

`.github/workflows/morning-scan.yml` runs the scan Tuesday–Saturday at 05:00 UTC (07:00 Oslo in summer, 06:00 in winter), after each US trading day, and sends the report by Telegram and/or email.

Add these under **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Required | What |
|---|---|---|
| `OPENAI_API_KEY` | recommended | Enables the AI catalyst score |
| `TELEGRAM_BOT_TOKEN` | for Telegram | Create a bot with @BotFather |
| `TELEGRAM_CHAT_ID` | for Telegram | Your id from @userinfobot (send your bot a message first) |
| `SMTP_USER` | for email | e.g. your Gmail address |
| `SMTP_PASSWORD` | for email | Gmail app password (myaccount.google.com/apppasswords) |
| `EMAIL_TO` | for email | Where to send the report |

Test it from **Actions → Morning scan → Run workflow**. A run fails (and GitHub emails you) if no market data could be fetched or a notification could not be sent.
