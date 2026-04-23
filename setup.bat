@echo off
REM ═══════════════════════════════════════════════════════════════════════════
REM  setup.bat  — First-time environment setup for the trading bot (Windows)
REM ═══════════════════════════════════════════════════════════════════════════

echo.
echo  ╔════════════════════════════════════════════════╗
echo  ║        Crypto Trading Bot — Setup (Windows)    ║
echo  ╚════════════════════════════════════════════════╝
echo.

REM ── 1. Check Python ──────────────────────────────────────────────────────
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo  ❌  Python not found. Please install Python 3.10+ and add to PATH.
    pause
    exit /b 1
)
FOR /F "tokens=2" %%i IN ('python --version 2^>^&1') DO echo  ✅  Python: %%i

REM ── 2. Create virtual environment ────────────────────────────────────────
IF EXIST venv (
    echo  ℹ️   Virtual environment already exists.
) ELSE (
    echo  ⚙️   Creating virtual environment...
    python -m venv venv
    echo  ✅  Virtual environment created.
)

REM ── 3. Install dependencies ──────────────────────────────────────────────
echo  ⚙️   Installing dependencies...
call venv\Scripts\activate.bat
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
echo  ✅  Dependencies installed.

REM ── 4. Create .env ───────────────────────────────────────────────────────
IF EXIST .env (
    echo  ℹ️   .env already exists — skipping.
) ELSE (
    copy .env.example .env >nul
    echo  ✅  .env created from .env.example
    echo.
    echo  ┌───────────────────────────────────────────────────────────────┐
    echo  │  ⚠️   IMPORTANT: Edit .env and fill in your API keys!           │
    echo  └───────────────────────────────────────────────────────────────┘
)

REM ── 5. Create data directory ─────────────────────────────────────────────
IF NOT EXIST data mkdir data
IF NOT EXIST logs mkdir logs

IF NOT EXIST data\trade_history.csv (
    echo timestamp,event,trade_id,exchange,symbol,strategy,side,entry_price,exit_price,sl_price,tp_price,trail_stop,qty,pnl_usdt,pnl_pct,regime_4h,regime_1h,adx_1h,atr_entry,reason,notes > data\trade_history.csv
    echo  ✅  data/trade_history.csv created.
)

echo.
echo  ╔════════════════════════════════════════════════╗
echo  ║  Setup complete!  Next steps:                  ║
echo  ║                                                ║
echo  ║  1. Edit .env — add your API keys              ║
echo  ║  2. venv\Scripts\activate                      ║
echo  ║  3. python main.py --demo                      ║
echo  ╚════════════════════════════════════════════════╝
echo.
pause
