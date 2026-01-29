"""
Base converters for various data providers.

Each converter transforms provider-specific format to internal Vektorr schemas.
"""
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import csv
import io

from schemas import Event, Odds


class BaseConverter(ABC):
    """Abstract base class for data converters."""

    @abstractmethod
    def convert_event(self, raw: Dict[str, Any]) -> Optional[Event]:
        """Convert raw event data to internal Event schema."""
        pass

    @abstractmethod
    def convert_odds(self, raw: Dict[str, Any]) -> List[Odds]:
        """Convert raw odds data to internal Odds schema."""
        pass

    def _parse_timestamp(self, ts: Any) -> datetime:
        """Parse various timestamp formats to datetime."""
        if isinstance(ts, datetime):
            return ts
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        if isinstance(ts, str):
            # Try ISO format
            ts = ts.replace('Z', '+00:00')
            return datetime.fromisoformat(ts)
        raise ValueError(f"Cannot parse timestamp: {ts}")


class SportMonksConverter(BaseConverter):
    """
    Converts SportMonks API format to internal schemas.

    SportMonks API docs: https://docs.sportmonks.com/football
    """

    EVENT_TYPE_MAP = {
        'GOAL': 'GOAL',
        'OWN_GOAL': 'GOAL',
        'PENALTY': 'GOAL',
        'SHOT': 'SHOT',
        'SHOT_ON_TARGET': 'SHOT',
        'SHOT_OFF_TARGET': 'SHOT',
        'SHOT_BLOCKED': 'SHOT',
        'DANGEROUS_ATTACK': 'DANGER_ATTACK',
        'ATTACK': 'DANGER_ATTACK',
        'CORNER': 'CORNER',
        'YELLOW_CARD': 'CARD',
        'YELLOWRED_CARD': 'RED_CARD',
        'RED_CARD': 'RED_CARD',
        'SUBSTITUTION': 'SUBSTITUTION',
        'VAR': 'VAR',
    }

    def convert_event(self, raw: Dict[str, Any]) -> Optional[Event]:
        """Convert SportMonks event to internal Event."""
        try:
            # Extract event type
            sm_type = raw.get('type', {})
            if isinstance(sm_type, dict):
                sm_type = sm_type.get('name', '').upper()
            else:
                sm_type = str(sm_type).upper()

            internal_type = self.EVENT_TYPE_MAP.get(sm_type)
            if not internal_type:
                return None

            # Parse timestamp
            time_data = raw.get('time', {})
            if isinstance(time_data, dict):
                t_event = self._parse_timestamp(time_data.get('starting_at') or time_data.get('timestamp'))
            else:
                t_event = self._parse_timestamp(time_data)

            # Determine team
            team_id = raw.get('team_id') or raw.get('participant_id')
            home_team_id = raw.get('home_team_id') or raw.get('localteam_id')
            team = 'HOME' if team_id == home_team_id else 'AWAY'

            # Extract xG if available
            xg = 0.0
            if 'xg' in raw:
                xg = float(raw['xg'])
            elif internal_type == 'SHOT':
                # Estimate xG for shots without data
                xg = 0.08

            return Event(
                match_id=str(raw.get('fixture_id', raw.get('match_id', 'unknown'))),
                t_event=t_event,
                t_recv=datetime.now(timezone.utc),
                type=internal_type,
                team=team,
                xg=xg,
                data={
                    'raw_type': sm_type,
                    'minute': raw.get('minute'),
                    'player_id': raw.get('player_id'),
                    'extra': raw.get('extra_info'),
                }
            )
        except Exception as e:
            return None

    def convert_odds(self, raw: Dict[str, Any]) -> List[Odds]:
        """Convert SportMonks odds to internal Odds list."""
        odds_list = []
        try:
            match_id = str(raw.get('fixture_id', raw.get('id', 'unknown')))

            # SportMonks odds come in various formats
            odds_data = raw.get('odds', []) or raw.get('markets', [])

            for market in odds_data:
                market_name = market.get('name', market.get('market_name', ''))

                # Map to internal market names
                if 'over' in market_name.lower() or 'total' in market_name.lower():
                    internal_market = 'OU'
                elif 'winner' in market_name.lower() or '1x2' in market_name.lower():
                    internal_market = 'H2H'
                else:
                    continue

                for outcome in market.get('outcomes', market.get('selections', [])):
                    selection = outcome.get('name', outcome.get('selection', ''))
                    price = float(outcome.get('odds', outcome.get('price', 0)))

                    if price <= 1.0:
                        continue

                    # Normalize selection names
                    if 'over' in selection.lower():
                        selection = 'OVER_2.5'
                    elif 'under' in selection.lower():
                        selection = 'UNDER_2.5'

                    odds_list.append(Odds(
                        match_id=match_id,
                        t_seen=datetime.now(timezone.utc),
                        t_recv=datetime.now(timezone.utc),
                        market=internal_market,
                        selection=selection,
                        price=round(price, 2),
                        is_suspended=raw.get('suspended', False)
                    ))

        except Exception:
            pass

        return odds_list


