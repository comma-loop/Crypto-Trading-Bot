"""
utils/logger.py
───────────────
Colourised, dual-output (console + rotating file) logger.
Every module in the bot imports get_logger(__name__).
"""

import logging
import logging.handlers
from pathlib import Path

try:
    import colorlog
    _HAS_COLORLOG = True
except ImportError:
    _HAS_COLORLOG = False


def get_logger(name: str, log_dir: Path | None = None, level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger                    # already configured

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # ── Console handler (coloured if available) ───────────────────────────
    if _HAS_COLORLOG:
        fmt = colorlog.ColoredFormatter(
            "%(log_color)s%(asctime)s [%(levelname)-8s]%(reset)s %(cyan)s%(name)s%(reset)s │ %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            log_colors={
                "DEBUG":    "white",
                "INFO":     "green",
                "WARNING":  "yellow",
                "ERROR":    "red",
                "CRITICAL": "bold_red",
            },
        )
    else:
        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)-8s] %(name)s │ %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # ── File handler (rotating) ───────────────────────────────────────────
    if log_dir:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            log_dir / "bot.log",
            maxBytes=5 * 1024 * 1024,   # 5 MB per file
            backupCount=5,
            encoding="utf-8",
        )
        fh.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)-8s] %(name)s │ %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(fh)

    logger.propagate = False
    return logger
