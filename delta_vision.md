# delta_vision.md

Gap analysis between `futurespec.md` (vision summary) and `all.md` (master spec).

Last updated: 2026-01-28
Scope: only what is in this repo right now.

---

## 1) Executive summary

`futurespec.md` is a short "vision + status" note. `all.md` is a full master
spec with hard requirements, governance, replay, monitoring, and extended
architecture. The gap is mostly "missing scope and constraints" rather than
wrong statements. The main risk is that teams follow `futurespec.md` and skip
the compliance and validation parts defined in `all.md`.

---

## 2) Gaps by category (what `futurespec.md` does not cover)

### A) Locked scope and non‑negotiables
- Leagues, markets, staking limits, and "NO BET default" are locked in `all.md`
  but not repeated in `futurespec.md`.
- Market scope in `all.md` includes OU (0.5/1.5/2.5), Next Goal, Double Chance.

### B) Data contracts and semantics (normative)
- `all.md` defines strict event/odds/clock/decision/execution schemas and
  mandatory timestamps (t_event / t_recv / t_seen).
- Vig‑less probability, EV definition, and "seen vs fill" rules are missing
  from `futurespec.md`.

### C) Match lifecycle and loop cadence
- `all.md` defines PRE/LIVE/POST lifecycle and Loop A/B/C schedules.
- `futurespec.md` only hints at "speed" and "HFT" without specifying cadence.

### D) Governance and risk controls
- `all.md` requires freeze rules, stop‑loss, change control, and audit trail.
- `futurespec.md` does not map these to concrete operational requirements.

### E) Replay, determinism, and validation
- `all.md` mandates replay, test matrix, and determinism checks.
- `futurespec.md` lists no replay or validation requirements.

### F) Observability and ops
- `all.md` includes KPIs, alerts, dashboards, and runbooks.
- `futurespec.md` lacks these operational expectations.

### G) Architecture depth
- `all.md` describes Hub‑Spoke‑Frontier topology, Redis state store, and
  service responsibilities in detail.
- `futurespec.md` only describes Spine/Brain/Interface/Execution at a high level.

### H) LLM role boundaries
- `all.md` has explicit "LLM vs ML" rules (where LLM is allowed and forbidden).
- `futurespec.md` covers phases (Copilot/Scout/Autonomy) but does not include
  the stricter prohibitions.

---

## 3) Potential contradictions / ambiguities

- "HFT + zero‑latency" vs `all.md` loop cadence (1–60s). Needs a clear
  definition of "real‑time" in this system.
- `futurespec.md` suggests Redis/SQLite for persistence, while current Phase‑1
  uses QuestDB + ILP. This should be clarified as intentional divergence.
- `all.md` includes extended v11.0 features (audio, OFI, front‑running tests).
  `futurespec.md` should explicitly mark those as Phase 2+ only.

---

## 4) Practical deltas to apply

1) Add a short "Locked scope" section to the future spec.
2) Reference the normative data contracts and loop cadence from `all.md`.
3) Add a "Validation and replay" requirement checklist.
4) Add an "Ops" block: KPIs, alerts, runbook ownership.
5) Clarify LLM boundary rules: "LLM is context‑only, never decision gate."
6) Resolve the "HFT vs loop cadence" wording to avoid misleading expectations.

---

## 5) What is already aligned

- Phase 1 is correctly described as "Copilot" with hard gates and HITL.
- Spine/Brain/Execution split matches the current repo structure.

