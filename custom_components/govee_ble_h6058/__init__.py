"""Govee BLE H6058: local Bluetooth control of Govee RGBWW lamps."""

from __future__ import annotations

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_MODEL, DOMAIN, MODELS
from .device import GoveeDevice

PLATFORMS: list[Platform] = [Platform.LIGHT, Platform.SENSOR, Platform.BINARY_SENSOR]

type GoveeConfigEntry = ConfigEntry[GoveeDevice]


async def async_setup_entry(hass: HomeAssistant, entry: GoveeConfigEntry) -> bool:
    """Set up one lamp."""
    address: str = entry.data[CONF_ADDRESS]
    model = MODELS.get(entry.data[CONF_MODEL])
    if model is None:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="unsupported_model",
            translation_placeholders={"model": entry.data[CONF_MODEL]},
        )
    if not bluetooth.async_ble_device_from_address(hass, address, connectable=True):
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="not_found",
            translation_placeholders={"address": address},
        )

    device = GoveeDevice(hass, address, model, entry.title)
    entry.runtime_data = device

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Connects, keeps the link alive and reconnects; cancelled on unload and shutdown.
    entry.async_create_background_task(hass, device.link.run(), f"{DOMAIN} link {address}")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: GoveeConfigEntry) -> bool:
    """Unload one lamp and close its BLE connection."""
    await entry.runtime_data.link.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
