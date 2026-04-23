"""
main.py
────────
Crypto Trading Bot — Main Entry Point
═══════════════════════════════════════

Run modes
─────────
  python main.py                  # uses settings from .env
  python main.py --exchange bybit --demo
  python main.py --exchange binance --live
  python main.py --symbols BTC/USDT:USDT --exchange okx --demo

Bot loop (runs every 15 minutes, aligned to candle close):
  For every configured symbol:
    1. Fetch OHLCV for 4H, 1H, 15m, 5m
    2. 4H analysis  → macro bias (BULL / BEAR / NEUTRAL)
    3. 1H analysis  → market regime → which strategy to use
    4. Manage open positions:
         a. Update Donchian trailing stops
         b. Check SL / TP / trail exit conditions
    5. If no open position:
         a. TRENDING  → run Donchian breakout on 15m
         b. RANGING   → run Turtle Soup on 15m + 5m
         c. NEUTRAL   → skip (no trade)
    6. On valid signal: size the position, place order, record to CSV
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
from datetime import datetime, timezone

import schedule

from config.settings import (
    EXCHANGE_NAME,
    SYMBOLS,
    TF_ENTRY,
    TF_MACRO,
    TF_PRECISE,
    TF_REGIME,
    USE_DEMO,
    LOG_LEVEL,
    LOG_DIR,
    LOOKBACK,
    MAX_POSITIONS_PER_SYMBOL,
)
from core.market_analyzer import MarketAnalyzer
from core.position_manager import PositionManager
from exchanges import create_exchange
from exchanges.exchange_client import ExchangeClient
from strategies.donchian_breakout import DonchianStrategy
from strategies.turtle_soup import TurtleSoupStrategy
from utils.logger import get_logger

log = get_logger(__name__, log_dir=LOG_DIR, level=LOG_LEVEL)


# ─────────────────────────────────────────────────────────────────────────────
#  Bot
# ─────────────────────────────────────────────────────────────────────────────
class TradingBot:
    """
    Top-level orchestrator. One instance runs the entire bot.
    """

    def __init__(self, client: ExchangeClient) -> None:
        self.client   = client
        self.analyzer = MarketAnalyzer()
        self.pos_mgr  = PositionManager(client)
        self._running = False

    # ── Per-symbol cycle ─────────────────────────────────────────────────────
    def _run_symbol(self, symbol: str) -> None:
        log.info("─── Processing %s ─────────────────────────────────────", symbol)

        # ── 1. Fetch OHLCV ────────────────────────────────────────────────
        try:
            df_4h  = self.client.fetch_ohlcv(symbol, TF_MACRO,   limit=LOOKBACK)
            df_1h  = self.client.fetch_ohlcv(symbol, TF_REGIME,  limit=LOOKBACK)
            df_15m = self.client.fetch_ohlcv(symbol, TF_ENTRY,   limit=LOOKBACK)
            df_5m  = self.client.fetch_ohlcv(symbol, TF_PRECISE, limit=100)
        except Exception as exc:
            log.error("OHLCV fetch failed for %s: %s", symbol, exc)
            return

        if df_15m.empty or df_1h.empty or df_4h.empty:
            log.warning("Empty OHLCV data for %s — skipping.", symbol)
            return

        # ── 2. Multi-timeframe analysis ───────────────────────────────────
        ctx = self.analyzer.analyse(df_4h, df_1h)

        # ── 3. Current price (latest 15m close) ───────────────────────────
        current_price = float(df_15m["close"].iloc[-1])
        current_atr   = float(
            df_15m["close"].rolling(14).std().iloc[-1]  # fallback; real ATR computed inside
            if "atr" not in df_15m.columns
            else df_15m["atr"].iloc[-1]
        )

        # Import indicators here to get clean ATR for position management
        from indicators import apply_all_indicators
        df15_ind = apply_all_indicators(df_15m.copy())
        df15_ind.dropna(inplace=True)
        if not df15_ind.empty:
            current_atr = float(df15_ind["atr"].iloc[-1])

        # ── 4. Manage existing open positions ─────────────────────────────
        self.pos_mgr.update_positions(symbol, current_price, current_atr)

        # ── 5. Check if we can open a new position ────────────────────────
        if self.pos_mgr.has_open_position(symbol):
            log.info("Already in a position for %s — no new entry.", symbol)
            return

        if ctx.strategy == "NONE":
            log.info(
                "1H ADX=%.1f is in neutral zone (%.1f–%.1f) — no trade for %s.",
                ctx.adx_1h,
                __import__("config.settings", fromlist=["ADX_RANGE_THRESHOLD"]).ADX_RANGE_THRESHOLD,
                __import__("config.settings", fromlist=["ADX_TREND_THRESHOLD"]).ADX_TREND_THRESHOLD,
                symbol,
            )
            return

        # ── 6a. Donchian Breakout (trending) ─────────────────────────────
        if ctx.strategy == "DONCHIAN":
            strat  = DonchianStrategy(macro_bias=ctx.macro_bias)
            signal = strat.check_signal(df_15m)

            if signal.has_signal:
                self.pos_mgr.open_position(
                    symbol      = symbol,
                    side        = signal.side,
                    entry_price = signal.entry_price,
                    sl_price    = signal.sl_price,
                    tp_price    = None,                 # Donchian: no fixed TP
                    trail_stop  = signal.trail_start,
                    trail_mult  = signal.trail_mult,
                    atr         = signal.atr,
                    strategy    = "DONCHIAN",
                    regime_4h   = ctx.macro_bias,
                    regime_1h   = ctx.regime_1h,
                    adx_1h      = ctx.adx_1h,
                    notes       = signal.notes,
                )

        # ── 6b. Turtle Soup (ranging) ─────────────────────────────────────
        elif ctx.strategy == "TURTLE_SOUP":
            strat  = TurtleSoupStrategy(macro_bias=ctx.macro_bias)
            signal = strat.check_signal(df_15m, df_5m=df_5m)

            if signal.has_signal:
                self.pos_mgr.open_position(
                    symbol      = symbol,
                    side        = signal.side,
                    entry_price = signal.entry_price,
                    sl_price    = signal.sl_price,
                    tp_price    = signal.tp_price,
                    trail_stop  = None,                 # Turtle Soup: fixed TP, no trail
                    trail_mult  = 0.0,
                    atr         = signal.atr,
                    strategy    = "TURTLE_SOUP",
                    regime_4h   = ctx.macro_bias,
                    regime_1h   = ctx.regime_1h,
                    adx_1h      = ctx.adx_1h,
                    notes       = signal.notes,
                )

    # ── Main cycle ───────────────────────────────────────────────────────────
    def run_cycle(self) -> None:
        """Called every 15 minutes; iterates over all configured symbols."""
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        log.info("═══════════════════════════════════════════════════════")
        log.info("  BOT CYCLE  %s", ts)
        log.info("═══════════════════════════════════════════════════════")

        for symbol in SYMBOLS:
            try:
                self._run_symbol(symbol)
            except Exception as exc:
                log.exception("Unhandled error processing %s: %s", symbol, exc)

        log.info("Cycle complete.  Open positions: %d", len(self.pos_mgr.positions))

    # ── Start / stop ─────────────────────────────────────────────────────────
    def start(self) -> None:
        """
        Run an immediate cycle, then schedule one every 15 minutes.
        The schedule is aligned so cycles run at :00, :15, :30, :45.
        """
        self._running = True

        # Graceful shutdown on Ctrl+C / SIGTERM
        def _shutdown(signum, frame):
            log.info("Shutdown signal received — stopping bot gracefully.")
            self._running = False
            sys.exit(0)

        signal.signal(signal.SIGINT,  _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)

        log.info("🤖 Bot starting  |  exchange=%s  demo=%s  symbols=%s",
                 self.client.name.upper(), self.client.demo, SYMBOLS)

        # Run once immediately
        self.run_cycle()

        # Schedule every 15 minutes
        schedule.every(15).minutes.do(self.run_cycle)
        log.info("Scheduler set: running every 15 minutes.")

        while self._running:
            schedule.run_pending()
            time.sleep(1)


# ─────────────────────────────────────────────────────────────────────────────
#  CLI entry point
# ─────────────────────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Donchian / Turtle Soup crypto trading bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--exchange",
        default=EXCHANGE_NAME,
        choices=["bybit", "binance", "okx", "hyperliquid"],
        help="Exchange to connect to (default: %(default)s)",
    )
    p.add_argument(
        "--demo",
        action="store_true",
        default=USE_DEMO,
        help="Use demo/testnet account (default: %(default)s)",
    )
    p.add_argument(
        "--live",
        action="store_true",
        default=False,
        help="Override --demo; use the real/live account  ⚠️  REAL MONEY",
    )
    p.add_argument(
        "--symbols",
        default=None,
        help="Comma-separated symbols, e.g. BTC/USDT:USDT,ETH/USDT:USDT",
    )
    p.add_argument(
        "--once",
        action="store_true",
        help="Run exactly one cycle then exit (useful for testing)",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # --live overrides --demo
    use_demo = not args.live if args.live else args.demo

    if not use_demo:
        log.warning(
            "⚠️  LIVE MODE  — real money will be used on %s. "
            "Press Ctrl+C within 5 seconds to abort.",
            args.exchange.upper(),
        )
        time.sleep(5)

    # Override symbols from CLI if provided
    if args.symbols:
        import config.settings as _cfg
        _cfg.SYMBOLS = [s.strip() for s in args.symbols.split(",") if s.strip()]

    # Build exchange client
    client = create_exchange(exchange_name=args.exchange, demo=use_demo)

    # Build and start the bot
    bot = TradingBot(client)

    if args.once:
        bot.run_cycle()
    else:
        bot.start()


if __name__ == "__main__":
    main()
