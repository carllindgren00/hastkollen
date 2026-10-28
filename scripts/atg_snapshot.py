"""Sparar ATG:s aktuella vinnarodds och V85-procent för dagens V85-omgång.

Användning: python3 scripts/atg_snapshot.py .work/snaps [--game V85_...]  (krypteras sedan med scripts/seal.py)
Skriver en JSON-fil per omgång som ännu inte är avgjord och lägger till den i
index.json, som sidans Logg-flik läser. Avd skrivs som "nr:odds:procent,...".
"""
import datetime as dt, json, os, sys, urllib.request
from zoneinfo import ZoneInfo

API = "https://www.atg.se/services/racinginfo/v1/api"
TZ = ZoneInfo("Europe/Stockholm")


def get(path):
    with urllib.request.urlopen(API + path, timeout=40) as r:
        return json.load(r)


def snapshot(gid, now):
    g = get(f"/games/{gid}")
    races = g.get("races") or []
    if not races:
        return None
    first = dt.datetime.fromisoformat(races[0]["startTime"]).replace(tzinfo=TZ)
    legs = []
    for r in races:
        parts = []
        for s in r["starts"]:
            if s.get("scratched"):
                continue
            pools = s.get("pools") or {}
            o = ((pools.get("vinnare") or {}).get("odds") or 0) / 100
            b = ((pools.get("V85") or {}).get("betDistribution") or 0) / 100
            parts.append(f"{s['number']}:{o:g}:{b:g}")
        legs.append(",".join(parts))
    return {
        "game": gid, "date": races[0]["date"][:10], "track": races[0]["track"]["name"],
        "status": g.get("status"), "taken": now.isoformat(timespec="minutes"),
        "minsToStart": round((first - now).total_seconds() / 60),
        "legStarts": [r.get("startTime") for r in races],
        "turnover": (g["pools"]["V85"].get("turnover") or 0) / 100, "legs": legs,
    }


if __name__ == "__main__":
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    now = dt.datetime.now(TZ)
    if "--game" in sys.argv:
        ids = [sys.argv[sys.argv.index("--game") + 1]]
    else:
        cal = get(f"/calendar/day/{now.date()}")
        ids = [g["id"] for g in cal.get("games", {}).get("V85", []) if g.get("id") and g.get("status") != "results"]
    if not ids:
        print("Ingen V85-omgång att logga i dag.")
    for gid in ids:
        snap = snapshot(gid, now)
        if not snap:
            print(gid, "har ingen startlista än")
            continue
        name = f"{gid}_{now:%Y%m%d%H%M}"
        json.dump(snap, open(os.path.join(out, name + ".json"), "w"), ensure_ascii=False)
        idx_path = os.path.join(out, "index.json")
        idx = json.load(open(idx_path)) if os.path.exists(idx_path) else []
        idx.append({"id": name, **{k: snap[k] for k in ("game", "date", "track", "taken", "minsToStart")}})
        json.dump(idx, open(idx_path, "w"), ensure_ascii=False, indent=0)
        print(os.path.join(out, name + ".json"), snap["status"], snap["minsToStart"], "min till start")