class TheOddsApiConverter(BaseConverter):
    """
    Converts The Odds API format to internal schemas.

    API docs: https://the-odds-api.com/liveapi/guides/v4/
    """

    def convert_event(self, raw: Dict[str, Any]) -> Optional[Event]:
        """The Odds API doesn't provide events, only odds."""
        return None

    def convert_odds(self, raw: Dict[str, Any]) -> List[Odds]:
        """Convert The Odds API odds to internal Odds list."""
        odds_list = []
        try:
            match_id = raw.get('id', 'unknown')
            commence_time = raw.get('commence_time')

            for bookmaker in raw.get('bookmakers', []):
                for market in bookmaker.get('markets', []):
                    market_key = market.get('key', '')

                    # Map market keys
                    if market_key == 'totals':
                        internal_market = 'OU'
                    elif market_key == 'h2h':
                        internal_market = 'H2H'
                    elif market_key == 'spreads':
                        internal_market = 'AH'
                    else:
                        continue

                    for outcome in market.get('outcomes', []):
                        selection = outcome.get('name', '')
                        price = float(outcome.get('price', 0))
                        point = outcome.get('point')

                        if price <= 1.0:
                            continue

                        # Normalize selection for totals
                        if internal_market == 'OU' and point:
                            if selection.lower() == 'over':
                                selection = f'OVER_{point}'
                            elif selection.lower() == 'under':
                                selection = f'UNDER_{point}'

                        odds_list.append(Odds(
                            match_id=match_id,
                            t_seen=datetime.now(timezone.utc),
                            t_recv=datetime.now(timezone.utc),
                            market=internal_market,
                            selection=selection,
                            price=round(price, 2),
                            is_suspended=False
                        ))

        except Exception:
            pass

        return odds_list


