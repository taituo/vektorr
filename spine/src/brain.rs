use anyhow::{Context, Result};
use chrono::{DateTime, Utc};
use reqwest::Client;
use serde::{Deserialize, Serialize};

use crate::types::{Event, Odds};

#[derive(Clone)]
pub struct BrainClient {
    base: String,
    client: Client,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct DecisionResponse {
    pub match_id: String,
    pub minute: i32,
    pub tps_label: String,
    pub xg_10m: f64,
    pub latency_p95: f64,
    pub can_bet: bool,
    pub reason: String,
    pub odds_price: Option<f64>,
    pub selection: Option<String>,
    pub market: Option<String>,
    pub exec_status: Option<String>,
    pub price_filled: Option<f64>,
    pub slippage: Option<f64>,
    pub timestamp: DateTime<Utc>,
}

impl BrainClient {
    pub fn new(base: String, timeout_ms: u64) -> Result<Self> {
        let client = Client::builder()
            .timeout(std::time::Duration::from_millis(timeout_ms))
            .build()
            .context("build brain http client")?;
        Ok(Self { base, client })
    }

    pub async fn send_event(&self, event: &Event) -> Result<DecisionResponse> {
        let url = format!("{}/event", self.base.trim_end_matches('/'));
        let resp = self
            .client
            .post(url)
            .json(event)
            .send()
            .await
            .context("brain /event request")?
            .error_for_status()
            .context("brain /event status")?;
        resp.json::<DecisionResponse>().await.context("brain /event json")
    }

    pub async fn send_odds(&self, odds: &Odds) -> Result<DecisionResponse> {
        let url = format!("{}/odds", self.base.trim_end_matches('/'));
        let resp = self
            .client
            .post(url)
            .json(odds)
            .send()
            .await
            .context("brain /odds request")?
            .error_for_status()
            .context("brain /odds status")?;
        resp.json::<DecisionResponse>().await.context("brain /odds json")
    }
}
