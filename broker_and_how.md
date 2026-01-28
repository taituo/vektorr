# Broker & Execution: How It Works (Summary)

This document consolidates the broker/execution discussion and how it fits the current architecture.

## 1. Two Execution Modes

### A) Manual Execution (Current / Recommended Start)
- System acts as a **signal engine** only.
- You place bets manually at the bookmaker/exchange of your choice.
- Benefits: zero integration complexity, no API limits, no broker onboarding.
- Trade-off: human latency and missed fills in fast markets.

### B) Automated Execution (Broker/Exchange)
- Requires API access and stable market mapping.
- Best when you want “end-to-end” automation.
- Requires more capital, operational discipline, and broker compliance.

## 2. Broker / Aggregator Reality (Non-manual)

### A) Brokers/Aggregators (e.g. Sportmarket, BetInAsia/BLACK, AsianConnect)
- **Single wallet** and unified API across multiple books (often MollyBet-type platforms).
- Access may require minimum turnover, setup fees, or account approval.
- Good for niche leagues *if* you can access Pinnacle/Asian liquidity.

### B) Exchanges (Betfair/Matchbook)
- Great API, no account limiting for winning.
- Niche-league liquidity can be poor; many orders remain unmatched.

## 3. Core Technical Challenge: Entity Mapping
- Your data provider uses one naming convention.
- Broker uses another (different team/league IDs).
- You need a **mapping table** to reconcile:
  - ProviderTeamID → BrokerTeamID
  - ProviderMatchID → BrokerMarketID

Without this, automation fails (wrong match, wrong market, or mismatched selection).

## 4. Execution Flow (Automated)
1) **Brain** generates `BET_READY` signal.
2) **Execution Adapter** resolves match + market (mapping table).
3) **Get Quote** (best price / max stake).
4) **Place Order** (limit order preferred).
5) **Receive Fill** (or reject/timeout).
6) **Record** in ledger (QuestDB / SQL).

## 5. Maker vs Taker (Niche Leagues)
- **Manual/Taker:** take available odds immediately.
- **Automated/Maker:** place a limit order at better odds and wait.
- In slow markets, maker can achieve better prices.
- But requires API + order management logic.

## 6. What We Have Today
- **Spine → Brain → QuestDB** pipeline is live.
- Execution is *not* automated.
- Decision signals can be used for manual bets.

## 7. What Is Needed for Automation
1) Broker account + API credentials.
2) Mapping table (provider → broker IDs).
3) Execution adapter (limit orders + status polling).
4) Risk limits + staking rules.
5) Settlement logic based on actual outcomes.

## 8. Recommended Path
- **Short term:** Manual execution, use system as “signal engine”.
- **Medium term:** Build mapping table + mock execution (paper trading).
- **Long term:** Integrate broker API once volume/edge is proven.

## 9. Checklist (Before Automating)
- [ ] Can you maintain P95 < 3s? (edge survives?)
- [ ] Are signals stable on 50+ matches?
- [ ] Do you have broker API access?
- [ ] Mapping table is >95% accurate.
- [ ] Risk limits and staking defined.

## 10. Minimal Schema Needed (Suggested)
- `match_map(provider, provider_match_id, broker_match_id, kickoff, home, away)`
- `team_map(provider, provider_team_id, broker_team_id, name)`
- `market_map(broker_market_id, selection_map)`

---

If you want, I can draft the **Execution Adapter interface** next (trait + stub), or the **mapping table schema** in QuestDB/Postgres.
