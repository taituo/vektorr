import json
import logging
import concurrent.futures
from typing import List, Dict, Any
import numpy as np

from tools.testbench_runner import TestbenchRunner, run_simulation

logging.basicConfig(level=logging.ERROR) # Quiet down logs for sweep

def run_single_config(ev_min: float, xg_min: float) -> Dict[str, Any]:
    # Create a custom config for this run
    config = {
        'L_MAX': 3.0,
        'XG_10M_MIN': xg_min,
        'EV_MIN': ev_min,
        'ODDS_MAX': 6.0,
        'MAX_BETS_PER_MATCH': 1
    }
    
    # Run 50 matches for this config
    # We use a custom runner instance to pass the config
    from tools.testbench_runner import TestbenchRunner, TEAM_PROFILES
    import random
    
    runner = TestbenchRunner()
    runner.config = config
    runner.engine.config = config # Update engine config too
    
    teams = list(TEAM_PROFILES.keys())
    results = []
    total_pnl = 0.0
    all_trades = []
    
    for i in range(50):
        home = random.choice(teams)
        away = random.choice(teams)
        res = runner.run_match(f"sweep_{i}", home, away, inject_chaos=True)
        results.append(res)
        total_pnl += res['pnl']
        all_trades.extend(res['trades'])
        
    wins = len([t for t in all_trades if t['outcome'] == 'WIN'])
    losses = len([t for t in all_trades if t['outcome'] == 'LOSS'])
    win_rate = wins / (wins + losses) if (wins + losses) > 0 else 0
    
    return {
        "ev_min": ev_min,
        "xg_min": xg_min,
        "total_pnl": total_pnl,
        "trades_count": len(all_trades),
        "win_rate": win_rate,
        "roi": (total_pnl / (len(all_trades) * 10)) if all_trades else 0
    }

def main():
    ev_values = [0.02, 0.05, 0.10, 0.15]
    xg_values = [0.1, 0.2, 0.3, 0.4]
    
    print(f"Starting parameter sweep: {len(ev_values) * len(xg_values)} combinations...")
    
    all_results = []
    
    with concurrent.futures.ProcessPoolExecutor() as executor:
        futures = []
        for ev in ev_values:
            for xg in xg_values:
                futures.append(executor.submit(run_single_config, ev, xg))
        
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            all_results.append(res)
            print(f"Done: EV_MIN={res['ev_min']:.2f}, XG_MIN={res['xg_min']:.2f} -> P&L: {res['total_pnl']:+8.2f}, ROI: {res['roi']*100:5.1f}%")

    # Sort and show top 5
    all_results.sort(key=lambda x: x['total_pnl'], reverse=True)
    
    print("\n" + "="*70)
    print(f"{ 'EV_MIN':<8} {'XG_MIN':<8} {'TRADES':<8} {'WIN%':<8} {'P&L':<10} {'ROI%':<8}")
    print("-" * 70)
    for r in all_results:
        print(f"{r['ev_min']:<8.2f} {r['xg_min']:<8.2f} {r['trades_count']:<8} {r['win_rate']*100:<8.1f} {r['total_pnl']:<10.2f} {r['roi']*100:<8.1f}")
    print("="*70)

if __name__ == "__main__":
    main()
