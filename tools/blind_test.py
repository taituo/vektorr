"""
Replay JSONL data into Brain API endpoints (/event, /odds).

Input format: same as tools/testbench_runner.py or tools/backtest.py capture.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import time
import urllib.request
from datetime import datetime
from typing import List, Tuple


def _parse_ts(ts: str) -> float:
    try:
        return datetime.fromisoformat(ts).timestamp()
    except Exception:
        return 0.0


def load_rows(path: str) -> List[dict]:
    rows: List[dict] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))

    def recv_ts(row: dict) -> float:
        return _parse_ts(row.get("t_recv") or row.get("t_seen") or row.get("t_event", ""))

    rows.sort(key=recv_ts)
    return rows


def post_json(url: str, payload: dict, timeout: float = 5.0) -> Tuple[int, dict | None]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            try:
                return resp.status, json.loads(body.decode())
            except Exception:
                return resp.status, None
    except Exception:
        return 0, None


def replay(rows: List[dict], brain_url: str, speed: float) -> List[dict]:
    out: List[dict] = []
    prev_ts = None
    for row in rows:
        kind = row.get("kind")
        if kind not in ("event", "odds"):
            continue

        if speed and speed > 0:
            ts = _parse_ts(row.get("t_recv") or row.get("t_seen") or row.get("t_event", ""))
            if prev_ts is not None and ts > prev_ts:
                time.sleep((ts - prev_ts) / speed)
            prev_ts = ts

        endpoint = "/event" if kind == "event" else "/odds"
        url = brain_url.rstrip("/") + endpoint
        payload = dict(row)
        payload.pop("kind", None)

        status, resp = post_json(url, payload)
        out.append(
            {
                "kind": kind,
                "status": status,
                "request": payload,
                "response": resp,
            }
        )
    return out


def summarize(responses: List[dict]) -> dict:
    total = len(responses)
    ok = sum(1 for r in responses if r["status"] == 200)
    reasons = {}
    for r in responses:
        resp = r.get("response") or {}
        reason = resp.get("reason")
        if reason:
            reasons[reason] = reasons.get(reason, 0) + 1
    return {"total": total, "ok": ok, "reasons": reasons}


def main() -> None:
    parser = argparse.ArgumentParser(description="Blind test replay into Brain API")
    parser.add_argument("--data", required=True, help="Path to JSONL data")
    parser.add_argument("--brain-url", default="http://localhost:8090")
    parser.add_argument("--out", default="results/blind_test.json")
    parser.add_argument("--speed", type=float, default=0.0, help="Replay speed (1=real-time, 0=no sleep)")
    parser.add_argument("--only-odds", action="store_true", help="Only post odds ticks (skip events)")
    parser.add_argument("--only-events", action="store_true", help="Only post event ticks (skip odds)")
    parser.add_argument("--bets-out", default=None, help="Write BET_READY decisions to JSONL")
    parser.add_argument("--requests-out", default=None, help="Write request payloads to JSONL")
    parser.add_argument("--reasons", default=None, help="Filter responses by reason list (comma-separated)")
    parser.add_argument("--sample-every", type=int, default=1, help="Only replay every Nth row")
    parser.add_argument("--sample-random", type=float, default=0.0, help="Random sample ratio (0-1)")
    parser.add_argument("--sample-seed", type=int, default=None, help="Random seed for sampling")
    parser.add_argument("--summary-out", default=None, help="Write summary JSON only")
    parser.add_argument("--dry-run", action="store_true", help="Skip POSTs and only summarize input")
    parser.add_argument("--max-rows", type=int, default=None, help="Stop after N rows")
    args = parser.parse_args()

    rows = load_rows(args.data)
    if args.only_events:
        rows = [r for r in rows if r.get("kind") == "event"]
    elif args.only_odds:
        rows = [r for r in rows if r.get("kind") == "odds"]
    if args.sample_every and args.sample_every > 1:
        rows = rows[:: args.sample_every]
    if args.sample_random and args.sample_random > 0:
        rng = random.Random(args.sample_seed)
        rows = [r for r in rows if rng.random() < args.sample_random]
    if args.max_rows and args.max_rows > 0:
        rows = rows[: args.max_rows]
    if args.dry_run:
        responses = [
            {
                "kind": r.get("kind"),
                "status": 0,
                "request": r,
                "response": None,
            }
            for r in rows
        ]
    else:
        responses = replay(rows, args.brain_url, args.speed)
    if args.reasons:
        reasons = {r.strip() for r in args.reasons.split(",") if r.strip()}
        responses = [r for r in responses if (r.get("response") or {}).get("reason") in reasons]
    summary = summarize(responses)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump({"summary": summary, "responses": responses}, f, indent=2)

    print(f"Wrote {len(responses)} responses → {args.out}")
    print(f"Summary: {summary}")

    if args.summary_out:
        os.makedirs(os.path.dirname(args.summary_out) or ".", exist_ok=True)
        with open(args.summary_out, "w") as f:
            json.dump(summary, f, indent=2)
        print(f"Wrote summary → {args.summary_out}")

    if args.bets_out:
        os.makedirs(os.path.dirname(args.bets_out) or ".", exist_ok=True)
        n_written = 0
        with open(args.bets_out, "w") as f:
            for r in responses:
                resp = r.get("response") or {}
                if resp.get("reason") != "BET_READY":
                    continue
                row = {
                    "kind": r.get("kind"),
                    "status": r.get("status"),
                    "request": r.get("request"),
                    "response": resp,
                }
                f.write(json.dumps(row) + "\n")
                n_written += 1
        print(f"Wrote {n_written} BET_READY rows → {args.bets_out}")

    if args.requests_out:
        os.makedirs(os.path.dirname(args.requests_out) or ".", exist_ok=True)
        n_written = 0
        with open(args.requests_out, "w") as f:
            for r in responses:
                req = r.get("request")
                if not req:
                    continue
                f.write(json.dumps(req) + "\n")
                n_written += 1
        print(f"Wrote {n_written} request rows → {args.requests_out}")


if __name__ == "__main__":
    main()
