#!/usr/bin/env python3
"""
Structured signals for the daily briefing — machine-readable data the search
layer cannot see. Every collector is best-effort: a failure produces a one-line
note, never an abort. Output is (a) a markdown SIGNALS block handed to the
model and (b) data/signals/<date>.json, committed to the repo so a time series
accumulates in git.

Sources (all free; FIRMS needs a free NASA MAP_KEY in env FIRMS_MAP_KEY):
  - IMF PortWatch (ArcGIS REST): chokepoint transits by vessel type, port calls
    and import/export tonnage, with same-week-2025 baselines.
  - tgju.org: open-market rial (USD, EUR), Tether/IRR, 18k gold gram, Emami coin.
  - IODA (Georgia Tech): Iran internet connectivity (BGP + active probing).
  - tzevaadom.co.il: Israel Home Front Command alerts by day and threat type.
  - OpenSky Network: aircraft counts over Iran and the Gulf (civil airspace proxy).
  - NASA FIRMS: VIIRS thermal anomalies near Iranian industrial sites.

Run standalone to print the block:  python3 scripts/signals.py
"""
import os
import json
import datetime
import collections
import requests

TODAY = datetime.date.today()
DATA_DIR = "data/signals"
PW = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services"
FIRMS_KEY = os.environ.get("FIRMS_MAP_KEY", "")
TIMEOUT = 40


def log(msg):
    print(f"[signals] {msg}", flush=True)


def d(s):
    return datetime.date.fromisoformat(s)


# --------------------------------------------------------------------------- #
# PortWatch
# --------------------------------------------------------------------------- #
CHOKEPOINTS = ["Strait of Hormuz", "Bab el-Mandeb Strait", "Suez Canal"]

# portid -> label. Grouped so the model sees the structure, not a list.
PORT_GROUPS = {
    "Gulf loading (inside Hormuz)": {
        "port1091": "Ras Tanura (SA)", "port1090": "Ras Laffan (QA)",
        "port744": "Jebel Ali (AE)", "port2164": "Kharg Island (IR)",
    },
    "Bypass loading (outside Hormuz)": {
        "port362": "Fujairah (AE)", "port570": "Yanbu King Fahd (SA)",
    },
    "Iran Gulf ports": {},      # filled from ISO3 query
    "Iran Caspian ports": {},   # filled from ISO3 query
    "Destination refineries": {
        "port1199": "Sikka/Jamnagar (IN)", "port824": "Ningbo (CN)",
        "port1338": "Ulsan (KR)",
    },
}
IRAN_CASPIAN = {"Bandar-e Anzali", "Amirabad Port", "Nowshahr Port"}


