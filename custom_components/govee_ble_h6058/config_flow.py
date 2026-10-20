"""Config flow: Bluetooth discovery, pick a discovered lamp, or enter a MAC address."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import CONF_MODEL, DOMAIN, MODELS, model_from_name

_MAC_RE = re.compile(r"^[0-9A-F]{2}([:-]?)[0-9A-F]{2}(\1[0-9A-F]{2}){4}$")


def normalize_mac(value: str) -> str | None:
    """'a1-b2-c3-d4-e5-f6' or 'a1b2c3d4e5f6' -> 'A1:B2:C3:D4:E5:F6'; None if invalid."""
    value = value.strip().upper()
    if not _MAC_RE.match(value):
        return None
    digits = value.replace(":", "").replace("-", "")
    return ":".join(digits[i : i + 2] for i in range(0, 12, 2))


def default_title(model: str, address: str) -> str:
    """'Govee H6058 E5F6', like the name the lamp advertises."""
    return f"Govee {model} {address.replace(':', '')[-4:]}"


class GoveeBleConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add one Govee lamp per config entry."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery: BluetoothServiceInfoBleak | None = None
        self._model: str | None = None
        self._discovered: dict[str, tuple[str, str]] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """A lamp was discovered via its advertisement."""
        await self.async_set_unique_id(discovery_info.address.upper())
        self._abort_if_unique_id_configured()
        model = model_from_name(discovery_info.name)
        if model is None:
            return self.async_abort(reason="not_supported")
        self._discovery = discovery_info
        self._model = model
        self.context["title_placeholders"] = {"name": discovery_info.name}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a discovered lamp."""
        assert self._discovery is not None and self._model is not None
        if user_input is not None:
            return self._create(self._discovery.address.upper(), self._model)
        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": self._discovery.name, "model": self._model},
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Offer the discovered lamps, or go to manual entry when there are none."""
        configured = self._async_current_ids(include_ignore=False)
        self._discovered = {}
        for info in async_discovered_service_info(self.hass, connectable=True):
            address = info.address.upper()
            model = model_from_name(info.name)
            if model is None or address in configured or address in self._discovered:
                continue
            self._discovered[address] = (info.name, model)
        if not self._discovered:
            return await self.async_step_manual()
        return self.async_show_menu(step_id="user", menu_options=["pick", "manual"])

    async def async_step_pick(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Pick one of the discovered lamps."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self._create(address, self._discovered[address][1])

        options = [
            SelectOptionDict(value=address, label=f"{name} ({address})")
            for address, (name, _model) in self._discovered.items()
        ]
        return self.async_show_form(
            step_id="pick",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): SelectSelector(
                        SelectSelectorConfig(options=options, mode=SelectSelectorMode.LIST)
                    )
                }
            ),
        )

    async def async_step_manual(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Enter the MAC address and model by hand."""
        errors: dict[str, str] = {}
        if user_input is not None:
            address = normalize_mac(user_input[CONF_ADDRESS])
            if address is None:
                errors[CONF_ADDRESS] = "invalid_address"
            else:
                await self.async_set_unique_id(address, raise_on_progress=False)
                self._abort_if_unique_id_configured()
                return self._create(address, user_input[CONF_MODEL].upper())

        schema = vol.Schema(
            {
                vol.Required(CONF_ADDRESS): str,
                vol.Required(CONF_MODEL, default="h6058"): SelectSelector(
                    SelectSelectorConfig(
                        # Translation keys must be lowercase; the stored model is upper case.
                        options=[model.lower() for model in MODELS],
                        mode=SelectSelectorMode.DROPDOWN,
                        translation_key="model",
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="manual",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    def _create(self, address: str, model: str) -> ConfigFlowResult:
        return self.async_create_entry(
            title=default_title(model, address),
            data={CONF_ADDRESS: address, CONF_MODEL: model},
        )
