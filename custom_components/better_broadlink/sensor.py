"""The Recording sensor: what to press now, for a dashboard beside the remote."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import RecordingStatus
from .entity import BetterBroadlinkEntity
from .hub import BetterBroadlinkConfigEntry


async def async_setup_entry(
    hass: HomeAssistant, entry: BetterBroadlinkConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add the Recording sensor."""
    async_add_entities([RecordingSensor(entry.runtime_data)])


class RecordingSensor(BetterBroadlinkEntity, SensorEntity):
    """Idle, waiting for a press, recorded, nothing heard or cancelled; the prompt and deadline as attributes."""

    _attr_translation_key = "recording"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [s.value for s in RecordingStatus]

    def __init__(self, hub) -> None:
        super().__init__(hub)
        self._attr_unique_id = f"{hub.mac}_recording"

    @property
    def native_value(self) -> str:
        """Where the recording is up to."""
        return self.hub.recording.status.value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """The command, which press, the prompt and when the wait ends."""
        r = self.hub.recording
        return {
            "command": r.command,
            "press": r.press or None,
            "presses": r.presses or None,
            "prompt": r.prompt or None,
            "ends_at": r.ends_at.isoformat() if r.ends_at else None,
        }

    async def async_added_to_hass(self) -> None:
        """Update whenever the recording moves on."""
        await super().async_added_to_hass()
        self.async_on_remove(self.hub.async_add_recording_listener(self.async_write_ha_state))
