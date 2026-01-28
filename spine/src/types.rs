use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

#[derive(Debug, Deserialize, Serialize)]
pub struct Event {
    pub match_id: String,
    pub t_event: DateTime<Utc>,
    pub t_recv: DateTime<Utc>,
    #[serde(rename = "type")]
    pub event_type: String,
    pub team: Option<String>,
    pub xg: f64,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct Odds {
    pub match_id: String,
    pub t_seen: DateTime<Utc>,
    pub t_recv: DateTime<Utc>,
    pub market: String,
    pub selection: String,
    pub price: f64,
    pub is_suspended: bool,
}
