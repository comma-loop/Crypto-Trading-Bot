"""
exchanges/__init__.py
─────────────────────
Factory to build the correct ExchangeClient from settings.
"""

from config.settings import EXCHANGE_NAME, USE_DEMO
from .exchange_client import ExchangeClient


def create_exchange(
    exchange_name: str | None = None,
    demo: bool | None = None,
) -> ExchangeClient:
    """
    Build and return an ExchangeClient.

    Falls back to the values defined in `.env` / ``config.settings``
    when arguments are not explicitly provided.
    """
    name = (exchange_name or EXCHANGE_NAME).lower()
    is_demo = demo if demo is not None else USE_DEMO
    return ExchangeClient(name, demo=is_demo)


__all__ = ["ExchangeClient", "create_exchange"]
