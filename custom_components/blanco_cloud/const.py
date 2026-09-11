from __future__ import annotations

from datetime import datetime, timedelta, timezone

DOMAIN = "blanco_cloud"
NAME = "BLANCO Cloud"
VERSION = "0.1.0"

CONF_DEVICE_ID = "device_id"
CONF_LOCALE = "locale"

UPDATE_INTERVAL = timedelta(minutes=5)
ACTION_LOOKBACK = timedelta(days=30)


def default_stat_ranges() -> list[dict[str, int | str]]:
    now = datetime.now(timezone.utc)
    return [
        {"name": "24h", "from": int((now - timedelta(hours=24)).timestamp() * 1000), "to": int(now.timestamp() * 1000)},
        {"name": "7d", "from": int((now - timedelta(days=7)).timestamp() * 1000), "to": int(now.timestamp() * 1000)},
        {"name": "30d", "from": int((now - timedelta(days=30)).timestamp() * 1000), "to": int(now.timestamp() * 1000)},
    ]
