"""Set up a Broadlink remote by its address."""
from __future__ import annotations

from typing import Any

import broadlink_async as blk
from broadlink_async.exceptions import BroadlinkException
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_NAME

from .const import CONF_DEVTYPE, CONF_MAC, CONF_MODEL, DOMAIN

CORE_DOMAIN = "broadlink"


class BetterBroadlinkConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ask for the remote's address (offering the ones Home Assistant's Broadlink integration already has)."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Find the remote, check it can record infrared, and add it."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            try:
                device = await blk.hello(host, timeout=5)
            except (BroadlinkException, OSError):
                errors["base"] = "cannot_connect"
            else:
                try:
                    if not hasattr(device, "capture"):
                        errors["base"] = "not_a_remote"
                    else:
                        await device.auth()
                except (BroadlinkException, OSError):
                    errors["base"] = "cannot_connect"
                finally:
                    await device.aclose()
            if not errors:
                await self.async_set_unique_id(device.mac.hex())
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME) or device.name or device.model or host,
                    data={CONF_HOST: host, CONF_MAC: device.mac.hex(), CONF_DEVTYPE: device.devtype, CONF_MODEL: device.model},
                )

        configured = {e.data.get(CONF_HOST) for e in self._async_current_entries()}
        suggested = next(
            (h for e in self.hass.config_entries.async_entries(CORE_DOMAIN) if (h := e.data.get(CONF_HOST)) not in configured),
            "",
        )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default=(user_input or {}).get(CONF_HOST, suggested)): str,
                vol.Optional(CONF_NAME): str,
            }),
            errors=errors,
        )
