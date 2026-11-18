"""Better Broadlink: record buttons from any infrared remote with a Broadlink, and send them."""
from __future__ import annotations

from broadlink_async.exceptions import BroadlinkException
import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_CODES,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_ICON,
    ATTR_NAME,
    ATTR_TOGGLE,
    ATTR_WINDOW,
    DEFAULT_WINDOW,
    DOMAIN,
    MAX_WINDOW,
    MIN_WINDOW,
)
from .hub import BetterBroadlinkConfigEntry, BetterBroadlinkHub

PLATFORMS = [Platform.BUTTON, Platform.SENSOR, Platform.SWITCH]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

ENTRY = {vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string}
RECORD_SCHEMA = vol.Schema({
    **ENTRY,
    vol.Required(ATTR_NAME): cv.string,
    vol.Optional(ATTR_TOGGLE, default=False): cv.boolean,
    vol.Optional(ATTR_WINDOW, default=DEFAULT_WINDOW): vol.All(vol.Coerce(int), vol.Range(MIN_WINDOW, MAX_WINDOW)),
    vol.Optional(ATTR_ICON): cv.icon,
})
ADD_SCHEMA = vol.Schema({
    **ENTRY,
    vol.Required(ATTR_NAME): cv.string,
    vol.Required(ATTR_CODES): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional(ATTR_ICON): cv.icon,
})
NAME_SCHEMA = vol.Schema({**ENTRY, vol.Required(ATTR_NAME): cv.string})
CANCEL_SCHEMA = vol.Schema(ENTRY)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the actions."""

    def hub_for(call: ServiceCall) -> BetterBroadlinkHub:
        entries = [e for e in hass.config_entries.async_entries(DOMAIN) if e.state is ConfigEntryState.LOADED]
        if entry_id := call.data.get(ATTR_CONFIG_ENTRY_ID):
            entries = [e for e in entries if e.entry_id == entry_id]
        if len(entries) != 1:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="no_entry" if not entries else "which_entry"
            )
        return entries[0].runtime_data

    def describe(hub: BetterBroadlinkHub, slug: str) -> dict:
        command = hub.commands[slug]
        return {"command": command.slug, "name": command.name, "platform": command.platform, "codes": len(command.codes)}

    async def record(call: ServiceCall) -> ServiceResponse:
        hub = hub_for(call)
        command = await hub.async_record(call.data[ATTR_NAME], call.data[ATTR_TOGGLE], call.data[ATTR_WINDOW],
                                         call.data.get(ATTR_ICON))
        return describe(hub, command.slug)

    async def add(call: ServiceCall) -> ServiceResponse:
        hub = hub_for(call)
        command = await hub.async_add(call.data[ATTR_NAME], call.data[ATTR_CODES], call.data.get(ATTR_ICON))
        return describe(hub, command.slug)

    async def send(call: ServiceCall) -> None:
        hub = hub_for(call)
        command = hub.command(call.data[ATTR_NAME])
        await hub.async_send(command.codes[0])

    async def forget(call: ServiceCall) -> None:
        hub = hub_for(call)
        await hub.async_forget(call.data[ATTR_NAME])

    async def cancel(call: ServiceCall) -> None:
        hub_for(call).async_cancel_recording()

    hass.services.async_register(DOMAIN, "record", record, RECORD_SCHEMA, supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, "add", add, ADD_SCHEMA, supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, "send", send, NAME_SCHEMA)
    hass.services.async_register(DOMAIN, "forget", forget, NAME_SCHEMA)
    hass.services.async_register(DOMAIN, "cancel_recording", cancel, CANCEL_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: BetterBroadlinkConfigEntry) -> bool:
    """Connect to the remote and add its entities."""
    hub = BetterBroadlinkHub(hass, entry)
    try:
        await hub.async_setup()
    except (BroadlinkException, OSError) as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN, translation_key="cannot_connect", translation_placeholders={"error": str(err)}
        ) from err
    entry.runtime_data = hub
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BetterBroadlinkConfigEntry) -> bool:
    """Close the session."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_close()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: BetterBroadlinkConfigEntry) -> None:
    """Delete the recorded commands with the entry."""
    hub = BetterBroadlinkHub(hass, entry)
    await hub.async_remove_storage()