class BetsApiConverter(BaseConverter):
    """
    Converts BetsAPI format to internal schemas.

    API docs: https://betsapi.com/docs/
    """

    EVENT_TYPE_MAP = {
        '1': 'GOAL',
        '2': 'CORNER',
        '3': 'CARD',
        '4': 'RED_CARD',
        '5': 'SUBSTITUTION',
        '10': 'SHOT',
        '12': 'DANGER_ATTACK',
    }

    def convert_event(self, raw: Dict[str, Any]) -> Optional[Event]:
        """Convert BetsAPI event to internal Event."""
        try:
            event_type_id = str(raw.get('type', raw.get('event_type', '')))
            internal_type = self.EVENT_TYPE_MAP.get(event_type_id)

            if not internal_type:
                return None

            # Parse timestamp (BetsAPI uses unix timestamps)
            t_event = self._parse_timestamp(raw.get('time', raw.get('timestamp')))

            # Team determination
            team_raw = raw.get('team', raw.get('side', ''))
            team = 'HOME' if team_raw in ('home', '1', 1) else 'AWAY'

            return Event(
                match_id=str(raw.get('match_id', raw.get('event_id', 'unknown'))),
                t_event=t_event,
                t_recv=datetime.now(timezone.utc),
                type=internal_type,
                team=team,
                xg=float(raw.get('xg', 0.0)),
                data={
                    'raw_type': event_type_id,
                    'minute': raw.get('minute'),
                    'text': raw.get('text'),
                }
            )
        except Exception:
            return None

    def convert_odds(self, raw: Dict[str, Any]) -> List[Odds]:
        """Convert BetsAPI odds to internal Odds list."""
        odds_list = []
        try:
            match_id = str(raw.get('match_id', raw.get('event_id', 'unknown')))

            # BetsAPI odds format
            odds_data = raw.get('odds', {})

            for market_key, outcomes in odds_data.items():
                # Map market
                if 'over' in market_key.lower() or 'total' in market_key.lower():
                    internal_market = 'OU'
                elif '1x2' in market_key.lower() or 'winner' in market_key.lower():
                    internal_market = 'H2H'
                else:
                    continue

                if isinstance(outcomes, dict):
                    for selection, price in outcomes.items():
                        if float(price) <= 1.0:
                            continue

                        odds_list.append(Odds(
                            match_id=match_id,
                            t_seen=datetime.now(timezone.utc),
                            t_recv=datetime.now(timezone.utc),
                            market=internal_market,
                            selection=selection,
                            price=round(float(price), 2),
                            is_suspended=raw.get('suspended', False)
                        ))

        except Exception:
            pass

        return odds_list


class CSVConverter(BaseConverter):
    """
    Converts CSV data to internal schemas.

    Supports flexible column mapping for historical data.
    """

    def __init__(
        self,
        event_columns: Dict[str, str] = None,
        odds_columns: Dict[str, str] = None
    ):
        """
        Initialize with column mappings.

        Args:
            event_columns: Map of internal field -> CSV column name
            odds_columns: Map of internal field -> CSV column name
        """
        self.event_columns = event_columns or {
            'match_id': 'match_id',
            't_event': 'timestamp',
            'type': 'event_type',
            'team': 'team',
            'xg': 'xg',
        }
        self.odds_columns = odds_columns or {
            'match_id': 'match_id',
            't_seen': 'timestamp',
            'market': 'market',
            'selection': 'selection',
            'price': 'odds',
        }

    def convert_event(self, raw: Dict[str, Any]) -> Optional[Event]:
        """Convert CSV row to internal Event."""
        try:
            cols = self.event_columns

            event_type = str(raw.get(cols['type'], '')).upper()
            if not event_type:
                return None

            return Event(
                match_id=str(raw.get(cols['match_id'], 'unknown')),
                t_event=self._parse_timestamp(raw.get(cols['t_event'])),
                t_recv=datetime.now(timezone.utc),
                type=event_type,
                team=str(raw.get(cols['team'], 'HOME')).upper(),
                xg=float(raw.get(cols.get('xg', 'xg'), 0.0)),
                data=raw
            )
        except Exception:
            return None

    def convert_odds(self, raw: Dict[str, Any]) -> List[Odds]:
        """Convert CSV row to internal Odds."""
        try:
            cols = self.odds_columns

            price = float(raw.get(cols['price'], 0))
            if price <= 1.0:
                return []

            return [Odds(
                match_id=str(raw.get(cols['match_id'], 'unknown')),
                t_seen=self._parse_timestamp(raw.get(cols['t_seen'])),
                t_recv=datetime.now(timezone.utc),
                market=str(raw.get(cols['market'], 'OU')),
                selection=str(raw.get(cols['selection'], '')),
                price=round(price, 2),
                is_suspended=raw.get('suspended', False)
            )]
        except Exception:
            return []

    def convert_csv_file(self, file_path: str, data_type: str = 'event') -> List:
        """
        Convert entire CSV file to internal format.

        Args:
            file_path: Path to CSV file
            data_type: 'event' or 'odds'

        Returns:
            List of Event or Odds objects
        """
        results = []

        with open(file_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if data_type == 'event':
                    result = self.convert_event(row)
                    if result:
                        results.append(result)
                else:
                    results.extend(self.convert_odds(row))

        return results
