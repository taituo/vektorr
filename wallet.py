import json
import uuid
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime


@dataclass
class Trade:
    trade_id: str
    timestamp: str
    match_id: str
    minute: int
    selection: str
    stake: float
    price_seen: float
    price_filled: Optional[float]
    slippage: float
    filled: bool
    outcome: Optional[str] = None  # WIN / LOSS / PENDING
    pnl: float = 0.0


class PaperWallet:
    """Virtual wallet for paper trading with P&L tracking."""

    def __init__(self, config: dict):
        self.balance = config.get('WALLET_START', 1000.0)
        self.default_stake = config.get('STAKE', 10.0)
        self.staking_mode = config.get('STAKING_MODE', 'flat')  # 'flat' or 'kelly'
        self.kelly_fraction = config.get('KELLY_FRACTION', 0.2)  # 20% of Kelly (safe)
        self.max_stake_pct = config.get('MAX_STAKE_PCT', 0.05)   # Max 5% of bankroll
        self.trades: List[Trade] = []
        self.log_file = "trade_log.jsonl"

    def calculate_kelly_stake(self, p_model: float, odds: float) -> float:
        """Calculates stake based on fractional Kelly criterion."""
        if odds <= 1.0 or p_model <= 0:
            return 0.0
        
        b = odds - 1.0
        q = 1.0 - p_model
        
        # Kelly formula: f* = (bp - q) / b
        f_star = (b * p_model - q) / b
        
        if f_star <= 0:
            return 0.0
            
        # Apply fractional Kelly and max limit
        stake_pct = f_star * self.kelly_fraction
        stake_pct = min(stake_pct, self.max_stake_pct)
        
        return round(self.balance * stake_pct, 2)

    @property
    def total_staked(self) -> float:
        return sum(t.stake for t in self.trades if t.filled)

    @property
    def total_pnl(self) -> float:
        return sum(t.pnl for t in self.trades if t.outcome in ("WIN", "LOSS"))

    @property
    def roi(self) -> float:
        staked = self.total_staked
        if staked == 0:
            return 0.0
        return (self.total_pnl / staked) * 100

    @property
    def pending_count(self) -> int:
        return len([t for t in self.trades if t.outcome == "PENDING"])

    def place_bet(self, match_id: str, minute: int, selection: str,
                  price_seen: float, price_filled: Optional[float],
                  slippage: float, filled: bool, p_model: float = 0.0) -> Optional[Trade]:
        if not filled:
            trade = Trade(
                trade_id=uuid.uuid4().hex[:12],
                timestamp=datetime.now().isoformat(),
                match_id=match_id,
                minute=minute,
                selection=selection,
                stake=0.0,
                price_seen=price_seen,
                price_filled=None,
                slippage=slippage,
                filled=False,
                outcome="REJECTED",
                pnl=0.0
            )
            self._log(trade)
            return trade

        # Determine stake
        if self.staking_mode == 'kelly' and p_model > 0:
            current_stake = self.calculate_kelly_stake(p_model, price_filled or price_seen)
        else:
            current_stake = self.default_stake

        if current_stake <= 0 or self.balance < current_stake:
            return None

        self.balance -= current_stake
        trade = Trade(
            trade_id=uuid.uuid4().hex[:12],
            timestamp=datetime.now().isoformat(),
            match_id=match_id,
            minute=minute,
            selection=selection,
            stake=current_stake,
            price_seen=price_seen,
            price_filled=price_filled,
            slippage=slippage,
            filled=True,
            outcome="PENDING"
        )
        self.trades.append(trade)
        self._log(trade)
        return trade

    def settle(self, trade: Trade, won: bool):
        """Settle a pending trade."""
        if won:
            trade.outcome = "WIN"
            trade.pnl = (trade.price_filled * trade.stake) - trade.stake
            self.balance += trade.stake + trade.pnl
        else:
            trade.outcome = "LOSS"
            trade.pnl = -trade.stake
        self._log(trade)

    def summary(self) -> dict:
        filled = [t for t in self.trades if t.filled]
        wins = [t for t in filled if t.outcome == "WIN"]
        losses = [t for t in filled if t.outcome == "LOSS"]
        return {
            "balance": round(self.balance, 2),
            "total_trades": len(filled),
            "wins": len(wins),
            "losses": len(losses),
            "pending": self.pending_count,
            "total_pnl": round(self.total_pnl, 2),
            "roi_pct": round(self.roi, 2)
        }

    def _log(self, trade: Trade):
        with open(self.log_file, "a") as f:
            f.write(json.dumps({
                "trade_id": trade.trade_id,
                "timestamp": trade.timestamp,
                "match_id": trade.match_id,
                "minute": trade.minute,
                "selection": trade.selection,
                "stake": trade.stake,
                "price_seen": trade.price_seen,
                "price_filled": trade.price_filled,
                "slippage": trade.slippage,
                "filled": trade.filled,
                "outcome": trade.outcome,
                "pnl": trade.pnl
            }) + "\n")
