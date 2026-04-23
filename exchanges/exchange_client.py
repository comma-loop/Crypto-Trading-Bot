"""
exchanges/exchange_client.py
────────────────────────────
A thin, exchange-agnostic wrapper around ccxt.  Handles:
  • Exchange instantiation (sandbox vs. live)
  • Credential lookup from config
  • Symbol normalisation per exchange
  • OHLCV fetching → pandas DataFrame
  • Balance / order / position helpers used by the rest of the bot
"""

from __future__ import annotations

import time
from typing import Any, Optional

import ccxt
import pandas as pd

from config.settings import (
    EXCHANGE_CREDENTIALS,
    LEVERAGE,
    LOOKBACK,
    USE_DEMO,
)
from utils.logger import get_logger

log = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Symbol normalisation per exchange
# ─────────────────────────────────────────────────────────────────────────────
def _normalise_symbol(exchange_name: str, symbol: str) -> str:
    """
    Different exchanges use slightly different symbol formats.
    Our internal format is always  BTC/USDT:USDT  (perpetual futures style).
    """
    if exchange_name == "hyperliquid":
        # Hyperliquid uses   BTC/USDC:USDC  or just  BTC  depending on ccxt version
        # Strip quote and settle currency and return the base only
        base = symbol.split("/")[0]
        return base
    return symbol


