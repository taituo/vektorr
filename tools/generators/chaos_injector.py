import random
from datetime import timedelta
from typing import List
from schemas import Event

class ChaosInjector:
    """
    Injects rare and difficult scenarios into match events.
    """
    
    def __init__(self, chaos_level: str = 'medium'):
        self.chaos_level = chaos_level

    def inject_late_drama(self, events: List[Event], num_goals: int = 1) -> List[Event]:
        """Adds goals in the final minutes of the match."""
        if not events:
            return events
            
        match_id = events[0].match_id
        last_event_time = max(e.t_event for e in events)
        
        for i in range(num_goals):
            minute = random.randint(88, 95)
            t_event = last_event_time + timedelta(minutes=i+1)
            team = random.choice(['HOME', 'AWAY'])
            
            events.append(Event(
                match_id=match_id,
                t_event=t_event,
                t_recv=t_event + timedelta(seconds=random.uniform(1, 4)),
                type='GOAL',
                team=team,
                xg=0.8,
                data={'minute': minute, 'drama': True}
            ))
        return events

    def inject_red_card_chaos(self, events: List[Event]) -> List[Event]:
        """Injects multiple red cards."""
        if not events:
            return events
            
        match_id = events[0].match_id
        for _ in range(random.randint(2, 4)):
            minute = random.randint(10, 80)
            t_event = events[0].t_event + timedelta(minutes=minute)
            team = random.choice(['HOME', 'AWAY'])
            
            events.append(Event(
                match_id=match_id,
                t_event=t_event,
                t_recv=t_event + timedelta(seconds=random.uniform(5, 10)),
                type='RED_CARD',
                team=team,
                data={'minute': minute, 'chaos': True}
            ))
        return events

    def inject_var_drama(self, events: List[Event]) -> List[Event]:
        """Simulates a VAR overturned goal."""
        if not events:
            return events
            
        match_id = events[0].match_id
        minute = random.randint(20, 70)
        t_event = events[0].t_event + timedelta(minutes=minute)
        
        # 1. The "Goal"
        events.append(Event(
            match_id=match_id,
            t_event=t_event,
            t_recv=t_event + timedelta(seconds=2),
            type='GOAL',
            team='HOME',
            data={'minute': minute}
        ))
        
        # 2. VAR check starts
        events.append(Event(
            match_id=match_id,
            t_event=t_event + timedelta(seconds=10),
            t_recv=t_event + timedelta(seconds=15),
            type='VAR',
            data={'minute': minute, 'status': 'CHECKING'}
        ))
        
        # 3. VAR Overturns
        events.append(Event(
            match_id=match_id,
            t_event=t_event + timedelta(seconds=120),
            t_recv=t_event + timedelta(seconds=125),
            type='VAR',
            data={'minute': minute, 'status': 'OVERTURNED', 'original_type': 'GOAL'}
        ))
        
        return events
