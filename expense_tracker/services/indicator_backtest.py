"""Popular TradingView-style indicators and a long-only buy/sell backtest."""

from __future__ import annotations

from datetime import date
from typing import Any, Callable

SignalFn = Callable[[list[dict[str, Any]]], list[str | None]]

_SMA = "MASimple@tv-basicstudies"
_EMA = "MAExp@tv-basicstudies"


def _sma(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    window = sum(values[:period])
    out[period - 1] = window / period
    for i in range(period, len(values)):
        window += values[i] - values[i - period]
        out[i] = window / period
    return out


def _ema(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    k = 2 / (period + 1)
    for i in range(period, len(values)):
        prev = out[i - 1]
        if prev is None:
            continue
        out[i] = values[i] * k + prev * (1 - k)
    return out


def _cross_up(fast: list[float | None], slow: list[float | None], i: int) -> bool:
    if i < 1:
        return False
    a0, b0, a1, b1 = fast[i - 1], slow[i - 1], fast[i], slow[i]
    return (
        a0 is not None
        and b0 is not None
        and a1 is not None
        and b1 is not None
        and a0 <= b0
        and a1 > b1
    )


def _cross_down(fast: list[float | None], slow: list[float | None], i: int) -> bool:
    if i < 1:
        return False
    a0, b0, a1, b1 = fast[i - 1], slow[i - 1], fast[i], slow[i]
    return (
        a0 is not None
        and b0 is not None
        and a1 is not None
        and b1 is not None
        and a0 >= b0
        and a1 < b1
    )


def _level_cross_up(series: list[float | None], level: float, i: int) -> bool:
    if i < 1:
        return False
    prev, cur = series[i - 1], series[i]
    return prev is not None and cur is not None and prev <= level < cur


def _level_cross_down(series: list[float | None], level: float, i: int) -> bool:
    if i < 1:
        return False
    prev, cur = series[i - 1], series[i]
    return prev is not None and cur is not None and prev >= level > cur


def _closes(candles: list[dict[str, Any]]) -> list[float]:
    return [float(c["close"]) for c in candles]


def _rsi(values: list[float], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return out
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        delta = values[i] - values[i - 1]
        if delta >= 0:
            gains += delta
        else:
            losses -= delta
    avg_gain = gains / period
    avg_loss = losses / period
    out[period] = 100.0 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))
    for i in range(period + 1, len(values)):
        delta = values[i] - values[i - 1]
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        out[i] = 100.0 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))
    return out


def _atr(candles: list[dict[str, Any]], period: int = 10) -> list[float | None]:
    out: list[float | None] = [None] * len(candles)
    if len(candles) <= period:
        return out
    trs: list[float] = [0.0]
    for i in range(1, len(candles)):
        high = float(candles[i]["high"])
        low = float(candles[i]["low"])
        prev = float(candles[i - 1]["close"])
        trs.append(max(high - low, abs(high - prev), abs(low - prev)))
    wilder = sum(trs[1 : period + 1]) / period
    out[period] = wilder
    for i in range(period + 1, len(candles)):
        wilder = (wilder * (period - 1) + trs[i]) / period
        out[i] = wilder
    return out


def _signals_sma_cross(
    candles: list[dict[str, Any]], fast: int, slow: int
) -> list[str | None]:
    closes = _closes(candles)
    a = _sma(closes, fast)
    b = _sma(closes, slow)
    out: list[str | None] = [None] * len(candles)
    for i in range(len(candles)):
        if _cross_up(a, b, i):
            out[i] = "buy"
        elif _cross_down(a, b, i):
            out[i] = "sell"
    return out


def _signals_ema_cross(
    candles: list[dict[str, Any]], fast: int, slow: int
) -> list[str | None]:
    closes = _closes(candles)
    a = _ema(closes, fast)
    b = _ema(closes, slow)
    out: list[str | None] = [None] * len(candles)
    for i in range(len(candles)):
        if _cross_up(a, b, i):
            out[i] = "buy"
        elif _cross_down(a, b, i):
            out[i] = "sell"
    return out


