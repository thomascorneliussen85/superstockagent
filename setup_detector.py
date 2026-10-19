class SetupDetector:
    @staticmethod
    def detect_setups(data: dict) -> list[str]:
        df = data['df']
        close = data['close']
        base_high = data['base_high']
        setups = []

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        # 1. Base Breakout (only from a tight base, see MAX_BASE_RANGE_PCT)
        dist_to_base_high = ((base_high - close) / close) * 100
        if data['is_tight_base'] and -2.0 <= dist_to_base_high <= 3.0:
            setups.append("BASE BREAKOUT (Near or breaking out of multi-month high)")

        # 2. High-Tight Flag (HTF)
        gain_1m = ((close - df['Close'].iloc[-22]) / df['Close'].iloc[-22]) * 100
        depth_10d = ((df['High'].tail(10).max() - df['Low'].tail(10).min()) / df['High'].tail(10).max()) * 100
        if gain_1m >= 50.0 and depth_10d <= 20.0:
            setups.append("HIGH-TIGHT FLAG (Explosive 50%+ gain with shallow pullback < 20%)")

        # 3. Pullback to 50 SMA
        sma50 = data['sma50']
        if abs(close - sma50) / sma50 <= 0.03:
            setups.append("50-SMA PULLBACK (Testing key institutional 50-day average)")

        # 4. Undercut & Rally (UNR)
        lowest_10d = df['Low'].tail(15).iloc[:-2].min()
        if prev['Low'] < lowest_10d and latest['Close'] > lowest_10d:
            setups.append("UNDERCUT & RALLY (Swept previous support level and reclaimed)")

        # 5. Episodic Pivot / Earnings Gap
        gap_pct = ((latest['Open'] - prev['Close']) / prev['Close']) * 100
        vol_ratio = latest['Volume'] / df['Volume'].tail(20).mean()
        if gap_pct >= 5.0 and vol_ratio >= 2.0:
            setups.append(f"EPISODIC PIVOT (Gap-up +{gap_pct:.1f}% with {vol_ratio:.1f}x volume)")

        return setups if setups else ["General Momentum Setup"]
