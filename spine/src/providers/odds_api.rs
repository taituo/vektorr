use anyhow::{Context, Result};
use chrono::{DateTime, Utc};
use reqwest::Client;
use serde::Deserialize;
use std::time::Instant;
use tokio::time::sleep;

use crate::brain::BrainClient;
use crate::ilp::{decision_to_ilp, match_map_to_ilp, odds_to_ilp};
use crate::mapping::MatchResolver;
use crate::match_id::canonical_match_id;
use crate::polling::{poll_sleep_ms, Deduper, next_backoff};
use crate::questdb::QuestDbClient;
use crate::types::Odds;
use std::sync::Arc;
use tokio::sync::Mutex;

#[derive(Clone)]
pub struct OddsApiConfig {
    pub api_key: String,
    pub base_url: String,
    pub sports: Vec<String>,
    pub regions: String,
    pub markets: String,
    pub poll_ms: u64,
    pub min_interval_ms: u64,
    pub timeout_ms: u64,
    pub dedup_capacity: usize,
    pub max_backoff_ms: u64,
    pub brain: Option<BrainClient>,
    pub match_resolver: Option<Arc<Mutex<MatchResolver>>>,
}

#[derive(Debug, Deserialize)]
pub struct Sport {
    pub key: String,
    pub group: String,
    pub title: String,
    pub active: bool,
}

#[derive(Debug, Deserialize)]
struct OddsApiEvent {
    id: String,
    sport_key: String,
    commence_time: DateTime<Utc>,
    home_team: String,
    away_team: String,
    bookmakers: Vec<Bookmaker>,
}

#[derive(Debug, Deserialize)]
struct Bookmaker {
    key: String,
    title: String,
    last_update: DateTime<Utc>,
    markets: Vec<Market>,
}

#[derive(Debug, Deserialize)]
struct Market {
    key: String,
    last_update: DateTime<Utc>,
    outcomes: Vec<Outcome>,
    #[serde(default, alias = "is_suspended", alias = "suspended")]
    is_suspended: Option<bool>,
}

#[derive(Debug, Deserialize)]
struct Outcome {
    name: String,
    price: f64,
    point: Option<f64>,
}

