import time
import requests
import subprocess
import os
import signal
import json
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

def run_test():
    # 1. Start Brain API
    print("Starting Brain API...")
    process = subprocess.Popen(
        ["./.venv/bin/python", "brain_api.py"],
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
            resp = requests.get(f"{api_url}/summary")
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
    
    try:
        # Simulate a match minute by minute
        for minute in range(1, 91): 
            events, odds = provider.get_data(minute)
            
            # Send events one by one to simulate real-time feed
            for e in events:
                try:
                    requests.post(f"{api_url}/event", json=json_serializable(e.model_dump()))
                except Exception as err:
                    print(f"Error sending event: {err}")
            
            # Send odds update
            try:
                resp = requests.post(f"{api_url}/odds", json=json_serializable(odds.model_dump()))
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
            # 0.5s per match minute = ~45 seconds for a full half
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\nStopping simulation...")
    finally:
        # Cleanup
        print("Stopping Brain API...")
        os.kill(process.pid, signal.SIGTERM)

if __name__ == "__main__":
    run_test()
