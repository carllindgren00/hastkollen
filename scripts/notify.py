"""Schemalägger en notis 30 minuter före start för V85, V65, Dagens Dubbel och Lunchdubbel.

Användning: NTFY_TOPIC=<hemligt kanalnamn> python3 scripts/notify.py docs/data/notified.json [--dry-run] [--test]
(--test skickar en testnotis direkt.)
Notisen skickas via ntfy.sh, som levererar den vid rätt klockslag även om GitHubs körning är sen.
Kanalnamnet är en hemlighet i GitHub (Settings → Secrets → Actions → NTFY_TOPIC) och finns inte i repot.
notified.json håller reda på vilka spel som redan fått en notis.
"""
import datetime as dt, json, os, sys, urllib.request
from zoneinfo import ZoneInfo

API = "https://www.atg.se/services/racinginfo/v1/api"
APP = "https://carllindgren00.github.io/hastkollen/"
TZ = ZoneInfo("Europe/Stockholm")
NAMES = {"V85": "V85", "V65": "V65", "dd": "Dagens Dubbel", "ld": "Lunchdubbel"}
BEFORE = 30   # minuter före start
AHEAD = 240   # schemalägg när notisen ska gå inom så här många minuter


def get(path):
    with urllib.request.urlopen(API + path, timeout=40) as r:
        return json.load(r)


def send(topic, title, message, at):
    body = {"topic": topic, "title": title, "message": message, "tags": ["horse_racing"], "click": APP}
    if at:
        body["delay"] = str(int(at.timestamp()))
    req = urllib.request.Request("https://ntfy.sh/", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=30).read()


def upcoming(now):
    for day in (now.date(), now.date() + dt.timedelta(days=1)):
        cal = get(f"/calendar/day/{day}")
        tracks = {t["id"]: t["name"] for t in cal.get("tracks", [])}
        for kind in NAMES:
            for g in cal.get("games", {}).get(kind, []):
                if g.get("id") and g.get("startTime") and g.get("status") in ("bettable", "upcoming"):
                    start = dt.datetime.fromisoformat(g["startTime"]).replace(tzinfo=TZ)
                    track = " och ".join(dict.fromkeys(tracks.get(t, "") for t in g.get("tracks", []) if tracks.get(t)))
                    yield g["id"], kind, track, start


if __name__ == "__main__":
    state_path, dry = sys.argv[1], "--dry-run" in sys.argv
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic and not dry:
        print("NTFY_TOPIC är inte satt, inga notiser skickas.")
        sys.exit(0)
    if topic and "--test" in sys.argv:
        send(topic, "Travhästarna", "Testnotis: notiserna fungerar. Du får en notis 30 minuter före varje spel.", None)
        print("Testnotis skickad")
    now = dt.datetime.now(TZ)
    state = json.load(open(state_path)) if os.path.exists(state_path) else {}
    # glöm spel som är äldre än tre dagar
    state = {k: v for k, v in state.items() if v >= (now - dt.timedelta(days=3)).isoformat()}
    sent = 0
    for gid, kind, track, start in upcoming(now):
        at = start - dt.timedelta(minutes=BEFORE)
        mins = (at - now).total_seconds() / 60
        left = (start - now).total_seconds() / 60
        if gid in state or left < 5 or mins > AHEAD:
            continue
        title = f"{NAMES[kind]} {track}".strip()
        if mins > 1:
            msg, when = f"Startar kl {start:%H:%M}, om 30 minuter. Öppna appen och tryck Hämta nu.", at
        else:  # körningen var sen: skicka direkt
            msg, when = f"Startar kl {start:%H:%M}, om {round(left)} minuter. Öppna appen och tryck Hämta nu.", None
        print(("[test] " if dry else "") + f"{title}: notis {'kl ' + format(when, '%H:%M') if when else 'nu'} – {msg}")
        if not dry:
            try:
                send(topic, title, msg, when)
            except Exception as e:  # försök igen vid nästa körning
                print(f"::warning::Kunde inte skicka notis för {gid}: {e}")
                continue
        state[gid] = start.isoformat()
        sent += 1
    if not dry:
        json.dump(state, open(state_path, "w"), indent=0, sort_keys=True)
    print(sent, "notiser schemalagda")
