import csv
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone


def exec_qdb(host: str, port: int, sql: str) -> None:
    base = f"http://{host}:{port}/exec"
    url = f"{base}?{urllib.parse.urlencode({'query': sql})}"
    with urllib.request.urlopen(url) as resp:
        resp.read()


def sql_escape(value: str) -> str:
    if value is None or value == "":
        return "NULL"
    return "'" + value.replace("'", "''") + "'"


def kickoff_to_ms(value: str) -> str:
    if value is None or value == "":
        return "NULL"
    v = value.strip()
    if v.isdigit():
        return v
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        return str(int(dt.timestamp() * 1000))
    except Exception:
        return sql_escape(v)


def sql_value(table: str, key: str, value: str) -> str:
    if table == "match_map" and key == "kickoff":
        return kickoff_to_ms(value)
    return sql_escape(value)


def load_csv(table: str, path: str, host: str, port: int) -> None:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cols = []
            vals = []
            for k, v in row.items():
                cols.append(k)
                vals.append(sql_value(table, k, v))
            cols.append("timestamp")
            vals.append("now()")
            sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join(vals)})"
            exec_qdb(host, port, sql)


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: python3 tools/load_mapping.py <table> <csv_path>")
        return 1

    table = sys.argv[1]
    path = sys.argv[2]
    host = os.getenv("QDB_HOST", "localhost")
    port = int(os.getenv("QDB_PORT", "9000"))

    load_csv(table, path, host, port)
    print(f"Loaded {path} into {table}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
