use anyhow::{Context, Result};
use chrono::{DateTime, NaiveDateTime, TimeZone, Utc};
use reqwest::Client;
use serde::Deserialize;
use serde_json::Value;
use std::collections::HashMap;
use std::time::Instant;
use tokio::time::sleep;

use crate::brain::BrainClient;
use crate::ilp::{decision_to_ilp, event_to_ilp, match_map_to_ilp};
use crate::mapping::MatchResolver;
use crate::match_id::canonical_match_id;
use crate::polling::{poll_sleep_ms, Deduper, next_backoff};
use crate::questdb::QuestDbClient;
use crate::types::Event;
use std::sync::Arc;
use tokio::sync::Mutex;

#[derive(Clone)]
pub struct SportMonksConfig {
    pub token: String,
    pub base_url: String,
    pub leagues: Vec<String>,
    pub poll_ms: u64,
    pub min_interval_ms: u64,
    pub timeout_ms: u64,
    pub dedup_capacity: usize,
    pub max_backoff_ms: u64,
    pub brain: Option<BrainClient>,
    pub match_resolver: Option<Arc<Mutex<MatchResolver>>>,
}

#[derive(Debug, Deserialize)]
struct LivescoresResponse {
    data: Value,
}

#[derive(Debug, Deserialize)]
struct Fixture {
    id: i64,
    league_id: Option<i64>,
    starting_at: Option<String>,
    starting_at_timestamp: Option<i64>,
    participants: Option<Vec<Participant>>,
    events: Option<Vec<FixtureEvent>>,
}

#[derive(Debug, Deserialize)]
struct Participant {
    id: i64,
    name: Option<String>,
    meta: Option<ParticipantMeta>,
}

#[derive(Debug, Deserialize)]
struct ParticipantMeta {
    location: Option<String>, // "home" / "away"
}

#[derive(Debug, Deserialize)]
struct FixtureEvent {
    id: i64,
    team_id: Option<i64>,
    minute: Option<i64>,
    extra_minute: Option<i64>,
    player_id: Option<i64>,
    #[serde(rename = "type_id")]
    event_type_id: Option<i64>,
    #[serde(rename = "type")]
    event_type: Option<EventType>,
}

#[derive(Debug, Deserialize)]
struct EventType {
    name: Option<String>,
    code: Option<String>,
    developer_name: Option<String>,
}

pub async fn run_sportmonks(mut qdb: QuestDbClient, cfg: SportMonksConfig) -> Result<()> {
    let client = Client::builder()
        .timeout(std::time::Duration::from_millis(cfg.timeout_ms))
        .build()
        .context("build sportmonks client")?;

    let mut dedup = Deduper::new(cfg.dedup_capacity);
    let mut backoff_ms: u64 = 0;

    loop {
        let loop_start = Instant::now();
        let url = build_livescores_url(&cfg);
        let resp = match client.get(url).send().await {
            Ok(resp) => resp,
            Err(err) => {
                eprintln!("sportmonks error: {err}");
                backoff_ms = next_backoff(backoff_ms, cfg.max_backoff_ms);
                sleep(poll_sleep_ms(cfg.poll_ms, cfg.min_interval_ms, backoff_ms, loop_start)).await;
                continue;
            }
        };

        let resp = match resp.error_for_status() {
            Ok(resp) => resp,
            Err(err) => {
                eprintln!("sportmonks status error: {err}");
                backoff_ms = next_backoff(backoff_ms, cfg.max_backoff_ms);
                sleep(poll_sleep_ms(cfg.poll_ms, cfg.min_interval_ms, backoff_ms, loop_start)).await;
                continue;
            }
        };

        let body: LivescoresResponse = resp.json().await.context("sportmonks json")?;
        let fixtures = parse_fixtures(body.data)?;

        let write_start = Instant::now();
        let mut batch: Vec<String> = Vec::new();
        for fixture in fixtures.iter() {
            let league_id = match fixture.league_id {
                Some(id) => id,
                None => continue,
            };
            if !cfg.leagues.iter().any(|id| id == &league_id.to_string()) {
                continue;
            }
            let (home, away) = match home_away_names(fixture) {
                Some(v) => v,
                None => continue,
            };
            let kickoff = fixture_start(fixture).unwrap_or_else(Utc::now);
            let provider_match_id = fixture.id.to_string();
            let (match_id, map_line) = if let Some(resolver) = &cfg.match_resolver {
                let mut resolver = resolver.lock().await;
                let res = resolver.resolve(
                    "sportmonks",
                    &provider_match_id,
                    &home,
                    &away,
                    kickoff,
                );
                let line = if res.is_new {
                    Some(match_map_to_ilp(
                        "sportmonks",
                        &provider_match_id,
                        &res.match_id,
                        &home,
                        &away,
                        kickoff,
                    ))
                } else {
                    None
                };
                (res.match_id, line)
            } else {
                (canonical_match_id(&home, &away, kickoff), None)
            };
            if let Some(line) = map_line {
                batch.push(line);
            }
            let team_map = team_location_map(fixture);

            if let Some(events) = &fixture.events {
                for ev in events.iter() {
                    let ev_key = format!("{}|{}", fixture.id, ev.id);
                    if !dedup.allow(ev_key) {
                        continue;
                    }
                    let ev_time = event_time(kickoff, ev);
                    let team = team_map.get(&ev.team_id.unwrap_or_default()).cloned();
                    let event_type = map_event_type(ev);
                    let event = Event {
                        match_id: match_id.clone(),
                        t_event: ev_time,
                        t_recv: Utc::now(),
                        event_type,
                        team,
                        xg: 0.0,
                    };
                    batch.push(event_to_ilp(&event));
                    if let Some(brain) = &cfg.brain {
                        let decision = brain.send_event(&event).await?;
                        batch.push(decision_to_ilp(&decision));
                    }
                }
            }
        }
        if !batch.is_empty() {
            qdb.write_lines(&batch).await?;
        }
        let write_ms = write_start.elapsed().as_millis() as u64;

        backoff_ms = 0;
        sleep(poll_sleep_ms(cfg.poll_ms, cfg.min_interval_ms, write_ms, loop_start)).await;
    }
}

