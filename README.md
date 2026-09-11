# BLANCO Cloud für Home Assistant

Eine inoffizielle Home-Assistant-Custom-Integration für BLANCO Smart Home
Cloud-Geräte. Sie verwendet den offenen Python-Client
[`blanco-smart-home-api-client`](https://github.com/blancoGDPD/blanco-smart-home-api-client).

> Dieses Projekt ist nicht mit BLANCO GmbH + Co KG verbunden oder von BLANCO
> unterstützt. Es ist ein privates Community-Projekt.

## Funktionen

- Filter- und CO₂-Restbestand
- Cloud-Verbindungsstatus
- Kühltemperatur, Wasserhärte und Kalibrierwerte
- Filterlebensdauer
- letzte Wasseraktion mit Wasserart und Menge
- historische Aktionen der letzten 30 Tage als Attribute
- einmaliger Backfill der letzten 365 Tage
- täglicher Wasserverbrauch als Home-Assistant-Langzeitstatistik
- automatische Token-Erneuerung

## Installation mit HACS

1. HACS öffnen.
2. **Integrations** → Menü **Custom repositories** öffnen.
3. Die GitHub-URL dieses Repositories eintragen.
4. Kategorie **Integration** auswählen und hinzufügen.
5. Nach **BLANCO Cloud** suchen und installieren.
6. Home Assistant neu starten.
7. **Einstellungen → Geräte & Dienste → Integration hinzufügen** öffnen.
8. **BLANCO Cloud** auswählen und die 64-stellige `dev_id` eingeben.

Die `dev_id` wird beim lokalen BLE-Pairing mit dem BLANCO-Gerät ausgegeben.
Sie ist weder die Bluetooth-MAC-Adresse noch die Seriennummer.

## Historischer Wasserverbrauch

Beim ersten Einrichten lädt die Integration Aktionen der letzten 365 Tage,
summiert Wasserentnahmen pro UTC-Tag und importiert sie als externe Statistik.
Die Statistik-ID hat dieses Format:

```text
blanco_cloud:water_consumption_<device-prefix>
```

Sie kann in einer Statistics Graph Card verwendet werden:

```yaml
type: statistics-graph
title: BLANCO Wasserverbrauch
entities:
  - blanco_cloud:water_consumption_<device-prefix>
days_to_show: 365
chart_type: bar
stat_types:
  - sum
```

Die historische Aktionserfassung wird lokal im Home-Assistant-Storage
gespeichert. Der einmalige Backfill wird nach erfolgreichem Abschluss nicht
erneut ausgeführt.

## Entwicklung und Tests

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt

python -m unittest discover -s tests -v
```

Cloud-Testskripte benötigen eine lokale Geräte-ID, die niemals committed
werden darf:

```bash
export BLANCO_DEVICE_ID='DEINE_64_STELLIGE_DEV_ID'
python test_blanco.py
python test_historical_actions.py --months 12 --json
```

## Lizenz

MIT; siehe [LICENSE](LICENSE).
