use crate::brain::DecisionResponse;
use crate::types::{Event, Odds};

pub fn event_to_ilp(event: &Event) -> String {
    let latency_ms = (event.t_recv - event.t_event).num_milliseconds();
    let team = event.team.as_deref().unwrap_or("UNKNOWN");
    let ts = event.t_event.timestamp_nanos_opt().unwrap_or(0);

    format!(
        "events,match_id={},team={},event_type={} xg={},latency_ms={} {}",
        escape_tag(&event.match_id),
        escape_tag(team),
        escape_tag(&event.event_type),
        event.xg,
        latency_ms,
        ts
    )
}

pub fn odds_to_ilp(odds: &Odds) -> String {
    let latency_ms = (odds.t_recv - odds.t_seen).num_milliseconds();
    let ts = odds.t_recv.timestamp_nanos_opt().unwrap_or(0);

    format!(
        "odds,match_id={},market={},selection={} price={},is_suspended={}i,latency_ms={} {}",
        escape_tag(&odds.match_id),
        escape_tag(&odds.market),
        escape_tag(&odds.selection),
        odds.price,
        if odds.is_suspended { 1 } else { 0 },
        latency_ms,
        ts
    )
}

pub fn decision_to_ilp(decision: &DecisionResponse) -> String {
    let ts = decision.timestamp.timestamp_nanos_opt().unwrap_or(0);
    let selection = decision.selection.as_deref().unwrap_or("NA");
    let market = decision.market.as_deref().unwrap_or("NA");
    let odds_price = decision.odds_price.unwrap_or(0.0);
    let exec_status = decision.exec_status.as_deref().unwrap_or("NA");
    let price_filled = decision.price_filled.unwrap_or(0.0);
    let slippage = decision.slippage.unwrap_or(0.0);

    format!(
        "decisions,match_id={},reason={},tps_label={},market={},selection={},exec_status={} can_bet={}i,xg_10m={},latency_p95={},odds_price={},price_filled={},slippage={},minute={}i {}",
        escape_tag(&decision.match_id),
        escape_tag(&decision.reason),
        escape_tag(&decision.tps_label),
        escape_tag(market),
        escape_tag(selection),
        escape_tag(exec_status),
        if decision.can_bet { 1 } else { 0 },
        decision.xg_10m,
        decision.latency_p95,
        odds_price,
        price_filled,
        slippage,
        decision.minute,
        ts
    )
}

fn escape_tag(value: &str) -> String {
    value
        .replace(',', "\\,")
        .replace(' ', "\\ ")
        .replace('=', "\\=")
}
