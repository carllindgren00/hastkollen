"""Provspel: spelar på låtsas varje omgång med flera strategier, utan pengar, för att se vilken som håller.

Användning: python3 scripts/provspel.py .work/prov docs/data/prov/index.json
Körs varje halvtimme av GitHub Actions. Två steg:
  1. Välj: för dagens V85, V65, V64, GS75, Dagens Dubbel och Lunchdubbel som startar om 8–45 minuter
     väljs en kupong per strategi med de odds som gäller just då, alltså samma odds som man själv har
     när man spelar. Sparas som <id>.json.
  2. Rätta: när omgången är avgjord sparas vinnarna och utdelningen som <id>-res.json.
Båda filerna krypteras sedan med scripts/seal.py. index.json är klartext och innehåller bara
spel, bana, datum och om omgången är rättad, inga kuponger eller odds.
Appen läser filerna och räknar ut hur varje strategi har gått.
"""
import datetime as dt, json, math, os, sys, urllib.request
from zoneinfo import ZoneInfo

API = "https://www.atg.se/services/racinginfo/v1/api"
TZ = ZoneInfo("Europe/Stockholm")
KINDS = ("V85", "V65", "V64", "GS75", "dd", "ld")
PRICE = {"V85": 0.5, "V65": 1, "V64": 1, "GS75": 1}  # kr per rad, samma som i appen
WINDOW = (8, 45)  # minuter före första start då kupongerna väljs
BUDGET = 100      # kr per omgång och strategi
ALPHA = 1.1       # oddsvikten från kalibreringen


def get(path):
    with urllib.request.urlopen(API + path, timeout=40) as r:
        return json.load(r)


def norm(d):
    t = sum(d.values()) or 1
    return {k: v / t for k, v in d.items()}


def conf(vp):
    # hur mycket oddsen ska väga: efter pengarna i vinnarspelet, som i appen
    return 1.0 if vp is None else vp / (vp + 1e5)


# ---------- Dagens Dubbel och Lunchdubbel ----------

def dd_probs(legs, vps, O):
    """Vinstchans per häst: vinnaroddsen, blandat med vad dubbelspelarna själva tror när vinnarspelet är tunt."""
    P = []
    for k, leg in enumerate(legs):
        m = {}
        for (a, b), o in O.items():
            n = a if k == 0 else b
            m[n] = m.get(n, 0) + 1 / o
        dd = norm({n: m.get(n, 1e-6) for n in leg})
        win = norm({n: (1 / o) ** ALPHA for n, o in leg.items() if o > 1})
        c = conf(vps[k]) if win else 0
        P.append(norm({n: c * win.get(n, 0) + (1 - c) * dd[n] for n in leg}))
    return P


def dd_build(P, O, N, lam):
    """Samma metod som appen: hästar A i lopp 1 och B i lopp 2, alla A×B rader.
    Mål = log(chans att träffa) + lam × log(snittvärde per rad)."""
    fav = [max(p, key=p.get) for p in P]
    A, B = [fav[0]], [fav[1]]

    def score(A, B):
        rows = [(a, b) for a in A for b in B if (a, b) in O]
        if not rows:
            return -1e9
        hit = sum(P[0][a] * P[1][b] for a, b in rows)
        ev = sum(P[0][a] * P[1][b] * O[(a, b)] for a, b in rows) / len(rows)
        return math.log(max(hit, 1e-12)) + lam * math.log(max(ev, 1e-9))

    cur = score(A, B)
    while True:
        best = None
        for k, S in ((0, A), (1, B)):
            if (len(A) + (k == 0)) * (len(B) + (k == 1)) > N:
                continue
            for n in P[k]:
                if n in S:
                    continue
                A2, B2 = (A + [n], B) if k == 0 else (A, B + [n])
                v = score(A2, B2)
                if best is None or v > best[0]:
                    best = (v, A2, B2)
        if not best or best[0] < cur:
            break
        cur, A, B = best
    return [[a, b] for a in A for b in B if (a, b) in O]


