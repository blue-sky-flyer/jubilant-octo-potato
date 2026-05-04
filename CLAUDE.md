# Iran War Economic Impact Framework — Project Context

## What this project is

This folder contains a structured analytical framework for tracking and reasoning about the economic and geopolitical impacts of the 2026 Iran-US/Israel war, which began February 28, 2026 with coordinated US-Israeli airstrikes on Iran.

The framework was designed to be loaded into Claude and used as an interactive reference — ask any question by sector, geography, scenario, or indicator.

## Primary file

- `iran-war-impact-framework.md` — the main framework document.

Example prompts:
- "What is the current scenario probability?"
- "What are the second-order impacts on agriculture?"
- "Which sectors are most exposed to a Hormuz closure?"
- "What precursor events should I watch for S3 escalation?"
- "Which ETFs are most exposed to the current scenario?"

## Framework structure

- **Daily Briefing** — top of the file, updated by the daily agent each morning
- **Background** — timeline of key events since Feb 28
- **Scenario Ladder** — 5 escalation scenarios (S1–S5) with probabilities and trigger events
- **Impact Catalog** — tiered impacts (T1: 0–3 months, T2: 3–12 months, T3: structural/long-run)
- **Update Log** — bottom of file, one row per agent run

## Current state as of last update (2026-03-26)

- Active scenario: **S2 — Partial Hormuz Disruption (45% probability)**
- Brent crude: ~$110/bbl (+53% since war start)
- Strait of Hormuz tanker traffic: ~3/day vs. 100+ pre-war
- US military campaign to reopen Hormuz ongoing (launched March 19)
- Peace negotiations via intermediaries — outcome uncertain
- Khamenei killed in initial strikes — disrupts Iranian nuclear command (lowers S4 risk)

## User context

The owner uses this framework for professional investment/strategic analysis and publishes a daily newsletter. Responses should be structured, evidence-grounded, and calibrated — flag uncertainty clearly. Use the scenario ladder and impact catalog as the backbone for any analysis.

---

# Conversational Instructions

When a conversation about this framework identifies a factual correction or a significant analytical insight, proactively offer to update `iran-war-context.md` directly before the conversation ends — corrections and durable insights belong in the Conflict Arc as structural facts. This is the feedback path from conversations back into the daily agent's corpus.

---

*Daily agent instructions are maintained in the remote trigger configuration, not here.*
