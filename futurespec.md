# FUTURE SPECIFICATION (Vision vs. Reality)

**Last Updated:** 2026-01-28
**Status:** Active Implementation Phase (MVP Completed)

## 1. Core Philosophy: "Survival First"

We are building a High-Frequency Trading (HFT) system for sports betting.
*   **Edge:** Comes from speed (low latency), context (TPS), and market execution (Maker vs Taker).
*   **Safety:** The system fails closed (Freezes) rather than guessing.

---

## 2. The Role of AI (Evolutionary Path)

This is the critical distinction from "Get Rich Quick" bots. We do not trust the LLM with money yet. We trust it with *context*.

### Phase 1: The Copilot (Current Status) ✅
*   **Role:** Architect, Coder, and Summarizer.
*   **Action:** The AI writes the Python/Rust code, explains "Why NO_BET?", and builds the TUI.
*   **Control:** 100% Human. The human presses the button (HITL) or defines the hard-coded logic in Python.
*   **Safety:** Hard gates in code (if latency > 3s, block).

### Phase 2: The Scout (Next Step) 🚧
*   **Role:** Semantic Signal Processor.
*   **Action:** LLM reads Twitter/Commentary and sets a "Tag" (e.g., `Context: STAR_PLAYER_INJURED`).
*   **Control:** The Python Brain reads this tag and *adjusts* the math (e.g., lowers xG threshold), but simply does not fire based on text alone.
*   **Safety:** The math (EV > 0) is still the final gatekeeper.

### Phase 3: Constrained Autonomy (The Goal) 🔮
*   **Role:** The Driver (with limits).
*   **Action:** "Maybe someday it can do what a human does without breaking rules."
*   **Mechanism:** The LLM can execute trades, BUT it operates inside a **Rust-based Sandbox**.
    *   It cannot bet more than `MAX_STAKE`.
    *   It cannot bet if `P95_LATENCY` is high.
    *   It cannot override the `Stop-Loss`.
*   **Result:** It mimics human intuition but is physically prevented from "tilting" or making technical errors.

---

## 3. Architecture: As-Built (Jan 2026)

### A. The Spine (Rust)
*   **Status:** operational.
*   **Function:** Ingests data, logs to QuestDB, pushes to Brain.
*   **Performance:** Zero-latency pass-through.

### B. The Brain (Python API)
*   **Status:** Operational (MVP).
*   **Function:** Holds state (`MatchState`), runs `BettingEngine`, calculates `TPS`.
*   **Key Feature:** `mappings.yaml` for entity resolution (HJK = Helsinki).

### C. The Interface (Textual TUI)
*   **Status:** "The Matrix Monitor" is live.
*   **Function:** Visualizes the "Heartbeat" of the market. Allows the human to "pick raisins" (Manual Execution) based on algorithmic signals.

### D. The Machine (Execution)
*   **Status:** Planned / In-Progress.
*   **Strategy:** Start with Manual/Betfair. Move to MollyBet/Black (Broker) only when volume justifies cost.

---

## 4. Next Concrete Steps

1.  **Connect Real Data:** Replace `MockProvider` with a real WebSocket/Polling feed.
2.  **Betfair Adapter:** Implement `brain/execution/betfair.py` to enable semi-auto execution.
3.  **Persistence:** Move state from memory to Redis/SQLite to survive restarts.

---

> "Matematiikka + Nopeus = Edge. Ihminen on jarru."
