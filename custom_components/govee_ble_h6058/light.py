"""Light entity: on/off, brightness, RGB and colour temperature."""

from __future__ import annotations

import time
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_call_later

from . import GoveeConfigEntry
from .const import DOMAIN
from .device import GoveeDevice
from .entity import GoveeEntity
from .protocol import brightness_frame, color_temp_frame, power_frame, rgb_frame

PARALLEL_UPDATES = 0

# After a command, ignore the lamp's reported power state for this long: a keep-alive reply
# that was already in flight could still show the old state.
POWER_SYNC_HOLDOFF = 3.5


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GoveeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the light of one lamp."""
    async_add_entities([GoveeLight(entry.runtime_data)])


class GoveeLight(GoveeEntity, LightEntity):
    """The lamp. State is optimistic and follows the lamp's power reports."""

    _attr_name = None
    _attr_translation_key = "lamp"
    _attr_supported_color_modes = {ColorMode.RGB, ColorMode.COLOR_TEMP}

    def __init__(self, device: GoveeDevice) -> None:
        super().__init__(device)
        self._attr_min_color_temp_kelvin = device.model.min_kelvin
        self._attr_max_color_temp_kelvin = device.model.max_kelvin
        self._attr_color_mode = ColorMode.RGB
        self._attr_is_on = device.power
        self._last_command = 0.0
        self._holdoff_unsub: CALLBACK_TYPE | None = None

    async def async_added_to_hass(self) -> None:
        """Follow the lamp's real on/off state (restart, physical button, app)."""
        await super().async_added_to_hass()
        self._device.sync_device_registry()
        if self._device.power is not None:
            self._attr_is_on = self._device.power
        self.async_on_remove(self._cancel_holdoff)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on, optionally with brightness, colour or colour temperature."""
        frames = [power_frame(True)]
        if ATTR_BRIGHTNESS in kwargs:
            brightness = kwargs[ATTR_BRIGHTNESS]
            frames.append(brightness_frame(brightness, self._device.model.brightness_max))
            self._attr_brightness = brightness
        if ATTR_RGB_COLOR in kwargs:
            red, green, blue = kwargs[ATTR_RGB_COLOR]
            frames.append(rgb_frame(red, green, blue))
            self._attr_color_mode = ColorMode.RGB
            self._attr_rgb_color = (red, green, blue)
        elif ATTR_COLOR_TEMP_KELVIN in kwargs:
            kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
            frames.append(color_temp_frame(kelvin))
            self._attr_color_mode = ColorMode.COLOR_TEMP
            self._attr_color_temp_kelvin = kelvin
        self._attr_is_on = True
        await self._send(frames)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off."""
        self._attr_is_on = False
        await self._send([power_frame(False)])

    @callback
    def _handle_device_update(self) -> None:
        power = self._device.power
        if power is None or power == self._attr_is_on:
            return
        if time.monotonic() - self._last_command < POWER_SYNC_HOLDOFF:
            return
        self._attr_is_on = power
        self.async_write_ha_state()

    @callback
    def _cancel_holdoff(self) -> None:
        if self._holdoff_unsub is not None:
            self._holdoff_unsub()
            self._holdoff_unsub = None

    @callback
    def _recheck_power(self, _now: Any = None) -> None:
        self._holdoff_unsub = None
        self._handle_device_update()

    async def _send(self, frames: list[bytes]) -> None:
        """Send over the persistent link and publish the commanded state."""
        self._last_command = time.monotonic()
        try:
            await self._device.link.send(frames)
        except ConnectionError as exc:
            # The command did not reach the lamp: show what the lamp last reported.
            if self._device.power is not None:
                self._attr_is_on = self._device.power
            self.async_write_ha_state()
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="send_failed",
                translation_placeholders={"name": self._device.name, "error": str(exc)},
            ) from exc
        self._last_command = time.monotonic()
        # No polling: publish the commanded state now, then re-check the lamp's report once the
        # hold-off is over.
        self.async_write_ha_state()
        self._cancel_holdoff()
        self._holdoff_unsub = async_call_later(
            self.hass, POWER_SYNC_HOLDOFF + 0.2, self._recheck_power
        )
