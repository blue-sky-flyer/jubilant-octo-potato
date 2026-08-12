#!/usr/bin/env python3
"""
Daily Iran-War briefing generator (GitHub Actions).

Pipeline:
  1. Read local context files (corrections, recent log, scenario probabilities).
  2. Build a SHARED evidence pack once, via Serper search + scrape (Google-fresh,
     full article text). Every model reads the identical pack -> fair comparison.
  3. Claude Sonnet 4.6 writes the authoritative core briefing.
  4. Challenger models (Gemini + open models via OpenRouter) each read the SAME
     evidence pack AND Claude's brief, and write a short "where I differ from
     Claude" section.
  5. Assemble core brief + dissent panel -> iran-war-impact-framework.md.
     The core model also returns the updated standing-sections file
     (iran-war-standing.md) after a delimiter; slow-moving sections live there
     and the briefing links to them (delta-only newsletter format).

The workflow then commits/pushes both files with the native GITHUB_TOKEN.

Design notes:
  - Core brief (Claude) is the only hard-fail path. Search-scrape and every
    challenger are best-effort: failures degrade to a noted stub, never abort.
  - Model IDs and endpoints are config constants at the top -- adjust freely.
"""

import os
import sys
import json
import datetime
import requests
from anthropic import Anthropic

# --------------------------------------------------------------------------- #
# Config -- edit these freely
# --------------------------------------------------------------------------- #
CORE_MODEL = "claude-sonnet-4-6"          # authoritative core-brief model

# Challenger roster. Gemini uses the dedicated Google key; the rest go through
# OpenRouter. Model strings change over time -- verify against the providers'
# model lists if a run reports an "unknown model" error.
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
REF_URL = ("https://github.com/blue-sky-flyer/jubilant-octo-potato/blob/main/"
           "iran-war-reference.md")
STANDING_URL = ("https://github.com/blue-sky-flyer/jubilant-octo-potato/blob/main/"
                "iran-war-standing.md")

# Delimiter between the briefing and the updated standing-sections file in the
# core model's single response. If absent, the old standing file is kept as-is.
STANDING_DELIM = "===STANDING-FILE==="

SCRAPE_TOP_N = 3        # scrape this many top links per query for full text
SCRAPE_CHARS = 2200     # truncate each scraped article to this many chars
SNIPPETS_PER_QUERY = 5  # organic snippets to keep per query

