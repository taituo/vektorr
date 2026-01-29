from typing import Dict, Any

TEAM_PROFILES: Dict[str, Dict[str, Any]] = {
    'Manchester City': {
        'strength': 92,
        'style': 'possession',
        'xg_per_90': 2.4,
        'xga_per_90': 0.8,
        'tempo': 'high',
        'late_goals_tendency': 0.7,
    },
    'Liverpool': {
        'strength': 90,
        'style': 'heavy_metal',
        'xg_per_90': 2.3,
        'xga_per_90': 0.9,
        'tempo': 'high',
        'late_goals_tendency': 0.6,
    },
    'Arsenal': {
        'strength': 89,
        'style': 'technical',
        'xg_per_90': 2.1,
        'xga_per_90': 0.8,
        'tempo': 'normal',
        'late_goals_tendency': 0.5,
    },
    'Real Madrid': {
        'strength': 91,
        'style': 'efficient',
        'xg_per_90': 2.2,
        'xga_per_90': 1.0,
        'tempo': 'normal',
        'late_goals_tendency': 0.8,
    },
    'Burnley': {
        'strength': 58,
        'style': 'direct',
        'xg_per_90': 1.1,
        'xga_per_90': 1.6,
        'tempo': 'low',
        'late_goals_tendency': 0.4,
    },
    'Luton Town': {
        'strength': 55,
        'style': 'brave',
        'xg_per_90': 1.2,
        'xga_per_90': 2.1,
        'tempo': 'high',
        'late_goals_tendency': 0.5,
    },
    'Generic Top': {
        'strength': 85,
        'style': 'normal',
        'xg_per_90': 1.8,
        'xga_per_90': 1.0,
        'tempo': 'normal',
        'late_goals_tendency': 0.5,
    },
    'Generic Mid': {
        'strength': 70,
        'style': 'normal',
        'xg_per_90': 1.3,
        'xga_per_90': 1.3,
        'tempo': 'normal',
        'late_goals_tendency': 0.5,
    },
    'Generic Bottom': {
        'strength': 55,
        'style': 'defensive',
        'xg_per_90': 0.9,
        'xga_per_90': 1.8,
        'tempo': 'low',
        'late_goals_tendency': 0.3,
    }
}

LEAGUE_PROFILES: Dict[str, Dict[str, Any]] = {
    'Premier League': {
        'avg_goals': 2.8,
        'tempo': 'high',
        'card_frequency': 'medium',
        'home_advantage': 1.15,
    },
    'La Liga': {
        'avg_goals': 2.5,
        'tempo': 'medium',
        'card_frequency': 'high',
        'home_advantage': 1.20,
    },
    'Champions League': {
        'avg_goals': 2.9,
        'tempo': 'high',
        'card_frequency': 'medium',
        'home_advantage': 1.10,
    },
}
