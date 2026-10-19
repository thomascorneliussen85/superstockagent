import sys
from datetime import date

import config
from scanner import StockScanner
from setup_detector import SetupDetector
from catalyst_agent import CatalystAgent
from notifier import send_notifications

def build_report(focus_list: list[dict], failed_tickers: list[str]) -> list[str]:
    lines = []
    if not focus_list:
        lines.append("No stocks passed all filters today. Exercise patience!")

    for item in focus_list:
        lines.append(f"🔥 {item['ticker']} | Price: ${item['close']} | ATR: {item['atr_pct']}% | Daily Vol: ${item['dollar_vol_M']}M")
        base_label = "tight" if item['is_tight_base'] else "loose"
        lines.append(f"📐 Base Range: {item['base_range_pct']}% ({base_label}, max {config.MAX_BASE_RANGE_PCT}%)")
        lines.append(f"📌 Technical Setups: {', '.join(item['setups'])}")
        ai = item['ai']
        if "score_1_to_10" in ai:
            lines.append(f"💡 Theme/Sector: {ai.get('theme_or_sector')}")
            lines.append(f"⚡ Catalyst (Score {ai.get('score_1_to_10')}/10): {ai.get('catalyst_type')} - {ai.get('catalyst_summary')}")
        elif "error" in ai:
            lines.append(f"⚠️ AI Error: {ai['error']}")
        else:
            lines.append(f"💡 AI Note: {ai.get('catalyst_summary', 'Manual review needed')}")
        lines.append("-" * 40)

    if failed_tickers:
        lines.append(f"⚠️ No market data for: {', '.join(failed_tickers)}")
    return lines

def run_super_stock_agent() -> int:
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

    if len(scanner.failed_tickers) == len(config.DEFAULT_TICKERS):
        print("❌ Could not fetch market data for any ticker. No report sent.")
        return 1

    report = "\n".join(build_report(focus_list, scanner.failed_tickers))
    print(report)

    subject = f"📋 Super Stock Focus List {date.today():%d.%m.%Y} ({len(focus_list)} stocks)"
    failed_channels = send_notifications(subject, report)
    return 1 if failed_channels else 0

if __name__ == "__main__":
    sys.exit(run_super_stock_agent())
