import os
import time
import json
import yaml
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

from betfair_adapter import BetfairAdapter


@dataclass
class Decision:
    match_id: str
    selection: Optional[str]
    market: Optional[str]
    odds_price: Optional[float]
    can_bet: bool
    reason: str
    timestamp: str


@dataclass
class ExecResult:
    status: str
    reason: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None


def load_config(path: str) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}


def query_questdb(host: str, port: int, sql: str) -> dict:
    base = f"http://{host}:{port}/exec"
    url = f"{base}?{urllib.parse.urlencode({'query': sql})}"
    with urllib.request.urlopen(url) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data


def exec_questdb(host: str, port: int, sql: str) -> None:
    base = f"http://{host}:{port}/exec"
    url = f"{base}?{urllib.parse.urlencode({'query': sql})}"
    with urllib.request.urlopen(url) as resp:
        resp.read()


def parse_decisions(rows: List[list], columns: List[dict]) -> List[Decision]:
    names = [c.get("name") for c in columns]
    decisions = []
    for row in rows:
        row_map = {names[i]: row[i] for i in range(len(names))}
        decisions.append(
            Decision(
                match_id=row_map.get("match_id"),
                selection=row_map.get("selection"),
                market=row_map.get("market"),
                odds_price=row_map.get("odds_price"),
                can_bet=bool(row_map.get("can_bet")),
                reason=row_map.get("reason"),
                timestamp=row_map.get("timestamp"),
            )
        )
    return decisions


def load_decisions(host: str, port: int, last_ts: Optional[str]) -> List[Decision]:
    where = "" if not last_ts else f"WHERE timestamp > '{last_ts}'"
    sql = (
        "SELECT timestamp, match_id, selection, market, odds_price, can_bet, reason "
        "FROM decisions "
        f"{where} ORDER BY timestamp ASC LIMIT 1000"
    )
    raw = query_questdb(host, port, sql)
    dataset = raw.get("dataset", [])
    columns = raw.get("columns", [])
    return parse_decisions(dataset, columns)


def should_execute(decision: Decision, config: dict) -> bool:
    if not decision.can_bet:
        return False
    if decision.odds_price is None:
        return False
    return True


def risk_limits_ok(decision: Decision, config: dict) -> bool:
    risk = config.get("risk", {})
    min_edge = risk.get("min_edge", 0.0)
    # Placeholder: real EV/edge check must use model prob; here we only check that odds exist.
    return min_edge >= 0.0


def dry_run_execute(decision: Decision) -> ExecResult:
    return ExecResult(status="DRY_RUN", reason="dry_run")


def sql_escape(value: Optional[str]) -> str:
    if value is None:
        return "NULL"
    return "'" + value.replace("'", "''") + "'"


def insert_execution(host: str, port: int, decision: Decision, result: ExecResult) -> None:
    sql = (
        "INSERT INTO executions (timestamp, match_id, market, selection, odds_price, status, reason) "
        "VALUES ("
        f"{sql_escape(decision.timestamp)},"
        f"{sql_escape(decision.match_id)},"
        f"{sql_escape(decision.market)},"
        f"{sql_escape(decision.selection)},"
        f"{decision.odds_price or 'NULL'},"
        f"{sql_escape(result.status)},"
        f"{sql_escape(result.reason)}"
        ")"
    )
    exec_questdb(host, port, sql)


def main():
    config = load_config(os.getenv("EXEC_CONFIG", "execution/config.yaml"))
    qdb = config.get("questdb", {})
    poll = config.get("poll", {})
    mode = config.get("mode", "dry_run")

    last_ts = None

    adapter = None
    if mode == "betfair":
        bf = config.get("betfair", {})
        adapter = BetfairAdapter(
            app_key=bf.get("app_key", ""),
            username=bf.get("username", ""),
            password=bf.get("password", ""),
            cert_path=bf.get("cert_path", ""),
            key_path=bf.get("key_path", ""),
        )
        adapter.login()

    while True:
        decisions = load_decisions(qdb.get("host", "localhost"), qdb.get("port", 9000), last_ts)
        for d in decisions:
            last_ts = d.timestamp
            if not should_execute(d, config):
                continue
            if not risk_limits_ok(d, config):
                continue
            if mode == "betfair" and adapter:
                # TODO: market mapping required
                result = adapter.place_order("MARKET_ID", "SELECTION_ID", d.odds_price, config["risk"]["stake"])
            else:
                result = dry_run_execute(d)

            log_line = {
                "timestamp": d.timestamp,
                "match_id": d.match_id,
                "market": d.market,
                "selection": d.selection,
                "odds_price": d.odds_price,
                "status": result.status,
                "reason": result.reason,
            }
            with open("execution_log.jsonl", "a") as f:
                f.write(json.dumps(log_line) + "\n")

            if qdb.get("log_to_questdb", False):
                try:
                    insert_execution(qdb.get("host", "localhost"), qdb.get("port", 9000), d, result)
                except Exception:
                    pass

        time.sleep(poll.get("interval_seconds", 2))


if __name__ == "__main__":
    main()
