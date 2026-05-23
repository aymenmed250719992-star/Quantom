"""
Comprehensive trading knowledge base — injected into every Gemini analysis prompt.
Upgraded with Agent-specific reasoning patterns and self-improvement rules.
"""

TRADING_KNOWLEDGE = """
════════════════════════════════════════
  COMPREHENSIVE TRADING KNOWLEDGE BASE
  Islamic Halal Trading Agent v3.0
════════════════════════════════════════

━━━ TECHNICAL INDICATORS ━━━

RSI (Relative Strength Index):
• RSI < 25: STRONGLY oversold — high-probability buy zone
• RSI < 30: Oversold — potential buy signal
• RSI 30-50: Bearish momentum recovering
• RSI 50: Trend neutral pivot
• RSI 50-70: Bullish momentum
• RSI > 70: Overbought — consider taking profit
• RSI > 75: STRONGLY overbought — high-probability reversal zone
• RSI BULLISH DIVERGENCE (price lower low, RSI higher low) = strongest buy signal
• RSI BEARISH DIVERGENCE (price higher high, RSI lower high) = strongest sell signal
• RSI Hidden Bullish Divergence: price higher low, RSI lower low = trend continuation BUY

MACD (Moving Average Convergence/Divergence):
• MACD line crosses ABOVE signal line = bullish momentum (BUY signal)
• MACD line crosses BELOW signal line = bearish momentum (SELL signal)
• MACD histogram EXPANDING positively = strong uptrend acceleration
• MACD histogram SHRINKING = momentum losing steam, prepare for reversal
• MACD ZERO LINE crossover above = trend officially turns bullish
• MACD divergence from price = pending reversal warning

Bollinger Bands (BB):
• Price at LOWER band + RSI < 35 = strong buy (mean reversion)
• Price at UPPER band + RSI > 65 = strong sell (mean reversion)
• BB SQUEEZE (bands extremely narrow) = explosive breakout imminent
• BB%B < 0.05 = deeply oversold, near lower band
• BB%B > 0.95 = deeply overbought, near upper band
• Price riding UPPER band with rising volume = strong uptrend (do NOT fight it)

━━━ CHART PATTERNS ━━━

High-Probability REVERSAL Patterns:
• Double Bottom (W): Strong bullish reversal — buy breakout above neckline
• Double Top (M): Strong bearish reversal — sell breakdown below neckline
• Head and Shoulders: Bearish reversal — sell breakdown below neckline
• Inverse Head and Shoulders: Bullish reversal — buy breakout above neckline
• Rounding Bottom: Slow institutional accumulation — long-term BUY

High-Probability CONTINUATION Patterns:
• Bull Flag: Brief pullback after strong up move — BUY the breakout
• Bear Flag: Brief bounce after strong down move — SELL the breakdown
• Ascending Triangle: Higher lows + horizontal resistance — bullish breakout expected
• Cup and Handle: Bullish continuation — buy breakout above cup rim

━━━ CANDLESTICK SIGNALS ━━━

Strong BULLISH Candlesticks:
• Hammer: Small body, long lower wick at support = reversal likely
• Bullish Engulfing: Large green candle engulfs previous red = strong reversal
• Dragonfly Doji at support: Buyers took full control
• Morning Star (3-candle): Red → Doji/small → Green = strong reversal
• Three White Soldiers: Three consecutive strong green candles = trend confirmed

Strong BEARISH Candlesticks:
• Shooting Star: Small body, long upper wick at resistance = reversal likely
• Bearish Engulfing: Large red candle engulfs previous green = strong reversal
• Evening Star (3-candle): Green → Doji/small → Red = strong reversal
• Three Black Crows: Three consecutive strong red candles = trend confirmed

━━━ VOLUME ANALYSIS ━━━

• HIGH volume + price RISE = strong uptrend (trust the move)
• HIGH volume + price FALL = strong downtrend (trust the move)
• LOW volume + price RISE = weak rally (suspect, could reverse)
• Volume SPIKE on breakout = confirms the breakout
• Declining volume on trend = trend losing conviction

━━━ TRADING STRATEGIES ━━━

Strategy 1 — MEAN REVERSION (best in ranging markets):
• RSI < 30 + price near BB lower band → BUY with SL below lower band
• RSI > 70 + price near BB upper band → SELL with SL above upper band
• Best when RSI divergence confirms the signal
• Set TP at BB midline (first) and BB upper/lower (second)

Strategy 2 — TREND FOLLOWING (best in trending markets):
• Identify trend using price structure and MACD
• Buy pullbacks to EMA/Bollinger midline in uptrends
• Confirm with MACD histogram positive/negative
• Optimal: RSI 40-60 during pullback = best entry

Strategy 3 — MOMENTUM BREAKOUT (best for explosive moves):
• Wait for BB Squeeze (very narrow bands)
• Look for volume expansion (volume > 1.5x average)
• Enter in direction of breakout with tight stop
• TP = width of pre-squeeze range added to breakout point

Strategy 4 — DIVERGENCE TRADING (highest accuracy):
• Find RSI or MACD divergence from price
• Confirm with candlestick reversal pattern
• Enter after confirmation candle closes
• This is the highest-accuracy strategy

━━━ RISK MANAGEMENT RULES (NON-NEGOTIABLE) ━━━

1. NEVER risk more than 1.5% of total capital per trade
2. Minimum Risk:Reward ratio = 1:2 (risk $1 to make $2)
3. Preferred Risk:Reward = 1:3 or better
4. Stop Loss placement:
   - Below recent swing low (for BUY trades)
   - Above recent swing high (for SELL trades)
   - Never more than 3% below entry
5. Take Profit targets:
   - First target: Previous resistance/support
   - Second target: BB upper/lower band
6. Position Sizing formula: Qty = (Balance × Risk%) / (Entry × SL%)
7. Maximum 3 open positions at one time
8. Reduce size in high-volatility conditions
9. NEVER average down on losing trades
10. Cut losses quickly, let profits run

━━━ AGENT SELF-IMPROVEMENT RULES ━━━

The agent reviews itself after every 5 trades:
• What indicator combinations had highest accuracy?
• Which market conditions produced best results?
• Were stops too tight or too loose?
• Is the risk:reward being maintained?
• Should the strategy mode change?

Confidence Threshold Adjustment:
• Win rate BELOW target → Increase threshold by 3% (be MORE selective)
• Win rate ABOVE target by 10%+ → Decrease threshold by 2% (get MORE trades)
• Always keep threshold between 60% minimum and 90% maximum

Agent Memory Rules:
• Every lesson from a closed trade is stored permanently
• Patterns with >65% win rate get confidence BONUS
• Patterns with <40% win rate get confidence PENALTY
• Agent can switch strategies: mean_reversion / trend_following / momentum_breakout / divergence

━━━ ISLAMIC FINANCE COMPLIANCE ━━━

Permitted (حلال):
✓ Spot trading with actual asset ownership
✓ Technical analysis-based decisions
✓ Risk management and capital preservation
✓ Diversification across multiple assets

Forbidden (حرام — HARD BLOCKED):
✗ Futures and derivatives (excessive uncertainty/gharar)
✗ Margin/leveraged trading (riba element)
✗ Short selling borrowed assets
✗ Purely speculative gambling without analysis

Islamic Trading Principle:
"والله لا يحب الفساد" — Preserve capital as religious duty.
Every trade must have sound analytical basis. Never trade on pure speculation.
Risk management is not optional — it is a moral obligation.

━━━ CRYPTOCURRENCY KNOWLEDGE ━━━

BTC/USDT: Market leader — other cryptos follow its direction
ETH/USDT: Second most liquid — follows BTC with amplified moves
SOL/USDT: High volatility — needs wider stops
XRP/USDT: Highly news-sensitive — avoid during major announcements
BNB/USDT: Exchange token — correlates with overall crypto sentiment

General Rules:
• Avoid holding positions during major US/Asian market opens
• Monday opens often see direction established for the week
• Friday afternoons see position squaring
• High correlation during BTC crashes — diversification limited in crisis
════════════════════════════════════════
"""


SYSTEM_PROMPT = """You are an expert Islamic-compliant cryptocurrency trading AI AGENT with deep knowledge of technical analysis, market psychology, and risk management.

Your core identity:
- You are an AUTONOMOUS AGENT, not just a bot — you PLAN, ACT, OBSERVE, and LEARN
- You have a persistent memory of every trade outcome and lesson
- You continuously improve your strategy based on what works
- You strictly follow Islamic finance principles (spot only, no leverage, no gambling)
- You think in terms of probability, risk-reward, and long-term capital preservation

Your decision framework:
1. EVIDENCE: What do the indicators say? (RSI, MACD, BB, volume)
2. CONTEXT: What market regime are we in? (trending, ranging, volatile)
3. MEMORY: What have past trades taught us about this setup?
4. RISK: Does the risk:reward justify entry? (minimum 1:2)
5. CONFIDENCE: Only act when confidence ≥ threshold

Always reference the knowledge base when making decisions.
Always preserve capital — a bad trade skipped is better than a loss taken."""
