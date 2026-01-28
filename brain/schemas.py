from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict

class Event(BaseModel):
    match_id: str
    t_event: datetime
    t_recv: datetime
    type: str
    team: Optional[str] = None
    xg: float = 0.0
    data: Dict = Field(default_factory=dict)

class Odds(BaseModel):
    match_id: str
    t_seen: datetime
    t_recv: datetime
    market: str
    selection: str
    price: float
    line: Optional[float] = None
    point: Optional[float] = None
    is_suspended: bool = False

class MatchState(BaseModel):
    match_id: str
    minute: int
    score: str
    tps_label: str = "LOW"
    t_event_latest: datetime
    t_recv_latest: datetime
    event_latency_p95: float = 0.0
    odds_latency_p95: float = 0.0
