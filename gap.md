# Vektorr Implementation Gap Analysis

Last updated: 2026-01-29

## Summary

| Category | Items | Complete | Status |
|----------|-------|----------|--------|
| P0 Critical Gates | 4 | 4 | ✅ Done |
| P1 Stability | 3 | 3 | ✅ Done |
| P2 Operational | 3 | 3 | ✅ Done |
| P3 Testbench | 4 | 4 | ✅ Done |
| P4 Converters | 4 | 4 | ✅ Done |
| P5 Infrastructure | 3 | 3 | ✅ Done |

**Tests: 201 passing**

---

## P0 Items - COMPLETE ✅

### P0.1 Vig Correction ✅
- **File**: `brain/engine.py:32-38`
- **Method**: `_remove_vig(price_map)` normalizes implied probabilities
- **Config**: `VIG_ENABLED: true` (config.yaml)
- **Test**: N/A (integrated into MMS context)

### P0.2 Execution-Risk EV + Gate ✅
- **File**: `brain/engine.py:253-267`
- **Gate**: `EXEC_RISK_*` / `SLIPPAGE_HIGH`
- **Config**: `EXECUTION_RISK_ENABLED: true`, `EXEC_MIN_FILL: 0.60`, `EXEC_MAX_SLIPPAGE: 0.05`
- **Test**: `test_gate_execution_risk_fill_rate` ✅

### P0.3 DISCONFIRM + PRICE_MOVED ✅
- **File**: `brain/engine.py:214-228`
- **Gates**: `PRICE_MOVED`, `DISCONFIRM_PRICE_MOVED`
- **Schema**: `MatchState.odds_price_prev`, `odds_price_signal`, `odds_signal_age_s`
- **Config**: `PRICE_MOVE_LIMIT: 0.03`, `DISCONFIRM_LIMIT: 0.03`, `DISCONFIRM_MAX_AGE_S: 120`
- **Tests**: `test_gate_price_moved`, `test_gate_disconfirm_price_moved` ✅

### P0.4 MMS Gate ✅
- **File**: `brain/engine.py:230-251`
- **Gate**: `MMS_LOW`
- **Config**: `MMS_GATE_ENABLED: true`, `MMS_MIN: 0.03`
- **Test**: `test_gate_mms_low` ✅

---

## P1 Items - COMPLETE ✅

### P1.5 Dynamic lambda(t) ✅
- **Status**: Wired into `brain/engine.py:147-153`
- Uses `DynamicLambdaModel` when `use_phase2_models=True`
- Adjusts λ based on match context (score, TPS, xG, red cards)

### P1.6 Real-time CLV tracking ✅
- **File**: `tools/clv_updater.py`
- **API**: `DecisionsTracker.get_pending_clv_updates()`, `update_closing_odds()`
- Runs as standalone scheduler or via brain API
- Mock fetcher included for testing

### P1.7 Bankroll single source ✅
- **File**: `execution/bankroll.py`
- **Class**: `Bankroll` with `add()`, `subtract()`, `settle_bet()`
- Subscriber pattern for component sync
- `sync_metrics_tracker()` helper for KillSwitch integration
- **Tests**: 8 tests in `TestBankroll`

### P1.8 TPS-adaptive latency ✅ (bonus)
- **File**: `brain/engine.py:198-204`, `engine.py:91-98`
- **Config**: `LATENCY_LIMITS: {LOW: 4.0, MID: 3.0, PRESS: 2.0, CHAOS: 1.5}`
- Stricter latency limits in volatile states
- **Test**: `TestTPSAdaptiveLatency`

---

## P2 Items - COMPLETE ✅

### P2.8 MonitorAgent ✅
- **File**: `brain/agents/monitor_agent.py`
- Tracks latency, error rate, staleness, fill rate
- Raises alerts (INFO, WARNING, CRITICAL)
- **Tests**: 6 tests in `TestMonitorAgent`

### P2.9 ReportAgent ✅
- **File**: `brain/agents/report_agent.py`
- Generates daily performance reports
- Tracks decisions, outcomes, CLV, streaks
- Delivery callbacks for Telegram/Slack
- **Tests**: 6 tests in `TestReportAgent`

### P2.10 KillSwitch in Live Path ✅
- **File**: `brain/service.py`
- Checks `kill_switch.is_running()` before decisions
- Checks metrics snapshot against triggers
- **Endpoints**:
  - `GET /kill_switch/status`
  - `POST /kill_switch/freeze`
  - `POST /kill_switch/unfreeze`
  - `POST /kill_switch/record_bet`
  - `GET /kill_switch/history`

---

## P3 Items - FUTURE ⏳

### P3.11 QuestDB Shared State
- Spine uses QuestDB
- Brain uses JSONL
- Not critical for MVP

### P3.12 Provider Integration
- Mock server works for testing
- Real exchange API not implemented

---

## Current Architecture

