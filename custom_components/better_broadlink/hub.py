"""The connection to one Broadlink remote, and the commands recorded with it."""
from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import logging
from typing import Any

import broadlink_async as blk
from broadlink_async.exceptions import (
    AuthorizationError,
    BroadlinkException,
    CaptureInProgressError,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .const import (
    CONF_DEVTYPE,
    CONF_MAC,
    CONF_MODEL,
    DOMAIN,
    PAUSE_BETWEEN_PRESSES,
    REARM_INTERVAL,
    SIGNAL_COMMANDS,
    STORAGE_VERSION,
    RecordingStatus,
)

_LOGGER = logging.getLogger(__name__)

type BetterBroadlinkConfigEntry = ConfigEntry[BetterBroadlinkHub]


@dataclass
class Command:
    """A recorded command: one code (a button) or an on/off pair (a switch)."""

    slug: str
    name: str
    codes: list[str]
    icon: str | None = None
    recorded: str | None = None

    @property
    def toggle(self) -> bool:
        """True for an on/off pair."""
        return len(self.codes) == 2

    @property
    def platform(self) -> str:
        """The entity platform the command shows up on."""
        return "switch" if self.toggle else "button"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Command:
        """Load a command from storage."""
        return cls(data["slug"], data["name"], list(data["codes"]), data.get("icon"), data.get("recorded"))


@dataclass
class Recording:
    """The recording in progress, or the last one."""

    status: RecordingStatus = RecordingStatus.IDLE
    command: str | None = None
    press: int = 0
    presses: int = 0
    ends_at: datetime | None = None

    @property
    def prompt(self) -> str:
        """What to do now, in words, for a dashboard."""
        if self.status is RecordingStatus.WAITING:
            if self.presses == 2:
                return f"Press {self.command} on the remote ({'on' if self.press == 1 else 'off'}, {self.press} of 2)"
            return f"Press {self.command} on the remote"
        if self.status is RecordingStatus.RECORDED:
            return f"{self.command} recorded"
        if self.status is RecordingStatus.NOTHING_HEARD:
            return f"Nothing heard for {self.command}"
        if self.status is RecordingStatus.CANCELLED:
            return f"Recording {self.command} cancelled"
        return ""


def decode_code(code: str) -> bytes:
    """Turn a stored or pasted base64 code into the packet the device sends."""
    code = code.strip()
    code = code.removeprefix("b64:")
    try:
        packet = base64.b64decode(code + "=" * (-len(code) % 4), validate=True)
    except (binascii.Error, ValueError) as err:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="bad_code", translation_placeholders={"error": str(err)}
        ) from err
    if len(packet) < 4:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="bad_code", translation_placeholders={"error": "too short"}
        )
    return packet


