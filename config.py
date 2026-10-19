import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

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
