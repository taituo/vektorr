import random
from dataclasses import dataclass
from typing import Optional


@dataclass
class ExecutionResult:
    filled: bool
    price_seen: float
    price_filled: Optional[float]
    slippage: float
    reason: str  # FILLED, REJECTED, PRICE_MOVED


class ExecutionStub:
    """Simulates bet execution with realistic fill/reject/slippage."""

    def __init__(self, config: dict):
        self.reject_rate = config.get('REJECT_RATE', 0.20)
        self.max_slippage = config.get('MAX_SLIPPAGE', 0.10)

    def execute(self, price_seen: float) -> ExecutionResult:
        # 20% chance of rejection (market moved, suspended, etc.)
        if random.random() < self.reject_rate:
            return ExecutionResult(
                filled=False,
                price_seen=price_seen,
                price_filled=None,
                slippage=0.0,
                reason="REJECTED"
            )

        # Slippage: price typically drops slightly between signal and fill
        slip = random.uniform(0.0, self.max_slippage)
        fill_price = max(1.01, price_seen - slip)

        return ExecutionResult(
            filled=True,
            price_seen=price_seen,
            price_filled=round(fill_price, 3),
            slippage=round(slip, 4),
            reason="FILLED"
        )
