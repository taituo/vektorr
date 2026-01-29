import json
import random
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any
from schemas import Event, Odds

class HistoricalRemixer:
    """
    Mutates historical match data to create new synthetic scenarios.
    """
    
    def __init__(self, source_path: str):
        self.source_path = source_path
        self.raw_data = self._load_data()
        
    def _load_data(self) -> List[Dict[str, Any]]:
        data = []
        with open(self.source_path, 'r') as f:
            for line in f:
                data.append(json.loads(line))
        return data

    def remix_match(self, match_id: str, new_match_id: str = None) -> List[Dict[str, Any]]:
        """Extracts a match and applies random mutations."""
        match_events = [d for d in self.raw_data if d.get('match_id') == match_id]
        if not match_events:
            return []
            
        new_match_id = new_match_id or f"remix-{str(uuid.uuid4())[:8]}"
        mutated_data = []
        
        # Determine time shift
        time_shift = timedelta(minutes=random.randint(-1440, 1440))
        
        # Determine mutations
        swap_teams = random.random() < 0.5
        
        for item in match_events:
            new_item = item.copy()
            new_item['match_id'] = new_match_id
            
            # Shift timestamps
            for ts_field in ['t_event', 't_recv', 't_seen']:
                if ts_field in new_item:
                    ts = datetime.fromisoformat(new_item[ts_field].replace('Z', '+00:00'))
                    new_item[ts_field] = (ts + time_shift).isoformat()
            
            # Swap teams if requested (simplified)
            if swap_teams and 'team' in new_item and new_item['team']:
                # This is a bit tricky without knowing all team names, 
                # but we can just tag them as HOME/AWAY if they were real names
                pass 
                
            # Add some noise to odds
            if new_item.get('kind') == 'odds':
                noise = 1.0 + (random.random() - 0.5) * 0.02 # ±1% noise
                new_item['price'] = round(new_item['price'] * noise, 2)
            
            mutated_data.append(new_item)
            
        return mutated_data

    def get_match_ids(self) -> List[str]:
        return list(set(d['match_id'] for d in self.raw_data))

if __name__ == "__main__":
    # Quick test
    remixer = HistoricalRemixer("data/capture_test.jsonl")
    ids = remixer.get_match_ids()
    if ids:
        remixed = remixer.remix_match(ids[0])
        print(f"Remixed match {ids[0]} -> {remixed[0]['match_id']}")
        print(f"Items: {len(remixed)}")
