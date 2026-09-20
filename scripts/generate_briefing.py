#!/usr/bin/env python3
"""
Daily Iran-War briefing generator (GitHub Actions).

Pipeline (redesigned 2026-09-19 — question-driven, data-first):
  0. SIGNALS: scripts/signals.py pulls structured data (PortWatch chokepoints and
     ports with 2025 baselines, rial/Tether/gold, Iran internet connectivity,
     Israel Home Front alerts, airspace snapshot, FIRMS thermal anomalies) and
     stores data/signals/<date>.json in the repo.
  1. PLAN: a planner model reads the owner's open-question ledger
     (iran-war-questions.md), today's signals and yesterday's briefing, and
     writes today's targeted search queries. A small fixed core set is added.
  2. SEARCH: Tavily runs the queries (news, last few days, full text).
  3. ANALYSE + WRITE: Claude Opus 5 (adaptive thinking) reads the ledger, the
     signals, the evidence pack and the context, and returns three documents
     in one response: the briefing, the updated standing file, the updated
     question ledger.
  4. CROSS-CHECK: challenger models (Gemini + open models via OpenRouter) read
     the same evidence and the briefing's calls and note where they differ.
  5. ASSEMBLE and write iran-war-impact-framework.md, iran-war-standing.md,
     iran-war-questions.md. The workflow commits everything incl. data/.

Design notes:
  - The core brief is the only hard-fail path. Signals, planner, search and
    challengers degrade to a noted stub, never abort.
  - The briefing is written for a reader who has already read ISW and the
    wires: it leads with the analytical calls that moved, not the news.
"""

import os
import re
import sys
import json
import datetime
import requests
from anthropic import Anthropic

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from signals import build_signals  # noqa: E402

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
CORE_MODEL = "claude-opus-5"              # analysis + writing
PLANNER_MODEL = "claude-sonnet-5"         # query planning (cheap)
CORE_EFFORT = "high"

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
OPENROUTER_MODELS = [
    ("DeepSeek-V3", "deepseek/deepseek-chat"),
    ("Qwen",        "qwen/qwen3-next-80b-a3b-instruct"),
    ("Llama 3.3",   "meta-llama/llama-3.3-70b-instruct"),
]

WAR_START = datetime.date(2026, 2, 28)
REPO_FILE = "iran-war-impact-framework.md"
CONTEXT_FILE = "iran-war-context.md"
REFERENCE_FILE = "iran-war-reference.md"
STANDING_FILE = "iran-war-standing.md"
QUESTIONS_FILE = "iran-war-questions.md"
GH = "https://github.com/blue-sky-flyer/jubilant-octo-potato/blob/main/"
REF_URL, STANDING_URL, QUESTIONS_URL = GH + REFERENCE_FILE, GH + STANDING_FILE, GH + QUESTIONS_FILE

STANDING_DELIM = "===STANDING-FILE==="
QUESTIONS_DELIM = "===QUESTIONS-FILE==="

SCRAPE_CHARS = 2400
SEARCH_DAYS = 4            # Tavily news recency window
PLANNED_QUERIES = 24