def _signals_macd(candles: list[dict[str, Any]]) -> list[str | None]:
    closes = _closes(candles)
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd: list[float | None] = [None] * len(closes)
    macd_vals: list[float] = []
    macd_idx: list[int] = []
    for i, (a, b) in enumerate(zip(ema12, ema26)):
        if a is None or b is None:
            continue
        value = a - b
        macd[i] = value
        macd_vals.append(value)
        macd_idx.append(i)
    signal_on_vals = _ema(macd_vals, 9)
    signal: list[float | None] = [None] * len(closes)
    for pos, idx in enumerate(macd_idx):
        signal[idx] = signal_on_vals[pos]
    out: list[str | None] = [None] * len(candles)
    for i in range(len(candles)):
        if _cross_up(macd, signal, i):
            out[i] = "buy"
        elif _cross_down(macd, signal, i):
            out[i] = "sell"
    return out


def _signals_rsi(candles: list[dict[str, Any]]) -> list[str | None]:
    rsi = _rsi(_closes(candles), 14)
    out: list[str | None] = [None] * len(candles)
    for i in range(len(candles)):
        if _level_cross_up(rsi, 30, i):
            out[i] = "buy"
        elif _level_cross_down(rsi, 70, i):
            out[i] = "sell"
    return out


def _signals_bollinger(candles: list[dict[str, Any]]) -> list[str | None]:
    closes = _closes(candles)
    mid = _sma(closes, 20)
    out: list[str | None] = [None] * len(candles)
    for i in range(len(candles)):
        if mid[i] is None or i < 20:
            continue
        window = closes[i - 19 : i + 1]
        mean = mid[i]
        var = sum((x - mean) ** 2 for x in window) / 20
        std = var**0.5
        lower = mean - 2 * std
        upper = mean + 2 * std
        prev = closes[i - 1]
        cur = closes[i]
        if prev < lower <= cur:
            out[i] = "buy"
        elif prev > upper >= cur:
            out[i] = "sell"
    return out


def _signals_stochastic(candles: list[dict[str, Any]]) -> list[str | None]:
    k_raw: list[float | None] = [None] * len(candles)
    for i in range(13, len(candles)):
        window = candles[i - 13 : i + 1]
        highest = max(float(c["high"]) for c in window)
        lowest = min(float(c["low"]) for c in window)
        denom = highest - lowest
        close = float(candles[i]["close"])
        k_raw[i] = 50.0 if denom == 0 else (close - lowest) / denom * 100
    k_vals = [0.0 if v is None else v for v in k_raw]
    k_sma = _sma(k_vals, 3)
    k: list[float | None] = [None if k_raw[i] is None else k_sma[i] for i in range(len(candles))]
    out: list[str | None] = [None] * len(candles)
    for i in range(len(candles)):
        if _level_cross_up(k, 20, i):
            out[i] = "buy"
        elif _level_cross_down(k, 80, i):
            out[i] = "sell"
    return out


def _signals_supertrend(candles: list[dict[str, Any]]) -> list[str | None]:
    atr = _atr(candles, 10)
    out: list[str | None] = [None] * len(candles)
    trend = 1
    final_upper = 0.0
    final_lower = 0.0
    for i in range(len(candles)):
        if atr[i] is None:
            continue
        high = float(candles[i]["high"])
        low = float(candles[i]["low"])
        close = float(candles[i]["close"])
        mid = (high + low) / 2
        basic_upper = mid + 3 * atr[i]
        basic_lower = mid - 3 * atr[i]
        if i == 0 or atr[i - 1] is None:
            final_upper = basic_upper
            final_lower = basic_lower
            continue
        prev_close = float(candles[i - 1]["close"])
        final_upper = (
            basic_upper
            if basic_upper < final_upper or prev_close > final_upper
            else final_upper
        )
        final_lower = (
            basic_lower
            if basic_lower > final_lower or prev_close < final_lower
            else final_lower
        )
        prev_trend = trend
        if close > final_upper:
            trend = 1
        elif close < final_lower:
            trend = -1
        if prev_trend <= 0 < trend:
            out[i] = "buy"
        elif prev_trend >= 0 > trend:
            out[i] = "sell"
    return out


