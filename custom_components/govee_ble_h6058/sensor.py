"""Battery sensor (battery-powered models only)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import GoveeConfigEntry
from .entity import GoveeEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GoveeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the battery sensor when the model has a battery."""
    device = entry.runtime_data
    if device.model.has_battery:
        async_add_entities([GoveeBatterySensor(device, "battery")])


class GoveeBatterySensor(GoveeEntity, SensorEntity):
    """Rough battery level: low 7 bits of the status byte of the lamp's status reply.

    The Govee app shows no percentage, only a coarse icon. The value plateaus around 84 while
    charging and reads 92 when full on the charger; use the charging and plugged-in sensors to
    know when to ignore it.
    """

    _attr_translation_key = "battery"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> int | None:
        status = self._device.status
        return status.battery if status else None

    @property
    def available(self) -> bool:
        status = self._device.status
        return status is not None and status.battery is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        status = self._device.status
        if status is None:
            return {}
        return {
            "raw_status_byte": status.status_byte,
            "charge_state": status.charge_state,
            "charging": status.charging,
        }