class BetterBroadlinkHub:
    """One Broadlink remote: its session, its recorded commands and the recording in progress."""

    def __init__(self, hass: HomeAssistant, entry: BetterBroadlinkConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.api: blk.Device | None = None
        self.commands: dict[str, Command] = {}
        self.recording = Recording()
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self._send_lock = asyncio.Lock()
        self._record_task: asyncio.Task | None = None
        self._listeners: list[Callable[[], None]] = []

    @property
    def mac(self) -> str:
        """The remote's MAC address, as Home Assistant formats it."""
        return format_mac(self.entry.data[CONF_MAC])

    @property
    def model(self) -> str | None:
        """The remote's model, as it reports it."""
        return self.entry.data.get(CONF_MODEL)

    async def async_setup(self) -> None:
        """Load the recorded commands and open a session with the remote."""
        stored = await self._store.async_load() or {}
        self.commands = {c["slug"]: Command.from_dict(c) for c in stored.get("commands", [])}
        api = blk.gendevice(
            self.entry.data[CONF_DEVTYPE],
            (self.entry.data[CONF_HOST], 80),
            bytes.fromhex(self.entry.data[CONF_MAC]),
            name=self.entry.title,
        )
        try:
            await api.auth()
        except (BroadlinkException, OSError):
            await api.aclose()
            raise
        self.api = api

    async def async_close(self) -> None:
        """Stop a recording and close the session."""
        if self._record_task is not None:
            self._record_task.cancel()
        if self.api is not None:
            await self.api.aclose()
            self.api = None

    async def _async_request[T](self, function: Callable[..., Awaitable[T]], *args: Any) -> T:
        """Call the remote, authenticating again once if the session has lapsed."""
        try:
            return await function(*args)
        except AuthorizationError:
            assert self.api is not None
            await self.api.auth()
            return await function(*args)

    async def async_send(self, code: str) -> None:
        """Send one recorded code."""
        if self.api is None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="not_connected")
        packet = decode_code(code)
        async with self._send_lock:
            try:
                await self._async_request(self.api.send_data, packet)
            except (BroadlinkException, OSError) as err:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="send_failed", translation_placeholders={"error": str(err)}
                ) from err

    # Recording

    @callback
    def async_add_recording_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Call ``listener`` whenever the recording changes; returns the remover."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    @callback
    def _set_recording(self, status: RecordingStatus, command: str | None, press: int = 0, presses: int = 0,
                       ends_at: datetime | None = None) -> None:
        self.recording = Recording(status, command, press, presses, ends_at)
        for listener in list(self._listeners):
            listener()

    async def _async_capture_one(self, window: float) -> bytes | None:
        """Wait up to ``window`` seconds for one press; the packet, or None if nothing was heard."""
        assert self.api is not None
        signals = self.api.capture(window=window, stop_after_first=True, rearm_interval=REARM_INTERVAL)
        async with contextlib.aclosing(signals):
            async for signal in signals:
                return signal.packet
        return None

    async def async_record(self, name: str, toggle: bool, window: float, icon: str | None) -> Command:
        """Record a button from the remote: one press, or two for an on/off pair."""
        slug = self._slug(name)
        if self.api is None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="not_connected")
        if self._record_task is not None:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="already_recording")
        presses = 2 if toggle else 1
        self._record_task = asyncio.current_task()
        codes: list[str] = []
        try:
            for press in range(1, presses + 1):
                if press > 1:
                    await asyncio.sleep(PAUSE_BETWEEN_PRESSES)
                self._set_recording(RecordingStatus.WAITING, name, press, presses,
                                    dt_util.utcnow() + timedelta(seconds=window))
                try:
                    packet = await self._async_capture_one(window)
                except CaptureInProgressError as err:
                    raise ServiceValidationError(translation_domain=DOMAIN, translation_key="already_recording") from err
                except (BroadlinkException, OSError) as err:
                    self._set_recording(RecordingStatus.NOTHING_HEARD, name, press, presses)
                    raise HomeAssistantError(
                        translation_domain=DOMAIN, translation_key="record_failed",
                        translation_placeholders={"error": str(err)},
                    ) from err
                if packet is None:
                    self._set_recording(RecordingStatus.NOTHING_HEARD, name, press, presses)
                    raise HomeAssistantError(
                        translation_domain=DOMAIN, translation_key="nothing_heard",
                        translation_placeholders={"name": name, "seconds": str(int(window))},
                    )
                codes.append(base64.b64encode(packet).decode())
        except asyncio.CancelledError:
            self._set_recording(RecordingStatus.CANCELLED, name, len(codes) + 1, presses)
            raise
        finally:
            self._record_task = None
        command = await self._async_store(slug, name, codes, icon)
        self._set_recording(RecordingStatus.RECORDED, name, presses, presses)
        return command

    @callback
    def async_cancel_recording(self) -> bool:
        """Stop the recording in progress; False if there wasn't one."""
        if self._record_task is None:
            return False
        self._record_task.cancel()
        return True

    # Commands

    def _slug(self, name: str) -> str:
        slug = slugify(name)
        if not slug:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="bad_name")
        return slug

    def command(self, name: str) -> Command:
        """A recorded command, by name or slug."""
        command = self.commands.get(slugify(name))
        if command is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="unknown_command", translation_placeholders={"name": name}
            )
        return command

    async def async_add(self, name: str, codes: list[str], icon: str | None) -> Command:
        """Store codes recorded elsewhere: one for a button, two (on, off) for a switch."""
        slug = self._slug(name)
        if len(codes) not in (1, 2):
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="one_or_two_codes")
        clean = [base64.b64encode(decode_code(code)).decode() for code in codes]
        return await self._async_store(slug, name, clean, icon)

    async def async_forget(self, name: str) -> None:
        """Forget a recorded command, and its entity."""
        command = self.command(name)
        self._remove_entity(command)
        del self.commands[command.slug]
        await self._async_save()
        async_dispatcher_send(self.hass, SIGNAL_COMMANDS.format(self.entry.entry_id), command.slug)

    async def _async_store(self, slug: str, name: str, codes: list[str], icon: str | None) -> Command:
        old = self.commands.get(slug)
        command = Command(slug, name, codes, icon or (old.icon if old else None), dt_util.utcnow().isoformat())
        if old is not None and old.platform != command.platform:
            self._remove_entity(old)   # a button re-recorded as an on/off pair, or the other way round
        self.commands[slug] = command
        await self._async_save()
        async_dispatcher_send(self.hass, SIGNAL_COMMANDS.format(self.entry.entry_id), slug)
        return command

    def unique_id(self, command: Command) -> str:
        """The unique id of a command's entity."""
        return f"{self.mac}_{command.slug}"

    @callback
    def _remove_entity(self, command: Command) -> None:
        registry = er.async_get(self.hass)
        if entity_id := registry.async_get_entity_id(command.platform, DOMAIN, self.unique_id(command)):
            registry.async_remove(entity_id)

    async def _async_save(self) -> None:
        await self._store.async_save({"commands": [asdict(c) for c in self.commands.values()]})

    async def async_remove_storage(self) -> None:
        """Delete the recorded commands (the config entry is being removed)."""
        await self._store.async_remove()
