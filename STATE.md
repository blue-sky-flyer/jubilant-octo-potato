# STATE — Iran War Impact Framework
*Updated: 2026-09-19*

## In flight
- **Question-driven, data-first briefing (deployed 2026-09-19):** owner found the news-digest format marginal next to ISW. Rebuilt: `scripts/signals.py` collects structured data with baselines (PortWatch chokepoints + ports, tgju rial/Tether/gold, IODA, Israel alerts, OpenSky, FIRMS if key); `iran-war-questions.md` is the owner's agenda (Q1 oil flows/dark transits, Q2 inside Iran: borders/ports/rail/people, Q3 capital flows, Q4 view from space, Q5 US posture and movements, Q6 Israel, Q7 Houthi front, Q8 Mecca pact, Q9 diplomacy); planner (Sonnet 5) writes ~24 targeted queries per day; core moved to Opus 5 with adaptive thinking, effort high, server-side fallbacks; briefing restructured to lead with 2-3 calls, <900 words. **Verify Sep 19-22: calls are grounded in signals, question ledger updates cleanly, standing file not corrupted, runtime <15 min, cost per run (Opus in/out tokens in the run log).**
- **Owner action: FIRMS key.** Register a free NASA FIRMS MAP_KEY (https://firms.modaps.eosdis.nasa.gov/api/map_key/) and add it as repo secret `FIRMS_MAP_KEY` to enable thermal-anomaly collection at nine Iranian industrial sites (Q4).

## Recently decided
- **2026-09-19:** Briefing redesign (see In flight). Rejected: making it longer. Data sources verified free/no-key: PortWatch ArcGIS, tgju, IODA, tzevaadom, OpenSky. USAspending and ADS-B military feeds probed and dropped (noisy / near-empty in theatre). Cloudflare Radar and UNHCR need tokens or scraping — not included.
- **2026-09-12:** Hold-run design retired after one live day. Sep 11: the 06:39 fire slept in-runner 5h11m (337 runner-min that day vs ~14 baseline); the 11:50 fire queued behind it, checked out the SHA pinned at queue time, missed the just-pushed briefing, regenerated (double API spend) and failed on rebase conflict. Replaced with external cron-job.org → workflow_dispatch (immediate, unthrottled) + `force` input for manual regen. Hourly cron fallback dropped the same day.
- **2026-09-10:** Generate near the deadline, not early — the 03:00 UTC gate had briefings landing 10pm–1am PT with a prior-evening evidence window (owner: too stale).
- **2026-08-30 → 09-02:** Hourly cron + gate after GitHub's scheduler degraded for this repo (delivers only ~6 of 24 fires/day in 2–5h sweeps since Aug 27; scheduler-side — `created_at == run_started_at`; no official incident; community reports match). Commit step rebases before push (a concurrent push stranded the Aug 30 briefing).
- **2026-08-12:** Remote trigger deleted — pipeline is GHA-only (`.github/workflows/daily-briefing.yml` → `scripts/generate_briefing.py`). Briefing switched to delta-only format; standing sections split into `iran-war-standing.md`; evidence rules (dated sources only, double-source contested claims, challenger disputes resolved each cycle) at top of `iran-war-context.md`.

## Next up
- PAT expires 2027-09-12 07:00 UTC — rotate in cron-job.org before then. Optional: add header `X-GitHub-Api-Version: 2022-11-28` to the cron-job.org job (unversioned REST sunsets 2028-03-10).
- Local working copy (this Dropbox folder) is **broken for git**: Dropbox evicted `.git` objects (mmap timeouts) and local main diverged ~Aug 30. Use a fresh clone for any git work; fix by re-cloning or moving the repo out of Dropbox (portfolio-wide `~/code/` move planned).

## Open questions
- Winter time: 6am PST = 14:00 UTC; current 11:50 UTC ping lands 3:50am PST. Optionally move the cron-job.org schedule to ~13:50 UTC after the November DST change .
