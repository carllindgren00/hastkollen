# Travhästarna

Webbapp med kupongförslag för V85, V65, Dagens Dubbel och Lunchdubbel, med data från ATG.

Appen: https://carllindgren00.github.io/hastkollen/ (öppna i mobilen och välj "Lägg till på hemskärmen").

Datan är krypterad. Appen frågar efter en kod och låser upp datan i webbläsaren; enheten förblir upplåst i 30 dagar.

## Så fungerar det

- `docs/` är det GitHub Pages publicerar. `docs/index.html` är hela appen och läser den krypterade `docs/data/v85.enc` eller `docs/data/v65.enc` och loggen i `docs/data/snapshots/`.
- `scripts/seal.py` krypterar datan. GitHub Actions har bara den publika nyckeln (`docs/data/pubkey.pem`) och kan kryptera men aldrig läsa. Den privata nyckeln ligger i `docs/data/keys.json`, krypterad en gång per kod (PBKDF2 med 600 000 varv och AES-GCM). Inga koder finns i repot eller i GitHubs inställningar.
- Byta koder: `printf 'kod1\nkod2\n' | python3 scripts/seal.py keygen docs/data`, och kryptera sedan om datan. Alla enheter får då skriva in en kod på nytt.
- `scripts/atg_v85.py` hämtar årets V85- eller V65-omgångar och nästa startlista från ATG:s öppna API (spelet anges som tredje argument).
  Den hämtar också jackpot (extra pengar i 8-rättspotten) och närmaste Dagens Dubbel med oddset för varje kombination.
- `scripts/atg_snapshot.py` sparar oddsen före start för V85, V65, Dagens Dubbel och Lunchdubbel: varje halvtimme de sista 2,5 timmarna, plus en gång tidigare samma dag. Med dem kan modellen testas med de odds man faktiskt hade när man spelade.
- Datan är uppdelad: `v85.enc`/`v65.enc` (aktuell omgång), `v85-hist.enc`/`v65-hist.enc` (årets avgjorda omgångar, sparas bara om när något ändrats) och `dubbel.enc`.
- `.github/workflows/atg.yml` kör skripten på schema och sparar datan i repot. Den kan också köras för hand under Actions → "Hämta från ATG" → Run workflow.

## Köra lokalt

```sh
python3 scripts/atg_v85.py .cache .work/v85.json
python3 scripts/seal.py file .work/v85.json docs/data/v85.enc
python3 -m http.server -d docs
```

Öppna sedan http://localhost:8000.

ATG:s API är inofficiellt och kan ändras utan förvarning. Appen har ingen koppling till ATG.

**Spela bara för pengar du har råd att förlora.** Det här är ett privat analysverktyg, inga speltips, och modellen ger ingen garanti att vinna. 18-årsgräns för spel. Pausa allt spel på [spelpaus.se](https://www.spelpaus.se), stöd och råd hos [Stödlinjen](https://www.stodlinjen.se), 020-81 91 00.
