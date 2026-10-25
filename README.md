# V85-kollen

Webbapp för V85: modell, kupong, andelar och historik med data från ATG.

Appen: https://carllindgren00.github.io/hastkollen/ (öppna i mobilen och välj "Lägg till på hemskärmen").

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

ATG:s API är inofficiellt och kan ändras utan förvarning.
