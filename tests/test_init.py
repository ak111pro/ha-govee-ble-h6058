"""Setup, entities, commands and unload with a mocked BLE link."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from custom_components.govee_ble_h6058 import light as light_module
from custom_components.govee_ble_h6058.const import DOMAIN
from custom_components.govee_ble_h6058.diagnostics import async_get_config_entry_diagnostics
from custom_components.govee_ble_h6058.protocol import (
    brightness_frame,
    color_temp_frame,
    power_frame,
    rgb_frame,
)
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_MODE,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGB_COLOR,
    ColorMode,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .conftest import ADDRESS, make_entry

FROM_ADDRESS = "custom_components.govee_ble_h6058.bluetooth.async_ble_device_from_address"
LIGHT = "light.desk_lamp"


@pytest.fixture
async def setup_lamp(hass: HomeAssistant, mock_link, ble_device):
    """Set up an H6058 entry named 'Desk lamp'; returns (entry, send, stop)."""
    send, stop = mock_link
    entry = make_entry()
    entry.add_to_hass(hass)
    with patch(FROM_ADDRESS, return_value=ble_device):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry, send, stop


def _reply(entry, cmd: int, payload: bytes) -> None:
    entry.runtime_data.handle_frame(cmd, payload + bytes(17 - len(payload)))


async def test_setup_creates_entities_with_mac_unique_ids(
    hass: HomeAssistant, setup_lamp, entity_registry: er.EntityRegistry
):
    entry, _send, _stop = setup_lamp
    assert entry.state is ConfigEntryState.LOADED
    ids = {
        e.unique_id: e.entity_id
        for e in er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    }
    assert ids == {
        "A1B2C3D4E5F6": LIGHT,
        "A1B2C3D4E5F6_battery": "sensor.desk_lamp_battery",
        "A1B2C3D4E5F6_charging": "binary_sensor.desk_lamp_charging",
        "A1B2C3D4E5F6_plugged_in": "binary_sensor.desk_lamp_plugged_in",
    }
    # Unknown until the lamp's first status reply.
    assert hass.states.get("sensor.desk_lamp_battery").state == STATE_UNAVAILABLE


async def test_untested_mains_model_has_no_battery_entities(
    hass: HomeAssistant, mock_link, ble_device, entity_registry: er.EntityRegistry
):
    entry = make_entry(model="H613A", title="Strip")
    entry.add_to_hass(hass)
    with patch(FROM_ADDRESS, return_value=ble_device):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    entities = er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    assert [e.entity_id for e in entities] == ["light.strip"]


async def test_not_ready_when_no_scanner_sees_the_lamp(hass: HomeAssistant, mock_link):
    entry = make_entry()
    entry.add_to_hass(hass)
    with patch(FROM_ADDRESS, return_value=None):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_status_reply_updates_power_and_battery(hass: HomeAssistant, setup_lamp):
    entry, _send, _stop = setup_lamp
    _reply(entry, 0x01, bytes([0x01, 0x00, 0xD4]))  # on, charging
    await hass.async_block_till_done()
    assert hass.states.get(LIGHT).state == STATE_ON
    battery = hass.states.get("sensor.desk_lamp_battery")
    assert battery.state == "84"
    assert battery.attributes["charge_state"] == "charging"
    assert battery.attributes["raw_status_byte"] == 0xD4
    assert hass.states.get("binary_sensor.desk_lamp_charging").state == STATE_ON
    assert hass.states.get("binary_sensor.desk_lamp_plugged_in").state == STATE_ON

    _reply(entry, 0x01, bytes([0x00, 0x00, 0x50]))  # off, on battery
    await hass.async_block_till_done()
    assert hass.states.get(LIGHT).state == STATE_OFF
    assert hass.states.get("sensor.desk_lamp_battery").state == "80"
    assert hass.states.get("binary_sensor.desk_lamp_charging").state == STATE_OFF
    assert hass.states.get("binary_sensor.desk_lamp_plugged_in").state == STATE_OFF


async def test_firmware_goes_to_the_device(
    hass: HomeAssistant, setup_lamp, device_registry: dr.DeviceRegistry
):
    entry, _send, _stop = setup_lamp
    _reply(entry, 0x06, b"1.01.11")
    device = device_registry.async_get_device(identifiers={(DOMAIN, ADDRESS)})
    assert device.sw_version == "1.01.11"
    assert device.model == "H6058"
    assert device.manufacturer == "Govee"
    assert device.name == "Desk lamp"


async def test_firmware_lookup_is_scoped_to_the_config_entry(
    hass: HomeAssistant, setup_lamp, device_registry: dr.DeviceRegistry
):
    """On HA 2026.10+ the device is looked up within its own config entry."""
    entry, _send, _stop = setup_lamp
    device = device_registry.async_get_device(identifiers={(DOMAIN, ADDRESS)})
    calls = []

    def by_identifier(_registry, identifier, config_entry_id):
        calls.append((identifier, config_entry_id))
        return device

    with patch.object(
        dr.DeviceRegistry, "async_get_device_by_identifier", by_identifier, create=True
    ):
        _reply(entry, 0x06, b"1.02.03")
    assert calls == [((DOMAIN, ADDRESS), entry.entry_id)]
    assert device_registry.async_get(device.id).sw_version == "1.02.03"


async def test_turn_on_with_brightness_and_colour(hass: HomeAssistant, setup_lamp):
    _entry, send, _stop = setup_lamp
    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: LIGHT, ATTR_BRIGHTNESS: 128, ATTR_RGB_COLOR: (255, 140, 0)},
        blocking=True,
    )
    assert send.await_args.args[0] == [
        power_frame(True),
        brightness_frame(128, 100),
        rgb_frame(255, 140, 0),
    ]
    state = hass.states.get(LIGHT)
    assert state.state == STATE_ON
    assert state.attributes[ATTR_BRIGHTNESS] == 128
    assert state.attributes[ATTR_COLOR_MODE] == ColorMode.RGB

    await hass.services.async_call(
        "light", "turn_on", {ATTR_ENTITY_ID: LIGHT, ATTR_COLOR_TEMP_KELVIN: 2700}, blocking=True
    )
    assert send.await_args.args[0] == [power_frame(True), color_temp_frame(2700)]
    state = hass.states.get(LIGHT)
    assert state.attributes[ATTR_COLOR_MODE] == ColorMode.COLOR_TEMP
    assert state.attributes[ATTR_COLOR_TEMP_KELVIN] == 2700
    assert state.attributes["min_color_temp_kelvin"] == 2200
    assert state.attributes["max_color_temp_kelvin"] == 6500


async def test_h6159_uses_0_255_brightness(hass: HomeAssistant, mock_link, ble_device):
    send, _stop = mock_link
    entry = make_entry(model="H6159", title="Strip")
    entry.add_to_hass(hass)
    with patch(FROM_ADDRESS, return_value=ble_device):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    await hass.services.async_call(
        "light", "turn_on", {ATTR_ENTITY_ID: "light.strip", ATTR_BRIGHTNESS: 200}, blocking=True
    )
    assert send.await_args.args[0][1] == brightness_frame(200, 255)


async def test_command_state_is_held_against_a_stale_reply(hass: HomeAssistant, setup_lamp):
    entry, _send, _stop = setup_lamp
    _reply(entry, 0x01, bytes([0x00, 0x00, 0x5C]))  # lamp reports off
    await hass.async_block_till_done()
    await hass.services.async_call("light", "turn_on", {ATTR_ENTITY_ID: LIGHT}, blocking=True)
    assert hass.states.get(LIGHT).state == STATE_ON
    # A keep-alive reply that was in flight still says "off": ignored during the hold-off.
    _reply(entry, 0x01, bytes([0x00, 0x00, 0x5D]))
    await hass.async_block_till_done()
    assert hass.states.get(LIGHT).state == STATE_ON


async def test_lamp_report_wins_after_the_hold_off(hass: HomeAssistant, setup_lamp):
    entry, _send, _stop = setup_lamp
    with patch.object(light_module, "POWER_SYNC_HOLDOFF", 0):
        await hass.services.async_call("light", "turn_off", {ATTR_ENTITY_ID: LIGHT}, blocking=True)
        assert hass.states.get(LIGHT).state == STATE_OFF
        _reply(entry, 0x01, bytes([0x01, 0x00, 0x5C]))  # physical button turned it on
        await hass.async_block_till_done()
    assert hass.states.get(LIGHT).state == STATE_ON


async def test_failed_send_raises_and_restores_reported_state(hass: HomeAssistant, setup_lamp):
    entry, send, _stop = setup_lamp
    _reply(entry, 0x01, bytes([0x00, 0x00, 0x5C]))
    await hass.async_block_till_done()
    send.side_effect = ConnectionError("no link")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("light", "turn_on", {ATTR_ENTITY_ID: LIGHT}, blocking=True)
    assert hass.states.get(LIGHT).state == STATE_OFF


async def test_diagnostics_redacts_the_address(hass: HomeAssistant, setup_lamp):
    entry, _send, _stop = setup_lamp
    _reply(entry, 0x01, bytes([0x01, 0x00, 0x5C]))
    data = await async_get_config_entry_diagnostics(hass, entry)
    assert ADDRESS not in str(data)
    assert data["model"]["model"] == "H6058"
    assert data["status"]["battery"] == 92
    assert data["status"]["charge_state"] == "full"


async def test_unload_stops_the_link(hass: HomeAssistant, setup_lamp):
    entry, _send, stop = setup_lamp
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    stop.assert_awaited_once()