ANTHROPIC_API_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY     = os.environ.get("GEMINI_API_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
SERPER_API_KEY     = os.environ.get("SERPER_API_KEY", "")
TAVILY_API_KEY     = os.environ.get("TAVILY_API_KEY", "")
SEARCH_PROVIDER    = os.environ.get("SEARCH_PROVIDER", "tavily")

TODAY = datetime.date.today()
TODAY_STR = TODAY.isoformat()
MONTH_STR = TODAY.strftime("%B")
DAY_N = (TODAY - WAR_START).days + 1
WEEK_N = (DAY_N + 6) // 7


def log(msg: str) -> None:
    print(f"[briefing] {msg}", flush=True)


# --------------------------------------------------------------------------- #
# Search
# --------------------------------------------------------------------------- #
CORE_QUERIES = [
    f"Iran war {TODAY_STR}",
    f"Strait of Hormuz tanker escort convoy transit {MONTH_STR} 2026",
    f"Brent crude price {TODAY_STR}",
    f"CENTCOM statement Iran {MONTH_STR} 2026",
    f"Iran ceasefire talks Oman Qatar {MONTH_STR} 2026",
    f"Houthi attack Saudi Arabia Red Sea {MONTH_STR} 2026",
    f"Israel strike Iran IDF {MONTH_STR} 2026",
    f"Iran protests economy rial {MONTH_STR} 2026",
]


def tavily_search(query: str) -> list:
    try:
        r = requests.post(
            "https://api.tavily.com/search",
            headers={"Content-Type": "application/json"},
            json={"api_key": TAVILY_API_KEY, "query": query, "search_depth": "basic",
                  "topic": "news", "days": SEARCH_DAYS, "max_results": 5,
                  "include_raw_content": True},
            timeout=45,
        )
        r.raise_for_status()
        out = []
        for item in r.json().get("results", []):
            content = (item.get("raw_content") or item.get("content") or "")[:SCRAPE_CHARS]
            out.append({"title": item.get("title", ""), "content": content,
                        "link": item.get("url", ""), "date": item.get("published_date", "")})
        return out
    except Exception as e:
        log(f"Tavily search failed for {query!r}: {e}")
        return []


def serper_search(query: str) -> list:
    try:
        r = requests.post("https://google.serper.dev/search",
                          headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
                          json={"q": query, "num": 8, "tbs": "qdr:w"}, timeout=30)
        r.raise_for_status()
        data = r.json()
        out = []
        for item in (data.get("organic") or [])[:5]:
            out.append({"title": item.get("title", ""), "content": item.get("snippet", ""),
                        "link": item.get("link", ""), "date": item.get("date", "")})
        return out
    except Exception as e:
        log(f"Serper search failed for {query!r}: {e}")
        return []


def build_evidence_pack(queries: list) -> str:
    search = tavily_search if SEARCH_PROVIDER == "tavily" else serper_search
    log(f"running {len(queries)} searches via {SEARCH_PROVIDER} ...")
    blocks, seen = [], set()
    for q in queries:
        results = search(q)
        lines = [f"### Query: {q}"]
        for res in results:
            if res["link"] in seen:
                lines.append(f"- {res['title']} (already included above) URL: {res['link']}")
                continue
            seen.add(res["link"])
            date = f" [published {res['date']}]" if res.get("date") else " [NO DATE IN METADATA — use only if the text carries a date]"
            lines.append(f"- {res['title']}{date}\n  URL: {res['link']}\n  {res['content']}")
        if len(lines) > 1:
            blocks.append("\n".join(lines))
    pack = "\n\n".join(blocks)
    log(f"evidence pack: {len(pack)} chars, {len(seen)} unique sources")
    return pack


# --------------------------------------------------------------------------- #
# Context files
# --------------------------------------------------------------------------- #
def head(path, n):
    try:
        with open(path, encoding="utf-8") as f:
            return "".join(f.readlines()[:n])
    except Exception as e:
        log(f"could not read {path}: {e}")
        return ""


def tail(path, n):
    try:
        with open(path, encoding="utf-8") as f:
            return "".join(f.readlines()[-n:])
    except Exception as e:
        log(f"could not read {path}: {e}")
        return ""


def full(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        log(f"could not read {path}: {e}")
        return ""


def yesterdays_brief():
    text = full(REPO_FILE)
    cut = text.find("## Model Cross-Check")
    return text[:cut] if cut > 0 else text[:12000]


def read_context() -> str:
    return (
        "=== KNOWN FACTUAL CORRECTIONS + EVIDENCE/FORMAT RULES (do NOT contradict) ===\n"
        + head(CONTEXT_FILE, 90)
        + "\n\n=== RECENT LOG / LAST KNOWN STATE ===\n"
        + tail(CONTEXT_FILE, 60)
        + "\n\n=== SCENARIO PROBABILITIES + ACTIVE INDICATORS ===\n"
        + head(REFERENCE_FILE, 80)
        + "\n\n=== YESTERDAY'S BRIEFING (the reader has seen this — do not repeat it) ===\n"
        + yesterdays_brief()
        + "\n\n=== CURRENT STANDING SECTIONS FILE (update only what changed) ===\n"
        + full(STANDING_FILE)
    )


# --------------------------------------------------------------------------- #
# Stage 1 — query planning
# --------------------------------------------------------------------------- #
PLAN_PROMPT = f"""You plan today's ({TODAY_STR}) open-source research for an Iran-war intelligence
briefing. Below are the owner's open questions (with current reads), today's structured
signals, and yesterday's briefing.

Write exactly {PLANNED_QUERIES} web-search queries, one per line, no numbering, no commentary.
Requirements:
- Each query targets evidence for a specific open question. Cover every question at least
  twice; weight toward questions where the signals hint at a change or contradiction.
- Go below the headline layer: name specific border crossings, ports, rail lines, airports,
  bases, ship names, units, exchanges, satellite-imagery reporting, company or agency names.
- Prefer queries that would surface numbers (counts, tonnes, prices, sorties, call-ups).
- Include local and regional press in English (Turkish, Pakistani, Iraqi, Gulf, Indian,
  Israeli outlets) and OSINT accounts, not only Western wires.
- Include "{MONTH_STR} 2026" or the date in each query so results are fresh.
- Do not repeat what yesterday's briefing already established.

=== OPEN QUESTIONS ===
{{questions}}

=== TODAY'S SIGNALS ===
{{signals}}

=== YESTERDAY'S BRIEFING ===
{{yesterday}}

Queries:"""


def parse_queries(text: str) -> list:
    """Accept numbered/bulleted/quoted lines, code fences, or ';'-separated lists."""
    text = re.sub(r"```[a-z]*", "", text)
    lines = []
    for ln in text.splitlines():
        ln = re.sub(r"^[\-\*\u2022\d\.\)\s]+", "", ln).strip().strip('"\u201c\u201d\'')
        if not ln or ln.lower().startswith(("queries", "here are", "note")):
            continue
        parts = [p.strip() for p in ln.split(";")] if ln.count(";") >= 2 else [ln]
        lines.extend(p for p in parts if 8 <= len(p) <= 220)
    seen, out = set(), []
    for q in lines:
        k = q.lower()
        if k not in seen:
            seen.add(k)
            out.append(q)
    return out


def plan_queries(client, questions, signals, yesterday) -> list:
    prompt = PLAN_PROMPT.format(questions=questions, signals=signals, yesterday=yesterday[:6000])
    for attempt in (1, 2):
        try:
            msg = client.messages.create(
                model=PLANNER_MODEL, max_tokens=3000,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(b.text for b in msg.content if b.type == "text")
            qs = parse_queries(text)
            log(f"planner attempt {attempt}: {len(qs)} queries parsed from {len(text)} chars")
            if len(qs) >= PLANNED_QUERIES // 2:
                return qs[:PLANNED_QUERIES + 4]
            log("planner raw output (first 1500 chars):\n" + text[:1500])
            prompt += ("\n\nYour previous answer was not in the required format. Output ONLY the "
                       f"{PLANNED_QUERIES} queries, one per line, plain text, nothing else.")
        except Exception as e:
            log(f"planner attempt {attempt} failed: {e}")
    log("planner fell back to core queries only")
    return []


# --------------------------------------------------------------------------- #
# Stage 3 — analysis + writing
# --------------------------------------------------------------------------- #
CORE_STRUCTURE = f"""# Iran War Economic Impact Framework
*Last updated by daily agent: {TODAY_STR}*

> **[Open questions]({QUESTIONS_URL}) · [Standing sections]({STANDING_URL}) · [Full reference]({REF_URL})**

---

## Daily Briefing - {TODAY_STR}

**Day {DAY_N} / Week {WEEK_N}.** [Two sentences: the one thing that matters most today and why. No recap of the war.]

### The calls — where the read moved
[Two or three, never more. For each:]
**Q[n] · [short question name] — [the call in one sentence].**
[Up to 130 words. The data and evidence behind the call: cite structured signals by source tag and dated sources by (Outlet, date, URL). Reconcile signals with reporting; where they conflict, say which you believe and why. State confidence (low / medium / high) and the single observation that would change the read. Label inferences as inferences.]

**Not moved today:** [One line. Remaining question numbers with short names, each "read unchanged since [date]".]

**Headlines the wires already have:** [Up to four one-line items with (Outlet, date, URL). No commentary. These are for the record, not analysis.]

**Corrections:** [Only if a prior briefing stated something now known to be wrong. Omit the line otherwise.]

**Market and flow readings ({TODAY_STR}):** [Tight bullets, only readings dated today or changed since yesterday: Brent; Hormuz visible transits and tanker DWT vs 2025 (PortWatch); rial and Tether premium (tgju); war-risk premium if new; any port-arrival divergence. Never write "no reading in pack".]

**Scenario update:** S1 X% / S2 X% / S3 X% / S4 X% / S5 X% — [one or two sentences on what moved and why, or "unchanged" with the reason it is unchanged].

**Standing sections updated today:** [Only the sections you changed, one line each with a link to its anchor in the standing file; "none" if none. Never restate anything written above.]
"""

CORE_PROMPT = f"""You are the analyst behind a professional Iran-war intelligence briefing for an investor
who has ALREADY read the ISW daily update and the wires before opening this. Today is {TODAY_STR}
(Day {DAY_N}). Your job is not to tell the reader what happened; it is to tell them what it means,
what the data says that the reporting does not, and where your read of the open questions moved.

METHOD
- Work the OPEN QUESTIONS ledger. For each question, test yesterday's read against today's
  structured signals and evidence pack. Look for contradictions between narrative and data
  (e.g. AIS transit counts vs port arrivals, official statements vs currency moves, "strikes
  ongoing" vs thermal anomalies). A contradiction is the most valuable thing you can report.
- Reason quantitatively where the signals allow: baselines, percent changes, what a number
  implies about volume or capacity. Show the arithmetic briefly.
- You may draw inferences that go beyond any single source, but label them as inferences
  and give the confidence. Never present an inference as a reported fact.
- Repetition is the primary failure mode. The reader saw yesterday's briefing. Do not restate
  its facts unless the read changed. Never state the same fact twice within today's briefing.
- The briefing above the Model Cross-Check stays under ~900 words. Shorter is better.

EVIDENCE RULES (they override everything else)
- Use only facts present in the evidence pack, the structured signals, or the context. Do
  not invent events, vessels, figures, or sources.
- Undated sources are ignored unless the text itself carries a clear date.
- Official releases confirm activity only through their release date. A claim that a kinetic
  action is "ongoing" needs a dated source from the past 72 hours.
- Single-sourced material claims are flagged single-sourced. State-sourced figures are
  attributed as claims ("Iran says", "CENTCOM says").
- If yesterday's Model Cross-Check disputed a fact, resolve it today (re-verify or correct).
- Every headline and every cited fact carries a real URL from the evidence pack.
- Scenario probabilities sum to exactly 100.

OUTPUT — three documents in one response, in this order, separated by the delimiters:

1. The briefing, matching this structure exactly:

{CORE_STRUCTURE}

2. The line {STANDING_DELIM}, then the COMPLETE updated {STANDING_FILE}. Start from the
current version in the context and change ONLY sections with a material 24-hour change;
update the body and bump that section's "Last materially changed" date to {TODAY_STR}. Leave
every other section byte-identical. Keep the header comment and update protocol intact.

3. The line {QUESTIONS_DELIM}, then the COMPLETE updated {QUESTIONS_FILE}. Keep the file's
header, rules, question titles and italic scope text byte-identical. For each question, rewrite
only the three fields: **Current read:** (one to three sentences, with confidence and the date
the read was last changed), **Evidence log:** (dated bullets, newest first, keep at most five,
each with a source tag or URL), **Would change the read:** (one sentence). A question with no
new evidence keeps yesterday's fields verbatim. Leave the Retired section untouched.

=== OPEN QUESTIONS LEDGER (current) ===
{{questions}}

=== STRUCTURED SIGNALS (today) ===
{{signals}}

=== CONTEXT ===
{{context}}

=== TODAY'S EVIDENCE PACK ===
{{evidence}}

Begin with the H1 title of the briefing. No preamble."""


def claude_core(client, questions, signals, context, evidence) -> str:
    prompt = CORE_PROMPT.format(questions=questions, signals=signals, context=context, evidence=evidence)
    with client.beta.messages.stream(
        model=CORE_MODEL,
        max_tokens=48000,
        output_config={"effort": CORE_EFFORT},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason == "refusal":
        log(f"core model refused: {getattr(msg, 'stop_details', None)}")
    if msg.stop_reason == "max_tokens":
        log("WARNING: core output hit max_tokens — trailing document may be truncated")
    u = msg.usage
    log(f"core usage: in={u.input_tokens} out={u.output_tokens} stop={msg.stop_reason}")
    return "".join(b.text for b in msg.content if b.type == "text").strip()


# --------------------------------------------------------------------------- #
# Stage 4 — challengers
# --------------------------------------------------------------------------- #
DIFF_PROMPT = """You are an independent analyst reviewing another analyst's ("Claude") daily
Iran-war briefing. You have the SAME structured signals and evidence pack.

In UNDER 180 words, state where YOUR reading differs: a call you think the data does not
support, a contradiction Claude missed, a question where you would move the read differently,
or a scenario probability you would set differently. Cite the signal or source. If you largely
agree, say so in one line and list only genuine differences. Do not restate the briefing.

=== STRUCTURED SIGNALS ===
{signals}

=== EVIDENCE PACK ===
{evidence}

=== CLAUDE'S BRIEFING ===
{brief}

Your differences (markdown bullets, under 180 words):"""


def gemini_diff(signals, evidence, brief) -> str:
    try:
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}")
        r = requests.post(url, json={"contents": [{"parts": [{"text": DIFF_PROMPT.format(
            signals=signals, evidence=evidence, brief=brief)}]}]}, timeout=120)
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        log(f"Gemini diff failed: {e}")
        return f"_Gemini cross-check unavailable this run ({e})._"


def openrouter_diff(model, signals, evidence, brief) -> str:
    try:
        r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                          headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}",
                                   "Content-Type": "application/json"},
                          json={"model": model, "max_tokens": 600, "messages": [{
                              "role": "user", "content": DIFF_PROMPT.format(
                                  signals=signals, evidence=evidence, brief=brief)}]},
                          timeout=150)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log(f"OpenRouter diff failed for {model}: {e}")
        return f"_Cross-check via {model} unavailable this run ({e})._"


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def split_documents(raw: str):
    core, standing, questions = raw, "", ""
    if QUESTIONS_DELIM in core:
        core, questions = core.split(QUESTIONS_DELIM, 1)
    if STANDING_DELIM in core:
        core, standing = core.split(STANDING_DELIM, 1)
    return core.strip(), standing.strip(), questions.strip()