# --------------------------------------------------------------------------- #
# Keys (from GitHub Actions secrets, injected as env vars)
# --------------------------------------------------------------------------- #
ANTHROPIC_API_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY     = os.environ.get("GEMINI_API_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
SERPER_API_KEY     = os.environ.get("SERPER_API_KEY", "")
TAVILY_API_KEY     = os.environ.get("TAVILY_API_KEY", "")
# Which search backend to use: "tavily" (search+extract, one call) or "serper" (Google SERP + scrape)
SEARCH_PROVIDER    = os.environ.get("SEARCH_PROVIDER", "tavily")

TODAY = datetime.date.today()
TODAY_STR = TODAY.isoformat()
MONTH_STR = TODAY.strftime("%B")            # e.g. "August"
DAY_N = (TODAY - WAR_START).days + 1
WEEK_N = (DAY_N + 6) // 7


def log(msg: str) -> None:
    print(f"[briefing] {msg}", flush=True)


# --------------------------------------------------------------------------- #
# Search + scrape (Serper)
# --------------------------------------------------------------------------- #
SEARCH_QUERIES = [
    f"Iran war Hormuz {TODAY_STR} 2026",
    f"CENTCOM Iran strikes {TODAY_STR} 2026",
    f"Iran ceasefire negotiations talks {MONTH_STR} 2026",
    f"Brent crude oil price today {MONTH_STR} 2026",
    f"Iran war tanker shipping Hormuz traffic {MONTH_STR} 2026",
    f"Iran domestic protests economy {MONTH_STR} 2026",
    f"Gulf states Iran attack response {MONTH_STR} 2026",
    f"Iran nuclear IAEA deal {MONTH_STR} 2026",
    f"BDTI tanker rates war risk insurance {MONTH_STR} 2026",
    f"Egypt Pakistan sovereign debt IMF Iran war {MONTH_STR} 2026",
    f"China Russia Iran war {MONTH_STR} 2026",
    f"Saudi Arabia UAE Fujairah pipeline oil production {MONTH_STR} 2026",
    f"Trump Iran war naval blockade statement {MONTH_STR} 2026",
    f"Israel Iran strike {MONTH_STR} 2026",
    f"Houthi Yemen missile attack Saudi Arabia Red Sea {TODAY_STR} 2026",
    f"Bab-el-Mandeb strait shipping tanker {MONTH_STR} 2026",
    # --- siege / endurance data ---
    f"global oil strategic petroleum reserve SPR OECD IEA stocks level days cover {MONTH_STR} 2026",
    f"global oil supply demand gap consumption barrels per day shortfall {MONTH_STR} 2026",
    f"Iran economic collapse inflation rial currency GDP capital flight {MONTH_STR} 2026",
    f"Iran regime stability protests unrest IRGC succession {MONTH_STR} 2026",
    f"Iran sabotage assassination cyberattack covert operation {MONTH_STR} 2026",
    f"Israel Mossad Iran covert action unexplained explosion facility {MONTH_STR} 2026",
]


def serper_search(query: str) -> list:
    try:
        r = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            json={"q": query, "num": 10},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        results = []
        for item in (data.get("organic") or [])[:SNIPPETS_PER_QUERY]:
            results.append({
                "title": item.get("title", ""),
                "snippet": item.get("snippet", ""),
                "link": item.get("link", ""),
                "date": item.get("date", ""),
            })
        # topStories are often the freshest for breaking news
        for item in (data.get("topStories") or [])[:3]:
            results.append({
                "title": item.get("title", ""),
                "snippet": "",
                "link": item.get("link", ""),
                "date": item.get("date", ""),
            })
        return results
    except Exception as e:
        log(f"search failed for {query!r}: {e}")
        return []


def serper_scrape(url: str) -> str:
    try:
        r = requests.post(
            "https://scrape.serper.dev",
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            json={"url": url},
            timeout=45,
        )
        r.raise_for_status()
        data = r.json()
        text = data.get("text") or data.get("markdown") or ""
        return text[:SCRAPE_CHARS]
    except Exception as e:
        log(f"scrape failed for {url}: {e}")
        return ""


def tavily_search(query: str) -> list:
    try:
        r = requests.post(
            "https://api.tavily.com/search",
            headers={"Content-Type": "application/json"},
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "search_depth": "basic",
                "max_results": 5,
                "include_raw_content": True,
            },
            timeout=45,
        )
        r.raise_for_status()
        data = r.json()
        out = []
        for item in data.get("results", []):
            content = (item.get("raw_content") or item.get("content") or "")[:SCRAPE_CHARS]
            out.append({
                "title": item.get("title", ""),
                "content": content,
                "link": item.get("url", ""),
            })
        return out
    except Exception as e:
        log(f"Tavily search failed for {query!r}: {e}")
        return []


def build_pack_tavily() -> str:
    log(f"running {len(SEARCH_QUERIES)} searches via Tavily ...")
    blocks = []
    for q in SEARCH_QUERIES:
        results = tavily_search(q)
        if not results:
            continue
        lines = [f"### Query: {q}"]
        for res in results:
            lines.append(f"- {res['title']}\n  URL: {res['link']}\n  {res['content']}")
        blocks.append("\n".join(lines))
    pack = "\n\n".join(blocks)
    log(f"evidence pack (tavily): {len(pack)} chars")
    return pack


def build_evidence_pack() -> str:
    if SEARCH_PROVIDER == "tavily":
        return build_pack_tavily()
    return build_pack_serper()


def build_pack_serper() -> str:
    log(f"running {len(SEARCH_QUERIES)} searches via Serper ...")
    blocks = []
    scraped_urls = set()
    for q in SEARCH_QUERIES:
        results = serper_search(q)
        if not results:
            continue
        lines = [f"### Query: {q}"]
        for i, res in enumerate(results):
            tag = f"{res['title']} ({res['date']})".strip()
            lines.append(f"- {tag}\n  {res['snippet']}\n  URL: {res['link']}")
            # scrape full text for the top few unique links
            if i < SCRAPE_TOP_N and res["link"] and res["link"] not in scraped_urls:
                scraped_urls.add(res["link"])
                full = serper_scrape(res["link"])
                if full:
                    lines.append(f"  FULL TEXT: {full}")
        blocks.append("\n".join(lines))
    pack = "\n\n".join(blocks)
    log(f"evidence pack: {len(pack)} chars, {len(scraped_urls)} articles scraped")
    return pack


# --------------------------------------------------------------------------- #
# Context files
# --------------------------------------------------------------------------- #
def head(path: str, n: int) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return "".join([next(f) for _ in range(n)])
    except StopIteration:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        log(f"could not read {path}: {e}")
        return ""


def tail(path: str, n: int) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return "".join(f.readlines()[-n:])
    except Exception as e:
        log(f"could not read {path}: {e}")
        return ""


