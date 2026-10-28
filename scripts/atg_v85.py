"""Hämtar V85-data från ATG och skriver den JSON som V85-kollen läser.

Användning: python3 scripts/atg_v85.py <cachekatalog> .work/v85.json  (krypteras sedan med scripts/seal.py)
Avslutade omgångar cachas; kommande/pågående hämtas alltid om.
"""
import datetime as dt, json, os, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

API = "https://www.atg.se/services/racinginfo/v1/api"
START = dt.date(2026, 1, 1)
SEX = {"mare": "sto", "gelding": "valack", "stallion": "hingst"}


def get(path):
    for i in range(4):
        try:
            with urllib.request.urlopen(API + path, timeout=40) as r:
                return json.load(r)
        except Exception:
            if i == 3:
                raise
            time.sleep(2 ** i)


def cached(cache, name, path, keep):
    f = os.path.join(cache, name + ".json")
    if os.path.exists(f):
        return json.load(open(f))
    d = get(path)
    if keep(d):
        json.dump(d, open(f, "w"))
    return d


def game_ids(cache, today):
    days = [START + dt.timedelta(days=i) for i in range((today - START).days + 9)]
    load = lambda day: cached(cache, "cal_" + day.isoformat(), f"/calendar/day/{day}",
                              lambda d: day < today - dt.timedelta(days=1))
    with ThreadPoolExecutor(8) as ex:
        cals = list(ex.map(load, days))
    ids = []
    for day, d in zip(days, cals):
        for g in d.get("games", {}).get("V85", []):
            ids.append((day.isoformat(), g.get("id"), g.get("status"), g.get("tracks")))
    return ids


def shoes(h):
    s = h.get("shoes") or {}
    if not s.get("reported"):
        return ""
    f, b = s["front"]["hasShoe"], s["back"]["hasShoe"]
    txt = "Skor runt" if f and b else "Barfota runt" if not (f or b) else "Barfota bak" if f else "Barfota fram"
    return txt + (" (ändrat)" if s["front"].get("changed") or s["back"].get("changed") else "")


def form(h, year):
    y = (h.get("statistics") or {}).get("years", {}).get(str(year))
    if not y or not y.get("starts"):
        return ""
    p = y.get("placement", {})
    return f"{y['starts']} st: {p.get('1', 0)}-{p.get('2', 0)}-{p.get('3', 0)}"


def odds(s):
    r = s.get("result") or {}
    if r.get("finalOdds"):
        return r["finalOdds"]
    o = ((s.get("pools") or {}).get("vinnare") or {}).get("odds") or 0
    return o / 100


def streck(s):
    v = ((s.get("pools") or {}).get("V85") or {}).get("betDistribution")
    return None if v is None else v / 100


def leg_len(r):
    return f"{r['distance']} m {'autostart' if r.get('startMethod') == 'auto' else 'voltstart'}"


def name(p):
    return f"{p.get('firstName', '')} {p.get('lastName', '')}".strip()


def build(cache, today):
    ids = game_ids(cache, today)
    rounds, last_done, open_games, waiting = [], None, [], None
    gids = [x for x in sorted(ids, key=lambda x: x[0]) if x[1]]
    with ThreadPoolExecutor(8) as ex:
        games = list(ex.map(lambda x: cached(cache, x[1], f"/games/{x[1]}", lambda d: d.get("status") == "results"), gids))
    for (date, gid, status, tracks), g in zip(gids, games):
        if not g.get("races"):
            continue
        if not (g.get("pools") or {}).get("V85"):
            # startlistan är ute men spelet har inte öppnat: inga odds eller V85-procent än
            waiting = waiting or {"date": date, "track": g["races"][0]["track"]["name"], "start": g["races"][0].get("startTime")}
            continue
        pool = g["pools"]["V85"]
        res = (pool.get("result") or {}).get("payouts") or {}
        done = g.get("status") == "results"
        if done:
            legs = []
            for r in g["races"]:
                run = [s for s in r["starts"] if not s.get("scratched")]
                legs.append({
                    "w": [[s["number"], s["horse"]["name"], name(s["driver"]), odds(s)]
                          for s in run if (s.get("result") or {}).get("place") == 1],
                    "h": [[s["number"], odds(s), streck(s)] for s in run],
                })
            rounds.append({"id": gid, "date": date, "track": g["races"][0]["track"]["name"],
                           "pay": {k: (v.get("payout") or 0) / 100 or None for k, v in res.items()},
                           "turnover": pool.get("turnover", 0) / 100, "legs": legs})
            last_done = g
        else:
            open_games.append(g)
    # närmaste omgång som går att spela på; annars den senast avgjorda
    cur = open_games[0] if open_games else last_done
    if open_games:
        waiting = None
    year = int(cur["races"][0]["date"][:4])
    field, odds_open = [], True
    for r in cur["races"]:
        h = []
        for s in r["starts"]:
            hs = s["horse"]
            info = f"{hs['age']} år {SEX.get(hs['sex'], hs['sex'])}"
            if s.get("distance", r["distance"]) != r["distance"]:
                info += f" · +{s['distance'] - r['distance']} m"
            h.append([s["number"], hs["name"], name(s["driver"]),
                      0 if s.get("scratched") else odds(s), name(hs.get("trainer", {})),
                      streck(s), info, shoes(hs), form(hs, year)])
        # ATG visar 99,99 på alla hästar innan vinnarspelet öppnat; räkna då på V85-procenten
        if all(x[3] >= 99.99 for x in h if x[3] > 0):
            odds_open = False
            for x in h:
                if x[3] > 0:
                    x[3] = round(min(999, 100 / max(x[5] or 0.1, 0.1)), 2)
        # pengar i vinnarspelet: tidigt i veckan några hundralappar, vid start runt en miljon
        vp = ((r.get("pools") or {}).get("vinnare") or {}).get("turnover")
        field.append({"avd": r["number"], "len": leg_len(r), "h": h, "vp": None if vp is None else vp / 100,
                      "w": [s["number"] for s in r["starts"] if (s.get("result") or {}).get("place") == 1]})
    upcoming = [(d, st) for d, gid, st, t in ids if d > cur["races"][0]["date"][:10]]
    later = [{"date": g["races"][0]["date"][:10], "track": g["races"][0]["track"]["name"]} for g in open_games[1:]]
    return {
        "updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
        "rounds": rounds[::-1],
        "cur": {"id": cur["id"], "date": cur["races"][0]["date"][:10], "track": cur["races"][0]["track"]["name"],
                "start": cur["races"][0].get("startTime"), "status": cur.get("status"),
                "done": cur.get("status") == "results",
                "pay": {k: (v.get("payout") or 0) / 100 or None for k, v in ((cur["pools"]["V85"].get("result") or {}).get("payouts") or {}).items()},
                "turnover": cur["pools"]["V85"].get("turnover", 0) / 100, "oddsOpen": odds_open, "field": field},
        "next": upcoming[0][0] if upcoming else None,
        "waiting": waiting,
        "later": later,
    }


if __name__ == "__main__":
    cache, out = sys.argv[1], sys.argv[2]
    os.makedirs(cache, exist_ok=True)
    data = build(cache, dt.date.today())
    json.dump(data, open(out, "w"), ensure_ascii=False, separators=(",", ":"))
    print(out, len(data["rounds"]), "omgångar; aktuell", data["cur"]["id"], data["cur"]["status"], "· nästa", data["next"])