INDICATORS: list[dict[str, Any]] = [
    {
        "id": "rsi_14",
        "tv_studies": [{"id": "RSI@tv-basicstudies", "inputs": {"length": 14}}],
        "name": {"en": "RSI (14)", "he": "RSI (14)"},
        "explanation": {
            "en": "Relative Strength Index. Buys when RSI climbs back above 30 (oversold bounce). Sells when it drops back below 70 (overbought fade). Very common on TradingView.",
            "he": "מדד כוח יחסי. קונה כשה־RSI חוזר מעל 30 (תיקון ממכירת יתר) ומוכר כשהוא יורד מתחת ל־70 (שיא קנייה). מהאינדיקטורים הנפוצים ב־TradingView.",
        },
        "signals": _signals_rsi,
    },
    {
        "id": "macd",
        "tv_studies": [{"id": "MACD@tv-basicstudies"}],
        "name": {"en": "MACD", "he": "MACD"},
        "explanation": {
            "en": "Moving Average Convergence Divergence. Buys when the MACD line crosses above its signal line, sells when it crosses below. A standard trend-and-momentum study.",
            "he": "התכנסות והתבדרות ממוצעים נעים. קונה כשקו ה־MACD חוצה מעל קו האות, ומוכר כשהוא חוצה מתחתיו. אינדיקטור מגמה ותאוצה סטנדרטי.",
        },
        "signals": _signals_macd,
    },
    {
        "id": "sma_50_200",
        "tv_studies": [
            {"id": _SMA, "inputs": {"length": 50}},
            {"id": _SMA, "inputs": {"length": 200}},
        ],
        "name": {"en": "Golden / Death Cross (SMA 50 / 200)", "he": "צלב זהב / מוות (SMA 50 / 200)"},
        "explanation": {
            "en": "Buys when the 50-day average crosses above the 200-day average (golden cross). Sells on the opposite cross (death cross). A slow, widely watched trend signal.",
            "he": "קונה כשממוצע 50 הימים חוצה מעל ממוצע 200 הימים (צלב זהב), ומוכר בהצלבה ההפוכה (צלב מוות). אות מגמה איטי ונפוץ.",
        },
        "signals": lambda c: _signals_sma_cross(c, 50, 200),
    },
    {
        "id": "ema_12_26",
        "tv_studies": [
            {"id": _EMA, "inputs": {"length": 12}},
            {"id": _EMA, "inputs": {"length": 26}},
        ],
        "name": {"en": "EMA crossover (12 / 26)", "he": "הצלבת EMA (12 / 26)"},
        "explanation": {
            "en": "Buys when the 12-day exponential average crosses above the 26-day average, and sells when it crosses below. Faster than the 50/200 SMA cross.",
            "he": "קונה כשממוצע מעריכי של 12 ימים חוצה מעל זה של 26 ימים, ומוכר בהצלבה ההפוכה. מהיר יותר מהצלבת SMA 50/200.",
        },
        "signals": lambda c: _signals_ema_cross(c, 12, 26),
    },
    {
        "id": "bollinger_20",
        "tv_studies": [{"id": "BB@tv-basicstudies", "inputs": {"in_0": 20, "in_1": 2}}],
        "name": {"en": "Bollinger Bands (20, 2)", "he": "רצועות בולינגר (20, 2)"},
        "explanation": {
            "en": "Buys when price bounces back up through the lower band, sells when it falls back through the upper band. Meant to fade stretches away from the 20-day average.",
            "he": "קונה כשהמחיר חוזר מעל הרצועה התחתונה, ומוכר כשהוא חוזר מתחת לרצועה העליונה. מיועד לתפוס תיקונים ממתיחות סביב ממוצע 20 הימים.",
        },
        "signals": _signals_bollinger,
    },
    {
        "id": "supertrend",
        "tv_studies": [{"id": "Supertrend@tv-basicstudies"}],
        "name": {"en": "Supertrend", "he": "Supertrend"},
        "explanation": {
            "en": "A trend-following overlay. Buys when Supertrend flips bullish and sells when it flips bearish. Popular on TradingView for catching sustained moves.",
            "he": "שכבת מגמה על הגרף. קונה כשה־Supertrend הופך שורי ומוכר כשהוא הופך דובי. נפוץ ב־TradingView לתפיסת מהלכים מתמשכים.",
        },
        "signals": _signals_supertrend,
    },
    {
        "id": "stochastic",
        "tv_studies": [{"id": "Stochastic@tv-basicstudies"}],
        "name": {"en": "Stochastic Oscillator", "he": "אוסצילטור סטוכסטי"},
        "explanation": {
            "en": "Buys when %K climbs back above 20, sells when it drops back below 80. Similar idea to RSI: buy oversold bounces, sell overbought drops.",
            "he": "קונה כש־%K חוזר מעל 20, ומוכר כשהוא יורד מתחת ל־80. רעיון דומה ל־RSI: קנייה בתיקון ממכירת יתר ומכירה בירידה מקניית יתר.",
        },
        "signals": _signals_stochastic,
    },
    {
        "id": "sma_20_50",
        "tv_studies": [
            {"id": _SMA, "inputs": {"length": 20}},
            {"id": _SMA, "inputs": {"length": 50}},
        ],
        "name": {"en": "SMA crossover (20 / 50)", "he": "הצלבת SMA (20 / 50)"},
        "explanation": {
            "en": "A shorter moving-average cross: buy when SMA 20 crosses above SMA 50, sell when it crosses below. More signals than the 50/200 cross, and more noise.",
            "he": "הצלבת ממוצעים קצרה יותר: קנייה כש־SMA 20 חוצה מעל SMA 50, ומכירה בהצלבה ההפוכה. יותר אותות מ־50/200, וגם יותר רעש.",
        },
        "signals": lambda c: _signals_sma_cross(c, 20, 50),
    },
]


