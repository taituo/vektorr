"""
Universal Data Converter - Auto-detects and converts from any supported provider.

Supports:
- SportMonks (events + odds)
- The Odds API (odds)
- BetsAPI (events + odds)
- CSV files (events + odds)
"""
from typing import Dict, Any, List, Optional, Union
from datetime import datetime

from tools.converters.base_converters import (
    BaseConverter,
    SportMonksConverter,
    TheOddsApiConverter,
    BetsApiConverter,
    CSVConverter,
)
from schemas import Event, Odds


class UniversalConverter:
    """
    Auto-detects source format and routes to the correct converter.

    Usage:
        converter = UniversalConverter()

        # Auto-detect and convert
        result = converter.convert(raw_data)

        # Or specify source explicitly
        result = converter.convert(raw_data, source='sportmonks')
    """

    def __init__(self):
        self.converters: Dict[str, BaseConverter] = {
            'sportmonks': SportMonksConverter(),
            'odds_api': TheOddsApiConverter(),
            'betsapi': BetsApiConverter(),
            'csv': CSVConverter(),
        }

    def detect_source(self, data: Dict[str, Any]) -> Optional[str]:
        """
        Detect data source from structure.

        Returns source name or None if undetectable.
        """
        # SportMonks indicators
        if 'fixture_id' in data:
            return 'sportmonks'
        if 'time' in data and isinstance(data.get('time'), dict):
            if 'starting_at' in data['time']:
                return 'sportmonks'

        # The Odds API indicators
        if 'bookmakers' in data and 'commence_time' in data:
            return 'odds_api'
        if 'sport_key' in data and 'bookmakers' in data:
            return 'odds_api'

        # BetsAPI indicators
        if 'event_id' in data and ('time' in data or 'odds' in data):
            return 'betsapi'
        if 'match_id' in data and 'type' in data and isinstance(data.get('type'), (str, int)):
            return 'betsapi'

        return None

    def convert(
        self,
        data: Dict[str, Any],
        source: str = None,
        data_type: str = 'auto'
    ) -> Union[Event, List[Odds], None]:
        """
        Convert data from any supported source.

        Args:
            data: Raw data dict
            source: Source name (auto-detected if None)
            data_type: 'event', 'odds', or 'auto'

        Returns:
            Event, List[Odds], or None
        """
        if source is None:
            source = self.detect_source(data)

        if not source or source not in self.converters:
            return None

        converter = self.converters[source]

        # Auto-detect data type
        if data_type == 'auto':
            # Check for odds indicators
            if 'bookmakers' in data or 'odds' in data or 'markets' in data:
                data_type = 'odds'
            else:
                data_type = 'event'

        if data_type == 'event':
            return converter.convert_event(data)
        else:
            return converter.convert_odds(data)

    def convert_batch(
        self,
        data_list: List[Dict[str, Any]],
        source: str = None,
        data_type: str = 'auto'
    ) -> Dict[str, List]:
        """
        Convert a batch of data items.

        Returns:
            Dict with 'events' and 'odds' lists
        """
        events = []
        odds = []

        for item in data_list:
            result = self.convert(item, source=source, data_type=data_type)

            if isinstance(result, Event):
                events.append(result)
            elif isinstance(result, list):
                odds.extend(result)

        return {'events': events, 'odds': odds}

    def register_converter(self, name: str, converter: BaseConverter):
        """Register a custom converter."""
        self.converters[name] = converter


def convert_file(
    file_path: str,
    source: str = 'csv',
    data_type: str = 'event',
    **kwargs
) -> List:
    """
    Convenience function to convert a file.

    Args:
        file_path: Path to data file
        source: Source format ('csv', 'json')
        data_type: 'event' or 'odds'
        **kwargs: Additional args for converter

    Returns:
        List of Event or Odds objects
    """
    if source == 'csv':
        converter = CSVConverter(**kwargs)
        return converter.convert_csv_file(file_path, data_type)

    # JSON file
    import json
    with open(file_path, 'r') as f:
        data = json.load(f)

    universal = UniversalConverter()

    if isinstance(data, list):
        result = universal.convert_batch(data, data_type=data_type)
        return result['events'] if data_type == 'event' else result['odds']
    else:
        result = universal.convert(data, data_type=data_type)
        if isinstance(result, list):
            return result
        return [result] if result else []


if __name__ == "__main__":
    # Quick tests
    universal = UniversalConverter()

    # Test SportMonks event
    sm_event = {
        "fixture_id": 12345,
        "type": {"name": "GOAL"},
        "time": {"starting_at": "2026-01-28T18:00:00Z"},
        "team_id": 1,
        "home_team_id": 1,
        "minute": 45,
        "xg": 0.65
    }

    result = universal.convert(sm_event)
    print(f"SportMonks event: {result}")
    assert result is not None
    assert result.type == 'GOAL'
    assert result.team == 'HOME'

    # Test The Odds API
    odds_api = {
        "id": "game123",
        "sport_key": "soccer_epl",
        "commence_time": "2026-01-28T18:00:00Z",
        "bookmakers": [{
            "key": "pinnacle",
            "markets": [{
                "key": "totals",
                "outcomes": [
                    {"name": "Over", "price": 2.10, "point": 2.5},
                    {"name": "Under", "price": 1.80, "point": 2.5}
                ]
            }]
        }]
    }

    result = universal.convert(odds_api)
    print(f"Odds API result: {len(result)} odds")
    assert len(result) == 2
    assert any(o.selection == 'OVER_2.5' for o in result)

    # Test BetsAPI event
    bets_event = {
        "match_id": "67890",
        "type": "1",  # GOAL
        "time": 1706468400,  # Unix timestamp
        "team": "home",
        "minute": 23
    }

    result = universal.convert(bets_event)
    print(f"BetsAPI event: {result}")
    assert result is not None
    assert result.type == 'GOAL'

    print("\n✅ All converter tests passed!")