def full(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        log(f"could not read {path}: {e}")
        return ""


def read_context() -> str:
    return (
        "=== KNOWN FACTUAL CORRECTIONS + EVIDENCE/FORMAT RULES (do NOT contradict) ===\n"
        + head(CONTEXT_FILE, 80)
        + "\n\n=== RECENT DAILY LOG / LAST KNOWN STATE ===\n"
        + tail(CONTEXT_FILE, 80)
        + "\n\n=== SCENARIO PROBABILITIES + ACTIVE INDICATORS ===\n"
        + head(REFERENCE_FILE, 80)
        + "\n\n=== YESTERDAY'S BRIEFING (do not repeat covered items) ===\n"
        + head(REPO_FILE, 80)
        + "\n\n=== CURRENT STANDING SECTIONS FILE (update only what changed) ===\n"
        + full(STANDING_FILE)
    )


# --------------------------------------------------------------------------- #
# Core brief (Claude)
# --------------------------------------------------------------------------- #
CORE_STRUCTURE = f"""# Iran War Economic Impact Framework
*Last updated by daily agent: {TODAY_STR}*

> **[Standing sections]({STANDING_URL}) · [Full reference]({REF_URL})**

---

## Daily Briefing - {TODAY_STR}

**Overall situation:** Day {DAY_N} / Week {WEEK_N}. [3-4 specific sentences on the last 24 hours.]

**What changed in the last 24 hours:**
1. **[Headline]** ([Source](URL), date): [Detail with names, figures, quotes. Only events dated within the last ~24-48h. Double-source where possible and say so.]
[3-5 numbered items, genuinely new only.]

**Corrections:** [Only if a prior briefing stated something now known to be wrong: state the correction plainly. Omit the section if none.]

**Market signals ({TODAY_STR}):** [Tight bullets: Brent (+curve), gold, Hormuz transits, war-risk/insurance, SPR, VIX/equities. Flag prior-day closes and unconfirmed readings.]

**Scenario update:** S1 X% / S2 X% / S3 X% / S4 X% / S5 X% — must sum to 100%. [What moved, by how much, and why — one or two sentences per change.]

**Standing sections** *(full detail in [iran-war-standing.md]({STANDING_URL}); one bullet each)*:
- **[Section name](link-to-anchor)** — [either "unchanged since [date]" or a ONE-LINE delta summary ending "— updated today".]
[One bullet per standing section. Never reprint a standing section's body here.]
"""

CORE_PROMPT = f"""You are the daily agent for a professional Iran-war economic-impact
newsletter. Write today's briefing ({TODAY_STR}) using ONLY the evidence pack below.

FRAMING: The conflict is in a SIEGE / ATTRITION phase. The briefing is DELTA-ONLY: it reports
what changed in the last 24 hours. All slow-moving analysis (Gulf States Adaptation, Strategic
Reserve Countdown/Day 0, Iranian State Disintegration Tracker, Sovereign Debt Stress,
Reconstruction Race, Covert Actions Ledger, Red Sea baseline, On the Ground in Iran, US Military
Posture & Munitions) lives in the STANDING SECTIONS FILE, which you maintain separately below.
The reader saw yesterday's briefing — repetition is the primary failure mode to avoid.

EVIDENCE RULES (also in the context block — these override everything else):
- UNDATED SOURCES ARE IGNORED. If a search result has no date/timestamp, do not use it at all.
- Official releases confirm activity only THROUGH their release date. Never present a stale
  release (e.g., a weeks-old CENTCOM release) as evidence of current/ongoing operations.
- Any claim that a kinetic action is "ongoing" needs a dated source from the past 72 hours.
  Single-sourced material claims must be flagged single-sourced; if confidence is questionable,
  find a second independent source in the pack or drop the claim.
- Attribute state-sourced figures as claims ("Iran says", "Trump claims"), never as fact.
- If yesterday's Model Cross-Check disputed a fact, resolve it today: re-verify it against the
  pack (note "re-verified") or remove/correct it (note the correction in the Corrections block).

HARD RULES:
- Use only facts present in the evidence pack. Do NOT invent events, vessels, or figures.
- Never contradict the KNOWN FACTUAL CORRECTIONS / EVIDENCE RULES in the context.
- Every "What changed" item must cite a real source URL from the evidence pack.
- Scenario probabilities must sum to exactly 100%.
- The briefing (everything above the Model Cross-Check) must stay under ~1,500 words.
- Match this exact structure and headers:

{CORE_STRUCTURE}

STANDING SECTIONS FILE: After the briefing, output the line {STANDING_DELIM} and then the
COMPLETE updated iran-war-standing.md. Start from the current version (provided in the context)
and change ONLY sections with a material 24-hour change: update the section body and bump its
"Last materially changed" date to {TODAY_STR}. Leave every other section byte-identical,
including its date. Keep the header comment and Update protocol intact. If nothing changed
anywhere, still output the delimiter followed by the file unchanged.

=== CONTEXT ===
{{context}}

=== TODAY'S EVIDENCE PACK ===
{{evidence}}

Output the finished briefing markdown starting with the H1 title, then {STANDING_DELIM},
then the complete standing file. No other preamble or commentary."""


def claude_core_brief(context: str, evidence: str) -> str:
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=CORE_MODEL,
        max_tokens=16000,
        messages=[{
            "role": "user",
            "content": CORE_PROMPT.format(context=context, evidence=evidence),
        }],
    )
    return "".join(b.text for b in msg.content if b.type == "text").strip()


