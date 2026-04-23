#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  setup.sh  — First-time environment setup for the trading bot
# ═══════════════════════════════════════════════════════════════════════════
set -e

VENV_DIR="venv"
PYTHON="python3"

echo ""
echo "╔════════════════════════════════════════════════╗"
echo "║        Crypto Trading Bot — Setup              ║"
echo "╚════════════════════════════════════════════════╝"
echo ""

# ── 1. Check Python ──────────────────────────────────────────────────────────
if ! command -v $PYTHON &>/dev/null; then
    echo "❌  python3 not found. Please install Python 3.10+ first."
    exit 1
fi

PY_VERSION=$($PYTHON --version 2>&1 | awk '{print $2}')
echo "✅  Python: $PY_VERSION"

# ── 2. Create virtual environment ────────────────────────────────────────────
if [ -d "$VENV_DIR" ]; then
    echo "ℹ️   Virtual environment already exists at ./$VENV_DIR"
else
    echo "⚙️   Creating virtual environment..."
    $PYTHON -m venv $VENV_DIR
    echo "✅  Virtual environment created."
fi

# ── 3. Activate and install dependencies ─────────────────────────────────────
echo "⚙️   Installing dependencies from requirements.txt..."
source "$VENV_DIR/bin/activate"
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
echo "✅  Dependencies installed."

# ── 4. Create .env from template ─────────────────────────────────────────────
if [ -f ".env" ]; then
    echo "ℹ️   .env already exists — skipping copy."
else
    cp .env.example .env
    echo "✅  .env created from .env.example"
    echo ""
    echo "┌─────────────────────────────────────────────────────────────┐"
    echo "│  ⚠️   IMPORTANT: Edit .env and fill in your API keys before  │"
    echo "│       running the bot!                                       │"
    echo "└─────────────────────────────────────────────────────────────┘"
fi

# ── 5. Create data directory and placeholder files ────────────────────────────
mkdir -p data logs

if [ ! -f "data/trade_history.csv" ]; then
    echo "timestamp,event,trade_id,exchange,symbol,strategy,side,entry_price,exit_price,sl_price,tp_price,trail_stop,qty,pnl_usdt,pnl_pct,regime_4h,regime_1h,adx_1h,atr_entry,reason,notes" > data/trade_history.csv
    echo "✅  data/trade_history.csv created."
fi

touch data/.gitkeep

echo ""
echo "╔════════════════════════════════════════════════╗"
echo "║  Setup complete!  Next steps:                  ║"
echo "║                                                ║"
echo "║  1. Edit .env  — add your API keys             ║"
echo "║  2. source venv/bin/activate                   ║"
echo "║  3. python main.py --demo                      ║"
echo "║                                                ║"
echo "║  Other run options:                            ║"
echo "║  python main.py --once --demo  (single cycle)  ║"
echo "║  python main.py --live         (⚠️  REAL MONEY) ║"
echo "╚════════════════════════════════════════════════╝"
echo ""