pub async fn run_odds_api(mut qdb: QuestDbClient, cfg: OddsApiConfig) -> Result<()> {
    let client = Client::builder()
        .timeout(std::time::Duration::from_millis(cfg.timeout_ms))
        .build()
        .context("build odds api client")?;

    let mut dedup = Deduper::new(cfg.dedup_capacity);
    let mut backoff_ms: u64 = 0;

    loop {
        let loop_start = Instant::now();
        let mut write_ms = 0u64;

        for sport in cfg.sports.iter() {
            let url = format!(
                "{}/v4/sports/{}/odds?regions={}&markets={}&oddsFormat=decimal&dateFormat=iso&apiKey={}",
                cfg.base_url.trim_end_matches('/'),
                sport,
                cfg.regions,
                cfg.markets,
                cfg.api_key
            );

            let resp = match client.get(url).send().await {
                Ok(resp) => resp,
                Err(err) => {
                    eprintln!("odds api error ({sport}): {err}");
                    backoff_ms = next_backoff(backoff_ms, cfg.max_backoff_ms);
                    sleep(poll_sleep_ms(cfg.poll_ms, cfg.min_interval_ms, backoff_ms, loop_start)).await;
                    continue;
                }
            };

            let resp = match resp.error_for_status() {
                Ok(resp) => resp,
                Err(err) => {
                    eprintln!("odds api status error ({sport}): {err}");
                    backoff_ms = next_backoff(backoff_ms, cfg.max_backoff_ms);
                    sleep(poll_sleep_ms(cfg.poll_ms, cfg.min_interval_ms, backoff_ms, loop_start)).await;
                    continue;
                }
            };

            let events: Vec<OddsApiEvent> = resp.json().await.context("odds api json")?;

            let write_start = Instant::now();
            let mut batch: Vec<String> = Vec::new();
            for event in events.iter() {
                let provider_match_id = event.id.clone();
                let (match_id, map_line) = if let Some(resolver) = &cfg.match_resolver {
                    let mut resolver = resolver.lock().await;
                    let res = resolver.resolve(
                        "odds_api",
                        &provider_match_id,
                        &event.home_team,
                        &event.away_team,
                        event.commence_time,
                    );
                    let line = if res.is_new {
                        Some(match_map_to_ilp(
                            "odds_api",
                            &provider_match_id,
                            &res.match_id,
                            &event.home_team,
                            &event.away_team,
                            event.commence_time,
                        ))
                    } else {
                        None
                    };
                    (res.match_id, line)
                } else {
                    (
                        canonical_match_id(&event.home_team, &event.away_team, event.commence_time),
                        None,
                    )
                };
                if let Some(line) = map_line {
                    batch.push(line);
                }
                for bookmaker in event.bookmakers.iter() {
                    for market in bookmaker.markets.iter() {
                        for outcome in market.outcomes.iter() {
                            let (market_name, selection) = map_market(&market.key, outcome);
                            if market_name.is_none() || selection.is_none() {
                                continue;
                            }
                            let market_name = market_name.unwrap();
                            let selection = selection.unwrap();
                            let t_seen = market.last_update;
                            let t_recv = Utc::now();
                            let line = outcome.point;
                            let point = outcome.point;

                            let odds = Odds {
                                match_id: match_id.clone(),
                                t_seen,
                                t_recv,
                                market: market_name,
                                selection,
                                price: outcome.price,
                                line,
                                point,
                                is_suspended: market.is_suspended.unwrap_or(false),
                            };

                            let dedup_key = format!(
                                "{}|{}|{}|{}|{}|{}",
                                event.id,
                                bookmaker.key,
                                market.key,
                                odds.selection,
                                odds.price,
                                market.last_update.timestamp()
                            );
                            if !dedup.allow(dedup_key) {
                                continue;
                            }

                            batch.push(odds_to_ilp(&odds));
                            if let Some(brain) = &cfg.brain {
                                let decision = brain.send_odds(&odds).await?;
                                batch.push(decision_to_ilp(&decision));
                            }
                        }
                    }
                }
            }
            if !batch.is_empty() {
                qdb.write_lines(&batch).await?;
            }
            write_ms = write_ms.max(write_start.elapsed().as_millis() as u64);
        }

        backoff_ms = 0;
        sleep(poll_sleep_ms(cfg.poll_ms, cfg.min_interval_ms, write_ms, loop_start)).await;
    }
}

pub async fn list_sports(base_url: &str, api_key: Option<&str>) -> Result<Vec<Sport>> {
    let client = Client::builder()
        .timeout(std::time::Duration::from_millis(5000))
        .build()
        .context("build odds api client")?;

    let mut url = format!("{}/v4/sports", base_url.trim_end_matches('/'));
    if let Some(key) = api_key {
        url = format!("{url}?apiKey={key}");
    }

    let resp = client
        .get(url)
        .send()
        .await
        .context("odds api list sports request")?
        .error_for_status()
        .context("odds api list sports status")?;

    let sports: Vec<Sport> = resp.json().await.context("odds api list sports json")?;
    Ok(sports)
}

fn map_market(key: &str, outcome: &Outcome) -> (Option<String>, Option<String>) {
    match key {
        "totals" => {
            if let Some(point) = outcome.point {
                let market = format!("OU_{}", trim_trailing_zeros(point));
                let selection = outcome.name.clone();
                (Some(market), Some(selection))
            } else {
                (None, None)
            }
        }
        "h2h" => {
            let market = "H2H".to_string();
            let selection = outcome.name.clone();
            (Some(market), Some(selection))
        }
        _ => (None, None),
    }
}

fn trim_trailing_zeros(value: f64) -> String {
    let s = format!("{value}");
    if s.contains('.') {
        s.trim_end_matches('0').trim_end_matches('.').to_string()
    } else {
        s
    }
}
