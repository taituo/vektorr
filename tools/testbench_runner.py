import json
import logging
import random
import yaml
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import asdict

from engine import BettingEngine
from schemas import MatchState, Event, Odds
from tools.generators.event_generator import EventGenerator
from tools.generators.odds_generator import OddsGenerator
from tools.generators.mock_broker import MockBroker
from tools.generators.team_profiles import TEAM_PROFILES
from tools.generators.chaos_injector import ChaosInjector

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TestbenchRunner:
    def __init__(self, config_path: str = "config.yaml"):
        try:
            with open(config_path, "r") as f:
                self.config = yaml.safe_load(f)
        except:
            self.config = {
                'L_MAX': 3.0,
                'XG_10M_MIN': 0.2,
                'EV_MIN': 0.05,
                'MAX_BETS_PER_MATCH': 1
            }
        
        self.engine = BettingEngine(self.config)
        self.broker = MockBroker(self.config)
        self.chaos = ChaosInjector()
        self.audit_logs = []

    def run_match(self, match_id: str, home_team: str, away_team: str, inject_chaos: bool = False) -> Dict[str, Any]:
        home_profile = TEAM_PROFILES.get(home_team, TEAM_PROFILES['Generic Mid'])
        away_profile = TEAM_PROFILES.get(away_team, TEAM_PROFILES['Generic Mid'])
        
        start_time = datetime.now()
        
        # 1. Generate full data
        e_gen = EventGenerator(
            match_id=match_id, 
            home_strength=home_profile['strength'],
            away_strength=away_profile['strength'],
            match_tempo=home_profile['tempo'],
            start_time=start_time
        )
        all_events = e_gen.generate_match()

        if inject_chaos:
            chaos_type = random.choice(['late_drama', 'red_card', 'var'])
            if chaos_type == 'late_drama':
                all_events = self.chaos.inject_late_drama(all_events)
            elif chaos_type == 'red_card':
                all_events = self.chaos.inject_red_card_chaos(all_events)
            elif chaos_type == 'var':
                all_events = self.chaos.inject_var_drama(all_events)
        
        # Value injection creates occasional mispricing opportunities for testing
        o_gen = OddsGenerator(match_id=match_id, value_injection_rate=0.02)
        all_odds = o_gen.generate_odds_stream(all_events, start_time)
        
        # 2. Simulation Loop
        bets_in_match = 0
        max_bets = self.config.get('MAX_BETS_PER_MATCH', 1)
        match_pnl = 0.0
        trades = []
        
        for minute in range(1, 91):
            now = start_time + timedelta(minutes=minute)
            events_so_far = [e for e in all_events if e.t_recv <= now]
            window_start = now - timedelta(minutes=10)
            events_window = [e for e in events_so_far if e.t_event >= window_start]
            
            # Filter for OVER_2.5 odds only (our target market)
            odds_at_min = [o for o in all_odds if o.t_recv <= now and o.selection == 'OVER_2.5']
            if not odds_at_min:
                continue
            latest_odds = odds_at_min[-1]
            
            self.broker.update_market_state(
                is_suspended=latest_odds.is_suspended,
                volatility=1.0
            )
            
            tps = self.engine.calculate_tps(events_window)
            event_latencies = [(e.t_recv - e.t_event).total_seconds() for e in events_window]
            p95 = float(np.percentile(event_latencies, 95)) if event_latencies else 0.0
            odds_latency = (latest_odds.t_recv - latest_odds.t_seen).total_seconds()

            home_goals = self._count_active_goals([e for e in events_so_far if e.team == 'HOME'], events_so_far)
            away_goals = self._count_active_goals([e for e in events_so_far if e.team == 'AWAY'], events_so_far)
            
            state = MatchState(
                match_id=match_id,
                minute=minute,
                score=f"{home_goals}-{away_goals}",
                tps_label=tps,
                t_event_latest=events_window[-1].t_event if events_window else now,
                t_recv_latest=now,
                event_latency_p95=p95,
                odds_latency_p95=odds_latency
            )
            
            if bets_in_match < max_bets:
                can_bet, reason, p_model, ev = self.engine.evaluate_gates(state, latest_odds, events_window)
                
                self.audit_logs.append({
                    "match_id": match_id,
                    "minute": minute,
                    "can_bet": can_bet,
                    "reason": reason,
                    "tps": tps,
                    "price": latest_odds.price,
                    "p_model": p_model,
                    "ev": ev
                })

                if can_bet:
                    fill_result = self.broker.place_order(
                        match_id=match_id,
                        minute=minute,
                        selection=latest_odds.selection,
                        price_seen=latest_odds.price,
                        stake=10.0
                    )
                    if fill_result.filled:
                        bets_in_match += 1
                        trades.append(fill_result)

        # 3. Settlement
        final_home_goals = self._count_active_goals([e for e in all_events if e.type == 'GOAL' and e.team == 'HOME'], all_events)
        final_away_goals = self._count_active_goals([e for e in all_events if e.type == 'GOAL' and e.team == 'AWAY'], all_events)
        total_goals = final_home_goals + final_away_goals
        
        for trade in trades:
            won = total_goals >= 3
            if won:
                trade.outcome = "WIN"
                trade.pnl = trade.stake * (trade.price_filled - 1)
            else:
                trade.outcome = "LOSS"
                trade.pnl = -trade.stake
            match_pnl += trade.pnl

        return {
            "match_id": match_id,
            "score": f"{final_home_goals}-{final_away_goals}",
            "pnl": match_pnl,
            "trades_count": len(trades),
            "trades": [asdict(t) for t in trades]
        }

    def _count_active_goals(self, goals: List[Event], all_events: List[Event]) -> int:
        overturned_minutes = [e.data.get('minute') for e in all_events if e.type == 'VAR' and e.data.get('status') == 'OVERTURNED']
        active_goals = 0
        for g in goals:
            if g.type == 'GOAL' and g.data.get('minute') not in overturned_minutes:
                active_goals += 1
        return active_goals

