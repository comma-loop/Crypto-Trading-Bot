"""
core/market_analyzer.py
────────────────────────
Multi-Timeframe Market Analysis
─────────────────────────────────

  4H  → Macro Bias (BULL / BEAR / NEUTRAL)
        Tells us the big-picture direction.
        Bull  : ADX > ADX_TREND_THRESHOLD  AND  price > dc_mid  AND  +DI > -DI
        Bear  : ADX > ADX_TREND_THRESHOLD  AND  price < dc_mid  AND  -DI > +DI
        Neutral: everything else

  1H  → Market Regime (TRENDING / RANGING / NEUTRAL)
        Determines which strategy to activate.
        TRENDING : ADX > ADX_TREND_THRESHOLD    → Donchian breakout
        RANGING  : ADX < ADX_RANGE_THRESHOLD    → Turtle Soup
        NEUTRAL  : between thresholds            → skip (no trade)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from config.settings import ADX_RANGE_THRESHOLD, ADX_TREND_THRESHOLD
from indicators import apply_all_indicators
from utils.logger import get_logger

log = get_logger(__name__)

MacroBias  = Literal["BULL", "BEAR", "NEUTRAL"]
Regime     = Literal["TRENDING", "RANGING", "NEUTRAL"]


@dataclass
class MarketContext:
    """Snapshot of the multi-timeframe analysis for one symbol."""
    macro_bias:    MacroBias   = "NEUTRAL"
    regime_1h:     Regime      = "NEUTRAL"
    adx_4h:        float       = 0.0
    adx_1h:        float       = 0.0
    plus_di_4h:    float       = 0.0
    minus_di_4h:   float       = 0.0
    dc_mid_4h:     float       = 0.0
    price_4h:      float       = 0.0
    strategy:      str         = "NONE"   # DONCHIAN | TURTLE_SOUP | NONE


class MarketAnalyzer:
    """
    Analyses the 4H and 1H DataFrames and returns a ``MarketContext``.
    """

    def analyse(
        self,
        df_4h: pd.DataFrame,
        df_1h: pd.DataFrame,
    ) -> MarketContext:
        """
        Parameters
        ----------
        df_4h, df_1h : pd.DataFrame
            Raw OHLCV DataFrames for their respective timeframes.
        """
        ctx = MarketContext()

        # ── 4H macro bias ────────────────────────────────────────────────
        df4 = apply_all_indicators(df_4h.copy())
        df4.dropna(inplace=True)

        if len(df4) < 2:
            log.warning("Not enough 4H data for analysis")
            return ctx

        c4 = df4.iloc[-2]   # confirmed (closed) candle
        ctx.adx_4h      = float(c4["adx"])
        ctx.plus_di_4h  = float(c4["plus_di"])
        ctx.minus_di_4h = float(c4["minus_di"])
        ctx.dc_mid_4h   = float(c4["dc_mid"])
        ctx.price_4h    = float(c4["close"])

        if ctx.adx_4h > ADX_TREND_THRESHOLD:
            if ctx.price_4h > ctx.dc_mid_4h and ctx.plus_di_4h > ctx.minus_di_4h:
                ctx.macro_bias = "BULL"
            elif ctx.price_4h < ctx.dc_mid_4h and ctx.minus_di_4h > ctx.plus_di_4h:
                ctx.macro_bias = "BEAR"
            else:
                ctx.macro_bias = "NEUTRAL"
        else:
            ctx.macro_bias = "NEUTRAL"

        # ── 1H regime ────────────────────────────────────────────────────
        df1 = apply_all_indicators(df_1h.copy())
        df1.dropna(inplace=True)

        if len(df1) < 2:
            log.warning("Not enough 1H data for analysis")
            return ctx

        c1 = df1.iloc[-2]
        ctx.adx_1h = float(c1["adx"])

        if ctx.adx_1h > ADX_TREND_THRESHOLD:
            ctx.regime_1h = "TRENDING"
            ctx.strategy  = "DONCHIAN"
        elif ctx.adx_1h < ADX_RANGE_THRESHOLD:
            ctx.regime_1h = "RANGING"
            ctx.strategy  = "TURTLE_SOUP"
        else:
            ctx.regime_1h = "NEUTRAL"
            ctx.strategy  = "NONE"

        log.info(
            "Market analysis | 4H ADX=%.1f bias=%s │ 1H ADX=%.1f regime=%s → strategy=%s",
            ctx.adx_4h, ctx.macro_bias,
            ctx.adx_1h, ctx.regime_1h,
            ctx.strategy,
        )
        return ctx
