#!/usr/bin/env python3
"""Fetch and display historical BLANCO water actions."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

from blanco_smart_home_api_client import BlancoApiClient, BlancoApiError


PAGE_SIZE = 300
WATER_TYPES = {1: "Still", 2: "Medium", 3: "Classic", 4: "Hot"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--device-id",
        default=os.environ.get("BLANCO_DEVICE_ID"),
        help="64-stellige BLANCO dev_id; alternativ BLANCO_DEVICE_ID verwenden",
    )
    parser.add_argument(
        "--months",
        type=int,
        default=3,
        help="Zeitraum rückwärts in 30-Tage-Monaten (Standard: 3)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=PAGE_SIZE,
        help="Einträge pro API-Seite (Standard: 300)",
    )
    parser.add_argument("--json", action="store_true", help="Rohdaten als JSON ausgeben")
    args = parser.parse_args()
    if not args.device_id or len(args.device_id) != 64:
        parser.error("--device-id oder BLANCO_DEVICE_ID mit 64 Hexadezimalzeichen erforderlich")
    if args.months < 1:
        parser.error("--months muss mindestens 1 sein")
    if not 1 <= args.count <= 300:
        parser.error("--count muss zwischen 1 und 300 liegen")
    return args


def value(action: dict[str, Any], key: str) -> Any:
    raw = action.get(key)
    return raw.value if hasattr(raw, "value") else raw


async def fetch_actions(
    client: BlancoApiClient,
    device_id: str,
    start_ms: int,
    count: int,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    cursor = start_ms
    seen: set[tuple[Any, ...]] = set()

    while True:
        status_code, result = await client.get_device_actions(
            device_id, from_ts=cursor, count=count, asc=True
        )
        print(f"API-Seite: HTTP {status_code}, {len(result['actions'])} Einträge ab {cursor}")
        page = result["actions"]
        if not page:
            break

        for action in page:
            key = (
                value(action, "evt_ts"),
                value(action, "act_type"),
                value(action, "tap_state"),
                value(action, "disp_wtr_amt"),
            )
            if key not in seen:
                seen.add(key)
                actions.append(action)

        timestamps = [value(action, "evt_ts") for action in page if value(action, "evt_ts")]
        if len(page) < count or not timestamps:
            break
        next_cursor = max(timestamps) + 1
        if next_cursor <= cursor:
            break
        cursor = next_cursor

    return actions


def print_action(action: dict[str, Any]) -> None:
    timestamp = value(action, "evt_ts")
    when = (
        datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).astimezone().isoformat(
            timespec="seconds"
        )
        if timestamp
        else "unbekannt"
    )
    water_type = WATER_TYPES.get(value(action, "tap_state"), "unbekannt")
    print(
        f"{when} | action={value(action, 'act_type')} | "
        f"wasser={water_type} | menge={value(action, 'disp_wtr_amt')} ml"
    )


async def async_main(args: argparse.Namespace) -> None:
    start = datetime.now(timezone.utc) - timedelta(days=args.months * 30)
    start_ms = int(start.timestamp() * 1000)

    async with aiohttp.ClientSession() as session:
        client = BlancoApiClient(
            session,
            app_version="historical-actions-test-1.0.0",
            app_build="1",
            os_version="macOS",
        )
        await client.register_app("de")
        auth = await client.authenticate(args.device_id)
        print(f"Authentifiziert, Gerätetyp: {auth['dev_type']}")
        print(f"Lade Aktionen seit {start.isoformat()} …")

        actions = await fetch_actions(client, args.device_id, start_ms, args.count)

    print(f"\nInsgesamt: {len(actions)} eindeutige Aktionen")
    if args.json:
        print(json.dumps(actions, default=lambda item: item.value if hasattr(item, "value") else str(item), indent=2))
    else:
        for action in actions:
            print_action(action)


def main() -> None:
    try:
        asyncio.run(async_main(parse_args()))
    except BlancoApiError as error:
        print(f"{type(error).__name__}: {error}")
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
