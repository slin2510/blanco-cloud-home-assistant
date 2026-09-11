#!/usr/bin/env python3
"""Read a BLANCO UNIT dev_id via the local BLE pairing protocol."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import hashlib
import json
import secrets
import string
import time
from dataclasses import dataclass
from typing import Any

from bleak.exc import BleakError
from bleak import BleakClient, BleakScanner


SERVICE_UUID = "847bba10-a31f-41bf-a35f-3f73a22bb307"
CHARACTERISTIC_UUID = "3b531d4d-ed58-4677-b2fa-1c72a86082cf"
SCAN_SECONDS = 15.0
RESPONSE_SECONDS = 10.0


class PairingError(RuntimeError):
    """Raised when the BLANCO pairing response is invalid or reports an error."""


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def make_token(pin: str, session_id: int, request_id: int) -> str:
    pin_hash = sha256_hex(pin)
    return sha256_hex(f"{pin_hash}{session_id}{request_id}")


def _random_id() -> int:
    return secrets.randbelow(9_000_000) + 1_000_000


def build_pairing_request(pin: str, session_id: int, request_id: int) -> bytes:
    payload = {
        "session": session_id,
        "id": request_id,
        "type": 1,
        "token": make_token(pin, session_id, request_id),
        "salt": f"{session_id}{request_id}",
        "body": {
            "meta": {
                "evt_type": 10,
                "dev_type": 1,
                "evt_ver": 1,
                "evt_ts": int(time.time() * 1000),
            },
            "pars": {},
        },
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\x00\xff"


def frame_message(payload: bytes, message_id: int = 1, mtu: int = 200) -> list[bytes]:
    """Frame a JSON payload using the BLANCO BLE packet format."""
    if not 0 <= message_id <= 255:
        raise ValueError("message_id must fit in one byte")
    first_capacity = mtu - 5
    next_capacity = mtu - 2
    chunks = [payload[:first_capacity]]
    rest = payload[first_capacity:]
    while rest:
        chunks.append(rest[:next_capacity])
        rest = rest[next_capacity:]
    if len(chunks) > 255:
        raise ValueError("message requires too many BLE packets")
    packets = [bytes((0xFF, 0, len(chunks), message_id, 0)) + chunks[0]]
    packets.extend(
        bytes((message_id, index)) + chunk
        for index, chunk in enumerate(chunks[1:], start=1)
    )
    return packets


class PacketAssembler:
    """Reassemble one BLANCO response from notification/read chunks."""

    def __init__(self) -> None:
        self._expected: int | None = None
        self._message_id: int | None = None
        self._parts: dict[int, bytes] = {}

    def add(self, packet: bytes) -> dict[str, Any] | None:
        if len(packet) < 6:
            raise PairingError("BLE packet is too short")
        if packet[0] == 0xFF:
            if packet[1] != 0 or packet[4] != 0:
                raise PairingError("invalid BLANCO first-packet header")
            self._expected = packet[2]
            self._message_id = packet[3]
            index = 0
            payload = packet[5:]
        else:
            if self._message_id is None or packet[0] != self._message_id:
                raise PairingError("BLE packet message ID does not match")
            index = packet[1]
            payload = packet[2:]

        if self._expected is None or self._message_id is None:
            raise PairingError("response did not start with a first packet")
        if index >= self._expected:
            raise PairingError("BLE packet index is outside the response")
        self._parts[index] = payload
        if len(self._parts) != self._expected:
            return None

        raw = b"".join(self._parts[i] for i in range(self._expected))
        raw = raw.split(b"\x00", 1)[0]
        if raw.endswith(b"\xff"):
            raw = raw[:-1]
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PairingError("BLE response was not valid JSON") from exc
        if not isinstance(result, dict):
            raise PairingError("BLE response JSON was not an object")
        return result


def extract_dev_id(response: dict[str, Any]) -> tuple[str, Any]:
    errors = response.get("body", {}).get("results", [])
    if errors and isinstance(errors[0], dict):
        error_items = errors[0].get("pars", {}).get("errs", [])
        if error_items:
            raise PairingError("pairing rejected (wrong PIN or device refused it)")
    meta = response.get("body", {}).get("meta", {})
    dev_id = meta.get("dev_id")
    if not isinstance(dev_id, str) or len(dev_id) != 64:
        raise PairingError("pairing response did not contain a valid 64-character dev_id")
    if any(char not in string.hexdigits for char in dev_id):
        raise PairingError("pairing response contained a non-hexadecimal dev_id")
    return dev_id, meta.get("dev_type")


@dataclass(frozen=True)
class Candidate:
    address: str
    name: str
    rssi: int | None


async def find_device() -> Candidate:
    print(f"Suche bis zu {SCAN_SECONDS:.0f} Sekunden nach BLANCO-Geräten …")
    discovered = await BleakScanner.discover(timeout=SCAN_SECONDS, return_adv=True)
    candidates: list[Candidate] = []
    for address, (device, advertisement) in discovered.items():
        service_uuids = {uuid.lower() for uuid in (advertisement.service_uuids or [])}
        name = device.name or advertisement.local_name or "Unbekannt"
        if SERVICE_UUID in service_uuids or "blanco" in name.lower():
            candidates.append(Candidate(address, name, advertisement.rssi))
    if not candidates:
        raise PairingError("kein BLANCO-Gerät gefunden; Gerät einschalten und näher heranbringen")
    if len(candidates) == 1:
        return candidates[0]
    print("Gefundene Geräte:")
    for index, candidate in enumerate(candidates, start=1):
        print(f"  {index}: {candidate.name} ({candidate.address}, RSSI {candidate.rssi})")
    choice = input("Gerät auswählen [1]: ").strip() or "1"
    try:
        return candidates[int(choice) - 1]
    except (ValueError, IndexError) as exc:
        raise PairingError("ungültige Geräteauswahl") from exc


async def pair(candidate: Candidate, pin: str) -> tuple[str, Any]:
    session_id = _random_id()
    request_id = _random_id()
    assembler = PacketAssembler()
    response_future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()

    def on_notification(_: Any, data: bytearray) -> None:
        if response_future.done():
            return
        try:
            response = assembler.add(bytes(data))
            if response is not None:
                response_future.set_result(response)
        except PairingError as exc:
            response_future.set_exception(exc)

    async with BleakClient(candidate.address) as client:
        notifications_enabled = False
        try:
            try:
                await client.start_notify(CHARACTERISTIC_UUID, on_notification)
                notifications_enabled = True
            except BleakError:
                print("Notifications werden nicht unterstützt; lese Antwort per BLE-Read …")

            request = build_pairing_request(pin, session_id, request_id)
            for packet in frame_message(request, message_id=request_id & 0xFF):
                await client.write_gatt_char(CHARACTERISTIC_UUID, packet, response=True)
            if notifications_enabled:
                response = await asyncio.wait_for(response_future, timeout=RESPONSE_SECONDS)
            else:
                deadline = asyncio.get_running_loop().time() + RESPONSE_SECONDS
                while True:
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        raise asyncio.TimeoutError
                    packet = await asyncio.wait_for(
                        client.read_gatt_char(CHARACTERISTIC_UUID), timeout=remaining
                    )
                    response = assembler.add(bytes(packet))
                    if response is not None:
                        break
        finally:
            if notifications_enabled:
                await client.stop_notify(CHARACTERISTIC_UUID)
    return extract_dev_id(response)


async def async_main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", help="BLE-Adresse/UUID des Geräts überspringt den Scan")
    args = parser.parse_args()
    pin = getpass.getpass("BLANCO-PIN (5 Stellen): ")
    if len(pin) != 5 or not pin.isdigit():
        raise PairingError("die PIN muss genau fünf Ziffern enthalten")
    candidate = Candidate(args.address, "manuell ausgewählt", None) if args.address else await find_device()
    print(f"Verbinde mit {candidate.name} ({candidate.address}) …")
    dev_id, dev_type = await pair(candidate, pin)
    print(f"dev_id: {dev_id}")
    print(f"dev_type: {dev_type}")
    return 0


def main() -> None:
    try:
        raise SystemExit(asyncio.run(async_main()))
    except (PairingError, asyncio.TimeoutError) as exc:
        print(f"Fehler: {exc}")
        raise SystemExit(1) from exc
    except KeyboardInterrupt:
        print("Abgebrochen.")
        raise SystemExit(130)


if __name__ == "__main__":
    main()
