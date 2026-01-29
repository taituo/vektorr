# Research: Soft-to-Hard Signals from the Niche Internet (2026)

## The Core Thesis
We are moving beyond "Event Data" (Shots, Goals) to "Narrative Data" (Sentiment, Rumor, Panic).
The goal is to detect the **"Irvistys" (Grimace)** before it becomes a **"Substitution"**.

---

## 1. The Data Sources (Beyond X/Reddit)
To find true edge, we must look where the "Degens" and "Insiders" live.

### Tier 1: The Mainstream (Laggy)
- **X.com (Twitter):** Good for breaking news, but heavily botted.
- **Reddit (r/soccer, r/sportsbook):** Good for consensus sentiment, but often slow.

### Tier 2: The Enthusiast Niche (Faster)
- **Discord Servers:** Specific betting communities (often invite-only).
- **Telegram Channels:** The heart of "Tipster" culture and courtside reporting.
- **Twitch/Kick Chats:** Real-time reaction to video feeds (faster than video itself).

### Tier 3: The Deep Niche (Alpha Source)
- **Localized Forums:**
  - *Flashscore comments:* Often toxic, but extremely fast local reactions.
  - *Futbolgrad (Russia/EE):* Insider team news.
  - *Hupu (China):* Massive volume, often faster on Asian market moves.
  - *Naver (Korea):* E-sports and local league dominance.
- **Specific Fan Forums:** (e.g., RedCafe for ManUtd) - "He's looking injured in warmups".

---

## 2. The Mechanics of Extraction (Soft-to-Hard)

How do we turn "shitposting" into a Probability Float?

### Step A: The "Grimace" Detector (Vision/Text)
- **Input:** "Mbappe holding hamstring" (Text) OR Screenshot of player down (Vision).
- **LLM Agent:** "Is this a tactical timewaste or a real injury?"
- **Confidence Score:** 0.0 - 1.0.

### Step B: The Panic Index (Sentiment)
- Monitor keywords: "sell", "rip", "gg", "broken", "fraud".
- Calculate **Velocity:** How fast are these words appearing?
- **Signal:** If Velocity > 3.0 sigma -> **PANIC DETECTED**.

### Step C: The Hardening (Execution)
1. **Soft Signal:** "Panic detected on X about Mbappe."
2. **Hard Check:** Check Odds API. Has PSG odds moved?
3. **Gap Finding:** If Sentiment = PANIC but Odds = STABLE -> **EXECUTE**.

---

## 3. Architecture for Niche Ingest
We cannot scrape everything. We must use **Snipers**.

1.  **Discovery Agent:** Scans mainstream (X/Reddit) for *topics* (e.g., "Injury").
2.  **Sniper Agent:** Deploys to niche sources (Discord/Forum) specific to that topic.
3.  **Synthesizer:** Aggregates conflicting reports (e.g., "It's just a cramp" vs "He's crying").

---

## 4. Polymarket Application
This pipeline is 1:1 applicable to Prediction Markets.
- *Source:* "Trump rally cancelled" (Local news site in Ohio).
- *Niche:* Local political forum discussions.
- *Mainstream:* CNN picks it up 30 mins later.
- *Trade:* Buy "NO" on "Will Trump hold rally?" contract immediately.

---

## 5. Next Steps (Actionable)
1. [ ] **List Building:** Curate a list of 50 high-signal Telegram/Discord channels.
2. [ ] **LLM Parser:** Build a prompt that extracts "Event, Entity, Sentiment" from chat logs.
3. [ ] **Correlation Test:** overlay Chat Velocity with Odds Movement to prove the edge.