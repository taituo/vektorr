use anyhow::{Context, Result};
use chrono::{DateTime, Utc};
use reqwest::{Client, Url};
use std::time::Instant;
use tokio::time::{sleep, Duration};

use crate::brain::BrainClient;
use crate::ilp::{decision_to_ilp, event_to_ilp, odds_to_ilp};
use crate::polling::{poll_sleep_ms, Deduper, next_backoff};
use crate::questdb::QuestDbClient;
use crate::types::{Event, Odds};

pub struct PollConfig {
    pub url: String,
    pub poll_ms: u64,
    pub min_interval_ms: u64,
    pub timeout_ms: u64,
    pub bearer_token: Option<String>,
    pub dedup_capacity: usize,
    pub max_backoff_ms: u64,
    pub brain: Option<BrainClient>,
}

pub async fn poll_events(mut qdb: QuestDbClient, cfg: PollConfig) -> Result<()> {
    let client = build_client(cfg.timeout_ms)?;
    let mut since: Option<DateTime<Utc>> = None;
    let mut dedup = Deduper::new(cfg.dedup_capacity);
    let mut backoff_ms: u64 = 0;

    loop {
        let loop_start = Instant::now();
        let url = with_since(&cfg.url, since)?;
        let mut req = client.get(url);
        if let Some(token) = cfg.bearer_token.as_deref() {
            req = req.bearer_auth(token);
        }

        let resp = match req.send().await {
            Ok(resp) => resp,
            Err(err) => {
                eprintln!("events poll error: {err}");
                backoff_ms = next_backoff(backoff_ms, cfg.max_backoff_ms);
                sleep(poll_sleep_ms(cfg.poll_ms, cfg.min_interval_ms, backoff_ms, loop_start)).await;
                continue;
            }
        };

        let resp = match resp.error_for_status() {
            Ok(resp) => resp,
            Err(err) => {
                eprintln!("events status error: {err}");
                backoff_ms = next_backoff(backoff_ms, cfg.max_backoff_ms);
                sleep(poll_sleep_ms(cfg.poll_ms, cfg.min_interval_ms, backoff_ms, loop_start)).await;
                continue;
            }
        };

        let events: Vec<Event> = resp.json().await.context("events json")?;

        let mut max_ts = since;
        let write_start = Instant::now();
        for event in events.iter() {
            if !dedup.allow(event_key(event)) {
                continue;
            }
            qdb.write_line(&event_to_ilp(event)).await?;
            if let Some(brain) = &cfg.brain {
                let decision = brain.send_event(event).await?;
                qdb.write_line(&decision_to_ilp(&decision)).await?;
            }
            max_ts = Some(match max_ts {
                Some(prev) => if event.t_event > prev { event.t_event } else { prev },
                None => event.t_event,
            });
        }
        let write_ms = write_start.elapsed().as_millis() as u64;

        since = max_ts;
        backoff_ms = 0;
        sleep(poll_sleep_ms(cfg.poll_ms, cfg.min_interval_ms, write_ms, loop_start)).await;
    }
}

pub async fn poll_odds(mut qdb: QuestDbClient, cfg: PollConfig) -> Result<()> {
    let client = build_client(cfg.timeout_ms)?;
    let mut since: Option<DateTime<Utc>> = None;
    let mut dedup = Deduper::new(cfg.dedup_capacity);
    let mut backoff_ms: u64 = 0;

    loop {
        let loop_start = Instant::now();
        let url = with_since(&cfg.url, since)?;
        let mut req = client.get(url);
        if let Some(token) = cfg.bearer_token.as_deref() {
            req = req.bearer_auth(token);
        }

        let resp = match req.send().await {
            Ok(resp) => resp,
            Err(err) => {
                eprintln!("odds poll error: {err}");
                backoff_ms = next_backoff(backoff_ms, cfg.max_backoff_ms);
                sleep(poll_sleep_ms(cfg.poll_ms, cfg.min_interval_ms, backoff_ms, loop_start)).await;
                continue;
            }
        };

        let resp = match resp.error_for_status() {
            Ok(resp) => resp,
            Err(err) => {
                eprintln!("odds status error: {err}");
                backoff_ms = next_backoff(backoff_ms, cfg.max_backoff_ms);
                sleep(poll_sleep_ms(cfg.poll_ms, cfg.min_interval_ms, backoff_ms, loop_start)).await;
                continue;
            }
        };

        let odds_list: Vec<Odds> = resp.json().await.context("odds json")?;

        let mut max_ts = since;
        let write_start = Instant::now();
        for odds in odds_list.iter() {
            if !dedup.allow(odds_key(odds)) {
                continue;
            }
            qdb.write_line(&odds_to_ilp(odds)).await?;
            if let Some(brain) = &cfg.brain {
                let decision = brain.send_odds(odds).await?;
                qdb.write_line(&decision_to_ilp(&decision)).await?;
            }
            max_ts = Some(match max_ts {
                Some(prev) => if odds.t_recv > prev { odds.t_recv } else { prev },
                None => odds.t_recv,
            });
        }
        let write_ms = write_start.elapsed().as_millis() as u64;

        since = max_ts;
        backoff_ms = 0;
        sleep(poll_sleep_ms(cfg.poll_ms, cfg.min_interval_ms, write_ms, loop_start)).await;
    }
}

fn build_client(timeout_ms: u64) -> Result<Client> {
    Client::builder()
        .timeout(Duration::from_millis(timeout_ms))
        .build()
        .context("build http client")
}

fn with_since(base: &str, since: Option<DateTime<Utc>>) -> Result<String> {
    if let Some(ts) = since {
        let mut url = Url::parse(base).context("parse url")?;
        url.query_pairs_mut().append_pair("since", &ts.to_rfc3339());
        return Ok(url.to_string());
    }
    Ok(base.to_string())
}


fn event_key(event: &Event) -> String {
    format!(
        "{}|{}|{}|{}",
        event.match_id,
        event.t_event.timestamp_nanos_opt().unwrap_or(0),
        event.event_type,
        event.team.as_deref().unwrap_or("UNKNOWN")
    )
}

fn odds_key(odds: &Odds) -> String {
    format!(
        "{}|{}|{}|{}|{}",
        odds.match_id,
        odds.t_recv.timestamp_nanos_opt().unwrap_or(0),
        odds.market,
        odds.selection,
        odds.is_suspended
    )
}
