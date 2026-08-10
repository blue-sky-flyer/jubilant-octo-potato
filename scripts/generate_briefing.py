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

The workflow then commits/pushes the file with the native GITHUB_TOKEN.

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
REF_URL = ("https://github.com/blue-sky-flyer/jubilant-octo-potato/blob/main/"
           "iran-war-reference.md")

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


def read_context() -> str:
    return (
        "=== KNOWN FACTUAL CORRECTIONS + HALLUCINATION GUARD (do NOT contradict) ===\n"
        + head(CONTEXT_FILE, 80)
        + "\n\n=== RECENT DAILY LOG / LAST KNOWN STATE ===\n"
        + tail(CONTEXT_FILE, 80)
        + "\n\n=== SCENARIO PROBABILITIES + ACTIVE INDICATORS ===\n"
        + head(REFERENCE_FILE, 80)
        + "\n\n=== YESTERDAY'S BRIEFING HEADLINE (do not repeat covered items) ===\n"
        + head(REPO_FILE, 60)
    )


# --------------------------------------------------------------------------- #
# Core brief (Claude)
# --------------------------------------------------------------------------- #
CORE_STRUCTURE = f"""# Iran War Economic Impact Framework
*Last updated by daily agent: {TODAY_STR}*

> **[Full reference]({REF_URL})**

---

## Daily Briefing - {TODAY_STR}

**Overall situation:** Day {DAY_N} / Week {WEEK_N}. [2-3 specific sentences.]

**Key developments:**
- **[HEADLINE]** ([Source](URL), date): [Detail with names, figures, quotes.]
[3-5 bullets, genuinely new today only.]

**On the Ground in Iran:** [Protests, fuel crisis, IRGC posture. Flag uncertainty.]

**Red Sea / Bab-el-Mandeb:** [Houthi activity, named vessel attacks, Yanbu threat, Bab-el-Mandeb status. Flag if no new activity.]

**Gulf States Adaptation:** [Saudi East-West pipeline, UAE Habshan-Fujairah, Fujairah/Kuwait status, Bahrain air defense.]

**Market Signals:** [Brent, BDTI, gold, VIX, war-risk insurance. Flag prior-day closes.]

**Sovereign Debt Stress:** [Egypt, Pakistan, Jordan, Turkey. New IMF actions.]

**Reconstruction Race:** [China/Russia positioning, Wang Yi pledges.]

**Information Warfare:** [Narrative battle today; who is winning and why.]

**Scenario Update:** S1 X% / S2 X% / S3 X% / S4 X% / S5 X% - must sum to 100%. Active scenario + key thresholds.
"""

CORE_PROMPT = f"""You are the daily agent for a professional Iran-war economic-impact
newsletter. Write today's briefing ({TODAY_STR}) using ONLY the evidence pack below.

HARD RULES:
- Use only facts present in the evidence pack. Do NOT invent events, vessels, or figures.
- Never contradict the KNOWN FACTUAL CORRECTIONS / HALLUCINATION GUARD in the context.
- Every Key Development bullet must cite a real source URL from the evidence pack.
- Do NOT reference the flagged pre-war/hallucinated events (M/V Magic Seas, M/V Eternity C, etc.).
- Scenario probabilities must sum to exactly 100%.
- Continue the analytical arc from the recent daily log; report only genuinely NEW developments.
- Keep it tight and evidence-grounded. Match this exact structure and headers:

{CORE_STRUCTURE}

=== CONTEXT ===
{{context}}

=== TODAY'S EVIDENCE PACK ===
{{evidence}}

Output ONLY the finished briefing markdown, starting with the H1 title. No preamble."""


def claude_core_brief(context: str, evidence: str) -> str:
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=CORE_MODEL,
        max_tokens=8000,
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
    core = claude_core_brief(context, evidence)
    if not core.strip():
        log("FATAL: empty core brief")
        return 1

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

    final = core.rstrip() + "\n" + "\n".join(dissent) + f"\n\n*[Full reference]({REF_URL})*\n"

    with open(REPO_FILE, "w", encoding="utf-8") as f:
        f.write(final)
    log(f"wrote {REPO_FILE} ({len(final)} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
