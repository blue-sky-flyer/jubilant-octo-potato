#!/usr/bin/env python3
"""
Manage the cron-job.org job that triggers the daily briefing.

The job POSTs to GitHub's workflow_dispatch endpoint for daily-briefing.yml.
API key lives OUTSIDE the repo at ~/.config/cron-job-org/api_key (never commit it).

Usage:
  scripts/cronjob.py show                 # schedule, next run, headers (token masked), notifications
  scripts/cronjob.py history              # recent executions with HTTP status
  scripts/cronjob.py set-time HH:MM       # daily at HH:MM UTC (e.g. 13:50 after the DST change)
  scripts/cronjob.py enable | disable
  scripts/cronjob.py set-header NAME VAL  # add/replace one request header (e.g. rotate the GitHub PAT)
"""
import json, sys, os, datetime, urllib.request

JOB_ID = 8438426
API = "https://api.cron-job.org"
KEY_PATH = os.path.expanduser("~/.config/cron-job-org/api_key")


def key() -> str:
    try:
        return open(KEY_PATH).read().strip()
    except OSError:
        sys.exit(f"API key not found at {KEY_PATH}")


def call(method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method,
                                 headers={"Authorization": f"Bearer {key()}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"{}")


def ts(t: int) -> str:
    if not t:
        return "never"
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def details():
    return call("GET", f"/jobs/{JOB_ID}")["jobDetails"]


def show():
    j = details()
    s = j["schedule"]
    print(f"title:    {j['title']}")
    print(f"enabled:  {j['enabled']}")
    print(f"schedule: {s['hours']}:{s['minutes']} tz={s['timezone']} mdays={s['mdays']} wdays={s['wdays']}")
    print(f"next:     {ts(j['nextExecution'])}")
    print(f"last:     {ts(j['lastExecution'])} status={j['lastStatus']}")
    print(f"url:      {j['url']}")
    print(f"body:     {j['extendedData'].get('body', '').strip()}")
    for k, v in j["extendedData"].get("headers", {}).items():
        if k.lower() == "authorization":
            v = v[:14] + "..." + v[-4:]
        print(f"header:   {k}: {v}")
    print(f"notify:   {j.get('notification')}")


def history():
    h = call("GET", f"/jobs/{JOB_ID}/history")
    for e in h.get("history", []):
        print(f"{ts(e['date'])}  http={e.get('httpStatus')}  status={e.get('status')}  "
              f"{e.get('duration')}ms  {e.get('url','')[:60]}")
    if not h.get("history"):
        print("no executions recorded")


def patch(job: dict):
    call("PATCH", f"/jobs/{JOB_ID}", {"job": job})


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "show"
    if cmd == "show":
        show()
    elif cmd == "history":
        history()
    elif cmd == "set-time":
        hh, mm = argv[2].split(":")
        patch({"schedule": {"timezone": "UTC", "hours": [int(hh)], "minutes": [int(mm)],
                            "mdays": [-1], "months": [-1], "wdays": [-1], "expiresAt": 0}})
        show()
    elif cmd in ("enable", "disable"):
        patch({"enabled": cmd == "enable"})
        show()
    elif cmd == "set-header":
        h = details()["extendedData"]["headers"]
        h[argv[2]] = argv[3]
        patch({"extendedData": {"headers": h}})
        show()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