def pw_query(layer, where, fields, order=None, extra=None):
    params = {"where": where, "outFields": ",".join(fields), "f": "json",
              "returnGeometry": "false", "resultRecordCount": 2000}
    if order:
        params["orderByFields"] = order
    if extra:
        params.update(extra)
    r = requests.get(f"{PW}/{layer}/FeatureServer/0/query", params=params, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"])
    rows = [f["attributes"] for f in data.get("features", [])]
    for row in rows:
        if isinstance(row.get("date"), str):
            row["date"] = row["date"][:10]
    return rows


_LATEST = {}


def latest_available(layer, where):
    """Newest date with data in a PortWatch layer (PortWatch lags 4-6 days and the
    last day or two can be partially reported, so anchor on the latest date that
    has data and drop it if it looks thin)."""
    if layer in _LATEST:
        return _LATEST[layer]
    rows = pw_query(layer, where, ["date"], "date DESC", {"resultRecordCount": 400})
    dates = sorted({d(r["date"]) for r in rows}, reverse=True)
    latest = dates[0] if dates else TODAY - datetime.timedelta(days=6)
    _LATEST[layer] = latest
    return latest


def week_windows(latest):
    """Seven full days ending on `latest`, the seven before, and the same
    calendar week in 2025."""
    w1 = (latest - datetime.timedelta(days=6), latest)
    w0 = (w1[0] - datetime.timedelta(days=7), w1[0] - datetime.timedelta(days=1))
    ly = (w1[0].replace(year=w1[0].year - 1), w1[1].replace(year=w1[1].year - 1))
    return w1, w0, ly


def pct(a, b):
    if not b:
        return "n/a"
    return f"{(a / b - 1) * 100:+.0f}%"


def portwatch_chokepoints():
    latest = latest_available("Daily_Chokepoints_Data",
                              f"portname='Strait of Hormuz' AND date >= DATE '{TODAY - datetime.timedelta(days=14)}'")
    w1, w0, ly = week_windows(latest)
    where = ("portname IN ({}) AND (date BETWEEN DATE '{}' AND DATE '{}' "
             "OR date BETWEEN DATE '{}' AND DATE '{}')").format(
        ",".join(f"'{c}'" for c in CHOKEPOINTS), w0[0], w1[1], ly[0], ly[1])
    rows = pw_query("Daily_Chokepoints_Data", where,
                    ["date", "portname", "n_total", "n_tanker", "n_container",
                     "n_dry_bulk", "capacity_tanker"], "portname,date")
    out, lines = {}, []
    for cp in CHOKEPOINTS:
        r = [x for x in rows if x["portname"] == cp]

        def agg(win):
            sel = [x for x in r if win[0] <= d(x["date"]) <= win[1]]
            n = max(len(sel), 1)
            return {"days": len(sel),
                    "total_pd": sum(x["n_total"] or 0 for x in sel) / n,
                    "tanker_pd": sum(x["n_tanker"] or 0 for x in sel) / n,
                    "container_pd": sum(x["n_container"] or 0 for x in sel) / n,
                    "tanker_dwt_pd": sum(x["capacity_tanker"] or 0 for x in sel) / n}
        a1, a0, aly = agg(w1), agg(w0), agg(ly)
        latest = r[-1] if r else None
        out[cp] = {"latest_day": latest, "week": a1, "prior_week": a0, "same_week_2025": aly,
                   "daily": [{k: x[k] for k in ("date", "n_total", "n_tanker", "capacity_tanker")}
                             for x in r if d(x["date"]) >= w1[0]]}
        lines.append(
            f"- **{cp}** (latest data {latest['date'] if latest else 'n/a'}): "
            f"{a1['total_pd']:.1f} transits/day, of which {a1['tanker_pd']:.1f} tankers "
            f"({a1['tanker_dwt_pd']/1000:.0f}k DWT/day). Prior week {a0['total_pd']:.1f}/{a0['tanker_pd']:.1f}. "
            f"Same week 2025: {aly['total_pd']:.0f}/{aly['tanker_pd']:.0f} ({aly['tanker_dwt_pd']/1e6:.2f}M DWT/day). "
            f"Tanker DWT vs 2025: {pct(a1['tanker_dwt_pd'], aly['tanker_dwt_pd'])}; vs prior week: {pct(a1['tanker_dwt_pd'], a0['tanker_dwt_pd'])}.")
        if latest and cp == "Strait of Hormuz":
            days = ", ".join(f"{x['date'][5:]}: {x['n_total']}/{x['n_tanker']}t" for x in r if d(x["date"]) >= w1[0])
            lines.append(f"  Hormuz daily (total/tankers): {days}")
    return out, lines


def portwatch_ports():
    # Port data trails a day behind the chokepoint series and the newest day is
    # often thin; anchor one day earlier than the chokepoint anchor.
    latest = latest_available("Daily_Chokepoints_Data",
                              f"portname='Strait of Hormuz' AND date >= DATE '{TODAY - datetime.timedelta(days=14)}'")
    latest = latest - datetime.timedelta(days=2)
    w1, w0, ly = week_windows(latest)
    # Iran ports by ISO3 + the named ports elsewhere
    named = {pid for g in PORT_GROUPS.values() for pid in g}
    where = ("(ISO3='IRN' OR portid IN ({})) AND (date BETWEEN DATE '{}' AND DATE '{}' "
             "OR date BETWEEN DATE '{}' AND DATE '{}')").format(
        ",".join(f"'{p}'" for p in named), w0[0], w1[1], ly[0], ly[1])
    rows = pw_query("Daily_Ports_Data", where,
                    ["date", "portid", "portname", "ISO3", "portcalls", "portcalls_tanker",
                     "import", "export", "import_tanker", "export_tanker"], "portname,date")
    groups = {k: dict(v) for k, v in PORT_GROUPS.items()}
    for x in rows:
        if x["ISO3"] == "IRN" and x["portid"] not in named:
            key = "Iran Caspian ports" if x["portname"] in IRAN_CASPIAN else "Iran Gulf ports"
            groups[key][x["portid"]] = f"{x['portname']} (IR)"

    def agg(sel):
        return {"calls": sum(x["portcalls"] or 0 for x in sel),
                "tanker_calls": sum(x["portcalls_tanker"] or 0 for x in sel),
                "import_kt": sum(x["import"] or 0 for x in sel) / 1000,
                "export_kt": sum(x["export"] or 0 for x in sel) / 1000,
                "tanker_import_kt": sum(x["import_tanker"] or 0 for x in sel) / 1000,
                "tanker_export_kt": sum(x["export_tanker"] or 0 for x in sel) / 1000}
    out, lines = {}, []
    for gname, ports in groups.items():
        if not ports:
            continue
        lines.append(f"- **{gname}** (7-day sums for {w1[0]}..{w1[1]} vs prior 7 days vs same week 2025; kt = thousand tonnes est.):")
        out[gname] = {}
        for pid, label in ports.items():
            r = [x for x in rows if x["portid"] == pid]
            a1 = agg([x for x in r if w1[0] <= d(x["date"]) <= w1[1]])
            a0 = agg([x for x in r if w0[0] <= d(x["date"]) <= w0[1]])
            aly = agg([x for x in r if ly[0] <= d(x["date"]) <= ly[1]])
            out[gname][label] = {"week": a1, "prior_week": a0, "same_week_2025": aly}
            lines.append(
                f"  - {label}: calls {a1['calls']} / {a0['calls']} / {aly['calls']}; "
                f"tanker calls {a1['tanker_calls']} / {a0['tanker_calls']} / {aly['tanker_calls']}; "
                f"exports {a1['export_kt']:.0f} / {a0['export_kt']:.0f} / {aly['export_kt']:.0f} kt; "
                f"imports {a1['import_kt']:.0f} / {a0['import_kt']:.0f} / {aly['import_kt']:.0f} kt")
    # Iran national split: Caspian vs Gulf share of calls
    try:
        cas = sum(v["week"]["calls"] for v in out.get("Iran Caspian ports", {}).values())
        gulf = sum(v["week"]["calls"] for v in out.get("Iran Gulf ports", {}).values())
        cas_ly = sum(v["same_week_2025"]["calls"] for v in out.get("Iran Caspian ports", {}).values())
        gulf_ly = sum(v["same_week_2025"]["calls"] for v in out.get("Iran Gulf ports", {}).values())
        lines.append(f"- **Iran port-call split, latest week:** Caspian {cas} vs Gulf {gulf} "
                     f"(same week 2025: Caspian {cas_ly} vs Gulf {gulf_ly}).")
        out["iran_split"] = {"caspian": cas, "gulf": gulf, "caspian_2025": cas_ly, "gulf_2025": gulf_ly}
    except Exception:
        pass
    return out, lines


# --------------------------------------------------------------------------- #
# tgju — rial, tether, gold
# --------------------------------------------------------------------------- #
TGJU_KEYS = {"price_dollar_rl": "USD/IRR open market", "price_eur": "EUR/IRR open market",
             "crypto-tether-irr": "Tether (USDT)/IRR", "geram18": "Gold 18k, per gram (IRR)",
             "sekee": "Emami gold coin (IRR)"}


def tgju():
    r = requests.get("https://call1.tgju.org/ajax.json", headers={"User-Agent": "Mozilla/5.0"}, timeout=TIMEOUT)
    r.raise_for_status()
    cur = r.json().get("current", {})
    out, lines = {}, []
    for k, label in TGJU_KEYS.items():
        if k in cur:
            p = float(str(cur[k].get("p", "0")).replace(",", ""))
            out[k] = {"label": label, "price": p, "day_change": cur[k].get("d"), "dp": cur[k].get("dp"),
                      "updated": cur[k].get("ts")}
    hist = load_history()
    usd = out.get("price_dollar_rl", {}).get("price")
    tether = out.get("crypto-tether-irr", {}).get("price")
    if usd:
        line = f"- **Rial, open market:** {usd:,.0f} IRR/USD"
        prev = prior_value(hist, ["tgju", "price_dollar_rl", "price"], days=7)
        if prev:
            line += f" ({pct(usd, prev[1])} vs {prev[0]}; positive = rial weaker)"
        if tether:
            line += f"; Tether {tether:,.0f} IRR ({(tether/usd-1)*100:+.1f}% vs cash dollar)"
        lines.append(line)
    if "sekee" in out:
        lines.append(f"- **Tehran gold:** Emami coin {out['sekee']['price']/1e6:,.0f}M IRR; 18k gram {out['geram18']['price']/1e6:,.1f}M IRR")
    return out, lines


# --------------------------------------------------------------------------- #
# IODA — Iran internet connectivity
# --------------------------------------------------------------------------- #
def ioda():
    now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    out, lines = {}, []
    for ds in ("bgp", "ping-slash24"):
        r = requests.get(f"https://api.ioda.inetintel.cc.gatech.edu/v2/signals/raw/country/IR",
                         params={"from": now - 86400 * 7, "until": now, "datasource": ds, "maxPoints": 400},
                         timeout=TIMEOUT)
        r.raise_for_status()
        s = r.json()["data"][0][0]
        vals = [v for v in s["values"] if v is not None]
        if not vals:
            continue
        step = s.get("step", 0)
        n24 = max(1, int(86400 / step)) if step else len(vals) // 7
        last24, prior = vals[-n24:], vals[:-n24] or vals
        out[ds] = {"last": vals[-1], "min_24h": min(last24), "mean_24h": sum(last24) / len(last24),
                   "mean_prior_6d": sum(prior) / len(prior)}
    if out:
        p = out.get("ping-slash24", {})
        b = out.get("bgp", {})
        lines.append(
            f"- **Iran internet (IODA):** active probing last {p.get('last', 0):,.0f} reachable /24s "
            f"(24h min {p.get('min_24h', 0):,.0f}; prior-6-day mean {p.get('mean_prior_6d', 0):,.0f}); "
            f"BGP visible prefixes last {b.get('last', 0):,.0f} (prior-6-day mean {b.get('mean_prior_6d', 0):,.0f}). "
            f"A drop >10% below the prior mean indicates a shutdown or infrastructure damage.")
    return out, lines


# --------------------------------------------------------------------------- #
# Israel Home Front Command alerts
# --------------------------------------------------------------------------- #
THREAT = {0: "rockets/missiles", 1: "unconventional", 2: "infiltration", 3: "earthquake",
          4: "tsunami", 5: "hostile aircraft/UAV", 6: "hazmat", 7: "terror"}


def israel_alerts():
    r = requests.get("https://api.tzevaadom.co.il/alerts-history", headers={"User-Agent": "Mozilla/5.0"}, timeout=TIMEOUT)
    r.raise_for_status()
    events = r.json()
    by_day = collections.defaultdict(lambda: collections.Counter())
    cities_by_day = collections.defaultdict(set)
    for ev in events:
        for a in ev.get("alerts", []):
            if a.get("isDrill"):
                continue
            day = datetime.datetime.fromtimestamp(a["time"], datetime.timezone.utc).date()
            by_day[day][THREAT.get(a.get("threat"), "other")] += 1
            cities_by_day[day].update(a.get("cities", []))
    cutoff = TODAY - datetime.timedelta(days=7)
    out = {day.isoformat(): {"alerts": dict(c), "localities": len(cities_by_day[day])}
           for day, c in by_day.items() if day >= cutoff}
    total7 = sum(sum(v["alerts"].values()) for v in out.values())
    prior = [day for day in by_day if cutoff - datetime.timedelta(days=7) <= day < cutoff]
    total_prior = sum(sum(by_day[day].values()) for day in prior)
    detail = "; ".join(f"{k[5:]}: " + ", ".join(f"{n} {t}" for t, n in v["alerts"].items())
                       for k, v in sorted(out.items())) or "none"
    lines = [f"- **Israel Home Front alerts, last 7 days:** {total7} alert events (prior 7 days: {total_prior}). {detail}."]
    return {"days": out, "total_7d": total7, "total_prior_7d": total_prior}, lines


# --------------------------------------------------------------------------- #
# OpenSky — airspace activity snapshot
# --------------------------------------------------------------------------- #
BOXES = {"Iran": (25, 44, 40, 63), "Gulf (KW/SA-east/QA/AE/OM)": (22, 46, 30, 60),
         "Israel/Lebanon": (29, 34, 34, 36.5), "Iraq": (29, 38.5, 37.5, 48.5)}


def opensky():
    out, parts = {}, []
    for name, (lamin, lomin, lamax, lomax) in BOXES.items():
        r = requests.get("https://opensky-network.org/api/states/all",
                         params={"lamin": lamin, "lomin": lomin, "lamax": lamax, "lomax": lomax}, timeout=TIMEOUT)
        r.raise_for_status()
        states = r.json().get("states") or []
        out[name] = len(states)
        parts.append(f"{name} {len(states)}")
    hist = load_history()
    prev = prior_value(hist, ["opensky", "Iran"], days=7)
    note = f" (Iran a week ago: {prev[1]})" if prev else ""
    return out, [f"- **Aircraft broadcasting ADS-B at run time (~11:55 UTC):** " + "; ".join(parts) + note
                 + ". Civil traffic proxy only; military aircraft in theatre generally do not broadcast."]


# --------------------------------------------------------------------------- #
# NASA FIRMS — thermal anomalies at Iranian industrial sites
# --------------------------------------------------------------------------- #
SITES = {  # name: (lon_min, lat_min, lon_max, lat_max)
    "Assaluyeh / South Pars": (52.4, 27.3, 52.8, 27.6),
    "Abadan refinery / Khorramshahr": (48.2, 30.2, 48.4, 30.45),
    "Bandar Abbas refinery / Shahid Rajaee": (56.0, 27.0, 56.4, 27.2),
    "Kharg Island": (50.25, 29.2, 50.4, 29.3),
    "Isfahan (refinery, steel, nuclear)": (51.5, 32.55, 51.9, 32.9),
    "Arak": (49.6, 34.0, 49.9, 34.15),
    "Tabriz refinery / petrochem": (46.1, 38.0, 46.4, 38.15),
    "Tehran south (refinery, Parchin)": (51.3, 35.45, 51.9, 35.65),
    "Mobarakeh steel": (51.35, 32.2, 51.55, 32.35),
}


def firms():
    if not FIRMS_KEY:
        return {}, ["- **Thermal anomalies (NASA FIRMS):** not collected — FIRMS_MAP_KEY not set."]
    out, lines = {}, []
    for name, (x0, y0, x1, y1) in SITES.items():
        url = (f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{FIRMS_KEY}/VIIRS_SNPP_NRT/"
               f"{x0},{y0},{x1},{y1}/10")
        r = requests.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        rows = [ln.split(",") for ln in r.text.strip().splitlines()[1:] if ln]
        # columns: latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight
        by_day = collections.defaultdict(lambda: [0, 0.0])
        for c in rows:
            try:
                by_day[c[5]][0] += 1
                by_day[c[5]][1] += float(c[12])
            except (IndexError, ValueError):
                pass
        days = sorted(by_day)
        last = days[-1] if days else None
        last_n, last_frp = by_day[last] if last else (0, 0.0)
        prior = [by_day[x] for x in days[:-1]]
        mean_n = sum(p[0] for p in prior) / max(len(prior), 1)
        mean_frp = sum(p[1] for p in prior) / max(len(prior), 1)
        out[name] = {"latest_day": last, "detections": last_n, "frp_mw": round(last_frp, 1),
                     "prior_9d_mean_detections": round(mean_n, 1), "prior_9d_mean_frp": round(mean_frp, 1),
                     "days_with_detections_10d": len(days)}
        lines.append(f"  - {name}: {last_n} detections / {last_frp:.0f} MW on {last or 'n/a'} "
                     f"(prior 9-day mean {mean_n:.1f} / {mean_frp:.0f} MW)")
    return out, ["- **Thermal anomalies (VIIRS, NASA FIRMS), latest day vs prior 9 days.** Persistent heat = flaring/furnaces "
                 "(throughput proxy); a spike is a fire or strike; disappearance is a shutdown:"] + lines


# --------------------------------------------------------------------------- #
# History helpers
# --------------------------------------------------------------------------- #
def load_history():
    hist = {}
    if not os.path.isdir(DATA_DIR):
        return hist
    for fn in sorted(os.listdir(DATA_DIR)):
        if fn.endswith(".json"):
            try:
                with open(os.path.join(DATA_DIR, fn), encoding="utf-8") as f:
                    hist[fn[:-5]] = json.load(f)
            except Exception:
                pass
    return hist


def prior_value(hist, path, days):
    """Value at `path` from the newest stored day that is >= `days` old (else the oldest available)."""
    target = (TODAY - datetime.timedelta(days=days)).isoformat()
    candidates = sorted(k for k in hist if k <= target) or sorted(hist)[:1]
    for k in reversed(candidates):
        v = hist[k]
        try:
            for p in path:
                v = v[p]
            return k, v
        except (KeyError, TypeError):
            continue
    return None


# --------------------------------------------------------------------------- #
# Assemble
# --------------------------------------------------------------------------- #
COLLECTORS = [
    ("Chokepoint transits (IMF PortWatch, AIS-derived — a floor: dark/escorted transits are invisible)", "portwatch_chokepoints", portwatch_chokepoints),
    ("Port activity (IMF PortWatch)", "portwatch_ports", portwatch_ports),
    ("Iranian currency and gold (tgju.org, Tehran open market)", "tgju", tgju),
    ("Iran internet connectivity (IODA)", "ioda", ioda),
    ("Israel Home Front Command alerts (tzevaadom.co.il)", "israel_alerts", israel_alerts),
    ("Airspace snapshot (OpenSky)", "opensky", opensky),
    ("Thermal anomalies at Iranian industrial sites (NASA FIRMS)", "firms", firms),
]


def build_signals():
    record = {"date": TODAY.isoformat(), "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    blocks = [f"### Structured signals — collected {record['generated_at'][:16]}Z",
              "*Machine-read data with baselines. Cite as '(PortWatch)', '(tgju)', '(IODA)', '(Home Front alerts)', "
              "'(FIRMS)', '(OpenSky)'. PortWatch lags ~4-5 days; its counts are AIS-visible only.*"]
    for title, key, fn in COLLECTORS:
        try:
            data, lines = fn()
            record[key] = data
            blocks.append(f"**{title}**\n" + "\n".join(lines))
            log(f"{key}: ok")
        except Exception as e:
            record[key] = {"error": str(e)[:300]}
            blocks.append(f"**{title}**\n- not available this run ({str(e)[:120]})")
            log(f"{key}: FAILED {e}")
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, f"{TODAY.isoformat()}.json"), "w", encoding="utf-8") as f:
        json.dump(record, f, indent=1, default=str)
    return "\n\n".join(blocks)


if __name__ == "__main__":
    print(build_signals())
