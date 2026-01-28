use anyhow::{Context, Result};
use axum::{
    extract::State,
    http::StatusCode,
    routing::{get, post},
    Json, Router,
};
use clap::Parser;
use std::sync::Arc;
use tokio::sync::Mutex;

mod brain;
mod ilp;
mod match_id;
mod polling;
mod providers;
mod questdb;
mod source;
mod types;

use brain::BrainClient;
use ilp::{decision_to_ilp, event_to_ilp, odds_to_ilp};
use questdb::QuestDbClient;
use source::{http_poll::PollConfig, jsonl::read_jsonl};
use types::{Event, Odds};

#[derive(Parser, Debug)]
#[command(name = "spine-ingestor", version, about = "Rust ingestor pushing data to QuestDB via ILP")]
struct Args {
    /// QuestDB ILP host
    #[arg(long, default_value = "127.0.0.1")]
    qdb_host: String,
    /// QuestDB ILP port (TCP)
    #[arg(long, default_value_t = 9009)]
    qdb_port: u16,
    /// JSONL events file to ingest
    #[arg(long)]
    events: Option<String>,
    /// JSONL odds file to ingest
    #[arg(long)]
    odds: Option<String>,
    /// WebSocket URL for streaming ingestion (expects envelope {kind,data})
    #[arg(long)]
    ws_url: Option<String>,
    /// Optional bearer token for WebSocket
    #[arg(long)]
    ws_bearer_token: Option<String>,
    /// WS reconnect interval in ms
    #[arg(long, default_value_t = 2000)]
    ws_reconnect_ms: u64,
    /// Brain base URL (e.g. http://127.0.0.1:8090)
    #[arg(long)]
    brain_url: Option<String>,
    /// Brain HTTP timeout in ms
    #[arg(long, default_value_t = 3000)]
    brain_timeout_ms: u64,
    /// Odds API key (The Odds API)
    #[arg(long)]
    odds_api_key: Option<String>,
    /// List available sports from The Odds API and exit
    #[arg(long, default_value_t = false)]
    odds_api_list_sports: bool,
    /// Odds API sports (comma separated keys, e.g. soccer_epl,soccer_sweden_allsvenskan)
    #[arg(long)]
    odds_api_sports: Option<String>,
    /// Odds API regions (default: eu)
    #[arg(long, default_value = "eu")]
    odds_api_regions: String,
    /// Odds API markets (default: totals)
    #[arg(long, default_value = "totals")]
    odds_api_markets: String,
    /// Odds API base URL
    #[arg(long, default_value = "https://api.the-odds-api.com")]
    odds_api_base: String,
    /// Odds API poll interval ms
    #[arg(long, default_value_t = 2000)]
    odds_api_poll_ms: u64,
    /// SportMonks token
    #[arg(long)]
    sportmonks_token: Option<String>,
    /// SportMonks leagues (comma separated IDs)
    #[arg(long)]
    sportmonks_leagues: Option<String>,
    /// SportMonks base URL
    #[arg(long, default_value = "https://api.sportmonks.com/v3/football")]
    sportmonks_base: String,
    /// SportMonks poll interval ms
    #[arg(long, default_value_t = 2000)]
    sportmonks_poll_ms: u64,
    /// Run HTTP server for event/odds ingestion (e.g. 0.0.0.0:8080)
    #[arg(long)]
    listen: Option<String>,
    /// Poll events from HTTP endpoint (expects JSON array of Event)
    #[arg(long)]
    events_url: Option<String>,
    /// Poll odds from HTTP endpoint (expects JSON array of Odds)
    #[arg(long)]
    odds_url: Option<String>,
    /// Poll interval in ms (HTTP polling mode)
    #[arg(long, default_value_t = 1000)]
    poll_ms: u64,
    /// Max requests per second per endpoint (HTTP polling mode, 0 disables)
    #[arg(long, default_value_t = 0)]
    max_rps: u32,
    /// HTTP timeout in ms (HTTP polling mode)
    #[arg(long, default_value_t = 5000)]
    timeout_ms: u64,
    /// Optional bearer token for HTTP polling
    #[arg(long)]
    bearer_token: Option<String>,
    /// Dedup cache size (0 disables)
    #[arg(long, default_value_t = 20000)]
    dedup_cap: usize,
    /// Max backoff in ms (HTTP polling mode)
    #[arg(long, default_value_t = 15000)]
    max_backoff_ms: u64,
}

