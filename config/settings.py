"""
config/settings.py
──────────────────
Loads all configuration from the .env file and exposes typed constants
used across the entire bot. Import this module wherever settings are needed.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ── Load .env (looks upward from this file's location) ────────────────────────
_root = Path(__file__).resolve().parent.parent
load_dotenv(_root / ".env")

# ─────────────────────────────────────────────────────────────────────────────
#  MODE
# ─────────────────────────────────────────────────────────────────────────────
USE_DEMO: bool = os.getenv("USE_DEMO", "true").lower() == "true"

# ─────────────────────────────────────────────────────────────────────────────
#  EXCHANGE
# ─────────────────────────────────────────────────────────────────────────────
EXCHANGE_NAME: str = os.getenv("EXCHANGE", "bybit").lower()

EXCHANGE_CREDENTIALS: dict = {
    "bybit": {
        "demo": {
            "api_key":    os.getenv("BYBIT_API_KEY_DEMO", ""),
            "api_secret": os.getenv("BYBIT_API_SECRET_DEMO", ""),
            "passphrase": None,
        },
        "real": {
            "api_key":    os.getenv("BYBIT_API_KEY_REAL", ""),
            "api_secret": os.getenv("BYBIT_API_SECRET_REAL", ""),
            "passphrase": None,
        },
    },
    "binance": {
        "demo": {
            "api_key":    os.getenv("BINANCE_API_KEY_DEMO", ""),
            "api_secret": os.getenv("BINANCE_API_SECRET_DEMO", ""),
            "passphrase": None,
        },
        "real": {
            "api_key":    os.getenv("BINANCE_API_KEY_REAL", ""),
            "api_secret": os.getenv("BINANCE_API_SECRET_REAL", ""),
            "passphrase": None,
        },
    },
    "okx": {
        "demo": {
            "api_key":    os.getenv("OKX_API_KEY_DEMO", ""),
            "api_secret": os.getenv("OKX_API_SECRET_DEMO", ""),
            "passphrase": os.getenv("OKX_PASSPHRASE_DEMO", ""),
        },
        "real": {
            "api_key":    os.getenv("OKX_API_KEY_REAL", ""),
            "api_secret": os.getenv("OKX_API_SECRET_REAL", ""),
            "passphrase": os.getenv("OKX_PASSPHRASE_REAL", ""),
        },
    },
    "hyperliquid": {
        "demo": {
            "api_key":    os.getenv("HYPERLIQUID_API_KEY_DEMO", ""),
            "api_secret": os.getenv("HYPERLIQUID_API_SECRET_DEMO", ""),
            "passphrase": None,
        },
        "real": {
            "api_key":    os.getenv("HYPERLIQUID_API_KEY_REAL", ""),
            "api_secret": os.getenv("HYPERLIQUID_API_SECRET_REAL", ""),
            "passphrase": None,
        },
    },
}

# ─────────────────────────────────────────────────────────────────────────────
#  SYMBOLS
# ─────────────────────────────────────────────────────────────────────────────
SYMBOLS: list[str] = [
    s.strip()
    for s in os.getenv("SYMBOLS", "BTC/USDT:USDT,ETH/USDT:USDT").split(",")
    if s.strip() and s.strip().upper().startswith(("BTC", "ETH"))
]

# Safety guard — if somehow the filter produces an empty list, fall back to defaults
if not SYMBOLS:
    SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT"]

# ─────────────────────────────────────────────────────────────────────────────
#  TIMEFRAMES
# ─────────────────────────────────────────────────────────────────────────────
TF_MACRO:   str = "4h"    # Overall market direction / big trend bias
TF_REGIME:  str = "1h"    # Strategy selection (trending vs. ranging)
TF_ENTRY:   str = "15m"   # Entry timeframe
TF_PRECISE: str = "5m"    # Precise reversal entry (Turtle Soup only)

# Candles fetched per timeframe (must cover DONCHIAN_PERIOD + ADX_PERIOD + buffer)
LOOKBACK: int = 250

# ─────────────────────────────────────────────────────────────────────────────
#  INDICATOR PARAMETERS
# ─────────────────────────────────────────────────────────────────────────────
ADX_PERIOD:      int   = int(os.getenv("ADX_PERIOD", "14"))
ATR_PERIOD:      int   = int(os.getenv("ATR_PERIOD", "14"))
DONCHIAN_PERIOD: int   = int(os.getenv("DONCHIAN_PERIOD", "20"))

# ADX thresholds
ADX_TREND_THRESHOLD: float = float(os.getenv("ADX_TREND_THRESHOLD", "25"))
ADX_RANGE_THRESHOLD: float = float(os.getenv("ADX_RANGE_THRESHOLD", "20"))

# ─────────────────────────────────────────────────────────────────────────────
#  RISK MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────
RISK_PER_TRADE:           float = float(os.getenv("RISK_PER_TRADE", "0.01"))
MAX_POSITIONS_PER_SYMBOL: int   = int(os.getenv("MAX_POSITIONS_PER_SYMBOL", "1"))
LEVERAGE:                 int   = int(os.getenv("LEVERAGE", "1"))

# Donchian strategy
DONCHIAN_SL_ATR_MULT:    float = float(os.getenv("DONCHIAN_SL_ATR_MULT", "3.0"))
DONCHIAN_TRAIL_ATR_MULT: float = float(os.getenv("DONCHIAN_TRAIL_ATR_MULT", "2.0"))

# Turtle Soup strategy (fixed per spec)
TURTLE_SL_ATR_MULT: float = float(os.getenv("TURTLE_SL_ATR_MULT", "1.5"))
TURTLE_TP_ATR_MULT: float = float(os.getenv("TURTLE_TP_ATR_MULT", "1.0"))

# How many candles back to look for the false-breakout wick in Turtle Soup
TURTLE_SOUP_LOOKBACK_CANDLES: int = 5

# ─────────────────────────────────────────────────────────────────────────────
#  PATHS
# ─────────────────────────────────────────────────────────────────────────────
DATA_DIR:              Path = _root / "data"
TRADE_HISTORY_CSV:     Path = DATA_DIR / "trade_history.csv"
OPEN_POSITIONS_JSON:   Path = DATA_DIR / "open_positions.json"
LOG_DIR:               Path = _root / "logs"

DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