def dd_pick(g, kind):
    pool = g["pools"][kind]
    races = g["races"]
    legs, vps = [], []
    for r in races:
        leg = {}
        for s in r["starts"]:
            if s.get("scratched"):
                continue
            leg[s["number"]] = (((s.get("pools") or {}).get("vinnare") or {}).get("odds") or 0) / 100
        legs.append(leg)
        vps.append((((r.get("pools") or {}).get("vinnare") or {}).get("turnover") or 0) / 100)
    co = pool.get("comboOdds") or []
    O = {}
    for a in legs[0]:
        for b in legs[1]:
            try:
                o = co[a - 1][b - 1] / 100
            except (IndexError, TypeError):
                continue
            if 1 < o < 999:
                O[(a, b)] = o
    if len(O) < 4:
        return None
    P = dd_probs(legs, vps, O)
    fav = [max(p, key=p.get) for p in P]
    value = sorted(((P[0][a] * P[1][b] * o, (a, b)) for (a, b), o in O.items() if P[0][a] * P[1][b] >= 0.02), reverse=True)
    S = {
        "favfav": [list(fav)] if tuple(fav) in O else [],
        "balans4": dd_build(P, O, 4, 1),
        "balans10": dd_build(P, O, 10, 1),
        "varde4": dd_build(P, O, 4, 2),
        "basta3": [list(r) for _, r in value[:3]],
        "spikalla": [[fav[0], b] for b in legs[1] if (fav[0], b) in O],
    }
    out = {}
    for name, rows in S.items():
        if rows:
            ev = sum(P[0][a] * P[1][b] * O[(a, b)] for a, b in rows) / len(rows)
            out[name] = {"rows": rows, "ev": round(ev, 3)}
    return {"turnover": (pool.get("turnover") or 0) / 100, "vp": vps, "strategies": out}


def dd_result(g, kind):
    res = ((g.get("pools") or {}).get(kind) or {}).get("result") or {}
    w = res.get("winners") or []
    if not w:
        return None
    return {"winners": [[x["combination"][0], x["combination"][1], (x.get("odds") or 0) / 100] for x in w]}


# ---------- V85, V65, V64 och GS75 ----------

def v_pick(g, kind):
    pool = g["pools"][kind]
    legs = []
    for r in g["races"]:
        vp = (((r.get("pools") or {}).get("vinnare") or {}).get("turnover") or 0) / 100
        hs = {}
        for s in r["starts"]:
            if s.get("scratched"):
                continue
            pools = s.get("pools") or {}
            o = ((pools.get("vinnare") or {}).get("odds") or 0) / 100
            st = ((pools.get(kind) or {}).get("betDistribution") or 0) / 100
            hs[s["number"]] = (o, st)
        if not hs:
            return None
        streck = norm({n: max(st, 0.1) for n, (o, st) in hs.items()})
        win = norm({n: (1 / o) ** ALPHA for n, (o, st) in hs.items() if o > 1})
        c = conf(vp) if win else 0
        p = norm({n: c * win.get(n, 0) + (1 - c) * streck[n] for n in hs})
        legs.append((p, streck))
    price = PRICE[kind]

    def build(lam):
        # börja med bästa hästen i varje avdelning och lägg sedan till den häst som ger mest per krona
        sc = [{n: p[n] * (p[n] / s[n]) ** lam for n in p} for p, s in legs]
        order = [sorted(x, key=x.get, reverse=True) for x in sc]
        pick = [[o[0]] for o in order]
        sums = [x[o[0]] for x, o in zip(sc, order)]
        rows = 1
        while True:
            best = None
            for i, (x, o) in enumerate(zip(sc, order)):
                if len(pick[i]) >= len(o):
                    continue
                n = o[len(pick[i])]
                new_rows = rows // len(pick[i]) * (len(pick[i]) + 1)
                if new_rows * price > BUDGET:
                    continue
                gain = math.log((sums[i] + x[n]) / sums[i]) / math.log((len(pick[i]) + 1) / len(pick[i]))
                if best is None or gain > best[0]:
                    best = (gain, i, n, new_rows)
            if not best:
                break
            _, i, n, rows = best
            pick[i].append(n)
            sums[i] += sc[i][n]
        return {"legs": pick, "rows": rows, "cost": round(rows * price, 2)}

    return {"turnover": (pool.get("turnover") or 0) / 100, "jackpot": pool.get("jackpotAmount") or 0,
            "price": price, "strategies": {"chans": build(0), "varde": build(0.5)}}


