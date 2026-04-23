"""
strategies/donchian_breakout.py
────────────────────────────────
Donchian Channel Breakout Strategy
────────────────────────────────────
Used when the 1H ADX signals a TRENDING market.

Entry Logic (15-minute timeframe):
  LONG  — The latest *closed* candle closes ABOVE the upper Donchian band
          AND the candle before it was at or below the upper band
          (i.e. a clean upward breakout).
          Confirmation: 4H bias must be BULL or NEUTRAL (never fade the macro).

  SHORT — The latest *closed* candle closes BELOW the lower Donchian band
          AND the candle before it was at or above the lower band.
          Confirmation: 4H bias must be BEAR or NEUTRAL.

Risk Management:
  Stop Loss  → wide: entry ± (DONCHIAN_SL_ATR_MULT × ATR)
  Take Profit→ ATR trailing stop managed by PositionManager
               (no fixed TP; the trail does all the work)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

import pandas as pd

from config.settings import DONCHIAN_SL_ATR_MULT, DONCHIAN_TRAIL_ATR_MULT
from indicators import apply_all_indicators
from utils.logger import get_logger

log = get_logger(__name__)

Bias = Literal["BULL", "BEAR", "NEUTRAL"]
Side = Literal["long", "short"]


@dataclass
class DonchianSignal:
    """Returned by ``DonchianStrategy.check_signal``."""
    has_signal:   bool
    side:         Optional[Side]  = None
    entry_price:  float           = 0.0
    sl_price:     float           = 0.0
    trail_start:  float           = 0.0     # initial trailing-stop level
    trail_mult:   float           = DONCHIAN_TRAIL_ATR_MULT
    atr:          float           = 0.0
    dc_upper:     float           = 0.0
    dc_lower:     float           = 0.0
    adx:          float           = 0.0
    notes:        str             = ""


class DonchianStrategy:
    """
    Evaluates the Donchian breakout signal on the 15-minute DataFrame.

    Parameters
    ----------
    macro_bias : str
        The trend direction determined from the 4H analysis.
        One of ``BULL``, ``BEAR``, or ``NEUTRAL``.
    """

    def __init__(self, macro_bias: Bias = "NEUTRAL") -> None:
        self.macro_bias = macro_bias

    # ── Main entry-point ─────────────────────────────────────────────────────
    def check_signal(
        self,
        df_15m: pd.DataFrame,
    ) -> DonchianSignal:
        """
        Check the most recent fully-closed 15m candle for a breakout signal.

        Parameters
        ----------
        df_15m : pd.DataFrame
            Raw OHLCV for the 15-minute timeframe with ≥ 60 rows.

        Returns
        -------
        DonchianSignal
        """
        df = apply_all_indicators(df_15m.copy())
        df.dropna(inplace=True)

        if len(df) < 3:
            log.debug("DonchianStrategy: not enough data (%d rows)", len(df))
            return DonchianSignal(has_signal=False, notes="Insufficient data")

        # Use the second-to-last row as the confirmed closed candle
        # (last row may still be forming)
        cur  = df.iloc[-2]   # latest closed candle
        prev = df.iloc[-3]   # the candle before it

        entry_price = cur["close"]
        atr         = cur["atr"]
        dc_upper    = cur["dc_upper"]
        dc_lower    = cur["dc_lower"]
        adx         = cur["adx"]

        # ── LONG breakout ────────────────────────────────────────────────
        if (
            cur["close"]  > dc_upper
            and prev["close"] <= prev["dc_upper"]
            and self.macro_bias in ("BULL", "NEUTRAL")
        ):
            sl_price    = entry_price - DONCHIAN_SL_ATR_MULT * atr
            trail_start = entry_price - DONCHIAN_TRAIL_ATR_MULT * atr

            log.info(
                "DONCHIAN LONG signal | entry=%.4f  SL=%.4f  (ATR=%.4f  ADX=%.1f)",
                entry_price, sl_price, atr, adx,
            )
            return DonchianSignal(
                has_signal=True,
                side="long",
                entry_price=entry_price,
                sl_price=sl_price,
                trail_start=trail_start,
                trail_mult=DONCHIAN_TRAIL_ATR_MULT,
                atr=atr,
                dc_upper=dc_upper,
                dc_lower=dc_lower,
                adx=adx,
                notes=f"Upward breakout above DC upper={dc_upper:.4f}",
            )

        # ── SHORT breakout ───────────────────────────────────────────────
        if (
            cur["close"]  < dc_lower
            and prev["close"] >= prev["dc_lower"]
            and self.macro_bias in ("BEAR", "NEUTRAL")
        ):
            sl_price    = entry_price + DONCHIAN_SL_ATR_MULT * atr
            trail_start = entry_price + DONCHIAN_TRAIL_ATR_MULT * atr

            log.info(
                "DONCHIAN SHORT signal | entry=%.4f  SL=%.4f  (ATR=%.4f  ADX=%.1f)",
                entry_price, sl_price, atr, adx,
            )
            return DonchianSignal(
                has_signal=True,
                side="short",
                entry_price=entry_price,
                sl_price=sl_price,
                trail_start=trail_start,
                trail_mult=DONCHIAN_TRAIL_ATR_MULT,
                atr=atr,
                dc_upper=dc_upper,
                dc_lower=dc_lower,
                adx=adx,
                notes=f"Downward breakout below DC lower={dc_lower:.4f}",
            )

        gap_to_upper = dc_upper - entry_price
        gap_to_lower = entry_price - dc_lower
        log.info(
            "Donchian: no signal | close=%.4f  need >%.4f (+%.4f) or <%.4f (-%.4f)  bias=%s  ADX=%.1f",
            entry_price, dc_upper, gap_to_upper, dc_lower, gap_to_lower, self.macro_bias, adx,
        )
        return DonchianSignal(has_signal=False, notes="No breakout")
