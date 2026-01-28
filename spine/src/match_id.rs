use chrono::{DateTime, Utc};

pub fn normalize_team(name: &str) -> String {
    name.chars()
        .filter(|c| c.is_ascii_alphanumeric())
        .map(|c| c.to_ascii_lowercase())
        .collect()
}

pub fn canonical_match_id(home: &str, away: &str, commence: DateTime<Utc>) -> String {
    let date = commence.format("%Y%m%d").to_string();
    let h = normalize_team(home);
    let a = normalize_team(away);
    format!("{date}:{h}:{a}")
}