# ─────────────────────────────────────────────────────────────────────────────
#  ExchangeClient
# ─────────────────────────────────────────────────────────────────────────────
class ExchangeClient:
    """
    Unified interface to Bybit / Binance / OKX / Hyperliquid via ccxt.

    Parameters
    ----------
    exchange_name : str
        One of ``bybit``, ``binance``, ``okx``, ``hyperliquid``.
    demo : bool
        If True uses sandbox/testnet endpoints where available.
    """

    def __init__(self, exchange_name: str, demo: bool = True) -> None:
        self.name = exchange_name.lower()
        self.demo = demo
        self._exchange: ccxt.Exchange = self._build_exchange()
        log.info(
            "ExchangeClient ready: %s  [%s]",
            self.name.upper(),
            "DEMO/TESTNET" if demo else "⚠️  LIVE",
        )

    # ── Construction ─────────────────────────────────────────────────────────
    def _build_exchange(self) -> ccxt.Exchange:
        mode = "demo" if self.demo else "real"
        creds = EXCHANGE_CREDENTIALS.get(self.name, {}).get(mode, {})

        config: dict[str, Any] = {
            "apiKey":          creds.get("api_key", ""),
            "secret":          creds.get("api_secret", ""),
            "enableRateLimit": True,
            "options": {
                "defaultType": "future",       # use perpetual futures market
                "adjustForTimeDifference": True,
            },
        }
        if creds.get("passphrase"):
            config["password"] = creds["passphrase"]

        if self.name not in ccxt.exchanges:
            raise ValueError(f"Exchange '{self.name}' not supported by ccxt.")

        exchange_class: type[ccxt.Exchange] = getattr(ccxt, self.name)
        exchange = exchange_class(config)

        # Sandbox / testnet setup
        if self.demo:
            if self.name == "bybit":
                # Bybit Demo Trading lives on bybit.com — demo keys work on the
                # normal endpoint. ccxt sandbox mode points to testnet.bybit.com
                # which is a completely separate system. Do NOT use sandbox here.
                pass
            elif self.name in ("binance", "okx"):
                exchange.set_sandbox_mode(True)
            elif self.name == "hyperliquid":
                # Hyperliquid testnet via ccxt option
                exchange.options["testnet"] = True

        return exchange

    # ── Market data ──────────────────────────────────────────────────────────
    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        limit: int = LOOKBACK,
        retries: int = 3,
    ) -> pd.DataFrame:
        """
        Fetch OHLCV candles and return a clean DataFrame.

        Returns
        -------
        pd.DataFrame
            Columns: open, high, low, close, volume
            Index:   UTC datetime
        """
        norm_symbol = _normalise_symbol(self.name, symbol)
        for attempt in range(1, retries + 1):
            try:
                raw = self._exchange.fetch_ohlcv(norm_symbol, timeframe, limit=limit)
                df = pd.DataFrame(
                    raw, columns=["timestamp", "open", "high", "low", "close", "volume"]
                )
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
                df.set_index("timestamp", inplace=True)
                df = df.astype(float)
                df.dropna(inplace=True)
                return df
            except (ccxt.NetworkError, ccxt.RequestTimeout) as exc:
                log.warning("OHLCV fetch attempt %d/%d failed: %s", attempt, retries, exc)
                if attempt < retries:
                    time.sleep(2 ** attempt)
            except ccxt.BaseError as exc:
                log.error("OHLCV fetch error for %s %s: %s", symbol, timeframe, exc)
                raise
        raise RuntimeError(f"Failed to fetch OHLCV for {symbol} {timeframe} after {retries} retries")

    def fetch_ticker(self, symbol: str) -> dict[str, Any]:
        norm = _normalise_symbol(self.name, symbol)
        return self._exchange.fetch_ticker(norm)

    # ── Account ───────────────────────────────────────────────────────────────
    def fetch_balance(self) -> dict[str, Any]:
        """Return the full balance dict from the exchange."""
        try:
            return self._exchange.fetch_balance()
        except ccxt.BaseError as exc:
            log.error("fetch_balance error: %s", exc)
            raise

    def get_usdt_balance(self) -> float:
        """Return available USDT (or USDC for Hyperliquid) balance."""
        bal = self.fetch_balance()
        quote = "USDC" if self.name == "hyperliquid" else "USDT"
        free = bal.get("free", {}).get(quote, 0.0)
        return float(free or 0.0)

    # ── Leverage ──────────────────────────────────────────────────────────────
    def set_leverage(self, symbol: str, leverage: int = LEVERAGE) -> None:
        norm = _normalise_symbol(self.name, symbol)
        try:
            self._exchange.set_leverage(leverage, norm)
            log.info("Leverage set to %dx for %s", leverage, symbol)
        except ccxt.BaseError as exc:
            # Some exchanges silently accept or have fixed leverage
            log.warning("Could not set leverage for %s: %s", symbol, exc)

    # ── Orders ────────────────────────────────────────────────────────────────
    def place_market_order(
        self,
        symbol: str,
        side: str,          # 'buy' | 'sell'
        qty: float,
        params: Optional[dict] = None,
    ) -> dict[str, Any]:
        """
        Place a market order.  `params` is passed through to ccxt for
        exchange-specific extras (e.g. positionSide for Binance hedge mode).
        """
        norm = _normalise_symbol(self.name, symbol)
        params = params or {}
        try:
            order = self._exchange.create_market_order(norm, side, qty, params=params)
            log.info("Market order placed: %s %s %s qty=%.6f", side.upper(), symbol, norm, qty)
            return order
        except ccxt.BaseError as exc:
            log.error("place_market_order error: %s", exc)
            raise

    def place_limit_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        params: Optional[dict] = None,
    ) -> dict[str, Any]:
        norm = _normalise_symbol(self.name, symbol)
        params = params or {}
        try:
            order = self._exchange.create_limit_order(norm, side, qty, price, params=params)
            log.info(
                "Limit order placed: %s %s qty=%.6f @ %.4f", side.upper(), symbol, qty, price
            )
            return order
        except ccxt.BaseError as exc:
            log.error("place_limit_order error: %s", exc)
            raise

    def cancel_order(self, order_id: str, symbol: str) -> dict[str, Any]:
        norm = _normalise_symbol(self.name, symbol)
        try:
            result = self._exchange.cancel_order(order_id, norm)
            log.info("Cancelled order %s for %s", order_id, symbol)
            return result
        except ccxt.BaseError as exc:
            log.warning("cancel_order error: %s", exc)
            return {}

    def fetch_open_orders(self, symbol: str) -> list[dict]:
        norm = _normalise_symbol(self.name, symbol)
        try:
            return self._exchange.fetch_open_orders(norm)
        except ccxt.BaseError as exc:
            log.error("fetch_open_orders error: %s", exc)
            return []

    # ── Exchange-side position query ──────────────────────────────────────────
    def fetch_positions(self, symbols: Optional[list[str]] = None) -> list[dict]:
        """Return all open positions (exchange-side view)."""
        try:
            if symbols:
                norms = [_normalise_symbol(self.name, s) for s in symbols]
                return self._exchange.fetch_positions(norms)
            return self._exchange.fetch_positions()
        except ccxt.BaseError as exc:
            log.error("fetch_positions error: %s", exc)
            return []

    # ── Convenience ───────────────────────────────────────────────────────────
    def get_min_order_qty(self, symbol: str) -> float:
        """Return the minimum order quantity for a symbol."""
        try:
            self._exchange.load_markets()
            norm = _normalise_symbol(self.name, symbol)
            market = self._exchange.market(norm)
            return float(market.get("limits", {}).get("amount", {}).get("min", 0.001) or 0.001)
        except Exception:
            return 0.001

    def get_price_precision(self, symbol: str) -> int:
        """Return number of decimal places for the symbol's price."""
        try:
            self._exchange.load_markets()
            norm = _normalise_symbol(self.name, symbol)
            market = self._exchange.market(norm)
            precision = market.get("precision", {}).get("price", 2)
            return int(precision) if isinstance(precision, (int, float)) else 2
        except Exception:
            return 2
