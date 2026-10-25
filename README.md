# V85-kollen

Webbapp för V85: modell, kupong, andelar och historik med data från ATG.

Appen ligger på Cloudflare Pages bakom Cloudflare Access, så bara godkända e-postadresser kommer in. Öppna den i mobilen och välj "Lägg till på hemskärmen".

## Så fungerar det

- `index.html` är hela appen. Den läser `data/v85.json` och `data/snapshots/index.json`.
- `scripts/atg_v85.py` hämtar årets V85-omgångar och nästa startlista från ATG:s öppna API.
- `scripts/atg_snapshot.py` sparar dagens vinnarodds och V85-procent, för att senare kunna testa modellen med de odds man faktiskt hade före start.
- `.github/workflows/atg.yml` kör skripten på schema och sparar datan i repot. Den kan också köras för hand under Actions → "Hämta från ATG" → Run workflow.

## Köra lokalt

```sh
python3 scripts/atg_v85.py .cache data/v85.json
python3 -m http.server
```

Öppna sedan http://localhost:8000.

ATG:s API är inofficiellt och kan ändras utan förvarning. Appen har ingen koppling till ATG.

**Spela bara för pengar du har råd att förlora.** Det här är ett privat analysverktyg, inga speltips, och modellen ger ingen garanti att vinna. 18-årsgräns för spel. Pausa allt spel på [spelpaus.se](https://www.spelpaus.se), stöd och råd hos [Stödlinjen](https://www.stodlinjen.se), 020-81 91 00.
