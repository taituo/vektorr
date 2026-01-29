import random
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

@dataclass
class FillResult:
    trade_id: str
    match_id: str
    timestamp: datetime
    minute: int
    selection: str
    stake: float
    price_seen: float
    price_filled: Optional[float]
    slippage: float
    filled: bool
    reason: str
    pnl: float = 0.0
    outcome: str = "PENDING"

class MockBroker:
    """
    Simulates a betting exchange (like Betfair) with realistic constraints.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.base_fill_rate = self.config.get('BASE_FILL_RATE', 0.85)
        self.mean_latency_ms = self.config.get('MEAN_LATENCY_MS', 150)
        self.std_latency_ms = self.config.get('STD_LATENCY_MS', 50)
        
        self.trades: List[FillResult] = []
        self.market_state = {"is_suspended": False, "volatility": 1.0}

    def update_market_state(self, is_suspended: bool, volatility: float = 1.0):
        self.market_state["is_suspended"] = is_suspended
        self.market_state["volatility"] = volatility

    def place_order(
        self, 
        match_id: str, 
        minute: int, 
        selection: str, 
        price_seen: float, 
        stake: float
    ) -> FillResult:
        # Simulate network latency
        latency_ms = max(50, random.gauss(self.mean_latency_ms, self.std_latency_ms))
        if random.random() < 0.05: # Occasional spike
            latency_ms += random.randint(300, 1000)
        
        # In a real simulation, we might actually sleep, but for mass testing we just record it
        # time.sleep(latency_ms / 1000.0) 
        
        trade_id = str(uuid.uuid4())[:8]
        
        # Fill logic
        fill_rate = self.base_fill_rate
        
        if self.market_state["is_suspended"]:
            return self._reject(trade_id, match_id, minute, selection, price_seen, stake, "SUSPENDED")
        
        # Large stakes are harder to fill
        if stake > 50:
            fill_rate -= 0.15
        
        # High volatility reduces fill rate
        if self.market_state["volatility"] > 2.0:
            fill_rate -= 0.20
            
        if random.random() > fill_rate:
            return self._reject(trade_id, match_id, minute, selection, price_seen, stake, "REJECTED_BY_MARKET")
        
        # Slippage model
        # Base slippage 1-2 ticks (simplified as percentage)
        base_slip_pct = random.uniform(0.01, 0.03)
        vol_factor = self.market_state["volatility"]
        
        # Late game slippage is higher
        minute_factor = 1.0 + (minute / 90.0)
        
        total_slip_pct = base_slip_pct * vol_factor * minute_factor
        price_filled = price_seen * (1.0 - total_slip_pct)
        
        # Round to 3 decimals as in example
        price_filled = round(price_filled, 3)
        slippage = round(price_seen - price_filled, 4)
        
        result = FillResult(
            trade_id=trade_id,
            match_id=match_id,
            timestamp=datetime.now(),
            minute=minute,
            selection=selection,
            stake=stake,
            price_seen=price_seen,
            price_filled=price_filled,
            slippage=slippage,
            filled=True,
            reason="FILLED"
        )
        
        self.trades.append(result)
        return result

    def _reject(self, trade_id, match_id, minute, selection, price_seen, stake, reason) -> FillResult:
        result = FillResult(
            trade_id=trade_id,
            match_id=match_id,
            timestamp=datetime.now(),
            minute=minute,
            selection=selection,
            stake=stake,
            price_seen=price_seen,
            price_filled=None,
            slippage=0.0,
            filled=False,
            reason=reason,
            outcome="REJECTED"
        )
        self.trades.append(result)
        return result

    def get_statistics(self) -> Dict[str, Any]:
        if not self.trades:
            return {}
            
        filled_trades = [t for t in self.trades if t.filled]
        return {
            "total_orders": len(self.trades),
            "fill_rate": len(filled_trades) / len(self.trades),
            "avg_slippage": sum(t.slippage for t in filled_trades) / len(filled_trades) if filled_trades else 0,
            "rejections": len(self.trades) - len(filled_trades)
        }