#[derive(Clone)]
struct AppState {
    qdb: Arc<Mutex<QuestDbClient>>,
    brain: Option<BrainClient>,
}

type AppResult<T> = std::result::Result<T, (StatusCode, String)>;

#[tokio::main]
async fn main() -> Result<()> {
    let args = Args::parse();

    if args.listen.is_some() && (args.events_url.is_some() || args.odds_url.is_some()) {
        anyhow::bail!("--listen cannot be combined with --events-url/--odds-url");
    }
    if args.listen.is_some() && args.ws_url.is_some() {
        anyhow::bail!("--listen cannot be combined with --ws-url");
    }
    if (args.events_url.is_some() || args.odds_url.is_some()) && args.ws_url.is_some() {
        anyhow::bail!("--events-url/--odds-url cannot be combined with --ws-url");
    }
    if (args.events_url.is_some() || args.odds_url.is_some() || args.listen.is_some() || args.ws_url.is_some())
        && (args.odds_api_key.is_some() || args.sportmonks_token.is_some())
    {
        anyhow::bail!("provider adapters cannot be combined with --listen/--events-url/--odds-url/--ws-url");
    }

    if let Some(addr) = args.listen.as_deref() {
        return run_http(
            addr,
            &args.qdb_host,
            args.qdb_port,
            args.brain_url.clone(),
            args.brain_timeout_ms,
        )
        .await;
    }

    if args.events_url.is_some() || args.odds_url.is_some() {
        return run_polling(args).await;
    }
    if let Some(ws_url) = args.ws_url.clone() {
        return run_ws(args, ws_url).await;
    }
    if args.odds_api_list_sports {
        let sports = providers::odds_api::list_sports(
            &args.odds_api_base,
            args.odds_api_key.as_deref(),
        )
        .await?;
        for sport in sports {
            println!("{} | {} | active={}", sport.key, sport.title, sport.active);
        }
        return Ok(());
    }
    if args.odds_api_key.is_some() || args.sportmonks_token.is_some() {
        return run_providers(args).await;
    }

    let mut client = QuestDbClient::connect(&args.qdb_host, args.qdb_port)
        .await
        .context("connect to QuestDB ILP")?;
    let brain = match args.brain_url {
        Some(url) => Some(BrainClient::new(url, args.brain_timeout_ms)?),
        None => None,
    };

    if let Some(events_path) = args.events.as_deref() {
        let events: Vec<Event> = read_jsonl(events_path).context("load events")?;
        for event in events {
            client.write_line(&event_to_ilp(&event)).await?;
            if let Some(brain) = &brain {
                let decision = brain.send_event(&event).await?;
                client.write_line(&decision_to_ilp(&decision)).await?;
            }
        }
    }

    if let Some(odds_path) = args.odds.as_deref() {
        let odds_list: Vec<Odds> = read_jsonl(odds_path).context("load odds")?;
        for odds in odds_list {
            client.write_line(&odds_to_ilp(&odds)).await?;
            if let Some(brain) = &brain {
                let decision = brain.send_odds(&odds).await?;
                client.write_line(&decision_to_ilp(&decision)).await?;
            }
        }
    }

    Ok(())
}

