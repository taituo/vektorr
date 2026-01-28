"""
Brain-side team/league name normalization.

NOTE: In production, Spine (Rust) handles team normalization via TeamMapper
before data reaches Brain. This module exists as a fallback for cases where
Brain receives data directly (e.g. manual testing, standalone mode without Spine).

The authoritative normalization lives in spine/src/mapping.rs.
Both read the same mappings.yaml file.
"""

import yaml
import logging
import os

logger = logging.getLogger("mapping")

class EntityMapper:
    def __init__(self, mapping_file="mappings.yaml"):
        self.mapping_file = mapping_file
        self.team_map = {}
        self.league_map = {}
        self.load_mappings()

    def load_mappings(self):
        if not os.path.exists(self.mapping_file):
            logger.warning(f"Mapping file {self.mapping_file} not found.")
            return

        try:
            with open(self.mapping_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                
                # Build reverse lookup for teams
                teams = data.get("TEAMS", {})
                for standard_name, variations in teams.items():
                    for var in variations:
                        self.team_map[var.lower()] = standard_name
                
                # Build reverse lookup for leagues
                leagues = data.get("LEAGUES", {})
                for standard_name, variations in leagues.items():
                    for var in variations:
                        self.league_map[var.lower()] = standard_name
                        
            logger.info(f"Loaded {len(self.team_map)} team variations and {len(self.league_map)} league variations.")
        except Exception as e:
            logger.error(f"Failed to load mappings: {e}")

    def resolve_team(self, name: str) -> str:
        """Translates any variation of a team name to the standard name."""
        if not name: return "UNKNOWN"
        name_lower = name.lower().strip()
        return self.team_map.get(name_lower, name) # Default to original if not found

    def resolve_league(self, name: str) -> str:
        """Translates any variation of a league name to the standard name."""
        if not name: return "UNKNOWN"
        name_lower = name.lower().strip()
        return self.league_map.get(name_lower, name)

if __name__ == "__main__":
    # Testi
    mapper = EntityMapper()
    test_names = ["HJK", "Helsingin Jalkapalloklubi", "Malmö FF", "Real Madrid"]
    for t in test_names:
        print(f"Original: {t:25} -> Resolved: {mapper.resolve_team(t)}")
