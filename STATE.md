# STATE — Iran War Impact Framework
*Updated: 2026-09-12*

## In flight
- **External-trigger migration (workflow deployed 2026-09-12; owner wiring cron-job.org):** primary trigger is a cron-job.org job POSTing to the `workflow_dispatch` endpoint at 11:50 UTC with a fine-grained PAT (this repo only, Actions: read+write). GitHub `schedule` trigger removed the same day (owner's call) — cron-job.org is the sole trigger; failure mode is a cron-job.org failure email + manual dispatch. Checkout now uses `ref: main` so queued runs see the fresh file. cron-job.org test ping 2026-09-12 21:42 UTC → GitHub run in <1s, gate no-op in 7s. **Verify: briefing commit ~11:58 UTC daily Sep 13–15.**

## Recently decided
- **2026-09-12:** Hold-run design retired after one live day. Sep 11: the 06:39 fire slept in-runner 5h11m (337 runner-min that day vs ~14 baseline); the 11:50 fire queued behind it, checked out the SHA pinned at queue time, missed the just-pushed briefing, regenerated (double API spend) and failed on rebase conflict. Replaced with external cron-job.org → workflow_dispatch (immediate, unthrottled) + `force` input for manual regen. Hourly cron fallback dropped the same day.
- **2026-09-10:** Generate near the deadline, not early — the 03:00 UTC gate had briefings landing 10pm–1am PT with a prior-evening evidence window (owner: too stale).
- **2026-08-30 → 09-02:** Hourly cron + gate after GitHub's scheduler degraded for this repo (delivers only ~6 of 24 fires/day in 2–5h sweeps since Aug 27; scheduler-side — `created_at == run_started_at`; no official incident; community reports match). Commit step rebases before push (a concurrent push stranded the Aug 30 briefing).
- **2026-08-12:** Remote trigger deleted — pipeline is GHA-only (`.github/workflows/daily-briefing.yml` → `scripts/generate_briefing.py`). Briefing switched to delta-only format; standing sections split into `iran-war-standing.md`; evidence rules (dated sources only, double-source contested claims, challenger disputes resolved each cycle) at top of `iran-war-context.md`.

## Next up
- PAT expires 2027-09-12 07:00 UTC — rotate in cron-job.org before then. Optional: add header `X-GitHub-Api-Version: 2022-11-28` to the cron-job.org job (unversioned REST sunsets 2028-03-10).
- Local working copy (this Dropbox folder) is **broken for git**: Dropbox evicted `.git` objects (mmap timeouts) and local main diverged ~Aug 30. Use a fresh clone for any git work; fix by re-cloning or moving the repo out of Dropbox (portfolio-wide `~/code/` move planned).

## Open questions
- Winter time: 6am PST = 14:00 UTC; current 11:50 UTC ping lands 3:50am PST. Optionally move the cron-job.org schedule to ~13:50 UTC after the November DST change .
