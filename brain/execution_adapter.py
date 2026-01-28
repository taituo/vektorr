from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import json


@dataclass
class ExecutionRequest:
    match_id: str
    selection: str
    price: float
    stake: float
    market: Optional[str] = None
    note: Optional[str] = None
    timestamp: datetime = datetime.now(timezone.utc)


@dataclass
class ExecutionResult:
    status: str
    reason: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None


class ExecutionAdapter(ABC):
    @abstractmethod
    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        raise NotImplementedError


class ManualExecutionAdapter(ExecutionAdapter):
    """Logs manual executions to JSONL. Does not place real bets."""

    def __init__(self, path: str = "manual_trades.jsonl") -> None:
        self.path = path

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        payload = asdict(request)
        payload["timestamp"] = request.timestamp.isoformat()
        with open(self.path, "a") as f:
            f.write(json.dumps(payload) + "\n")
        return ExecutionResult(status="MANUAL_LOGGED", meta={"path": self.path})


class StubExecutionAdapter(ExecutionAdapter):
    """No-op adapter for dry runs."""

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        return ExecutionResult(status="NOOP", reason="stub")
