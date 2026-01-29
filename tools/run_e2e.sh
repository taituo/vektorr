#!/usr/bin/env bash
# E2E test runner: starts QuestDB, mock server, brain, and spine.
# Usage: bash tools/run_e2e.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PIDS=()

cleanup() {
  echo "Stopping all processes..."
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null
}
trap cleanup EXIT

# 1. QuestDB
echo "==> Starting QuestDB..."
(cd "$ROOT/infra/questdb" && docker compose up -d)

# Wait for QuestDB HTTP API
for i in $(seq 1 30); do
  if curl -sf http://localhost:9000/exec?query=SELECT+1 >/dev/null 2>&1; then
    echo "    QuestDB ready"
    break
  fi
  sleep 1
done

# 2. Mock server
echo "==> Starting mock server on :9999..."
python3 "$ROOT/tools/mock_server.py" --port 9999 --matches 3 --speed 2 --tempo normal --chaos 0.0 --seed 42 &
PIDS+=($!)
sleep 1

# 3. Brain
echo "==> Starting brain on :8090..."
(cd "$ROOT/brain" && uvicorn service:app --port 8090) &
PIDS+=($!)
sleep 2

# 4. Spine
echo "==> Starting spine..."
(cd "$ROOT/spine" && cargo run -- \
  --events-url http://localhost:9999/events \
  --odds-url http://localhost:9999/odds \
  --brain-url http://localhost:8090 \
  --qdb-host localhost) &
PIDS+=($!)

echo "==> E2E pipeline running. Press Ctrl+C to stop."
wait