def v_result(g, kind):
    pool = (g.get("pools") or {}).get(kind) or {}
    pays = (pool.get("result") or {}).get("payouts") or {}
    if not pays:
        return None
    winners = [[s["number"] for s in r["starts"] if (s.get("result") or {}).get("place") == 1] for r in g["races"]]
    return {"winners": winners, "pay": {k: (v.get("payout") or 0) / 100 for k, v in pays.items()}}


# ---------- körningen ----------

def main(out, idx_path):
    os.makedirs(out, exist_ok=True)
    os.makedirs(os.path.dirname(idx_path), exist_ok=True)
    idx = json.load(open(idx_path)) if os.path.exists(idx_path) else []
    have = {x["id"] for x in idx}
    now = dt.datetime.now(TZ)

    # 1. välj kuponger för spel som startar snart
    try:
        cal = get(f"/calendar/day/{now.date()}")
    except Exception as e:
        print(f"::warning::Provspel: kunde inte läsa kalendern: {e}")
        cal = {}
    for kind in KINDS:
        for c in cal.get("games", {}).get(kind, []):
            gid = c.get("id")
            if not gid or gid in have or c.get("status") != "bettable" or not c.get("startTime"):
                continue
            mins = (dt.datetime.fromisoformat(c["startTime"]).replace(tzinfo=TZ) - now).total_seconds() / 60
            if not WINDOW[0] <= mins <= WINDOW[1]:
                continue
            try:
                g = get(f"/games/{gid}")
                pick = dd_pick(g, kind) if kind in ("dd", "ld") else v_pick(g, kind)
            except Exception as e:
                print(f"::warning::Provspel: kunde inte välja {gid}: {e}")
                continue
            if not pick or not pick["strategies"]:
                print(gid, "har inga odds än")
                continue
            r0 = g["races"][0]
            meta = {"id": gid, "kind": kind, "date": r0["date"][:10], "track": r0["track"]["name"],
                    "start": c["startTime"], "picked": now.isoformat(timespec="minutes"), "minsToStart": round(mins)}
            json.dump({**meta, **pick}, open(os.path.join(out, gid + ".json"), "w"), ensure_ascii=False)
            idx.append({**meta, "settled": False})
            have.add(gid)
            print("Provspel valt:", gid, round(mins), "min före start")

    # 2. rätta omgångar som är avgjorda
    for x in idx:
        if x.get("settled"):
            continue
        start = dt.datetime.fromisoformat(x["start"]).replace(tzinfo=TZ)
        if now < start + dt.timedelta(minutes=20):
            continue
        try:
            g = get(f"/games/{x['id']}")
        except Exception as e:
            print(f"::warning::Provspel: kunde inte rätta {x['id']}: {e}")
            continue
        kind = x["kind"]
        res = dd_result(g, kind) if kind in ("dd", "ld") else v_result(g, kind)
        if res:
            json.dump({"id": x["id"], **res}, open(os.path.join(out, x["id"] + "-res.json"), "w"), ensure_ascii=False)
            x["settled"] = True
            print("Provspel rättat:", x["id"])
        elif g.get("status") == "cancelled" or now > start + dt.timedelta(days=3):
            x["settled"] = "void"  # inställd eller inget resultat: räknas inte
            print("Provspel struket:", x["id"])
    json.dump(idx, open(idx_path, "w"), ensure_ascii=False, indent=0)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
