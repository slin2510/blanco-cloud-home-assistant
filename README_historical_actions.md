# Historische BLANCO-Aktionen testen

Das Skript `test_historical_actions.py` registriert eine Test-App, authentifiziert
die BLANCO-Cloud und lädt historische Aktionen seitenweise.

```bash
cd /Users/nschoettle/code/blanco_home_assistant
source .venv/bin/activate
export BLANCO_DEVICE_ID='DEINE_64_STELLIGE_DEV_ID'
python test_historical_actions.py --months 3
```

Für Rohdaten als JSON:

```bash
python test_historical_actions.py --months 12 --json
```

Das Skript lädt maximal 300 Einträge pro API-Seite und setzt automatisch mit
dem letzten Zeitstempel der vorherigen Seite fort. Die Monatsangabe wird als
30-Tage-Zeitraum interpretiert. Es werden keine Geräteeinstellungen verändert.
