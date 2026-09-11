from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_ID, DOMAIN
from .coordinator import BlancoCloudCoordinator, BlancoCloudData


def _param(params: dict[str, Any], key: str) -> Any:
    value = params.get(key)
    return value.get("val") if isinstance(value, dict) and "val" in value else value


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value.value if hasattr(value, "value") else value


@dataclass(frozen=True, kw_only=True)
class BlancoSensorDescription(SensorEntityDescription):
    value_fn: Callable[[BlancoCloudData], Any]
    attrs_fn: Callable[[BlancoCloudData], dict[str, Any]] | None = None


def _status_params(data: BlancoCloudData) -> dict[str, Any]:
    return data.status.get("params", {})


def _settings_params(data: BlancoCloudData) -> dict[str, Any]:
    return data.settings.get("params", {})


WATER_TYPE_NAMES = {
    1: "Still",
    2: "Medium",
    3: "Classic",
    4: "Heiß",
}


def _last_action(data: BlancoCloudData) -> str | None:
    actions = data.actions.get("actions", [])
    if not actions:
        return None
    action = actions[-1]
    water_type = WATER_TYPE_NAMES.get(action.get("tap_state"), "Unbekannt")
    amount = action.get("disp_wtr_amt")
    if amount is not None:
        return f"{water_type} – {amount} ml"
    return water_type


def _last_action_attributes(data: BlancoCloudData) -> dict[str, Any]:
    actions = data.actions.get("actions", [])
    last_action = actions[-1] if actions else {}
    recent_actions = actions[-20:]
    return {
        "water_type": WATER_TYPE_NAMES.get(last_action.get("tap_state"), "Unbekannt"),
        "amount_ml": last_action.get("disp_wtr_amt"),
        "action_code": last_action.get("act_type"),
        "timestamp": last_action.get("evt_ts"),
        "recent_actions": _json_safe(recent_actions),
        "total_actions": len(actions),
        "info": _json_safe(data.actions.get("info", {})),
    }


DESCRIPTIONS = (
    BlancoSensorDescription(key="filter_rest", name="Filter Rest", native_unit_of_measurement=PERCENTAGE, state_class=SensorStateClass.MEASUREMENT, value_fn=lambda d: _param(_status_params(d), "filter_rest")),
    BlancoSensorDescription(key="co2_rest", name="CO₂ Rest", native_unit_of_measurement=PERCENTAGE, state_class=SensorStateClass.MEASUREMENT, value_fn=lambda d: _param(_status_params(d), "co2_rest")),
    BlancoSensorDescription(key="cooling_temperature", name="Cooling Temperature", native_unit_of_measurement=UnitOfTemperature.CELSIUS, state_class=SensorStateClass.MEASUREMENT, value_fn=lambda d: _param(_settings_params(d), "set_point_cooling")),
    BlancoSensorDescription(key="water_hardness", name="Water Hardness", value_fn=lambda d: _param(_settings_params(d), "wtr_hardness")),
    BlancoSensorDescription(key="still_water_calibration", name="Still Water Calibration", value_fn=lambda d: _param(_settings_params(d), "calib_still_wtr")),
    BlancoSensorDescription(key="soda_water_calibration", name="Soda Water Calibration", value_fn=lambda d: _param(_settings_params(d), "calib_soda_wtr")),
    BlancoSensorDescription(key="filter_lifetime", name="Filter Lifetime", value_fn=lambda d: _param(_settings_params(d), "filter_life_tm")),
    BlancoSensorDescription(key="connection_status", name="Connection Status", value_fn=lambda d: "connected" if d.status.get("info", {}).get("connected") else "disconnected", attrs_fn=lambda d: {"online": d.status.get("info", {}).get("online"), "device_type": d.status.get("info", {}).get("dev_type")}),
    BlancoSensorDescription(key="last_action", name="Last Action", value_fn=_last_action, attrs_fn=_last_action_attributes),
    BlancoSensorDescription(key="water_statistics", name="Water Statistics", value_fn=lambda d: "available" if d.stats.get("ranges") else "unavailable", attrs_fn=lambda d: {"ranges": _json_safe(d.stats.get("ranges", [])), "info": _json_safe(d.stats.get("info", {}))}),
)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: BlancoCloudCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(BlancoSensor(coordinator, entry.data[CONF_DEVICE_ID], description) for description in DESCRIPTIONS)


class BlancoSensor(CoordinatorEntity[BlancoCloudCoordinator], SensorEntity):
    entity_description: BlancoSensorDescription

    def __init__(self, coordinator: BlancoCloudCoordinator, device_id: str, description: BlancoSensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{device_id}_{description.key}"
        self._attr_device_info = {"identifiers": {(DOMAIN, device_id)}, "name": "BLANCO Smart Home", "manufacturer": "BLANCO", "model": "Smart Home Cloud"}

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        return self.entity_description.attrs_fn(self.coordinator.data) if self.entity_description.attrs_fn else None
