"""Hämtar V85- eller V65-data från ATG och skriver den JSON som appen Travhästarna läser.

Användning: python3 scripts/atg_v85.py <cachekatalog> .work/v85.json [V85|V65|DUBBEL]  (krypteras sedan med scripts/seal.py)
V85/V65 skriver två filer: <ut>.json med aktuell omgång och <ut>-hist.json med årets avgjorda omgångar.
DUBBEL skriver närmaste Dagens Dubbel och Lunchdubbel.
Avslutade omgångar cachas; kommande/pågående hämtas alltid om.
"""
import datetime as dt, json, os, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

API = "https://www.atg.se/services/racinginfo/v1/api"
START = dt.date(2026, 1, 1)
GAME = sys.argv[3] if len(sys.argv) > 3 else "V85"  # spelformen: V85 eller V65
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


def safe_get(path):
    # en enstaka hämtning som misslyckas ska inte stoppa hela körningen
    try:
        return get(path)
    except Exception as e:
        # ::warning:: syns som en anteckning på körningen i GitHub
        print(f"::warning::Kunde inte hämta {path}: {e}")
        return {}


def cached(cache, name, path, keep):
    f = os.path.join(cache, name + ".json")
    if os.path.exists(f):
        return json.load(open(f))
    d = safe_get(path)
    if d and keep(d):
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
        for g in d.get("games", {}).get(GAME, []):
            ids.append((day.isoformat(), g.get("id"), g.get("status"), g.get("tracks")))
    return ids


def shoes(h):
    s = h.get("shoes") or {}
    if not s.get("reported"):
        return ""
    if not s.get("front") or not s.get("back"):
        return ""
    f, b = s["front"].get("hasShoe"), s["back"].get("hasShoe")
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
    v = ((s.get("pools") or {}).get(GAME) or {}).get("betDistribution")
    return None if v is None else v / 100


def leg_len(r):
    return f"{r['distance']} m {'autostart' if r.get('startMethod') == 'auto' else 'voltstart'}"


def name(p):
    p = p or {}  # t.ex. kusk som inte är klar än
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
        if not (g.get("pools") or {}).get(GAME):
            # startlistan är ute men spelet har inte öppnat: inga odds eller V85-procent än
            waiting = waiting or {"date": date, "track": g["races"][0]["track"]["name"], "start": g["races"][0].get("startTime")}
            continue
        pool = g["pools"][GAME]
        res = (pool.get("result") or {}).get("payouts") or {}
        done = g.get("status") == "results"
        if not done and g.get("status") not in ("bettable", "ongoing", "upcoming"):
            continue  # inställd eller struken omgång
        if done:
            legs = []
            for r in g["races"]:
                run = [s for s in r["starts"] if not s.get("scratched")]
                legs.append({
                    "w": [[s["number"], s["horse"]["name"], name(s.get("driver")), odds(s)]
                          for s in run if (s.get("result") or {}).get("place") == 1],
                    "h": [[s["number"], odds(s), streck(s)] for s in run],
                })
            rounds.append({"id": gid, "date": date, "track": g["races"][0]["track"]["name"],
                           "pay": {k: (v.get("payout") or 0) / 100 or None for k, v in res.items()},
                           "turnover": pool.get("turnover", 0) / 100, "jp": pool.get("jackpotAmount"), "legs": legs})
            last_done = g
        else:
            open_games.append(g)
    # närmaste omgång som går att spela på; annars den senast avgjorda
    cur = open_games[0] if open_games else last_done
    if cur is None:
        print(f"::error::Fick ingen {GAME}-omgång från ATG ({len(ids)} omgångar i kalendern, {sum(1 for g in games if g.get('races'))} med lopp).")
        sys.exit(1)
    if open_games:
        waiting = None
    year = int(cur["races"][0]["date"][:4])
    field, odds_open = [], True
    for r in cur["races"]:
        h = []
        for s in r["starts"]:
            hs = s["horse"]
            info = " ".join(x for x in [f"{hs['age']} år" if hs.get("age") else "", SEX.get(hs.get("sex"), hs.get("sex") or "")] if x)
            if s.get("distance", r["distance"]) != r["distance"]:
                info += f" · +{s['distance'] - r['distance']} m"
            h.append([s["number"], hs["name"], name(s.get("driver")),
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
                "pay": {k: (v.get("payout") or 0) / 100 or None for k, v in ((cur["pools"][GAME].get("result") or {}).get("payouts") or {}).items()},
                "turnover": cur["pools"][GAME].get("turnover", 0) / 100, "oddsOpen": odds_open,
                # extra pengar i toppotten (8 rätt på V85, 6 rätt på V65) (jackpot från förra omgången eller ATG:s egna tillskott), i kronor
                "jackpot": cur["pools"][GAME].get("jackpotAmount"), "field": field},
        "next": upcoming[0][0] if upcoming else None,
        "waiting": waiting,
        "later": later,
    }


def build_dd(today, kind="dd"):
    """Närmaste Dagens Dubbel (dd) eller Lunchdubbel (ld) som går att spela: båda loppens hästar
    och oddset för varje kombination."""
    for day in [today + dt.timedelta(days=i) for i in range(8)]:
        cal = safe_get(f"/calendar/day/{day}")
        ids = [g["id"] for g in cal.get("games", {}).get(kind, []) if g.get("id") and g.get("status") == "bettable"]
        for gid in ids:
            g = safe_get(f"/games/{gid}")
            pool = (g.get("pools") or {}).get(kind) or {}
            if len(g.get("races") or []) != 2 or not pool.get("comboOdds"):
                continue
            legs = []
            for r in g["races"]:
                vp = ((r.get("pools") or {}).get("vinnare") or {}).get("turnover")
                legs.append({"race": r["number"], "track": r["track"]["name"], "start": r.get("startTime"),
                             "len": leg_len(r), "vp": None if vp is None else vp / 100,
                             "h": [[s["number"], s["horse"]["name"], name(s.get("driver")),
                                    0 if s.get("scratched") else odds(s)] for s in r["starts"]]})
            return {"id": gid, "date": g["races"][0]["date"][:10], "turnover": pool.get("turnover", 0) / 100,
                    "combo": pool["comboOdds"], "legs": legs}
    return None


if __name__ == "__main__":
    cache, out = sys.argv[1], sys.argv[2]
    os.makedirs(cache, exist_ok=True)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    def dump(obj, path):
        json.dump(obj, open(path, "w"), ensure_ascii=False, separators=(",", ":"))

    try:
        if GAME == "DUBBEL":
            dump({"updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
                  "dd": build_dd(dt.date.today(), "dd"), "ld": build_dd(dt.date.today(), "ld")}, out)
            print(out, "Dagens Dubbel och Lunchdubbel")
            sys.exit(0)
        data = build(cache, dt.date.today())
    except Exception:
        import traceback
        # hela felet som en anteckning på körningen i GitHub
        print("::error::" + traceback.format_exc().replace("\n", "%0A"))
        raise
    data["game"] = GAME
    # historiken ändras bara när en omgång avgörs, så den sparas för sig
    dump({"game": GAME, "rounds": data.pop("rounds")}, out[:-5] + "-hist.json")
    dump(data, out)
    data["rounds"] = json.load(open(out[:-5] + "-hist.json"))["rounds"]
    print(out, len(data["rounds"]), "omgångar; aktuell", data["cur"]["id"], data["cur"]["status"], "· nästa", data["next"])