def main() -> int:
    if not ANTHROPIC_API_KEY:
        log("FATAL: ANTHROPIC_API_KEY not set")
        return 1
    if SEARCH_PROVIDER == "serper" and not SERPER_API_KEY:
        log("FATAL: SERPER_API_KEY not set")
        return 1
    if SEARCH_PROVIDER == "tavily" and not TAVILY_API_KEY:
        log("FATAL: TAVILY_API_KEY not set")
        return 1

    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    # 0. signals
    try:
        signals = build_signals()
    except Exception as e:
        log(f"signals failed entirely: {e}")
        signals = "_Structured signals unavailable this run._"

    questions = full(QUESTIONS_FILE) or "_Question ledger missing._"
    yesterday = yesterdays_brief()
    context = read_context()

    # 1. plan + 2. search
    planned = plan_queries(client, questions, signals, yesterday)
    evidence = build_evidence_pack(CORE_QUERIES + planned)
    if not evidence.strip():
        log("FATAL: empty evidence pack (search failed) -- aborting")
        return 1

    # 3. analyse + write
    log(f"analysing and writing with {CORE_MODEL} (effort={CORE_EFFORT}) ...")
    raw = claude_core(client, questions, signals, context, evidence)
    if not raw.strip():
        log("FATAL: empty core brief")
        return 1
    core, standing, new_questions = split_documents(raw)

    if standing.startswith("# Iran War") and len(standing) > 3000:
        with open(STANDING_FILE, "w", encoding="utf-8") as f:
            f.write(standing + "\n")
        log(f"wrote {STANDING_FILE} ({len(standing)} chars)")
    else:
        log("standing file not updated this run (missing delimiter or payload too short)")

    if new_questions.startswith("# Open Questions") and len(new_questions) > 2500 \
            and new_questions.count("## Q") >= questions.count("## Q"):
        with open(QUESTIONS_FILE, "w", encoding="utf-8") as f:
            f.write(new_questions + "\n")
        log(f"wrote {QUESTIONS_FILE} ({len(new_questions)} chars)")
    else:
        log("questions file not updated this run (missing delimiter, too short, or questions dropped)")

    # 4. cross-check
    log("gathering challenger cross-checks ...")
    sections = [("Gemini", gemini_diff(signals, evidence, core))]
    for name, model in OPENROUTER_MODELS:
        sections.append((name, openrouter_diff(model, signals, evidence, core)))

    dissent = ["\n---\n",
               "## Model Cross-Check — differences from the core brief",
               "*Each model below read the same signals and evidence pack and Claude's briefing, "
               "then noted where its conclusions differ. Challengers are a cross-check, not the "
               "published analysis.*\n"]
    for name, text in sections:
        dissent.append(f"### {name}\n{text}\n")

    # 5. assemble
    final = (core.rstrip() + "\n" + "\n".join(dissent)
             + f"\n\n*[Open questions]({QUESTIONS_URL}) · [Standing sections]({STANDING_URL}) · "
               f"[Full reference]({REF_URL})*\n")
    with open(REPO_FILE, "w", encoding="utf-8") as f:
        f.write(final)
    log(f"wrote {REPO_FILE} ({len(final)} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
