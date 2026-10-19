import config
from scanner import StockScanner
from setup_detector import SetupDetector
from catalyst_agent import CatalystAgent

def run_super_stock_agent():
    print("=" * 60)
    print("🚀 RUNNING SUPER STOCK DISCOVERY AGENT (Connor Bates Model)")
    print("=" * 60)

    scanner = StockScanner(
        min_dollar_vol=config.MIN_DAILY_DOLLAR_VOLUME,
        min_atr_pct=config.MIN_ATR_PERCENT,
        base_days=config.LOOKBACK_BASE_DAYS,
        max_base_range=config.MAX_BASE_RANGE_PCT
    )

    catalyst_agent = CatalystAgent(api_key=config.OPENAI_API_KEY)
    focus_list = []

    print(f"\n[1/3] Scanning {len(config.DEFAULT_TICKERS)} tickers against quantitative filters...")

    for ticker in config.DEFAULT_TICKERS:
        data = scanner.scan_ticker(ticker)
        if not data:
            continue

        print(f" -> Approved on Dollar Volume & ATR: {ticker}")

        # Detect Setups
        setups = SetupDetector.detect_setups(data)

        # AI Catalyst Analysis
        print(f"    Fetching news & evaluating catalysts for {ticker}...")
        news = catalyst_agent.fetch_recent_news(ticker)
        ai_analysis = catalyst_agent.analyze_catalyst_and_theme(ticker, news, setups)

        focus_list.append({
            "ticker": ticker,
            "close": data["close"],
            "dollar_vol_M": data["avg_dollar_vol_M"],
            "atr_pct": data["atr_pct"],
            "base_range_pct": data["base_range_pct"],
            "is_tight_base": data["is_tight_base"],
            "setups": setups,
            "ai": ai_analysis
        })

    # Output Reporting
    print("\n" + "=" * 60)
    print("📋 FINAL SUPER STOCK FOCUS LIST")
    print("=" * 60 + "\n")

    if not focus_list:
        print("No stocks passed all filters today. Exercise patience!")
        return

    for item in focus_list:
        print(f"🔥 **{item['ticker']}** | Price: ${item['close']} | ATR: {item['atr_pct']}% | Daily Vol: ${item['dollar_vol_M']}M")
        base_label = "tight" if item['is_tight_base'] else "loose"
        print(f"📐 **Base Range:** {item['base_range_pct']}% ({base_label}, max {config.MAX_BASE_RANGE_PCT}%)")
        print(f"📌 **Technical Setups:** {', '.join(item['setups'])}")
        ai = item['ai']
        if "score_1_to_10" in ai:
            print(f"💡 **Theme/Sector:** {ai.get('theme_or_sector')}")
            print(f"⚡ **Catalyst (Score {ai.get('score_1_to_10')}/10):** {ai.get('catalyst_type')} - {ai.get('catalyst_summary')}")
        elif "error" in ai:
            print(f"⚠️ **AI Error:** {ai['error']}")
        else:
            print(f"💡 **AI Note:** {ai.get('catalyst_summary', 'Manual review needed')}")
        print("-" * 60)

if __name__ == "__main__":
    run_super_stock_agent()