```
Live path (brain/service.py):
  Spine -> /event, /odds -> BettingEngine.evaluate_gates() -> decisions.jsonl

  Gates in evaluate_gates():
  1. LATENCY_HIGH (L_MAX)
  2. MARKET_SUSPENDED
  3. QUALITY_LOW (TPS=LOW or xG<0.2)
  4. PRICE_MOVED (new)
  5. DISCONFIRM_PRICE_MOVED (new)
  6. MMS_LOW (new)
  7. EXEC_RISK_* / SLIPPAGE_HIGH (new)
  8. EV_LOW

Orchestrator path (orchestrator.py):
  Full Phase 2-4 integration
  KillSwitch + StagedRollout enforced
  LearningAgent + Oversight
```

---

## Test Coverage

| Component | Tests | Status |
|-----------|-------|--------|
| Engine gates | 22 | ✅ All pass |
| Phase 2 models | 35 | ✅ All pass |
| Phase 3 agents | 34 | ✅ All pass |
| Phase 4 safety | 42 | ✅ All pass |
| Orchestrator | 13 | ✅ All pass |
| Wallet | 4 | ✅ All pass |
| Execution/Staking | 10 | ✅ All pass |
| P5 Integration | 15 | ✅ All pass |
| **Total** | **201** | ✅ |

P0 gate tests:
- `test_gate_price_moved` ✅
- `test_gate_disconfirm_price_moved` ✅
- `test_gate_mms_low` ✅
- `test_gate_execution_risk_fill_rate` ✅

P1 tests:
- `TestBankroll` (8 tests) ✅
- `TestTPSAdaptiveLatency` ✅

P2 tests:
- `TestMonitorAgent` (6 tests) ✅
- `TestReportAgent` (6 tests) ✅

improve_more.md tests:
- `test_weighted_xg_*` (2 tests) ✅
- `test_tps_velocity_*` (2 tests) ✅
- `TestStealth` (6 tests) ✅
- `TestKellyStaking` (7 tests) ✅

---

## improve_more.md Items - Status

| Item | Status |
|------|--------|
| Dynamic Decay (weighted xG) | ✅ `calculate_weighted_xg()` |
| Pressure Velocity (TPS_V) | ✅ `calculate_tps_with_velocity()` |
| Market Disconfirm 2.0 | ✅ `DISCONFIRM_PRICE_MOVED` gate |
| Smart Staking (Kelly) | ✅ `execution/calculate_kelly_stake()` + live path |
| Anti-Detection (Stealth) | ✅ `execution/stealth.py` |
| Automatic Kill-Switch | ✅ `execution/kill_switch.py` |
| Docker Compose | ✅ `docker-compose.yml` |
| Health Checks | ✅ MonitorAgent |
| Telegram Bot | ✅ `tools/telegram_bot.py` |

---

## Testbench Infrastructure ✅

### Generators (tools/generators/)
- **EventGenerator** - Realistic match events with xG, latency, tempo
- **OddsGenerator** - Price movement, event reactions, value injection
- **MockBroker** - Exchange simulation with fill/reject/slippage
- **ChaosInjector** - Edge case generation (late drama, red cards, VAR)

### Testbench Runner (tools/testbench_runner.py)
- Runs synthetic matches against live engine
- Tracks P&L, gate rejections, trade outcomes
- Configurable chaos injection
- Results output to `results/simulation_latest.json`

### Usage
```bash
PYTHONPATH=. python3 tools/testbench_runner.py  # 100 matches default
```

---

## Data Converters ✅

### Universal Converter (tools/converters/)
- **SportMonksConverter** - Events + odds from SportMonks API
- **TheOddsApiConverter** - Odds from The Odds API
- **BetsApiConverter** - Events + odds from BetsAPI
- **CSVConverter** - Flexible column mapping for historical data

### Usage
```python
from tools.converters import UniversalConverter

converter = UniversalConverter()
event = converter.convert(raw_data)  # Auto-detects source
odds = converter.convert(raw_data, source='odds_api')
```

---

## Phase 5 Infrastructure ✅

### QuestDB Integration
- **File**: `brain/questdb_client.py`
- ILP (InfluxDB Line Protocol) for fast writes
- Writes events, odds, decisions to QuestDB
- Enable with `QUESTDB_ENABLED=true`

### Provider Poller
- **File**: `spine/provider_poller.py`
- Polls SportMonks (events) and The Odds API (odds)
- Auto-converts and forwards to Brain
- Configure in `spine/provider_config.yaml`

### WebSocket Feed
- **File**: `spine/websocket_feed.py`
- Real-time streaming data ingestion
- Message format: `{"kind": "event"|"odds", "data": {...}}`
- Port 8001

### Docker Compose
Updated with all services:
- brain (port 8000)
- questdb (ports 9000, 9009, 8812)
- provider-poller
- websocket-feed (port 8001)
- telegram-bot (optional, `--profile notifications`)

---

## Remaining Work

### Production Readiness
1. Add actual API keys to `spine/provider_config.yaml`
2. Configure Telegram bot credentials
3. Set up monitoring/alerting dashboards
4. Load testing with testbench
