"""Base entity."""

from __future__ import annotations

from homeassistant.helpers.entity import Entity

from .device import GoveeDevice


class GoveeEntity(Entity):
    """Entity of one lamp, updated from the lamp's replies (no polling)."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, device: GoveeDevice, key: str | None = None) -> None:
        self._device = device
        self._attr_device_info = device.device_info
        self._attr_unique_id = f"{device.unique_prefix}_{key}" if key else device.unique_prefix

    async def async_added_to_hass(self) -> None:
        """Follow the lamp's updates."""
        self.async_on_remove(self._device.async_add_listener(self._handle_device_update))

    def _handle_device_update(self) -> None:
        self.async_write_ha_state()