async fn run_polling(args: Args) -> Result<()> {
    let mut handles = Vec::new();
    let brain = match args.brain_url.clone() {
        Some(url) => Some(BrainClient::new(url, args.brain_timeout_ms)?),
        None => None,
    };

    if let Some(events_url) = args.events_url.clone() {
        let client = QuestDbClient::connect(&args.qdb_host, args.qdb_port)
            .await
            .context("connect to QuestDB ILP (events)")?;
        let cfg = PollConfig {
            url: events_url,
            poll_ms: args.poll_ms,
            min_interval_ms: min_interval_ms(args.max_rps),
            timeout_ms: args.timeout_ms,
            bearer_token: args.bearer_token.clone(),
            dedup_capacity: args.dedup_cap,
            max_backoff_ms: args.max_backoff_ms,
            brain: brain.clone(),
        };
        handles.push(tokio::spawn(async move {
            source::http_poll::poll_events(client, cfg).await
        }));
    }

    if let Some(odds_url) = args.odds_url.clone() {
        let client = QuestDbClient::connect(&args.qdb_host, args.qdb_port)
            .await
            .context("connect to QuestDB ILP (odds)")?;
        let cfg = PollConfig {
            url: odds_url,
            poll_ms: args.poll_ms,
            min_interval_ms: min_interval_ms(args.max_rps),
            timeout_ms: args.timeout_ms,
            bearer_token: args.bearer_token.clone(),
            dedup_capacity: args.dedup_cap,
            max_backoff_ms: args.max_backoff_ms,
            brain: brain.clone(),
        };
        handles.push(tokio::spawn(async move {
            source::http_poll::poll_odds(client, cfg).await
        }));
    }

    if handles.is_empty() {
        anyhow::bail!("polling mode requires --events-url and/or --odds-url");
    }

    for handle in handles {
        let res = handle.await.context("poll task join")??;
        // If a poller exits, return its result (likely an error).
        return Ok(res);
    }

    Ok(())
}

async fn run_ws(args: Args, ws_url: String) -> Result<()> {
    let client = QuestDbClient::connect(&args.qdb_host, args.qdb_port)
        .await
        .context("connect to QuestDB ILP (ws)")?;
    let brain = match args.brain_url.clone() {
        Some(url) => Some(BrainClient::new(url, args.brain_timeout_ms)?),
        None => None,
    };
    let cfg = source::ws::WsConfig {
        url: ws_url,
        bearer_token: args.ws_bearer_token.clone(),
        reconnect_ms: args.ws_reconnect_ms,
        brain,
    };
    source::ws::run_ws(client, cfg).await
}

async fn run_providers(args: Args) -> Result<()> {
    let brain = match args.brain_url.clone() {
        Some(url) => Some(BrainClient::new(url, args.brain_timeout_ms)?),
        None => None,
    };
    let mut handles = Vec::new();

    if let Some(token) = args.sportmonks_token.clone() {
        let leagues = args
            .sportmonks_leagues
            .clone()
            .unwrap_or_default()
            .split(',')
            .filter(|s| !s.is_empty())
            .map(|s| s.trim().to_string())
            .collect::<Vec<_>>();
        if leagues.is_empty() {
            anyhow::bail!("--sportmonks-leagues is required when --sportmonks-token is set");
        }
        let qdb = QuestDbClient::connect(&args.qdb_host, args.qdb_port)
            .await
            .context("connect to QuestDB ILP (sportmonks)")?;
        let cfg = providers::sportmonks::SportMonksConfig {
            token,
            base_url: args.sportmonks_base.clone(),
            leagues,
            poll_ms: args.sportmonks_poll_ms,
            min_interval_ms: min_interval_ms(args.max_rps),
            timeout_ms: args.timeout_ms,
            dedup_capacity: args.dedup_cap,
            max_backoff_ms: args.max_backoff_ms,
            brain: brain.clone(),
        };
        handles.push(tokio::spawn(async move {
            providers::sportmonks::run_sportmonks(qdb, cfg).await
        }));
    }

    if let Some(key) = args.odds_api_key.clone() {
        let sports = args
            .odds_api_sports
            .clone()
            .unwrap_or_default()
            .split(',')
            .filter(|s| !s.is_empty())
            .map(|s| s.trim().to_string())
            .collect::<Vec<_>>();
        if sports.is_empty() {
            anyhow::bail!("--odds-api-sports is required when --odds-api-key is set");
        }
        let qdb = QuestDbClient::connect(&args.qdb_host, args.qdb_port)
            .await
            .context("connect to QuestDB ILP (odds api)")?;
        let cfg = providers::odds_api::OddsApiConfig {
            api_key: key,
            base_url: args.odds_api_base.clone(),
            sports,
            regions: args.odds_api_regions.clone(),
            markets: args.odds_api_markets.clone(),
            poll_ms: args.odds_api_poll_ms,
            min_interval_ms: min_interval_ms(args.max_rps),
            timeout_ms: args.timeout_ms,
            dedup_capacity: args.dedup_cap,
            max_backoff_ms: args.max_backoff_ms,
            brain: brain.clone(),
        };
        handles.push(tokio::spawn(async move {
            providers::odds_api::run_odds_api(qdb, cfg).await
        }));
    }

    if handles.is_empty() {
        anyhow::bail!("provider mode requires --sportmonks-token or --odds-api-key");
    }

    for handle in handles {
        let res = handle.await.context("provider task join")??;
        return Ok(res);
    }

    Ok(())
}

