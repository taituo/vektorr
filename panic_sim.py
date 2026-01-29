import json
import time
from datetime import datetime, timedelta
from orchestrator import Orchestrator, OrchestratorConfig, Stage
from brain.engine import BettingEngine
from schemas import MatchState, Odds, Event

def run_panic_simulation():
    # 1. Konfigurointi: Aggressiivisempi EV-raja tähän testiin
    config_dict = {
        'L_MAX': 3.0,
        'EV_MIN': 0.05,        # 5% etu riittää
        'XG_10M_MIN': 0.1,     # Vaaditaan jonkinlaista painetta
        'use_phase2_models': True
    }
    
    engine = BettingEngine(config_dict)
    
    print("=== PANIC SCENARIO: 'The Red Card Overreaction' ===")
    print("Tilanne: Kotijoukkue (suosikki) saa punaisen kortin 60. minuutilla.")
    print("Oletus: Markkina ylireagoi, mutta kotijoukkue jatkaa painostusta.\n")

    # 2. Skenaarion aikajana
    # Luodaan dataa minuutti minuutilta
    match_id = "panic_match_001"
    base_time = datetime.now()
    
    # Kertoimien kehitys
    # Alussa suosikki on vahva (1.80)
    odds_trajectory = [1.80] * 60 
    # Min 60: Punainen kortti -> Kerroin räjähtää 2.80:aan (paniikki)
    odds_trajectory += [2.80] * 5 
    # Min 65->: Markkina tajuaa virheen hitaasti, laskee vähän (2.60)
    odds_trajectory += [2.60] * 25

    # xG-tuotanto (Threat)
    # Tasainen paine koko pelin, ei romahda kortista
    events_buffer = []

    for minute in range(50, 80): # Simuloidaan vain kiinnostava jakso
        current_time = base_time + timedelta(minutes=minute)
        
        # 3. Generoidaan tapahtumia (Data)
        # Joka minuutti joku "tapahtuma", joka ylläpitää xG-painetta
        # Min 60: PUNAINEN KORTTI (mutta paine jatkuu sen jälkeen)
        
        if minute == 60:
            events_buffer.append(Event(
                match_id=match_id, t_event=current_time, t_recv=current_time,
                type="RED_CARD", team="HOME", xg=0.0
            ))
            print(f"⏱️ MIN {minute}: 🟥 RED CARD (HOME)! Market PANICS! Odds: 1.80 -> 2.80")
        
        # Kotijoukkue saa silti laukauksia (tasoitusmaali roikkuu ilmassa)
        if minute % 2 == 0: 
            events_buffer.append(Event(
                match_id=match_id, t_event=current_time, t_recv=current_time,
                type="SHOT", team="HOME", xg=0.12 # Hyvä paikka
            ))
        
        # Pidetään bufferissa vain viimeiset 10min (kuten Engine tekee)
        recent_events = [e for e in events_buffer if (current_time - e.t_event).total_seconds() <= 600]

        # 4. Rakennetaan tila (State)
        tps = engine.calculate_tps(recent_events)
        
        state = MatchState(
            match_id=match_id,
            minute=minute,
            score="0-1", # Suosikki häviöllä, pakko hyökätä
            tps_label=tps,
            t_event_latest=current_time,
            t_recv_latest=current_time,
            event_latency_p95=0.5 # Nopea feed
        )

        current_odds = odds_trajectory[minute]
        odds_obj = Odds(
            match_id=match_id, t_seen=current_time, t_recv=current_time,
            market="NEXT_GOAL", selection="HOME", price=current_odds, is_suspended=False
        )

        # 5. Kysytään Botilta päätös
        can_bet, reason, p_model, ev = engine.evaluate_gates(state, odds_obj, recent_events)
        
        # Tulostetaan tilanne
        status_icon = "🟢" if can_bet else "🔴"
        print(f"MIN {minute}: Odds {current_odds:.2f} | TPS: {tps} | xG_10m: {sum(e.xg for e in recent_events):.2f} | EV: {ev:+.1%} -> {status_icon} {reason}")
        
        if can_bet:
            print(f"   >>> 💰 BOOM! VALUE DETECTED! Lyödään vetoa ylireagointia vastaan!")
            # Simuloidaan veto ja lopetetaan (tai jatketaan)
            # break 

        time.sleep(0.2)

if __name__ == "__main__":
    run_panic_simulation()
