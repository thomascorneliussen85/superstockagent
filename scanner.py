import yfinance as yf
import pandas as pd
import numpy as np

class StockScanner:
    def __init__(self, min_dollar_vol: float, min_atr_pct: float, base_days: int, max_base_range: float):
        self.min_dollar_vol = min_dollar_vol
        self.min_atr_pct = min_atr_pct
        self.base_days = base_days
        self.max_base_range = max_base_range
        self.failed_tickers = []

    def scan_ticker(self, ticker: str) -> dict | None:
        """Fetch market data and evaluate Super Stock quantitative metrics."""
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period="1y")

            if df.empty:
                self.failed_tickers.append(ticker)
                return None
            if len(df) < 120:
                return None

            # Calculate Technical Indicators
            df['SMA5'] = df['Close'].rolling(window=5).mean()
            df['SMA10'] = df['Close'].rolling(window=10).mean()
            df['EMA21'] = df['Close'].ewm(span=21, adjust=False).mean()
            df['SMA50'] = df['Close'].rolling(window=50).mean()
            df['SMA200'] = df['Close'].rolling(window=200).mean()

            # ATR Calculation
            high_low = df['High'] - df['Low']
            high_close = np.abs(df['High'] - df['Close'].shift())
            low_close = np.abs(df['Low'] - df['Close'].shift())
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            df['ATR14'] = tr.rolling(window=14).mean()
            df['ATR_Pct'] = (df['ATR14'] / df['Close']) * 100

            # Daily Dollar Volume (20-day average)
            df['Dollar_Volume'] = df['Close'] * df['Volume']
            avg_dollar_volume = df['Dollar_Volume'].tail(20).mean()

            current_close = df['Close'].iloc[-1]
            current_atr_pct = df['ATR_Pct'].iloc[-1]

            # 1. Liquidity & Volatility Checks
            if avg_dollar_volume < self.min_dollar_vol or current_atr_pct < self.min_atr_pct:
                return None

            # 2. Base Consolidation Check
            base_df = df.tail(self.base_days)
            base_high = base_df['High'].max()
            base_low = base_df['Low'].min()
            base_range_pct = ((base_high - base_low) / base_low) * 100
            is_tight_base = base_range_pct <= self.max_base_range

            # 3. Macro Trend Check (Must not be in deep downtrend)
            is_above_50sma = current_close >= df['SMA50'].iloc[-1] * 0.95
            is_above_200sma = current_close >= df['SMA200'].iloc[-1] * 0.90

            if not (is_above_50sma and is_above_200sma):
                return None

            return {
                "ticker": ticker,
                "close": round(current_close, 2),
                "avg_dollar_vol_M": round(avg_dollar_volume / 1e6, 1),
                "atr_pct": round(current_atr_pct, 2),
                "base_high": round(base_high, 2),
                "base_low": round(base_low, 2),
                "base_range_pct": round(base_range_pct, 1),
                "is_tight_base": is_tight_base,
                "sma50": round(df['SMA50'].iloc[-1], 2),
                "sma200": round(df['SMA200'].iloc[-1], 2),
                "df": df
            }

        except Exception as e:
            print(f"Error scanning {ticker}: {e}")
            self.failed_tickers.append(ticker)
            return None