fn min_interval_ms(max_rps: u32) -> u64 {
    if max_rps == 0 {
        return 0;
    }
    let max_rps = max_rps as u64;
    (1000 + max_rps - 1) / max_rps
}

async fn run_http(
    listen: &str,
    host: &str,
    port: u16,
    brain_url: Option<String>,
    brain_timeout_ms: u64,
) -> Result<()> {
    let client = QuestDbClient::connect(host, port)
        .await
        .context("connect to QuestDB ILP")?;
    let brain = match brain_url {
        Some(url) => Some(BrainClient::new(url, brain_timeout_ms)?),
        None => None,
    };

    let state = AppState {
        qdb: Arc::new(Mutex::new(client)),
        brain,
    };

    let app = Router::new()
        .route("/health", get(health))
        .route("/event", post(post_event))
        .route("/odds", post(post_odds))
        .with_state(state);

    let listener = tokio::net::TcpListener::bind(listen)
        .await
        .with_context(|| format!("bind {listen}"))?;

    axum::serve(listener, app).await.context("serve http")?;
    Ok(())
}

async fn health() -> StatusCode {
    StatusCode::NO_CONTENT
}

async fn post_event(State(state): State<AppState>, Json(event): Json<Event>) -> AppResult<StatusCode> {
    {
        let mut client = state.qdb.lock().await;
        client
            .write_line(&event_to_ilp(&event))
            .await
            .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
    }
    if let Some(brain) = &state.brain {
        let decision = brain
            .send_event(&event)
            .await
            .map_err(|e| (StatusCode::BAD_GATEWAY, e.to_string()))?;
        let mut client = state.qdb.lock().await;
        client
            .write_line(&decision_to_ilp(&decision))
            .await
            .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
    }
    Ok(StatusCode::NO_CONTENT)
}

async fn post_odds(State(state): State<AppState>, Json(odds): Json<Odds>) -> AppResult<StatusCode> {
    {
        let mut client = state.qdb.lock().await;
        client
            .write_line(&odds_to_ilp(&odds))
            .await
            .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
    }
    if let Some(brain) = &state.brain {
        let decision = brain
            .send_odds(&odds)
            .await
            .map_err(|e| (StatusCode::BAD_GATEWAY, e.to_string()))?;
        let mut client = state.qdb.lock().await;
        client
            .write_line(&decision_to_ilp(&decision))
            .await
            .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;
    }
    Ok(StatusCode::NO_CONTENT)
}
