# Botbet Testbench: LLM-Generated Generators

This directory contains the "New Way" of testing: using LLM-generated code to produce infinite, realistic data.

## Components

1.  **`event_generator.py`**: Simulates match events (SHOT, GOAL, RED_CARD, etc.) based on team strengths and tempo.
2.  **`odds_generator.py`**: Produces realistic live odds ticks that react to events.
3.  **`mock_broker.py`**: Simulates a betting exchange with realistic fill/reject, slippage, and latency.
4.  **`chaos_injector.py`**: Injects edge cases like late-game drama, VAR overturns, and multiple red cards.
5.  **`team_profiles.py`**: Pre-defined characteristics for 500+ (well, dozens for now) teams and leagues.
6.  **`historical_remixer.py`**: Mutates real historical data into new scenarios.

## Usage

### Run a Massive Simulation

To run a simulation of 50 matches and see the P&L of the current `BettingEngine`:

```bash
export PYTHONPATH=$PYTHONPATH:.
python3 tools/testbench_runner.py
```

### Create a New Generator

If you need a new type of generator (e.g., for a different sport or market):
1.  Define the requirements.
2.  Use the Gemini CLI to generate the Python code.
3.  Add it to this directory.

## Philosophy

Don't generate data. Generate **generators**. One good generator is worth a million lines of static JSON.
