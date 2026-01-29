import json
from collections import Counter
from typing import Dict, Any

def analyze(file_path: str):
    with open(file_path, 'r') as f:
        data = json.load(f)
    
    summary = data.get('summary', {})
    audit_logs = data.get('audit_logs', [])
    results = data.get('results', [])
    
    print("=" * 60)
    print(f"TESTBENCH ANALYSIS: {file_path}")
    print("=" * 60)
    print(f"Total Matches:  {summary.get('total_matches')}")
    print(f"Total P&L:      {summary.get('total_pnl'):+.2f}")
    print(f"Win Rate:       {summary.get('win_rate', 0)*100:.1f}%")
    
    # 1. Gate Statistics
    reasons = [log['reason'] for log in audit_logs if not log['can_bet']]
    reason_counts = Counter(reasons)
    total_rejected = sum(reason_counts.values())
    
    print("\nGATE REJECTION STATISTICS:")
    for reason, count in reason_counts.most_common():
        pct = (count / total_rejected) * 100 if total_rejected > 0 else 0
        print(f"  {reason:20}: {count:5} ({pct:5.1f}%)")
    
    # 2. Success by TPS Label
    success_by_tps = {}
    all_trades = [t for r in results for t in r['trades']]
    
    # We need to map trades back to audit logs to find TPS at time of trade
    # (Simplified: find TPS in audit logs for successful bets)
    bet_logs = [log for log in audit_logs if log['can_bet']]
    
    tps_outcomes = Counter([(log['match_id'], log['minute']) for log in bet_logs])
    
    # This is slightly complex to do perfectly without better indexing, 
    # but let's look at average price vs outcome
    if all_trades:
        avg_price = sum(t['price_filled'] for t in all_trades) / len(all_trades)
        print(f"\nTRADE METRICS:")
        print(f"  Total Trades:   {len(all_trades)}")
        print(f"  Avg Fill Price: {avg_price:.3f}")
        
    print("=" * 60)

if __name__ == "__main__":
    analyze("results/simulation_latest.json")
