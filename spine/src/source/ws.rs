use anyhow::{Context, Result};
use futures_util::{SinkExt, StreamExt};
use http::Request;
use serde::Deserialize;
use serde_json::Value;
use tokio::time::{sleep, Duration};
use tokio_tungstenite::{connect_async, tungstenite::Message};

use crate::brain::BrainClient;
use crate::ilp::{decision_to_ilp, event_to_ilp, odds_to_ilp};
use crate::questdb::QuestDbClient;
use crate::types::{Event, Odds};

#[derive(Clone)]
pub struct WsConfig {
    pub url: String,
    pub bearer_token: Option<String>,
    pub reconnect_ms: u64,
    pub brain: Option<BrainClient>,
}

#[derive(Debug, Deserialize)]
struct Envelope {
    kind: String,
    data: Value,
}

pub async fn run_ws(mut qdb: QuestDbClient, cfg: WsConfig) -> Result<()> {
    loop {
        match connect_and_stream(&mut qdb, cfg.clone()).await {
            Ok(()) => {
                sleep(Duration::from_millis(cfg.reconnect_ms)).await;
            }
            Err(err) => {
                eprintln!("ws error: {err}");
                sleep(Duration::from_millis(cfg.reconnect_ms)).await;
            }
        }
    }
}

async fn connect_and_stream(qdb: &mut QuestDbClient, cfg: WsConfig) -> Result<()> {
    let mut req = Request::builder()
        .uri(&cfg.url)
        .header("User-Agent", "spine-ws-ingestor");
    if let Some(token) = cfg.bearer_token.as_deref() {
        req = req.header("Authorization", format!("Bearer {token}"));
    }
    let req = req.body(())?;

    let (mut stream, _) = connect_async(req)
        .await
        .context("connect ws")?;

    while let Some(msg) = stream.next().await {
        match msg? {
            Message::Text(text) => {
                handle_message(qdb, &cfg, &text).await?;
            }
            Message::Binary(bytes) => {
                if let Ok(text) = String::from_utf8(bytes) {
                    handle_message(qdb, &cfg, &text).await?;
                }
            }
            Message::Ping(payload) => {
                stream.send(Message::Pong(payload)).await?;
            }
            Message::Close(_) => break,
            _ => {}
        }
    }

    Ok(())
}

async fn handle_message(qdb: &mut QuestDbClient, cfg: &WsConfig, text: &str) -> Result<()> {
    let env: Envelope = serde_json::from_str(text).context("ws json")?;
    match env.kind.as_str() {
        "event" => {
            let event: Event = serde_json::from_value(env.data).context("ws event parse")?;
            qdb.write_line(&event_to_ilp(&event)).await?;
            if let Some(brain) = &cfg.brain {
                let decision = brain.send_event(&event).await?;
                qdb.write_line(&decision_to_ilp(&decision)).await?;
            }
        }
        "odds" => {
            let odds: Odds = serde_json::from_value(env.data).context("ws odds parse")?;
            qdb.write_line(&odds_to_ilp(&odds)).await?;
            if let Some(brain) = &cfg.brain {
                let decision = brain.send_odds(&odds).await?;
                qdb.write_line(&decision_to_ilp(&decision)).await?;
            }
        }
        _ => {}
    }
    Ok(())
}
