import time
import requests
import subprocess
import os
import signal
from mock_provider import MockProvider

def run_test():
    # 1. Start Brain API
    print("Starting Brain API...")
    process = subprocess.Popen(
        ["./.venv/bin/python", "brain_api_legacy.py"],
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
        process.terminate()
        return

    print("API Ready. Starting simulation...")
    
    match_id = "integration_test_001"
    provider = MockProvider(match_id=match_id)
    
    for minute in range(1, 46): # 45 minutes simulation
        events, odds = provider.get_data(minute)
        
        # Send events one by one
        for e in events:
            requests.post(f"{api_url}/event", json=json_serializable(e.model_dump()))
            
        # Send odds
        resp = requests.post(f"{api_url}/odds", json=json_serializable(odds.model_dump()))
        decision = resp.json()
        
        if decision.get("can_bet"):
            print(f"MIN {minute:2d} | BET SIGNAL: {decision['reason']} | Status: {decision['exec_status']} | Price: {decision['price_filled']}")

    # Get final summary
    resp = requests.get(f"{api_url}/summary")
    summary = resp.json()
    print("\n" + "="*50)
    print("INTEGRATION TEST SUMMARY")
    print(f"  Balance: {summary['balance']}")
    print(f"  Trades: {summary['total_trades']}")
    print(f"  P&L: {summary['total_pnl']}")
    print("="*50)

    # Cleanup
    print("Stopping Brain API...")
    os.kill(process.pid, signal.SIGTERM)

def json_serializable(d):
    """Convert datetime objects to ISO strings for JSON."""
    from datetime import datetime
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d

if __name__ == "__main__":
    run_test()
