"""Diagnostics download: model, firmware, link and the last status reply."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant

from . import GoveeConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: GoveeConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for one lamp (the MAC address is redacted)."""
    device = entry.runtime_data
    status = device.status
    return {
        "entry": async_redact_data(dict(entry.data), {CONF_ADDRESS}),
        "model": asdict(device.model),
        "firmware": device.firmware,
        "connected": device.connected,
        "status": {**asdict(status), "charge_state": status.charge_state} if status else None,
    }
