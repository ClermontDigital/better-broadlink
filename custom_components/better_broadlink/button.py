"""A button for each recorded command with one code."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import SIGNAL_COMMANDS
from .entity import CommandEntity
from .hub import BetterBroadlinkConfigEntry


async def async_setup_entry(
    hass: HomeAssistant, entry: BetterBroadlinkConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add a button per one-code command, now and as more are recorded."""
    hub = entry.runtime_data
    known: set[str] = set()

    @callback
    def add_new(_: str | None = None) -> None:
        known.intersection_update(s for s, c in hub.commands.items() if not c.toggle)
        new = [CommandButton(hub, c) for s, c in hub.commands.items() if not c.toggle and s not in known]
        known.update(b.slug for b in new)
        if new:
            async_add_entities(new)

    add_new()
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_COMMANDS.format(entry.entry_id), add_new))


class CommandButton(CommandEntity, ButtonEntity):
    """Sends a recorded code."""

    async def async_press(self) -> None:
        """Send the code."""
        await self.hub.async_send(self.command.codes[0])
