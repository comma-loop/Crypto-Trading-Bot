# 🤖 Donchian / Turtle Soup Crypto Trading Bot

A multi-exchange, multi-timeframe Python trading bot that automatically switches
between two complementary strategies based on live market conditions.

---

## 🗺️ Strategy Overview

### Multi-Timeframe Framework

| Timeframe | Role |
|-----------|------|
| **4H** | Macro trend bias — BULL / BEAR / NEUTRAL |
| **1H** | Regime detection — TRENDING or RANGING |
| **15m** | Primary entry timeframe |
| **5m** | Precise reversal timing (Turtle Soup only) |

### 📈 Strategy 1 — Donchian Channel Breakout (Trending Market)
**Activated when:** 1H ADX > 25

- **Long**: 15m candle closes *above* the 20-period Donchian upper band, 4H bias = BULL or NEUTRAL
- **Short**: 15m candle closes *below* the 20-period Donchian lower band, 4H bias = BEAR or NEUTRAL
- **Stop Loss**: Wide — entry ± (3.0 × ATR) to avoid wick stop-outs
- **Take Profit**: No fixed TP — uses an **ATR Trailing Stop** that ratchets in your favour as price moves

### 🔄 Strategy 2 — Turtle Soup (Ranging Market / False Breakout)
**Activated when:** 1H ADX < 20

Fades false Donchian breakouts. When price briefly pokes outside the channel then reverses back inside, we trade the rejection.

- **Long (fade false breakdown)**: Recent wick below lower band → closed back inside → 5m bullish candle confirms
  - **SL** = entry − 1.5 × ATR
  - **TP** = entry + 1.0 × ATR

- **Short (fade false breakout)**: Recent wick above upper band → closed back inside → 5m bearish candle confirms
  - **SL** = entry + 1.5 × ATR
  - **TP** = entry − 1.0 × ATR

### ⚪ Neutral Zone (ADX 20–25)
No trades. Both strategies have lower edge in transitional conditions.

---

## 🏗️ Project Structure

```
crypto_trading_bot/
├── main.py                   # Entry point & bot loop
├── setup.sh / setup.bat      # One-command setup
├── requirements.txt
├── .env.example              # Template for API keys
├── .gitignore
│
├── config/
│   └── settings.py           # All constants, loaded from .env
│
├── exchanges/
│   ├── __init__.py           # Factory: create_exchange()
│   └── exchange_client.py    # Unified ccxt wrapper
│
├── indicators/
│   └── indicators.py         # ATR, ADX, Donchian (pure pandas/numpy)
│
├── strategies/
│   ├── donchian_breakout.py  # Trending market strategy
│   └── turtle_soup.py        # Ranging / false-breakout strategy
│
├── risk/
│   └── risk_manager.py       # Position sizing, trailing stop, PnL
│
├── core/
│   ├── market_analyzer.py    # 4H + 1H multi-timeframe analysis
│   └── position_manager.py   # Open/update/close positions + CSV logs
│
├── utils/
│   ├── logger.py             # Colourised rotating logger
│   └── trade_tracker.py      # CSV + JSON persistence
│
└── data/
    ├── trade_history.csv      # Complete trade log (gitignored)
    └── open_positions.json    # Live state (gitignored)
```

---

## ⚡ Quick Start

### 1. Clone & Setup

```bash
# Linux / macOS
chmod +x setup.sh && ./setup.sh

# Windows
setup.bat
```

### 2. Configure API Keys

Edit `.env` and fill in your keys for the exchange you want to use:

```env
USE_DEMO=true          # Start with demo!
EXCHANGE=bybit

BYBIT_API_KEY_DEMO=xxxxx
BYBIT_API_SECRET_DEMO=xxxxx
```

### 3. Run the Bot

```bash
# Activate venv first
source venv/bin/activate          # Linux/macOS
venv\Scripts\activate             # Windows

# Run in demo mode (reads from .env)
python main.py

# Run one cycle only (great for testing)
python main.py --once --demo

# Override exchange from CLI
python main.py --exchange binance --demo
python main.py --exchange okx --demo

# ⚠️  LIVE trading (real money)
python main.py --live
```

---

## 🔑 Exchange Setup Guide

### Bybit (Testnet)
1. Go to https://testnet.bybit.com → create account
2. API Management → Create Key → enable **Read** + **Trade**
3. Paste into `.env` as `BYBIT_API_KEY_DEMO` / `BYBIT_API_SECRET_DEMO`

### Binance (Testnet)
1. Go to https://testnet.binancefutures.com
2. Generate HMAC keys → paste into `.env`

### OKX (Demo Trading)
1. Log in to OKX → Demo Trading mode
2. API → Create API Key (needs passphrase!) → paste all three into `.env`

### Hyperliquid (Testnet)
1. Go to https://app.hyperliquid-testnet.xyz
2. Connect wallet → API Keys → generate key
3. Use wallet address as `api_key` and private key as `api_secret`

---

## ⚙️ Configuration Reference

All settings live in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_DEMO` | `true` | Use testnet/sandbox |
| `EXCHANGE` | `bybit` | Active exchange |
| `SYMBOLS` | `BTC/USDT:USDT,ETH/USDT:USDT` | Perpetual futures symbols |
| `RISK_PER_TRADE` | `0.01` | 1% of balance per trade |
| `LEVERAGE` | `1` | Position leverage |
| `ADX_PERIOD` | `14` | ADX indicator period |
| `ATR_PERIOD` | `14` | ATR indicator period |
| `DONCHIAN_PERIOD` | `20` | Donchian channel period |
| `ADX_TREND_THRESHOLD` | `25` | ADX above → TRENDING |
| `ADX_RANGE_THRESHOLD` | `20` | ADX below → RANGING |
| `DONCHIAN_SL_ATR_MULT` | `3.0` | SL width for Donchian trades |
| `DONCHIAN_TRAIL_ATR_MULT` | `2.0` | Trailing stop distance |
| `TURTLE_SL_ATR_MULT` | `1.5` | Fixed per spec |
| `TURTLE_TP_ATR_MULT` | `1.0` | Fixed per spec |

---

## 📊 Trade History CSV

Every trade event is logged to `data/trade_history.csv`:

| Column | Description |
|--------|-------------|
| `timestamp` | UTC time of event |
| `event` | `OPEN` / `UPDATE_TRAIL` / `CLOSE` |
| `trade_id` | Unique identifier |
| `strategy` | `DONCHIAN` or `TURTLE_SOUP` |
| `side` | `long` or `short` |
| `entry_price` / `exit_price` | Execution prices |
| `sl_price` / `tp_price` | Stop and target |
| `trail_stop` | Current trailing stop level |
| `pnl_usdt` / `pnl_pct` | Realised profit/loss |
| `regime_4h` / `regime_1h` | Market context at entry |
| `adx_1h` / `atr_entry` | Indicator values at entry |
| `reason` | Exit reason: `SL_HIT` / `TP_HIT` / `TRAIL_STOP` |

---

## ⚠️ Disclaimer

This software is for **educational purposes**. Crypto trading carries significant
financial risk. Always test thoroughly in demo mode before using real funds.
The authors are not responsible for any financial losses.

---

## 🛠️ Dependencies

- [ccxt](https://github.com/ccxt/ccxt) — unified exchange API
- [pandas](https://pandas.pydata.org/) — data manipulation
- [numpy](https://numpy.org/) — numerical computing
- [python-dotenv](https://github.com/theskumar/python-dotenv) — env config
- [schedule](https://github.com/dbader/schedule) — job scheduling
- [colorlog](https://github.com/borntyping/python-colorlog) — coloured logging
