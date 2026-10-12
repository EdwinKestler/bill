"""Explicit live-wallet composition root."""

from __future__ import annotations

from .adapter import RgbBillAdapter
from .config import RgbSettings
from .native import RgbLibBackend


def open_adapter(settings: RgbSettings) -> RgbBillAdapter:
    """Open exactly the active role's wallet and acquire its process lock."""
    return RgbBillAdapter(settings, RgbLibBackend.open(settings))
