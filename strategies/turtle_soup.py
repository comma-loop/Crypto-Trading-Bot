"""
strategies/turtle_soup.py
──────────────────────────
Turtle Soup Strategy (Larry Connor & Linda Bradford Raschke)
─────────────────────────────────────────────────────────────
Used when the 1H ADX signals a RANGING market (ADX < ADX_RANGE_THRESHOLD).

Core Idea
─────────
"Turtle Soup" fades a false Donchian breakout.  Classic Turtles BUY when price
breaks the 20-period high and SELL when it breaks the 20-period low.
Turtle Soup does the opposite: it fades those breakouts when they quickly
reverse back inside the channel.

False-Breakout Detection (15-minute frame):
  SELL (short) setup — false upward breakout:
    1. Within the last TURTLE_SOUP_LOOKBACK_CANDLES candles, at least one HIGH
       traded ABOVE the upper Donchian band.
    2. The latest confirmed candle CLOSES BACK INSIDE (close < dc_upper).
    3. 4H bias is BEAR or NEUTRAL (don't fade a screaming bull market).

  BUY (long) setup  — false downward breakout:
    1. Within the last TURTLE_SOUP_LOOKBACK_CANDLES candles, at least one LOW
       traded BELOW the lower Donchian band.
    2. The latest confirmed candle CLOSES BACK INSIDE (close > dc_lower).
    3. 4H bias is BULL or NEUTRAL.

Precise Entry Timing (5-minute frame):
  After the 15m setup is identified, we look at the 5m chart for a
  reversal confirmation candle:
    • For SELL: a bearish 5m candle (close < open) that closes below the
      breakout wick.
    • For BUY:  a bullish 5m candle (close > open) that closes above the
      low of the false breakdown wick.
  Entry is at the close of that 5m confirmation candle.

Risk Management (fixed per spec):
  BUY  position:  SL = entry − 1.5 × ATR     TP = entry + 1.0 × ATR
  SELL position:  SL = entry + 1.5 × ATR     TP = entry − 1.0 × ATR
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

import pandas as pd

from config.settings import (
    TURTLE_SL_ATR_MULT,
    TURTLE_TP_ATR_MULT,
    TURTLE_SOUP_LOOKBACK_CANDLES,
)
from indicators import apply_all_indicators
from utils.logger import get_logger

log = get_logger(__name__)

Bias = Literal["BULL", "BEAR", "NEUTRAL"]
Side = Literal["long", "short"]


@dataclass
class TurtleSoupSignal:
    """Returned by ``TurtleSoupStrategy.check_signal``."""
    has_signal:  bool
    side:        Optional[Side] = None
    entry_price: float          = 0.0
    sl_price:    float          = 0.0
    tp_price:    float          = 0.0
    atr:         float          = 0.0
    dc_upper:    float          = 0.0
    dc_lower:    float          = 0.0
    adx:         float          = 0.0
    notes:       str            = ""


class TurtleSoupStrategy:
    """
    Evaluates the Turtle Soup false-breakout signal.

    Parameters
    ----------
    macro_bias : str
        Trend direction from the 4H analysis (``BULL``, ``BEAR``, ``NEUTRAL``).
    """

    def __init__(self, macro_bias: Bias = "NEUTRAL") -> None:
        self.macro_bias = macro_bias

    # ── Main entry-point ─────────────────────────────────────────────────────
    def check_signal(
        self,
        df_15m: pd.DataFrame,
        df_5m:  Optional[pd.DataFrame] = None,
    ) -> TurtleSoupSignal:
        """
        Check for a Turtle Soup false-breakout signal.

        Parameters
        ----------
        df_15m : pd.DataFrame
            15-minute OHLCV with at least 60 rows.
        df_5m : pd.DataFrame | None
            5-minute OHLCV.  When provided, used for precise entry timing.
            When ``None`` the bot uses the 15m close price as the entry.
        """
        df15 = apply_all_indicators(df_15m.copy())
        df15.dropna(inplace=True)

        if len(df15) < TURTLE_SOUP_LOOKBACK_CANDLES + 3:
            return TurtleSoupSignal(has_signal=False, notes="Insufficient 15m data")

        # Confirmed candle = second-to-last (last may still be forming)
        confirmed = df15.iloc[-2]
        lookback_window = df15.iloc[-(TURTLE_SOUP_LOOKBACK_CANDLES + 2): -1]

        dc_upper = confirmed["dc_upper"]
        dc_lower = confirmed["dc_lower"]
        close    = confirmed["close"]
        atr      = confirmed["atr"]
        adx      = confirmed["adx"]

        # ── FALSE UPWARD BREAKOUT → SHORT (Sell) ─────────────────────────
        false_up_breakout = (
            lookback_window["high"].max() > dc_upper   # wick poked above
            and close < dc_upper                        # closed back inside
            and self.macro_bias in ("BEAR", "NEUTRAL")
        )

        # ── FALSE DOWNWARD BREAKOUT → LONG (Buy) ─────────────────────────
        false_down_breakout = (
            lookback_window["low"].min() < dc_lower    # wick poked below
            and close > dc_lower                        # closed back inside
            and self.macro_bias in ("BULL", "NEUTRAL")
        )

        if not false_up_breakout and not false_down_breakout:
            log.debug(
                "No Turtle Soup setup | close=%.4f  dc=[%.4f, %.4f]",
                close, dc_lower, dc_upper,
            )
            return TurtleSoupSignal(has_signal=False, notes="No false breakout")

        side: Side = "short" if false_up_breakout else "long"

        # ── Precise entry: use 5m confirmation candle if available ────────
        entry_price = self._get_precise_entry(df_5m, side, atr) or close

        # ── SL / TP (fixed per spec) ──────────────────────────────────────
        if side == "long":
            sl_price = entry_price - TURTLE_SL_ATR_MULT * atr
            tp_price = entry_price + TURTLE_TP_ATR_MULT * atr
        else:
            sl_price = entry_price + TURTLE_SL_ATR_MULT * atr
            tp_price = entry_price - TURTLE_TP_ATR_MULT * atr

        notes = (
            f"False {'upward' if side == 'short' else 'downward'} breakout | "
            f"dc_{'upper' if side == 'short' else 'lower'}="
            f"{dc_upper if side == 'short' else dc_lower:.4f}"
        )
        log.info(
            "TURTLE SOUP %s signal | entry=%.4f  SL=%.4f  TP=%.4f  (ATR=%.4f  ADX=%.1f)",
            side.upper(), entry_price, sl_price, tp_price, atr, adx,
        )

        return TurtleSoupSignal(
            has_signal=True,
            side=side,
            entry_price=entry_price,
            sl_price=sl_price,
            tp_price=tp_price,
            atr=atr,
            dc_upper=dc_upper,
            dc_lower=dc_lower,
            adx=adx,
            notes=notes,
        )

    # ── Precise 5m entry ─────────────────────────────────────────────────────
    def _get_precise_entry(
        self,
        df_5m: Optional[pd.DataFrame],
        side: Side,
        atr_15m: float,
    ) -> Optional[float]:
        """
        Look at the last few 5m candles for a confirmation candle.
        Returns the close price of the confirmation candle, or None.
        """
        if df_5m is None or len(df_5m) < 5:
            return None

        df5 = df_5m.copy().tail(10)

        # Most recent two complete candles
        for i in range(-2, -6, -1):
            try:
                c = df5.iloc[i]
            except IndexError:
                break

            if side == "long":
                # Bullish reversal candle: close > open
                if c["close"] > c["open"]:
                    log.debug("5m LONG confirmation candle @ %.4f", c["close"])
                    return float(c["close"])
            else:
                # Bearish reversal candle: close < open
                if c["close"] < c["open"]:
                    log.debug("5m SHORT confirmation candle @ %.4f", c["close"])
                    return float(c["close"])

        log.debug("No 5m confirmation candle found; falling back to 15m close")
        return None