fn build_livescores_url(cfg: &SportMonksConfig) -> String {
    let base = cfg.base_url.trim_end_matches('/');
    let include = "participants;events.type";
    let leagues = cfg.leagues.join(",");
    format!(
        "{base}/livescores?api_token={token}&include={include}&filters=fixtureLeagues:{leagues}",
        base = base,
        token = cfg.token,
        include = include,
        leagues = leagues
    )
}

fn parse_fixtures(data: Value) -> Result<Vec<Fixture>> {
    if data.is_array() {
        let fixtures: Vec<Fixture> = serde_json::from_value(data)?;
        return Ok(fixtures);
    }
    if data.is_object() {
        let fixture: Fixture = serde_json::from_value(data)?;
        return Ok(vec![fixture]);
    }
    Ok(Vec::new())
}

fn home_away_names(fixture: &Fixture) -> Option<(String, String)> {
    let participants = fixture.participants.as_ref()?;
    let mut home: Option<String> = None;
    let mut away: Option<String> = None;
    for p in participants.iter() {
        let location = p.meta.as_ref().and_then(|m| m.location.as_deref());
        match location {
            Some("home") => home = p.name.clone(),
            Some("away") => away = p.name.clone(),
            _ => {}
        }
    }
    match (home, away) {
        (Some(h), Some(a)) => Some((h, a)),
        _ => None,
    }
}

fn team_location_map(fixture: &Fixture) -> HashMap<i64, String> {
    let mut map = HashMap::new();
    if let Some(participants) = &fixture.participants {
        for p in participants.iter() {
            if let Some(meta) = &p.meta {
                if let Some(loc) = meta.location.as_deref() {
                    if loc == "home" {
                        map.insert(p.id, "HOME".to_string());
                    } else if loc == "away" {
                        map.insert(p.id, "AWAY".to_string());
                    }
                }
            }
        }
    }
    map
}

fn fixture_start(fixture: &Fixture) -> Option<DateTime<Utc>> {
    if let Some(ts) = fixture.starting_at_timestamp {
        return Some(DateTime::<Utc>::from_timestamp(ts, 0)?);
    }
    if let Some(s) = fixture.starting_at.as_deref() {
        return parse_datetime(s);
    }
    None
}

fn parse_datetime(s: &str) -> Option<DateTime<Utc>> {
    if let Ok(dt) = DateTime::parse_from_rfc3339(s) {
        return Some(dt.with_timezone(&Utc));
    }
    if let Ok(naive) = NaiveDateTime::parse_from_str(s, "%Y-%m-%d %H:%M:%S") {
        return Some(Utc.from_utc_datetime(&naive));
    }
    None
}

fn event_time(kickoff: DateTime<Utc>, ev: &FixtureEvent) -> DateTime<Utc> {
    let minute = ev.minute.unwrap_or(0);
    let extra = ev.extra_minute.unwrap_or(0);
    let total = minute + extra;
    kickoff + chrono::Duration::minutes(total)
}

fn map_event_type(ev: &FixtureEvent) -> String {
    let name = ev
        .event_type
        .as_ref()
        .and_then(|t| t.developer_name.clone().or(t.name.clone()).or(t.code.clone()))
        .unwrap_or_else(|| "OTHER".to_string());
    let lower = name.to_lowercase();
    if lower.contains("goal") {
        "GOAL".to_string()
    } else if lower.contains("card") {
        "CARD".to_string()
    } else if lower.contains("shot") {
        "SHOT".to_string()
    } else if lower.contains("corner") {
        "CORNER".to_string()
    } else if lower.contains("danger") {
        "DANGER_ATTACK".to_string()
    } else {
        name
    }
}
