"""Charging and plugged-in sensors (battery-powered models only)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import GoveeConfigEntry
from .entity import GoveeEntity
from .protocol import StatusReading

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GoveeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the charging and plugged-in sensors when the model has a battery."""
    device = entry.runtime_data
    if device.model.has_battery:
        async_add_entities(
            [GoveePluggedInSensor(device, "plugged_in"), GoveeChargingSensor(device, "charging")]
        )


class _StatusBinarySensor(GoveeEntity, BinarySensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def _value(self, status: StatusReading) -> bool:
        raise NotImplementedError

    @property
    def is_on(self) -> bool | None:
        status = self._device.status
        return self._value(status) if status else None

    @property
    def available(self) -> bool:
        return self._device.status is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        status = self._device.status
        if status is None:
            return {}
        return {"raw_status_byte": status.status_byte, "charge_state": status.charge_state}


class GoveePluggedInSensor(_StatusBinarySensor):
    """External power connected: bit 2 of the status byte."""

    _attr_translation_key = "plugged_in"
    _attr_device_class = BinarySensorDeviceClass.PLUG

    def _value(self, status: StatusReading) -> bool:
        return status.plugged


class GoveeChargingSensor(_StatusBinarySensor):
    """Charging in progress: bit 7 of the status byte (matches the Govee app's charging icon)."""

    _attr_translation_key = "charging"
    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING

    def _value(self, status: StatusReading) -> bool:
        return status.charging
