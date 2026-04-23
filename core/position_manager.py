"""
core/position_manager.py
─────────────────────────
Manages the lifecycle of every open trade:

  OPEN   → store position metadata, log to CSV, place SL/TP orders
  UPDATE → update trailing stop (Donchian trades only)
  CLOSE  → detect exit triggers, place closing order, log to CSV

Position state is persisted to  data/open_positions.json  so the bot
can survive a restart without orphaning open trades.

Position schema (one entry per trade_id):
{
  "trade_id":     "BTC-USDT_20240101_120000",
  "exchange":     "bybit",
  "symbol":       "BTC/USDT:USDT",
  "strategy":     "DONCHIAN",          # or TURTLE_SOUP
  "side":         "long",
  "entry_price":  42000.0,
  "sl_price":     40500.0,
  "tp_price":     null,                # null for Donchian (trail-only)
  "trail_stop":   41200.0,             # null for Turtle Soup
  "trail_mult":   2.0,
  "qty":          0.05,
  "atr":          500.0,
  "regime_4h":    "BULL",
  "regime_1h":    "TRENDING",
  "adx_1h":       28.5,
  "order_id":     "abc123",
  "opened_at":    "2024-01-01 12:00:00 UTC"
}
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

from config.settings import EXCHANGE_NAME, LEVERAGE
from exchanges.exchange_client import ExchangeClient
from risk.risk_manager import RiskManager
from utils.logger import get_logger
from utils.trade_tracker import log_trade_event, load_positions, save_positions

log = get_logger(__name__)

_risk = RiskManager()


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


class PositionManager:
    """
    Manages the full lifecycle of open positions.

    Parameters
    ----------
    client : ExchangeClient
        Live or demo exchange client.
    """

    def __init__(self, client: ExchangeClient) -> None:
        self.client     = client
        self.positions: dict[str, dict[str, Any]] = load_positions()
        log.info("PositionManager loaded %d open position(s) from disk.", len(self.positions))

    # ── Properties ───────────────────────────────────────────────────────────
    def has_open_position(self, symbol: str) -> bool:
        return any(p["symbol"] == symbol for p in self.positions.values())

    def get_open_position(self, symbol: str) -> Optional[dict[str, Any]]:
        for pos in self.positions.values():
            if pos["symbol"] == symbol:
                return pos
        return None

    # ── Open a new position ──────────────────────────────────────────────────
    def open_position(
        self,
        symbol:      str,
        side:        str,        # 'long' | 'short'
        entry_price: float,
        sl_price:    float,
        tp_price:    Optional[float],
        trail_stop:  Optional[float],
        trail_mult:  float,
        atr:         float,
        strategy:    str,        # 'DONCHIAN' | 'TURTLE_SOUP'
        regime_4h:   str,
        regime_1h:   str,
        adx_1h:      float,
        notes:       str = "",
    ) -> Optional[str]:
        """
        Place a market entry order and register the position.

        Returns the trade_id if successful, else None.
        """
        if self.has_open_position(symbol):
            log.warning("Already have an open position for %s — skipping.", symbol)
            return None

        # ── Fetch balance & size position ─────────────────────────────────
        try:
            balance = self.client.get_usdt_balance()
        except Exception as exc:
            log.error("Could not fetch balance: %s", exc)
            return None

        min_qty = self.client.get_min_order_qty(symbol)
        qty = _risk.calculate_position_size(
            balance_usdt=balance,
            entry_price=entry_price,
            sl_price=sl_price,
            leverage=LEVERAGE,
            min_qty=min_qty,
        )

        # ── Place market order ─────────────────────────────────────────────
        order_side = "buy" if side == "long" else "sell"
        try:
            self.client.set_leverage(symbol, LEVERAGE)
            order = self.client.place_market_order(symbol, order_side, qty)
            order_id = order.get("id", "unknown")
            # Use actual filled price if available
            filled_price = float(order.get("average") or order.get("price") or entry_price)
        except Exception as exc:
            log.error("Order placement failed for %s: %s", symbol, exc)
            return None

        # ── Register position ──────────────────────────────────────────────
        trade_id = f"{symbol.replace('/', '-').replace(':', '-')}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        pos: dict[str, Any] = {
            "trade_id":    trade_id,
            "exchange":    EXCHANGE_NAME,
            "symbol":      symbol,
            "strategy":    strategy,
            "side":        side,
            "entry_price": filled_price,
            "sl_price":    sl_price,
            "tp_price":    tp_price,
            "trail_stop":  trail_stop,
            "trail_mult":  trail_mult,
            "qty":         qty,
            "atr":         atr,
            "regime_4h":   regime_4h,
            "regime_1h":   regime_1h,
            "adx_1h":      adx_1h,
            "order_id":    order_id,
            "opened_at":   _now_utc(),
            "notes":       notes,
        }

        self.positions[trade_id] = pos
        save_positions(self.positions)

        log_trade_event("OPEN", {
            "trade_id":    trade_id,
            "exchange":    EXCHANGE_NAME,
            "symbol":      symbol,
            "strategy":    strategy,
            "side":        side,
            "entry_price": filled_price,
            "sl_price":    sl_price,
            "tp_price":    tp_price or "",
            "trail_stop":  trail_stop or "",
            "qty":         qty,
            "atr_entry":   atr,
            "regime_4h":   regime_4h,
            "regime_1h":   regime_1h,
            "adx_1h":      adx_1h,
            "notes":       notes,
        })

        log.info(
            "✅ OPENED [%s] %s %s  qty=%.6f  entry=%.4f  SL=%.4f  TP=%s  Trail=%s",
            strategy, side.upper(), symbol, qty, filled_price,
            sl_price,
            f"{tp_price:.4f}" if tp_price else "—",
            f"{trail_stop:.4f}" if trail_stop else "—",
        )
        return trade_id

    # ── Update trailing stop ─────────────────────────────────────────────────
    def update_positions(self, symbol: str, current_price: float, current_atr: float) -> None:
        """
        Called on every price tick / cycle.  Updates trailing stops for
        Donchian positions and checks all exit conditions.
        """
        pos = self.get_open_position(symbol)
        if not pos:
            return

        side         = pos["side"]
        trail_stop   = pos.get("trail_stop")
        trail_mult   = pos.get("trail_mult", 2.0)
        sl_price     = pos["sl_price"]
        tp_price     = pos.get("tp_price")
        trade_id     = pos["trade_id"]

        # ── Update trailing stop (Donchian only) ──────────────────────────
        if pos["strategy"] == "DONCHIAN" and trail_stop is not None:
            new_trail = _risk.update_trailing_stop(
                side=side,
                current_price=current_price,
                current_trail=trail_stop,
                atr=current_atr,
                trail_mult=trail_mult,
            )
            if new_trail != trail_stop:
                pos["trail_stop"] = new_trail
                save_positions(self.positions)
                log_trade_event("UPDATE_TRAIL", {
                    "trade_id":  trade_id,
                    "exchange":  pos["exchange"],
                    "symbol":    symbol,
                    "strategy":  pos["strategy"],
                    "side":      side,
                    "entry_price": pos["entry_price"],
                    "trail_stop":  new_trail,
                    "notes":     f"Trail updated {trail_stop:.4f} → {new_trail:.4f}",
                })
                trail_stop = new_trail

        # ── Check exit conditions ─────────────────────────────────────────
        exit_reason = _risk.check_exit(
            side=side,
            current_price=current_price,
            sl_price=sl_price,
            tp_price=tp_price,
            trail_stop=trail_stop,
        )

        if exit_reason:
            self.close_position(trade_id, current_price, exit_reason)

    # ── Close a position ─────────────────────────────────────────────────────
    def close_position(
        self,
        trade_id:     str,
        exit_price:   float,
        reason:       str = "MANUAL",
    ) -> None:
        """
        Place a closing market order and remove the position from state.
        """
        pos = self.positions.get(trade_id)
        if not pos:
            log.warning("close_position: trade_id %s not found.", trade_id)
            return

        symbol = pos["symbol"]
        side   = pos["side"]
        qty    = pos["qty"]

        close_side = "sell" if side == "long" else "buy"
        try:
            self.client.place_market_order(symbol, close_side, qty)
        except Exception as exc:
            log.error("Could not close position %s: %s", trade_id, exc)
            # Continue to remove from state anyway to avoid ghost positions
            # (user should manually check the exchange)

        pnl_usdt, pnl_pct = _risk.calculate_pnl(
            side=side,
            entry_price=pos["entry_price"],
            exit_price=exit_price,
            qty=qty,
        )

        log_trade_event("CLOSE", {
            "trade_id":    trade_id,
            "exchange":    pos["exchange"],
            "symbol":      symbol,
            "strategy":    pos["strategy"],
            "side":        side,
            "entry_price": pos["entry_price"],
            "exit_price":  exit_price,
            "sl_price":    pos["sl_price"],
            "tp_price":    pos.get("tp_price", ""),
            "trail_stop":  pos.get("trail_stop", ""),
            "qty":         qty,
            "pnl_usdt":    pnl_usdt,
            "pnl_pct":     pnl_pct,
            "regime_4h":   pos.get("regime_4h", ""),
            "regime_1h":   pos.get("regime_1h", ""),
            "adx_1h":      pos.get("adx_1h", ""),
            "atr_entry":   pos.get("atr", ""),
            "reason":      reason,
            "notes":       pos.get("notes", ""),
        })

        emoji = "💰" if pnl_usdt >= 0 else "📉"
        log.info(
            "%s CLOSED [%s] %s %s  exit=%.4f  PnL=%.2f USDT (%.2f%%)  reason=%s",
            emoji, pos["strategy"], side.upper(), symbol,
            exit_price, pnl_usdt, pnl_pct, reason,
        )

        del self.positions[trade_id]
        save_positions(self.positions)
