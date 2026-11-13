"""Sparar ATG:s odds före start för dagens V85, V65, Dagens Dubbel och Lunchdubbel.

Användning: python3 scripts/atg_snapshot.py .work/snaps [docs/data/snapshots/files.json] [--game <id>]
(krypteras sedan med scripts/seal.py). Körs varje halvtimme. En omgång loggas när det är högst
150 minuter kvar till första start, plus en tidig gång samma dag, så att det går att testa
modellen med de odds man faktiskt hade när man spelade.

V85/V65: "legs" är en text per avdelning, "nr:vinnarodds:spelprocent,...", och "vp" pengarna i
vinnarspelet per lopp. dd/ld: "legs" är "nr:vinnarodds,..." per lopp och "combo" ATG:s odds för
varje kombination (rad = häst i första loppet).
"""
import datetime as dt, json, os, sys, urllib.request
from zoneinfo import ZoneInfo

API = "https://www.atg.se/services/racinginfo/v1/api"
TZ = ZoneInfo("Europe/Stockholm")
KINDS = ("V85", "V65", "dd", "ld")
NEAR, EARLY = 150, 600  # minuter före start


def get(path):
    with urllib.request.urlopen(API + path, timeout=40) as r:
        return json.load(r)


def snapshot(gid, now):
    kind = gid.split("_")[0]
    g = get(f"/games/{gid}")
    races = g.get("races") or []
    pool = (g.get("pools") or {}).get(kind)
    if not races or not pool:
        return None
    first = dt.datetime.fromisoformat(races[0]["startTime"]).replace(tzinfo=TZ)
    legs, vp = [], []
    for r in races:
        parts = []
        for s in r["starts"]:
            if s.get("scratched"):
                continue
            pools = s.get("pools") or {}
            o = ((pools.get("vinnare") or {}).get("odds") or 0) / 100
            if kind in ("dd", "ld"):
                parts.append(f"{s['number']}:{o:g}")
            else:
                b = ((pools.get(kind) or {}).get("betDistribution") or 0) / 100
                parts.append(f"{s['number']}:{o:g}:{b:g}")
        legs.append(",".join(parts))
        vp.append((((r.get("pools") or {}).get("vinnare") or {}).get("turnover") or 0) / 100)
    snap = {
        "game": gid, "kind": kind, "date": races[0]["date"][:10], "track": races[0]["track"]["name"],
        "status": g.get("status"), "taken": now.isoformat(timespec="minutes"),
        "minsToStart": round((first - now).total_seconds() / 60),
        "legStarts": [r.get("startTime") for r in races],
        "turnover": (pool.get("turnover") or 0) / 100, "legs": legs, "vp": vp,
    }
    if kind in ("dd", "ld"):
        snap["combo"] = json.dumps(pool.get("comboOdds") or [], separators=(",", ":"))
    else:
        snap["jackpot"] = pool.get("jackpotAmount")
    return snap


def wanted(g, now, logged):
    """Logga nära start, och en tidig gång samma dag."""
    if not g.get("id") or g.get("status") != "bettable" or not g.get("startTime"):
        return False
    mins = (dt.datetime.fromisoformat(g["startTime"]).replace(tzinfo=TZ) - now).total_seconds() / 60
    return 0 < mins <= NEAR or (NEAR < mins <= EARLY and g["id"] not in logged)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = args[0]
    os.makedirs(out, exist_ok=True)
    now = dt.datetime.now(TZ)
    if "--game" in sys.argv:
        ids = [sys.argv[sys.argv.index("--game") + 1]]
    else:
        logged = set()
        if len(args) > 1 and os.path.exists(args[1]):
            logged = {x["game"] for x in json.load(open(args[1]))}
        cal = get(f"/calendar/day/{now.date()}")
        ids = [g["id"] for k in KINDS for g in cal.get("games", {}).get(k, []) if wanted(g, now, logged)]
    if not ids:
        print("Inget spel nära start att logga just nu.")
    for gid in ids:
        try:
            snap = snapshot(gid, now)
        except Exception as e:  # ett spel som krånglar ska inte stoppa de andra
            print(f"::warning::Kunde inte logga {gid}: {e}")
            continue
        if not snap:
            print(gid, "har inga odds än")
            continue
        name = f"{gid}_{now:%Y%m%d%H%M}"
        json.dump(snap, open(os.path.join(out, name + ".json"), "w"), ensure_ascii=False)
        print(os.path.join(out, name + ".json"), snap["status"], snap["minsToStart"], "min till start")
