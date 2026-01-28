import os
import time
import urllib.parse
import urllib.request


def main() -> int:
    host = os.getenv("QDB_HOST", "localhost")
    port = os.getenv("QDB_PORT", "9000")
    sql_path = os.getenv("QDB_SCHEMA", os.path.join(os.path.dirname(__file__), "schema.sql"))
    wait_s = int(os.getenv("QDB_WAIT_TIMEOUT", "60"))

    base = f"http://{host}:{port}/exec"

    deadline = time.time() + wait_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base}?query=select%201", timeout=2) as resp:
                resp.read()
            break
        except Exception:
            time.sleep(1)
    else:
        raise SystemExit("QuestDB not ready within timeout")

    with open(sql_path, "r", encoding="utf-8") as f:
        sql = f.read()

    statements = [s.strip() for s in sql.split(";") if s.strip()]
    for stmt in statements:
        query = urllib.parse.urlencode({"query": stmt})
        url = f"{base}?{query}"
        with urllib.request.urlopen(url) as resp:
            resp.read()

    print(f"Applied {len(statements)} statements from {sql_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
