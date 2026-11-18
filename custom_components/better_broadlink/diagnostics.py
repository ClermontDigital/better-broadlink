"""Diagnostics: the remote and what's recorded, without the codes themselves."""
from __future__ import annotations

import base64
from typing import Any

from homeassistant.core import HomeAssistant

from .hub import BetterBroadlinkConfigEntry


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: BetterBroadlinkConfigEntry) -> dict[str, Any]:
    """The entry, the session and each command's shape."""
    hub = entry.runtime_data
    return {
        "entry": {**entry.data, "title": entry.title},
        "connected": hub.api is not None,
        "recording": {"status": hub.recording.status.value, "command": hub.recording.command,
                      "press": hub.recording.press, "presses": hub.recording.presses},
        "commands": [
            {"slug": c.slug, "name": c.name, "platform": c.platform, "recorded": c.recorded,
             "codes": [{"bytes": len(p), "type": f"0x{p[0]:02x}"} for p in (base64.b64decode(code) for code in c.codes)]}
            for c in hub.commands.values()
        ],
    }
