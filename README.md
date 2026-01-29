# Vektorr

A deterministic, latency-sensitive decision engine for live sports markets. The system prioritizes capital preservation through strict gating and noise rejection.

## System Design

Vektorr operates on a **fail-closed** principle. If data quality, latency, or market conditions do not meet defined thresholds, the system defaults to **NO BET**.

### Core Constraints
- **Determinism:** The decision pipeline is stateless and reproducible. `f(events, odds)` must yield the exact same result in live and replay modes.
- **Latency Gating:** Hard limits on event-to-decision latency (default 3000ms). Any breach triggers an immediate freeze.
- **Auditability:** Every tick, decision, and rejection is logged to QuestDB with a specific `reason_code`.
- **Isolation:** Ingestion (Spine/Rust) is decoupled from decision logic (Brain/Python) to ensure stability.

## Architecture

| Component | Technology | Responsibility |
|-----------|------------|----------------|
| **Spine** | Rust | Ingests WebSocket/Polling feeds, normalizes data, handles IO. |
| **Brain** | Python | Calculates metrics (TPS, xG), evaluates gates, issues signals. |
| **Storage** | QuestDB | High-throughput ILP ingestion for events and time-series data. |
| **Execution** | Python | Manages risk, sizing (Kelly), and staged rollout (Paper $\to$ Live). |

## Operational Status

| Module | Status | Notes |
| :--- | :--- | :--- |
| **Ingestion** | Ready | SportMonks & Odds API adapters implemented in Rust. |
| **Logic** | Ready | Phase 2 models (Dynamic Lambda, TPS Velocity) active. |
| **Safety** | Active | Kill-switches for drawdown and latency spikes enabled. |
| **Integration** | Pending | Requires API keys and active Docker container to run. |

## Directory Structure

- `spine/` - Rust source for data ingestion.
- `brain/` - Python source for models and API.
- `execution/` - Risk management and order placement logic.
- `infra/` - Infrastructure configuration (Docker, QuestDB).
- `tools/` - Utilities for backtesting, simulation, and data analysis.

## Usage

This software is designed for automated operation. Manual intervention is required only for:
1. Configuration changes (`config.yaml`).
2. Unfreezing the system after a circuit breaker trip.
3. Reviewing daily performance logs.
