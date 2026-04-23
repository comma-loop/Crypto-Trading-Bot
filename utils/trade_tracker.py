"""
utils/trade_tracker.py
──────────────────────
Writes every trade event (open, update, close) to a CSV file so you can
review the bot's full history offline.
"""

import csv
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import TRADE_HISTORY_CSV, OPEN_POSITIONS_JSON
from utils.logger import get_logger

log = get_logger(__name__)

# ── CSV column order ──────────────────────────────────────────────────────────
CSV_HEADERS = [
    "timestamp",
    "event",           # OPEN | UPDATE_TRAIL | CLOSE
    "trade_id",
    "exchange",
    "symbol",
    "strategy",        # DONCHIAN | TURTLE_SOUP
    "side",            # long | short
    "entry_price",
    "exit_price",
    "sl_price",
    "tp_price",
    "trail_stop",
    "qty",
    "pnl_usdt",
    "pnl_pct",
    "regime_4h",       # BULL | BEAR | NEUTRAL
    "regime_1h",       # TRENDING | RANGING | NEUTRAL
    "adx_1h",
    "atr_entry",
    "reason",          # SL_HIT | TP_HIT | TRAIL_STOP | MANUAL
    "notes",
]

_lock = threading.Lock()


def _ensure_csv(path: Path) -> None:
    """Create the CSV with headers if it doesn't exist."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writeheader()
        log.info("Created trade history CSV: %s", path)


def log_trade_event(event: str, trade: dict[str, Any]) -> None:
    """
    Append a single row to the CSV.

    Parameters
    ----------
    event : str
        One of ``OPEN``, ``UPDATE_TRAIL``, ``CLOSE``.
    trade : dict
        Must contain at minimum the keys defined in ``CSV_HEADERS``.
    """
    _ensure_csv(TRADE_HISTORY_CSV)

    row = {h: "" for h in CSV_HEADERS}
    row["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    row["event"] = event
    row.update({k: v for k, v in trade.items() if k in CSV_HEADERS})

    with _lock:
        with open(TRADE_HISTORY_CSV, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writerow(row)

    log.debug("CSV logged [%s] trade_id=%s  symbol=%s", event, row.get("trade_id"), row.get("symbol"))


# ─────────────────────────────────────────────────────────────────────────────
#  Open-position persistence  (JSON state file)
# ─────────────────────────────────────────────────────────────────────────────

def save_positions(positions: dict[str, Any]) -> None:
    """Persist the current open-positions dict to disk."""
    try:
        OPEN_POSITIONS_JSON.parent.mkdir(parents=True, exist_ok=True)
        with open(OPEN_POSITIONS_JSON, "w", encoding="utf-8") as f:
            json.dump(positions, f, indent=2, default=str)
    except OSError as exc:
        log.error("Could not save positions: %s", exc)


def load_positions() -> dict[str, Any]:
    """Load persisted open positions from disk (returns empty dict if missing)."""
    if not OPEN_POSITIONS_JSON.exists():
        return {}
    try:
        with open(OPEN_POSITIONS_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("Could not load positions (%s) — starting fresh.", exc)
        return {}