def get_indicator(indicator_id: str) -> dict[str, Any] | None:
    wanted = (indicator_id or "").strip()
    for item in INDICATORS:
        if item["id"] == wanted:
            return item
    return None


def catalog_for_lang(lang: str) -> list[dict[str, Any]]:
    loc = "he" if lang == "he" else "en"
    rows = []
    for item in INDICATORS:
        rows.append(
            {
                "id": item["id"],
                "name": item["name"].get(loc) or item["name"]["en"],
                "explanation": item["explanation"].get(loc) or item["explanation"]["en"],
                "tv_studies": item["tv_studies"],
            }
        )
    return rows


def run_backtest(
    candles: list[dict[str, Any]],
    indicator_id: str,
    start: date,
    capital: float,
) -> dict[str, Any]:
    """Long-only all-in/all-out backtest from start date using close prices."""
    spec = get_indicator(indicator_id)
    if spec is None:
        raise ValueError("Unknown indicator")
    if capital <= 0:
        raise ValueError("Capital must be positive")
    if not candles:
        raise ValueError("No price history")

    signals = spec["signals"](candles)
    cash = float(capital)
    shares = 0.0
    trades: list[dict[str, Any]] = []
    last_close = float(candles[-1]["close"])

    for i, bar in enumerate(candles):
        day = bar["date"]
        if isinstance(day, str):
            day = date.fromisoformat(day)
        if day < start:
            continue
        close = float(bar["close"])
        last_close = close
        signal = signals[i]
        if signal == "buy" and cash > 0:
            shares = cash / close
            value = cash
            cash = 0.0
            trades.append(
                {
                    "side": "buy",
                    "date": day.isoformat(),
                    "price": round(close, 4),
                    "shares": round(shares, 6),
                    "value": round(value, 2),
                }
            )
        elif signal == "sell" and shares > 0:
            cash = shares * close
            trades.append(
                {
                    "side": "sell",
                    "date": day.isoformat(),
                    "price": round(close, 4),
                    "shares": round(shares, 6),
                    "value": round(cash, 2),
                }
            )
            shares = 0.0

    open_value = shares * last_close
    equity = cash + open_value
    pnl = equity - capital
    return {
        "indicator_id": indicator_id,
        "starting_capital": round(capital, 2),
        "ending_equity": round(equity, 2),
        "pnl": round(pnl, 2),
        "pnl_pct": round((pnl / capital) * 100, 2) if capital else 0.0,
        "open_position": shares > 0,
        "open_shares": round(shares, 6) if shares else 0.0,
        "last_close": round(last_close, 4),
        "trades": trades,
        "buy_count": sum(1 for t in trades if t["side"] == "buy"),
        "sell_count": sum(1 for t in trades if t["side"] == "sell"),
        "tv_studies": spec["tv_studies"],
    }
