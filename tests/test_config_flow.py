"""Config flow: Bluetooth discovery, pick a discovered lamp, manual MAC entry."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from custom_components.govee_ble_h6058.config_flow import normalize_mac
from custom_components.govee_ble_h6058.const import CONF_MODEL, DOMAIN, MODELS, NAME_PREFIXES
from homeassistant.components.bluetooth.match import ble_device_matches
from homeassistant.config_entries import SOURCE_BLUETOOTH, SOURCE_USER
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import ADDRESS, make_entry, service_info

DISCOVERED = "custom_components.govee_ble_h6058.config_flow.async_discovered_service_info"


@pytest.fixture(autouse=True)
def no_setup():
    """Creating an entry must not start the integration in these tests."""
    with patch("custom_components.govee_ble_h6058.async_setup_entry", return_value=True):
        yield


async def test_bluetooth_discovery(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=service_info()
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "bluetooth_confirm"
    assert result["description_placeholders"] == {"name": "Govee_H6058_E5F6", "model": "H6058"}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Govee H6058 E5F6"
    assert result["data"] == {CONF_ADDRESS: ADDRESS, CONF_MODEL: "H6058"}
    assert result["result"].unique_id == ADDRESS


async def test_bluetooth_discovery_of_an_untested_model(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_BLUETOOTH},
        data=service_info("ihoment_H6159_1A2B", "A4:C1:38:00:1A:2B"),
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_ADDRESS: "A4:C1:38:00:1A:2B", CONF_MODEL: "H6159"}


async def test_bluetooth_discovery_already_configured(hass: HomeAssistant):
    make_entry().add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=service_info()
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_bluetooth_discovery_unsupported_model(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_BLUETOOTH},
        data=service_info("Govee_H617C_4253", "C4:39:32:33:42:53"),
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_supported"


async def test_user_picks_a_discovered_lamp(hass: HomeAssistant):
    configured = make_entry(address="11:22:33:44:55:66")
    configured.add_to_hass(hass)
    infos = [
        service_info(),
        service_info("Govee_H6058_5566", "11:22:33:44:55:66"),  # already configured
        service_info("Govee_H617C_4253", "C4:39:32:33:42:53"),  # not supported
    ]
    with patch(DISCOVERED, return_value=infos):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["pick", "manual"]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "pick"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "pick"
    options = result["data_schema"].schema[CONF_ADDRESS].config["options"]
    assert [o["value"] for o in options] == [ADDRESS]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: ADDRESS}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_ADDRESS: ADDRESS, CONF_MODEL: "H6058"}


async def test_user_menu_to_manual(hass: HomeAssistant):
    with patch(DISCOVERED, return_value=[service_info()]):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "manual"}
    )
    assert result["step_id"] == "manual"


async def test_manual_entry_when_nothing_is_discovered(hass: HomeAssistant):
    with patch(DISCOVERED, return_value=[]):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manual"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: "nonsense", CONF_MODEL: "H6058"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_ADDRESS: "invalid_address"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: "a1-b2-c3-d4-e5-f6", CONF_MODEL: "H613D"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Govee H613D E5F6"
    assert result["data"] == {CONF_ADDRESS: ADDRESS, CONF_MODEL: "H613D"}


async def test_manual_entry_already_configured(hass: HomeAssistant):
    make_entry().add_to_hass(hass)
    with patch(DISCOVERED, return_value=[]):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: ADDRESS.lower(), CONF_MODEL: "H6058"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("A1:B2:C3:D4:E5:F6", ADDRESS),
        (" a1:b2:c3:d4:e5:f6 ", ADDRESS),
        ("A1-B2-C3-D4-E5-F6", ADDRESS),
        ("A1B2C3D4E5F6", ADDRESS),
        ("A1:B2-C3:D4:E5:F6", None),
        ("A1:B2:C3:D4:E5", None),
        ("ZZ:B2:C3:D4:E5:F6", None),
    ],
)
def test_normalize_mac(value, expected):
    assert normalize_mac(value) == expected


def _manifest_matchers() -> list[dict]:
    manifest = Path(__file__).parent.parent / "custom_components" / DOMAIN / "manifest.json"
    return json.loads(manifest.read_text())["bluetooth"]


@pytest.mark.parametrize(
    ("name", "matches"),
    [
        ("Govee_H6058_E5F6", True),  # what the real lamp advertises
        ("ihoment_H6159_1A2B", True),
        ("GBK_H613D_0001", True),
        ("Govee_H617C_4253", False),
        ("Govee_H5075_1234", False),  # a thermometer
    ],
)
def test_manifest_matchers(name, matches):
    """The manifest's matchers, evaluated by Home Assistant's own Bluetooth matcher."""
    info = service_info(name)
    assert any(ble_device_matches(m, info) for m in _manifest_matchers()) is matches


def test_every_model_has_matchers():
    names = {m["local_name"] for m in _manifest_matchers()}
    for model in MODELS:
        for prefix in NAME_PREFIXES:
            assert f"{prefix}_{model}*" in names
