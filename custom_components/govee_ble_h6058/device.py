"""One Govee lamp: its BLE link and the values read from it."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo

from .ble import GoveeBleLink
from .const import DOMAIN, ModelInfo
from .protocol import CMD_FIRMWARE, CMD_POWER, StatusReading, decode_firmware, decode_status


class GoveeDevice:
    """State shared by all entities of one lamp."""

    def __init__(self, hass: HomeAssistant, address: str, model: ModelInfo, name: str) -> None:
        self._hass = hass
        self.address = address
        self.model = model
        self.name = name
        self.connected = False
        self.firmware: str | None = None
        self.status: StatusReading | None = None
        self._listeners: list[Callable[[], None]] = []
        self.link = GoveeBleLink(
            name,
            # Re-resolved on every connection attempt so the best connectable scanner is used.
            lambda: bluetooth.async_ble_device_from_address(hass, address, connectable=True),
            on_frame=self.handle_frame,
            on_state=self.handle_state,
        )

    @property
    def unique_prefix(self) -> str:
        """MAC without colons, the base of every entity's unique id."""
        return self.address.replace(":", "")

    @property
    def power(self) -> bool | None:
        """Power state the lamp last reported."""
        return self.status.power if self.status else None

    @property
    def device_info(self) -> DeviceInfo:
        """Shared by all entities so they end up on one device."""
        info = DeviceInfo(
            identifiers={(DOMAIN, self.address)},
            connections={(CONNECTION_BLUETOOTH, self.address)},
            name=self.name,
            manufacturer="Govee",
            model=self.model.model,
        )
        if self.firmware:
            info["sw_version"] = self.firmware
        return info

    @callback
    def async_add_listener(self, update: Callable[[], None]) -> Callable[[], None]:
        """Call `update` whenever a value changes; returns a remove function."""
        self._listeners.append(update)

        def _remove() -> None:
            if update in self._listeners:
                self._listeners.remove(update)

        return _remove

    @callback
    def _notify(self) -> None:
        for update in list(self._listeners):
            update()

    @callback
    def handle_state(self, connected: bool) -> None:
        """Link went up or down."""
        if connected != self.connected:
            self.connected = connected
            self._notify()

    @callback
    def handle_frame(self, cmd: int, payload: bytes) -> None:
        """Called for every valid 0xAA reply from the lamp."""
        changed = False
        if cmd == CMD_POWER:
            status = decode_status(payload)
            if status != self.status:
                self.status = status
                changed = True
        elif cmd == CMD_FIRMWARE:
            firmware = decode_firmware(payload)
            if firmware and firmware != self.firmware:
                self.firmware = firmware
                self.sync_device_registry()
                changed = True
        if changed:
            self._notify()

    @callback
    def sync_device_registry(self) -> None:
        """Put the firmware version on the device page."""
        if not self.firmware:
            return
        registry = dr.async_get(self._hass)
        device = registry.async_get_device(identifiers={(DOMAIN, self.address)})
        if device is not None and device.sw_version != self.firmware:
            registry.async_update_device(device.id, sw_version=self.firmware)
