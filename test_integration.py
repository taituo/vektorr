import time
import requests
import subprocess
import os
import signal
import json
import sys
from pathlib import Path
from mock_provider import MockProvider

def json_serializable(d):
    """Convert datetime objects to ISO strings for JSON."""
    from datetime import datetime
    new_d = {}
    for k, v in d.items():
        if isinstance(v, datetime):
            new_d[k] = v.isoformat()
        else:
            new_d[k] = v
    return new_d

def resolve_python():
    venv_python = Path(__file__).resolve().parent / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable

def load_runtime_config():
    fast = os.getenv("FAST", "").lower() in {"1", "true", "yes"}
    sim_minutes = int(os.getenv("SIM_MINUTES", "15" if fast else "90"))
    sleep_seconds = float(os.getenv("SLEEP_SECONDS", "0.05" if fast else "0.5"))
    request_timeout = float(os.getenv("REQUEST_TIMEOUT", "2.0"))
    return sim_minutes, sleep_seconds, request_timeout

def run_test():
    sim_minutes, sleep_seconds, request_timeout = load_runtime_config()
    # 1. Start Brain API
    print("Starting Brain API...")
    process = subprocess.Popen(
        [resolve_python(), "brain_api.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # Wait for API to be ready
    api_url = "http://localhost:8090"
    max_retries = 10
    ready = False
    for _ in range(max_retries):
        try:
            resp = requests.get(f"{api_url}/summary", timeout=request_timeout)
            if resp.status_code == 200:
                ready = True
                break
        except:
            pass
        time.sleep(1)
        print("Waiting for API...")
    
    if not ready:
        print("API failed to start")
        # Print stderr to see what went wrong
        _, stderr = process.communicate()
        print(stderr)
        process.terminate()
        return

    print("API Ready. Starting simulation...")
    print("Open another terminal and run: ./.venv/bin/python monitor.py")
    print("Press Ctrl+C to stop simulation.")
    
    match_id = "live_sim_001"
    provider = MockProvider(match_id=match_id)
    print(f"Simulation config: minutes={sim_minutes} sleep={sleep_seconds}s timeout={request_timeout}s")
    
    try:
        # Simulate a match minute by minute
        for minute in range(1, sim_minutes + 1): 
            events, odds = provider.get_data(minute)
            
            # Send events one by one to simulate real-time feed
            for e in events:
                try:
                    requests.post(
                        f"{api_url}/event",
                        json=json_serializable(e.model_dump()),
                        timeout=request_timeout,
                    )
                except Exception as err:
                    print(f"Error sending event: {err}")
            
            # Send odds update
            try:
                resp = requests.post(
                    f"{api_url}/odds",
                    json=json_serializable(odds.model_dump()),
                    timeout=request_timeout,
                )
                if resp.status_code == 200:
                    decision = resp.json()
                    if decision.get("can_bet"):
                        print(f"🎯 BET PLACED at Min {minute}")
                    else:
                        # Print a dot to show aliveness without spamming
                        print(".", end="", flush=True)
            except Exception as err:
                print(f"Error sending odds: {err}")
            
            # Sleep to make the simulation watchable in the TUI
            # Default: 0.5s per match minute (~45s for a full match); override via SLEEP_SECONDS
            time.sleep(sleep_seconds)

    except KeyboardInterrupt:
        print("\nStopping simulation...")
    finally:
        # Cleanup
        print("Stopping Brain API...")
        os.kill(process.pid, signal.SIGTERM)

if __name__ == "__main__":
    run_test()
