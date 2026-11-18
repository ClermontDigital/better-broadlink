"""A switch for each recorded on/off pair (the first press turns it on, the second off)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import SIGNAL_COMMANDS
from .entity import CommandEntity
from .hub import BetterBroadlinkConfigEntry


async def async_setup_entry(
    hass: HomeAssistant, entry: BetterBroadlinkConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add a switch per on/off pair, now and as more are recorded."""
    hub = entry.runtime_data
    known: set[str] = set()

    @callback
    def add_new(_: str | None = None) -> None:
        known.intersection_update(s for s, c in hub.commands.items() if c.toggle)
        new = [CommandSwitch(hub, c) for s, c in hub.commands.items() if c.toggle and s not in known]
        known.update(s.slug for s in new)
        if new:
            async_add_entities(new)

    add_new()
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_COMMANDS.format(entry.entry_id), add_new))


class CommandSwitch(CommandEntity, SwitchEntity, RestoreEntity):
    """Sends the "on" code or the "off" code. Infrared has no answer back, so the state is the last one sent."""

    _attr_assumed_state = True
    _attr_is_on = False

    async def async_added_to_hass(self) -> None:
        """Pick up the last state sent."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            self._attr_is_on = last.state == STATE_ON

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Send the first code."""
        await self.hub.async_send(self.command.codes[0])
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Send the second code."""
        await self.hub.async_send(self.command.codes[1])
        self._attr_is_on = False
        self.async_write_ha_state()
