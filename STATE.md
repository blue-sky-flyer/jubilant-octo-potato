# STATE — Iran War Impact Framework
*Updated: 2026-09-10*

## In flight
- **Briefing delivery redesign (deployed 2026-09-10, first live day 2026-09-11):** hourly GHA cron; the first fire delivered in the 06:00–11:50 UTC window HOLDS (sleeps in-runner) until 11:50 UTC, then generates — briefing lands ~12:00 UTC (5:00am PDT), fresh and ahead of the 6am PT read deadline. Fires before 06:00 skip; fires after 11:50 generate immediately as fallback. **Verify completion times Sep 11–13.**

## Recently decided
- **2026-09-10:** Generate near the deadline, not early — the 03:00 UTC gate had briefings landing 10pm–1am PT with a prior-evening evidence window (owner: too stale).
- **2026-08-30 → 09-02:** Hourly cron + gate after GitHub's scheduler degraded for this repo (delivers only ~6 of 24 fires/day in 2–5h sweeps since Aug 27; scheduler-side — `created_at == run_started_at`; no official incident; community reports match). Commit step rebases before push (a concurrent push stranded the Aug 30 briefing).
- **2026-08-12:** Remote trigger deleted — pipeline is GHA-only (`.github/workflows/daily-briefing.yml` → `scripts/generate_briefing.py`). Briefing switched to delta-only format; standing sections split into `iran-war-standing.md`; evidence rules (dated sources only, double-source contested claims, challenger disputes resolved each cycle) at top of `iran-war-context.md`.

## Next up
- Watch Sep 11–13: briefing commit should appear ~12:00 UTC daily. If any day misses 6am PT, wire the hard guarantee: external cron (e.g. cron-job.org) calling `workflow_dispatch` at ~11:50 UTC — needs a fine-grained PAT (this repo, Actions: write) from the owner. Manual dispatch has been 100% reliable throughout the scheduler degradation.
- Local working copy (this Dropbox folder) is **broken for git**: Dropbox evicted `.git` objects (mmap timeouts) and local main diverged ~Aug 30. Use a fresh clone for any git work; fix by re-cloning or moving the repo out of Dropbox (portfolio-wide `~/code/` move planned).

## Open questions
- Does GitHub's scheduler recover for this repo? (Still sweep-delivery as of Sep 10.) If it does, the hold design still works — a healthy 06:53 fire simply holds until 11:50.
- Winter time: 6am PST = 14:00 UTC; current 11:50 UTC target lands 3:50am PST. Optionally shift target to ~13:50 UTC after the November DST change if later delivery is preferred.
