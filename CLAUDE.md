# Iran War Economic Impact Framework — Project Context

## What this project is

This folder contains a structured analytical framework for tracking and reasoning about the economic and geopolitical impacts of the 2026 Iran-US/Israel war, which began February 28, 2026 with coordinated US-Israeli airstrikes on Iran.

The framework was designed to be loaded into Claude and used as an interactive reference — ask any question by sector, geography, scenario, or indicator.

## Primary files

- `iran-war-impact-framework.md` — the daily briefing (delta-only: what changed in the last 24 hours).
- `iran-war-standing.md` — standing sections (Gulf adaptation, SPR Day 0, Disintegration Tracker, Covert Actions Ledger, etc.), each with a "last materially changed" date. The briefing links here instead of repeating them.
- `iran-war-context.md` — rolling context for the daily agent: factual corrections, evidence/format rules, conflict arc, weekly summaries.
- `iran-war-reference.md` — historical reference (scenario history, impact catalog, update log).
- `iran-war-questions.md` — the owner's open analytical questions (the agenda). The agent updates each question's current read, evidence log and what-would-change-it every run; only the owner adds or retires questions.
- `data/signals/<date>.json` — structured signals collected each run by `scripts/signals.py` (PortWatch chokepoints and ports with 2025 baselines, rial/Tether/gold, Iran internet connectivity, Israel Home Front alerts, airspace snapshot, FIRMS thermal anomalies). A time series accumulates in git.

Example prompts:
- "What is the current scenario probability?"
- "What are the second-order impacts on agriculture?"
- "Which sectors are most exposed to a Hormuz closure?"
- "What precursor events should I watch for S3 escalation?"
- "Which ETFs are most exposed to the current scenario?"

## Framework structure

- **Daily Briefing** — top of the file, updated by the daily agent each morning. Written for a reader who has already read ISW and the wires: it leads with the two or three open questions where the read moved (data, confidence, what would change it), then headlines as links only, then market and flow readings, scenario update, and standing-section deltas. Under ~900 words.
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

*The daily agent runs entirely via GitHub Actions (remote trigger deleted 2026-08-12). `.github/workflows/daily-briefing.yml` runs `scripts/generate_briefing.py` once a day, triggered by a cron-job.org POST to the `workflow_dispatch` endpoint at 11:50 UTC (managed with `scripts/cronjob.py`; API key at `~/.config/cron-job-org/api_key`). There is no GitHub `schedule` trigger. Manual `workflow_dispatch` takes a search-provider override and a `force` flag. Pipeline (redesigned 2026-09-19): signals → query planning (Claude Sonnet 5 reads the question ledger and signals, writes ~24 targeted queries) → Tavily news search → Claude Opus 5 analyses and writes the briefing, the updated standing file and the updated question ledger in one response → challenger cross-check → commit. The agent's instructions live in the script's `CORE_PROMPT`/`CORE_STRUCTURE`/`PLAN_PROMPT` constants, plus the corrections and evidence/format rules at the top of `iran-war-context.md`, loaded every run. To change what the briefing investigates, edit `iran-war-questions.md`. Optional secret `FIRMS_MAP_KEY` (free NASA key) enables thermal-anomaly collection. Pipeline status and history: `STATE.md`.*

*Gemini key provenance: the Actions secret `GEMINI_API_KEY` (used by the `gemini_diff` challenger cross-check) is the key named `jubilant-octo-potato` in Hanoz's personal GCP project "Gemini Keys" (ID `gen-lang-client-0492564449`), created 2026-08-10, restricted to the Generative Language API. Rotate in GCP console → APIs & Services → Credentials, then `gh secret set GEMINI_API_KEY`. That project also holds FabricateIQ's key — never delete it.*
