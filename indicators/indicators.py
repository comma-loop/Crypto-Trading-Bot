"""
indicators/indicators.py
─────────────────────────
Pure-pandas / numpy implementations of the three indicators used by the bot:

  ATR  — Average True Range (Wilder's smoothing)
  ADX  — Average Directional Index (Wilder's +DI / -DI / ADX)
  Donchian Channel — Period high / low / midline

All functions accept a DataFrame with columns [open, high, low, close, volume]
and return a new DataFrame with the indicator columns appended.
No external TA library dependency — everything is reproducible.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from config.settings import ADX_PERIOD, ATR_PERIOD, DONCHIAN_PERIOD


# ─────────────────────────────────────────────────────────────────────────────
#  ATR
# ─────────────────────────────────────────────────────────────────────────────
def add_atr(df: pd.DataFrame, period: int = ATR_PERIOD, col: str = "atr") -> pd.DataFrame:
    """
    Append an ATR column using Wilder's exponential smoothing (alpha = 1/period).

    True Range = max(
        High - Low,
        |High - PrevClose|,
        |Low  - PrevClose|
    )
    """
    high  = df["high"]
    low   = df["low"]
    prev  = df["close"].shift(1)

    tr = pd.concat(
        [high - low, (high - prev).abs(), (low - prev).abs()], axis=1
    ).max(axis=1)

    df = df.copy()
    df[col] = tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    return df


# ─────────────────────────────────────────────────────────────────────────────
#  ADX  (+DI / -DI included)
# ─────────────────────────────────────────────────────────────────────────────
def add_adx(
    df: pd.DataFrame,
    period: int = ADX_PERIOD,
    col_adx: str  = "adx",
    col_plus: str = "plus_di",
    col_minus: str = "minus_di",
) -> pd.DataFrame:
    """
    Append ADX, +DI, and -DI columns.

    Algorithm: Wilder's method (same as the original 1978 paper).
    """
    df = df.copy()

    high       = df["high"]
    low        = df["low"]
    prev_high  = high.shift(1)
    prev_low   = low.shift(1)
    prev_close = df["close"].shift(1)

    # ── Directional Movement ─────────────────────────────────────────────
    up_move   = high - prev_high
    down_move = prev_low - low

    plus_dm  = np.where((up_move > down_move)   & (up_move > 0),   up_move,   0.0)
    minus_dm = np.where((down_move > up_move)   & (down_move > 0), down_move, 0.0)

    # ── True Range ───────────────────────────────────────────────────────
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)

    # ── Wilder's smoothing (EWM with alpha = 1/period) ───────────────────
    alpha = 1.0 / period

    atr_s      = tr.ewm(alpha=alpha, adjust=False, min_periods=period).mean()
    plus_dm_s  = pd.Series(plus_dm,  index=df.index).ewm(alpha=alpha, adjust=False, min_periods=period).mean()
    minus_dm_s = pd.Series(minus_dm, index=df.index).ewm(alpha=alpha, adjust=False, min_periods=period).mean()

    plus_di  = 100.0 * plus_dm_s  / atr_s.replace(0, np.nan)
    minus_di = 100.0 * minus_dm_s / atr_s.replace(0, np.nan)

    di_sum  = (plus_di + minus_di).replace(0, np.nan)
    dx      = 100.0 * (plus_di - minus_di).abs() / di_sum
    adx     = dx.ewm(alpha=alpha, adjust=False, min_periods=period).mean()

    df[col_adx]   = adx
    df[col_plus]  = plus_di
    df[col_minus] = minus_di
    return df


# ─────────────────────────────────────────────────────────────────────────────
#  Donchian Channel
# ─────────────────────────────────────────────────────────────────────────────
def add_donchian(
    df: pd.DataFrame,
    period: int = DONCHIAN_PERIOD,
    col_upper:  str = "dc_upper",
    col_lower:  str = "dc_lower",
    col_middle: str = "dc_mid",
) -> pd.DataFrame:
    """
    Append Donchian Channel columns.

    Upper  = rolling(period) high
    Lower  = rolling(period) low
    Middle = (Upper + Lower) / 2
    """
    df = df.copy()
    df[col_upper]  = df["high"].rolling(period).max()
    df[col_lower]  = df["low"].rolling(period).min()
    df[col_middle] = (df[col_upper] + df[col_lower]) / 2.0
    return df


# ─────────────────────────────────────────────────────────────────────────────
#  Convenience: apply all indicators at once
# ─────────────────────────────────────────────────────────────────────────────
def apply_all_indicators(
    df: pd.DataFrame,
    atr_period: int      = ATR_PERIOD,
    adx_period: int      = ADX_PERIOD,
    donchian_period: int = DONCHIAN_PERIOD,
) -> pd.DataFrame:
    """Apply ATR, ADX, and Donchian Channel to a OHLCV DataFrame."""
    df = add_atr(df, period=atr_period)
    df = add_adx(df, period=adx_period)
    df = add_donchian(df, period=donchian_period)
    return df
