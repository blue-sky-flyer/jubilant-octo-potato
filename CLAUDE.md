# Iran War Economic Impact Framework — Project Context

## What this project is

This folder contains a structured analytical framework for tracking and reasoning about the economic and geopolitical impacts of the 2026 Iran-US/Israel war, which began February 28, 2026 with coordinated US-Israeli airstrikes on Iran.

The framework was designed to be loaded into Claude and used as an interactive reference — ask any question by sector, geography, scenario, or indicator.

## Primary files

- `iran-war-impact-framework.md` — the daily briefing (delta-only: what changed in the last 24 hours).
- `iran-war-standing.md` — standing sections (Gulf adaptation, SPR Day 0, Disintegration Tracker, Covert Actions Ledger, etc.), each with a "last materially changed" date. The briefing links here instead of repeating them.
- `iran-war-context.md` — rolling context for the daily agent: factual corrections, evidence/format rules, conflict arc, weekly summaries.
- `iran-war-reference.md` — historical reference (scenario history, impact catalog, update log).

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

## Current state

Always check the Daily Briefing (top of `iran-war-impact-framework.md`) and the Conflict Arc in `iran-war-context.md` on origin/main — the local copy goes stale between sessions. Do not rely on any snapshot written into this file.

## User context

The owner uses this framework for professional investment/strategic analysis and publishes a daily newsletter. Responses should be structured, evidence-grounded, and calibrated — flag uncertainty clearly. Use the scenario ladder and impact catalog as the backbone for any analysis.

---

# Conversational Instructions

When a conversation about this framework identifies a factual correction or a significant analytical insight, proactively offer to update `iran-war-context.md` directly before the conversation ends — corrections and durable insights belong in the Conflict Arc as structural facts. This is the feedback path from conversations back into the daily agent's corpus.

---

*Daily agent instructions are maintained in the remote trigger configuration, not here.*
