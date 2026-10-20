"""Shared fixtures. Bluetooth is never started: the integration's BLE calls are patched."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.govee_ble_h6058.const import CONF_MODEL, DOMAIN
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant

ADDRESS = "A1:B2:C3:D4:E5:F6"


def service_info(
    name: str = "Govee_H6058_E5F6", address: str = ADDRESS
) -> BluetoothServiceInfoBleak:
    """Advertisement of a lamp as Home Assistant's Bluetooth integration reports it."""
    return BluetoothServiceInfoBleak(
        name=name,
        address=address,
        rssi=-65,
        manufacturer_data={34818: bytes.fromhex("ec000101015c")},
        service_data={},
        service_uuids=["00010203-0405-0607-0809-0a0b0c0d1910"],
        source="local",
        device=BLEDevice(address, name, None),
        advertisement=AdvertisementData(
            local_name=name,
            manufacturer_data={},
            service_data={},
            service_uuids=[],
            tx_power=None,
            rssi=-65,
            platform_data=(),
        ),
        connectable=True,
        time=0,
        tx_power=None,
    )


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load the integration from custom_components."""
    return


@pytest.fixture(autouse=True)
def skip_bluetooth_setup(hass: HomeAssistant) -> None:
    """Pretend the bluetooth dependency is set up, so no adapter is touched."""
    hass.config.components.add("bluetooth")


@pytest.fixture
def ble_device() -> BLEDevice:
    return BLEDevice(ADDRESS, "Govee_H6058_E5F6", None)


@pytest.fixture
def mock_link():
    """Replace the BLE link's network side: run() idles, send() records frames."""

    async def _idle(self):
        return None

    with (
        patch(
            "custom_components.govee_ble_h6058.ble.GoveeBleLink.run",
            autospec=True,
            side_effect=_idle,
        ),
        patch(
            "custom_components.govee_ble_h6058.ble.GoveeBleLink.send",
            new_callable=AsyncMock,
        ) as send,
        patch(
            "custom_components.govee_ble_h6058.ble.GoveeBleLink.async_stop",
            new_callable=AsyncMock,
        ) as stop,
    ):
        yield send, stop


def make_entry(model: str = "H6058", address: str = ADDRESS, title: str = "Desk lamp"):
    return MockConfigEntry(
        domain=DOMAIN,
        title=title,
        unique_id=address,
        data={CONF_ADDRESS: address, CONF_MODEL: model},
    )