# --------------------------------------------------------------------------- #
# Challenger "differences" sections
# --------------------------------------------------------------------------- #
DIFF_PROMPT = """You are an independent analyst reviewing another analyst's ("Claude")
daily Iran-war briefing. You have the SAME evidence pack they used.

In UNDER 200 words, state specifically where YOUR reading of this evidence differs from
Claude's briefing: different conclusions, different scenario probabilities, developments
Claude missed or overweighted, or claims you think are unsupported by the evidence.
Cite the evidence. If you largely agree, say so in one line and list only genuine
differences. Do not restate Claude's briefing. Be concrete and calibrated.

=== TODAY'S EVIDENCE PACK ===
{evidence}

=== CLAUDE'S BRIEFING ===
{brief}

Your differences (markdown bullet points, under 200 words):"""


def gemini_diff(evidence: str, brief: str) -> str:
    try:
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}")
        r = requests.post(
            url,
            json={"contents": [{"parts": [{"text": DIFF_PROMPT.format(
                evidence=evidence, brief=brief)}]}]},
            timeout=90,
        )
        r.raise_for_status()
        data = r.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        log(f"Gemini diff failed: {e}")
        return f"_Gemini cross-check unavailable this run ({e})._"


def openrouter_diff(model: str, evidence: str, brief: str) -> str:
    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}",
                     "Content-Type": "application/json"},
            json={"model": model, "max_tokens": 600, "messages": [{
                "role": "user",
                "content": DIFF_PROMPT.format(evidence=evidence, brief=brief),
            }]},
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log(f"OpenRouter diff failed for {model}: {e}")
        return f"_Cross-check via {model} unavailable this run ({e})._"


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
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

    context = read_context()
    evidence = build_evidence_pack()
    if not evidence.strip():
        log("FATAL: empty evidence pack (search failed) -- aborting")
        return 1

    log(f"writing core brief with {CORE_MODEL} ...")
    raw = claude_core_brief(context, evidence)
    if not raw.strip():
        log("FATAL: empty core brief")
        return 1

    # Split briefing from the updated standing-sections file. Standing update is
    # best-effort: if the delimiter is missing or the payload looks truncated,
    # keep the existing standing file untouched.
    core, standing = raw, ""
    if STANDING_DELIM in raw:
        core, standing = raw.split(STANDING_DELIM, 1)
        core, standing = core.strip(), standing.strip()
    if standing.startswith("# Iran War") and len(standing) > 3000:
        with open(STANDING_FILE, "w", encoding="utf-8") as f:
            f.write(standing + "\n")
        log(f"wrote {STANDING_FILE} ({len(standing)} chars)")
    else:
        log("standing file not updated this run (missing delimiter or payload too short)")

    log("gathering challenger cross-checks ...")
    sections = []
    sections.append(("Gemini", gemini_diff(evidence, brief=core)))
    for name, model in OPENROUTER_MODELS:
        sections.append((name, openrouter_diff(model, evidence, brief=core)))

    dissent = ["\n---\n",
               "## Model Cross-Check — differences from the core brief",
               "*Each model below read the same evidence pack and Claude's briefing above, "
               "then noted where its conclusions differ. Challengers are a cross-check, not "
               "the published analysis.*\n"]
    for name, text in sections:
        dissent.append(f"### {name}\n{text}\n")

    final = (core.rstrip() + "\n" + "\n".join(dissent)
             + f"\n\n*[Standing sections]({STANDING_URL}) · [Full reference]({REF_URL})*\n")

    with open(REPO_FILE, "w", encoding="utf-8") as f:
        f.write(final)
    log(f"wrote {REPO_FILE} ({len(final)} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
