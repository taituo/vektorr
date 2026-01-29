
import json
import time
from datetime import datetime
from orchestrator import Orchestrator, OrchestratorConfig, Stage

def run_simulation(events_path, odds_path):
    config = OrchestratorConfig(stage=Stage.PAPER)
    orch = Orchestrator(config)
    orch.start()

    with open(events_path) as fe, open(odds_path) as fo:
        events_lines = fe.readlines()
        odds_lines = fo.readlines()

    print(f"Starting simulation with {len(events_lines)} events and {len(odds_lines)} odds.")
    print("Watching for signals... (Press Ctrl+C to stop)")
    
    # Simple simulation: just process chunks
    for i in range(0, min(len(events_lines), len(odds_lines)), 5):
        event_chunk = [json.loads(l) for l in events_lines[i:i+5]]
        odds_chunk = json.loads(odds_lines[i]) # Just take one odds update
        
        match_state = {
            "match_id": event_chunk[0].get("match_id", "sim_match"),
            "minute": i // 5, # Simple minute proxy
            "score": "0-0",
            "tps_label": "MID",
            "latency": 0.5
        }
        
        decision = orch.process_match(match_state, odds_chunk, event_chunk)
        
        if decision["action"] == "BET":
            print(f"🎯 SIGNAL: {decision['action']} @ {decision['odds']} (EV: {decision['ev']:.2%}, TPS: {decision['tps_label']})")
        elif i % 50 == 0:
            print(f"Minute {match_state['minute']}: {decision['reason']} (TPS: {decision['tps_label']})")
        
        time.sleep(0.5)

    orch.stop()

if __name__ == "__main__":
    run_simulation("events_log.jsonl", "odds_log.jsonl")
