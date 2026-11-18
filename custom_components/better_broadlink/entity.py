"""Base entity: everything Better Broadlink adds sits on the remote's own device."""
from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, SIGNAL_COMMANDS
from .hub import BetterBroadlinkHub, Command


class BetterBroadlinkEntity(Entity):
    """An entity of one Broadlink remote.

    A device belongs to one config entry, so this is a device of its own beside the one Home Assistant's Broadlink
    integration makes for the same remote. It's identified by the MAC address but doesn't claim it as a connection,
    which the other device already has.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, hub: BetterBroadlinkHub) -> None:
        self.hub = hub
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, hub.mac)},
            name=hub.entry.title,
            manufacturer="Broadlink",
            model=hub.model,
        )


class CommandEntity(BetterBroadlinkEntity):
    """The entity of a recorded command (a button, or a switch for an on/off pair)."""

    def __init__(self, hub: BetterBroadlinkHub, command: Command) -> None:
        super().__init__(hub)
        self.slug = command.slug
        self._attr_unique_id = hub.unique_id(command)
        self._attr_name = command.name
        self._attr_icon = command.icon

    @property
    def command(self) -> Command:
        """The command as it's stored now (it may have been recorded again)."""
        return self.hub.commands[self.slug]

    @property
    def available(self) -> bool:
        """Unavailable while the remote has no session."""
        return self.hub.api is not None and self.slug in self.hub.commands

    async def async_added_to_hass(self) -> None:
        """Follow the command when it's recorded again (a new name or icon)."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_COMMANDS.format(self.hub.entry.entry_id), self._async_changed)
        )

    @callback
    def _async_changed(self, slug: str) -> None:
        if slug != self.slug or slug not in self.hub.commands:
            return
        self._attr_name = self.command.name
        self._attr_icon = self.command.icon
        self.async_write_ha_state()
