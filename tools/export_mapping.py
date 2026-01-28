import csv
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Optional


TABLE_COLUMNS = {
    "match_map": ["provider", "provider_match_id", "match_id", "kickoff", "home", "away", "seen"],
    "team_map": ["provider", "provider_team_id", "team_name", "team_canonical"],
    "market_map": ["provider", "provider_market_id", "market", "selection", "line"],
}


def query_qdb(host: str, port: int, sql: str) -> dict:
    base = f"http://{host}:{port}/exec"
    url = f"{base}?{urllib.parse.urlencode({'query': sql})}"
    with urllib.request.urlopen(url) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if "error" in data:
        raise RuntimeError(data["error"])
    return data


def kickoff_to_iso(value) -> str:
    if value is None or value == "":
        return ""
    try:
        ms = int(value)
        dt = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")
    except Exception:
        return str(value)


def export_table(table: str, path: str, host: str, port: int, limit: Optional[int]) -> None:
    if table not in TABLE_COLUMNS:
        raise SystemExit(f"Unknown table: {table}")

    cols = TABLE_COLUMNS[table]
    limit_sql = "" if not limit else f" LIMIT {limit}"
    sql = f"SELECT {', '.join(cols)} FROM {table}{limit_sql}"
    data = query_qdb(host, port, sql)

    names = [c.get("name") for c in data.get("columns", [])]
    rows = data.get("dataset", [])

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(cols)
        for row in rows:
            row_map = {names[i]: row[i] for i in range(len(names))}
            out = []
            for col in cols:
                value = row_map.get(col)
                if table == "match_map" and col == "kickoff":
                    out.append(kickoff_to_iso(value))
                else:
                    out.append("" if value is None else str(value))
            writer.writerow(out)


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: python3 tools/export_mapping.py <table> <csv_path> [--limit N]")
        return 1

    table = sys.argv[1]
    path = sys.argv[2]
    limit = None
    if "--limit" in sys.argv:
        idx = sys.argv.index("--limit")
        if idx + 1 < len(sys.argv):
            try:
                limit = int(sys.argv[idx + 1])
            except ValueError:
                return 1

    host = os.getenv("QDB_HOST", "localhost")
    port = int(os.getenv("QDB_PORT", "9000"))

    export_table(table, path, host, port, limit)
    print(f"Exported {table} to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
