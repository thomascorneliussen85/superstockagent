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
