from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class BetfairOrderResult:
    status: str
    matched_price: Optional[float] = None
    reason: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None


class BetfairAdapter:
    """Skeleton adapter for Betfair API. Fill in login + place order when keys are available."""

    def __init__(self, app_key: str, username: str, password: str, cert_path: str, key_path: str):
        self.app_key = app_key
        self.username = username
        self.password = password
        self.cert_path = cert_path
        self.key_path = key_path

    def login(self) -> bool:
        # TODO: implement Betfair login
        return True

    def place_order(self, market_id: str, selection_id: str, price: float, stake: float) -> BetfairOrderResult:
        # TODO: implement Betfair place order
        return BetfairOrderResult(status="DRY_RUN", matched_price=None)
