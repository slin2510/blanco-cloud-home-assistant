from __future__ import annotations

import logging
from dataclasses import dataclass
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, TypeVar

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.util.unit_conversion import VolumeConverter
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from blanco_smart_home_api_client import BlancoApiClient, BlancoApiError, BlancoTokenExpiredError

from .const import ACTION_LOOKBACK, DOMAIN, UPDATE_INTERVAL, default_stat_ranges

_LOGGER = logging.getLogger(__name__)
_T = TypeVar("_T")


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value.value if hasattr(value, "value") else value


@dataclass(slots=True)
class BlancoCloudData:
    status: dict[str, Any]
    settings: dict[str, Any]
    actions: dict[str, Any]
    stats: dict[str, Any]


class BlancoCloudCoordinator(DataUpdateCoordinator[BlancoCloudData]):
    def __init__(self, hass: HomeAssistant, client: BlancoApiClient, device_id: str) -> None:
        self.client = client
        self.device_id = device_id
        self.history_store = Store(
            hass, 1, f"{DOMAIN}_{device_id[:16]}_historical_actions", private=True
        )
        super().__init__(hass, logger=_LOGGER, name=DOMAIN, update_interval=UPDATE_INTERVAL)

    async def async_import_historical_data(self) -> None:
        """Import the previous 12 months into Home Assistant statistics once."""
        existing = await self.history_store.async_load()
        if existing and existing.get("statistics_imported"):
            _LOGGER.debug("Historical BLANCO import already completed")
            return

        try:
            actions = await self._fetch_actions_since(
                datetime.now(timezone.utc) - timedelta(days=365)
            )
            await self._import_daily_statistics(actions)
            await self.history_store.async_save(
                {
                    "statistics_imported": True,
                    "imported_at": datetime.now(timezone.utc).isoformat(),
                    "action_count": len(actions),
                    "actions": actions,
                }
            )
            _LOGGER.info("Imported %d historical BLANCO actions", len(actions))
        except (BlancoApiError, HomeAssistantError) as err:
            _LOGGER.warning("Historical BLANCO import failed: %s", err)

    async def _fetch_actions_since(self, start: datetime) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        cursor = int(start.timestamp() * 1000)
        page_size = 300

        while True:
            _, result = await self._call_with_token_retry(
                self.client.get_device_actions,
                self.device_id,
                cursor,
                page_size,
                True,
            )
            page = result.get("actions", [])
            if not page:
                break
            for action in page:
                key = (
                    action.get("evt_ts"),
                    action.get("act_type"),
                    action.get("tap_state"),
                    action.get("disp_wtr_amt"),
                )
                if key not in seen:
                    seen.add(key)
                    actions.append(_json_safe(action))
            timestamps = [action.get("evt_ts") for action in page if action.get("evt_ts")]
            if len(page) < page_size or not timestamps:
                break
            next_cursor = max(timestamps) + 1
            if next_cursor <= cursor:
                break
            cursor = next_cursor
        return actions

    async def _import_daily_statistics(self, actions: list[dict[str, Any]]) -> None:
        """Convert water-dispense actions into daily external statistics."""
        from homeassistant.components.recorder.models import (
            StatisticData,
            StatisticMeanType,
            StatisticMetaData,
        )
        from homeassistant.components.recorder.statistics import async_add_external_statistics
        from homeassistant.const import UnitOfVolume

        daily_litres: defaultdict[datetime, float] = defaultdict(float)
        for action in actions:
            if action.get("act_type") != 1000:
                continue
            timestamp = action.get("evt_ts")
            amount_ml = action.get("disp_wtr_amt")
            if not timestamp or not isinstance(amount_ml, (int, float)):
                continue
            day = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            daily_litres[day] += float(amount_ml) / 1000

        if not daily_litres:
            _LOGGER.info("No water-dispense actions found for historical import")
            return

        statistic_id = f"{DOMAIN}:water_consumption_{self.device_id[:16]}"
        metadata = StatisticMetaData(
            mean_type=StatisticMeanType.NONE,
            has_sum=True,
            name="BLANCO Water Consumption",
            source=DOMAIN,
            statistic_id=statistic_id,
            unit_class=VolumeConverter.UNIT_CLASS,
            unit_of_measurement=UnitOfVolume.LITERS,
        )
        cumulative = 0.0
        statistics = []
        for day in sorted(daily_litres):
            cumulative += daily_litres[day]
            statistics.append(
                StatisticData(start=day, state=daily_litres[day], sum=cumulative)
            )
        async_add_external_statistics(self.hass, metadata, statistics)

    async def _call_with_token_retry(self, method: Callable[..., Awaitable[_T]], *args: Any) -> _T:
        try:
            return await method(*args)
        except BlancoTokenExpiredError:
            await self.client.renew_token(self.device_id)
            return await method(*args)

    async def _optional_call(self, method: Callable[..., Awaitable[_T]], *args: Any) -> _T | None:
        try:
            return await self._call_with_token_retry(method, *args)
        except BlancoApiError as err:
            _LOGGER.warning("Optional BLANCO endpoint failed: %s", err)
            return None

    async def _async_update_data(self) -> BlancoCloudData:
        try:
            _, status = await self._call_with_token_retry(self.client.get_device_status, self.device_id)
            _, settings = await self._call_with_token_retry(self.client.get_device_settings, self.device_id)
        except BlancoApiError as err:
            raise UpdateFailed(f"BLANCO cloud request failed: {err}") from err

        now = datetime.now(timezone.utc)
        action_from = int((now - ACTION_LOOKBACK).timestamp() * 1000)
        actions_response = await self._optional_call(
            self.client.get_device_actions, self.device_id, action_from, 300, True
        )
        stats_response = await self._optional_call(
            self.client.get_device_stats, self.device_id, default_stat_ranges()
        )
        actions = actions_response[1] if actions_response else None
        stats = stats_response[1] if stats_response else None
        return BlancoCloudData(
            status=status,
            settings=settings,
            actions=actions or {"actions": [], "info": {}},
            stats=stats or {"ranges": [], "info": {}},
        )
