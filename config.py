import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# --- NOTIFICATIONS (each channel is used only when its settings are present) ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
SMTP_HOST = os.getenv("SMTP_HOST") or "smtp.gmail.com"
SMTP_PORT = int(os.getenv("SMTP_PORT") or 465)
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
EMAIL_TO = os.getenv("EMAIL_TO", "")

# --- CONNOR BATES SUPER STOCK PARAMETERS ---
MIN_DAILY_DOLLAR_VOLUME = 80_000_000   # Min $80M USD Daily Dollar Volume
MIN_ATR_PERCENT = 4.5                  # Min 4.5% - 5.0% Daily ATR %
LOOKBACK_BASE_DAYS = 120              # Base consolidation lookback (~6 months)
MAX_BASE_RANGE_PCT = 35.0              # Max % range inside base

# Universe of high-growth / volatile stocks to scan
DEFAULT_TICKERS = [
    "PLTR", "NVDA", "CEG", "VST", "RKLB", "CRWD", "APP", "SNDK",
    "IONQ", "OKLO", "MP", "PL", "U", "SMCI", "TSLA", "PATH"
]
