"""
risk/risk_manager.py
─────────────────────
Handles all risk-related calculations:

  1. Position sizing  — how many contracts/coins to buy given:
       • account balance
       • risk percentage per trade
       • distance from entry to SL (in price terms)

  2. Trailing stop updates  — for the Donchian strategy, the trailing
     stop ratchets up/down as price moves favourably.

  3. Exit checks  — returns a reason string when SL, TP, or trail stop
     is breached.
"""

from __future__ import annotations

from typing import Literal, Optional

from config.settings import (
    DONCHIAN_TRAIL_ATR_MULT,
    LEVERAGE,
    RISK_PER_TRADE,
)
from utils.logger import get_logger

log = get_logger(__name__)

Side = Literal["long", "short"]


class RiskManager:
    """
    Stateless helper; every method is a pure calculation.
    """

    # ── Position sizing ───────────────────────────────────────────────────────
    @staticmethod
    def calculate_position_size(
        balance_usdt:   float,
        entry_price:    float,
        sl_price:       float,
        risk_fraction:  float = RISK_PER_TRADE,
        leverage:       int   = LEVERAGE,
        min_qty:        float = 0.001,
    ) -> float:
        """
        Calculate the position size (in base-asset units) such that, if SL
        is hit, the loss equals ``risk_fraction × balance``.

        Formula
        -------
            risk_usdt  = balance × risk_fraction
            sl_distance = |entry - sl| / entry   (as a fraction of price)
            position_value = risk_usdt / sl_distance
            qty = position_value / entry_price

        Leverage inflates buying power but does NOT change the risk in USDT —
        the SL distance already captures the dollar risk.
        """
        risk_usdt    = balance_usdt * risk_fraction
        sl_distance  = abs(entry_price - sl_price)

        if sl_distance == 0:
            log.warning("SL distance is zero; cannot size position")
            return min_qty

        qty = risk_usdt / sl_distance
        qty = max(qty, min_qty)

        log.debug(
            "Position size | balance=%.2f  risk=%.2f  sl_dist=%.4f  qty=%.6f",
            balance_usdt, risk_usdt, sl_distance, qty,
        )
        return qty

    # ── Trailing stop ─────────────────────────────────────────────────────────
    @staticmethod
    def update_trailing_stop(
        side:         Side,
        current_price: float,
        current_trail: float,
        atr:           float,
        trail_mult:    float = DONCHIAN_TRAIL_ATR_MULT,
    ) -> float:
        """
        Ratchet the trailing stop in the favourable direction.

        For LONG:
            new_trail = max(current_trail, current_price − trail_mult × ATR)
            (trail only moves UP; never back down)

        For SHORT:
            new_trail = min(current_trail, current_price + trail_mult × ATR)
            (trail only moves DOWN; never back up)

        Returns the (possibly updated) trailing stop level.
        """
        trail_distance = trail_mult * atr
        if side == "long":
            candidate = current_price - trail_distance
            new_trail  = max(current_trail, candidate)
        else:
            candidate = current_price + trail_distance
            new_trail  = min(current_trail, candidate)

        if new_trail != current_trail:
            log.debug(
                "Trail updated [%s] %.4f → %.4f  (price=%.4f  dist=%.4f)",
                side, current_trail, new_trail, current_price, trail_distance,
            )
        return new_trail

    # ── Exit checks ───────────────────────────────────────────────────────────
    @staticmethod
    def check_exit(
        side:         Side,
        current_price: float,
        sl_price:      float,
        tp_price:      Optional[float],
        trail_stop:    Optional[float],
    ) -> Optional[str]:
        """
        Return the exit reason if any exit condition is met, else ``None``.

        Exit reasons: ``"SL_HIT"`` | ``"TP_HIT"`` | ``"TRAIL_STOP"``
        """
        if side == "long":
            if current_price <= sl_price:
                return "SL_HIT"
            if tp_price is not None and current_price >= tp_price:
                return "TP_HIT"
            if trail_stop is not None and current_price <= trail_stop:
                return "TRAIL_STOP"
        else:  # short
            if current_price >= sl_price:
                return "SL_HIT"
            if tp_price is not None and current_price <= tp_price:
                return "TP_HIT"
            if trail_stop is not None and current_price >= trail_stop:
                return "TRAIL_STOP"
        return None

    # ── P&L helpers ───────────────────────────────────────────────────────────
    @staticmethod
    def calculate_pnl(
        side:        Side,
        entry_price: float,
        exit_price:  float,
        qty:         float,
    ) -> tuple[float, float]:
        """
        Return (pnl_usdt, pnl_pct).

        pnl_pct is relative to notional value (entry_price × qty).
        """
        if side == "long":
            pnl_usdt = (exit_price - entry_price) * qty
        else:
            pnl_usdt = (entry_price - exit_price) * qty

        notional = entry_price * qty
        pnl_pct  = (pnl_usdt / notional * 100) if notional else 0.0
        return round(pnl_usdt, 4), round(pnl_pct, 4)