def run_simulation(n_matches: int = 10, chaos_pct: float = 0.2):
    runner = TestbenchRunner()
    teams = list(TEAM_PROFILES.keys())
    results = []
    total_pnl = 0.0
    
    logger.info(f"Starting simulation of {n_matches} matches (Chaos: {chaos_pct*100}%)...")
    
    for i in range(n_matches):
        home = random.choice(teams)
        away = random.choice(teams)
        match_id = f"sim_{i:04d}"
        inject_chaos = random.random() < chaos_pct
        res = runner.run_match(match_id, home, away, inject_chaos=inject_chaos)
        results.append(res)
        total_pnl += res['pnl']
        
        if i % 10 == 0 and i > 0:
            logger.info(f"Progress: {i}/{n_matches} | Current P&L: {total_pnl:+.2f}")
            
    all_trades = [t for r in results for t in r['trades']]
    win_rate = 0
    if all_trades:
        wins = len([t for t in all_trades if t['outcome'] == 'WIN'])
        losses = len([t for t in all_trades if t['outcome'] == 'LOSS'])
        win_rate = wins / (wins + losses) if (wins+losses) > 0 else 0
    
    with open("results/simulation_latest.json", "w") as f:
        json.dump({
            "summary": {
                "total_matches": n_matches,
                "total_pnl": total_pnl,
                "win_rate": win_rate
            },
            "results": results,
            "audit_logs": runner.audit_logs
        }, f, indent=2, default=str)
    
    logger.info(f"SIMULATION COMPLETE. P&L: {total_pnl:+.2f}")
    return results

if __name__ == "__main__":
    import os
    if not os.path.exists("results"):
        os.makedirs("results")
    run_simulation(100, chaos_pct=0.2)