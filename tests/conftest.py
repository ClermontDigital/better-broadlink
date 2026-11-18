"""A fake Broadlink remote: it 'hears' whatever a test queues, and keeps what it's asked to send."""
import asyncio
import base64
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.better_broadlink.const import CONF_DEVTYPE, CONF_MAC, CONF_MODEL, DOMAIN
from homeassistant.const import CONF_HOST

pytest_plugins = ["pytest_homeassistant_custom_component"]

MAC = "e81656b7ea95"
HOST = "192.168.1.27"
# Two real codes from an Akai remote (TCL112AC), as the RM4 Pro records them, cut short.
TURBO_ON = bytes.fromhex("2600cc016233" + "0f23" * 20 + "000d05")
TURBO_OFF = bytes.fromhex("2600cc016233" + "0f22" * 20 + "000d05")
WAIT = object()   # queued instead of a code: the press never comes, the window runs out


class FakeRemote:
    """Stands in for broadlink_async's rm4pro."""

    def __init__(self) -> None:
        self.host = (HOST, 80)
        self.mac = bytes.fromhex(MAC)
        self.devtype = 0x520B
        self.model = "RM4 pro"
        self.name = "RainbowRemote"
        self.heard: list = []          # what each capture window will hear: bytes, None (nothing) or WAIT
        self.sent: list[bytes] = []
        self.auths = 0
        self.fail_next_send_with = None
        self.windows: list[dict] = []
        self.closed = False

    async def auth(self) -> bool:
        self.auths += 1
        return True

    async def send_data(self, data: bytes) -> None:
        if (err := self.fail_next_send_with) is not None:
            self.fail_next_send_with = None
            raise err
        self.sent.append(data)

    async def capture(self, window: float = 30.0, **kwargs):
        self.windows.append({"window": window, **kwargs})
        item = self.heard.pop(0) if self.heard else None
        if item is WAIT:
            await asyncio.sleep(3600)
        if isinstance(item, bytes):
            yield SimpleNamespace(packet=item)

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def remote() -> FakeRemote:
    fake = FakeRemote()
    with patch("custom_components.better_broadlink.hub.blk.gendevice", return_value=fake), \
         patch("custom_components.better_broadlink.config_flow.blk.hello", return_value=fake):
        yield fake


def make_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN, title="RainbowRemote", unique_id=MAC,
        data={CONF_HOST: HOST, CONF_MAC: MAC, CONF_DEVTYPE: 0x520B, CONF_MODEL: "RM4 pro"},
    )


@pytest.fixture
async def entry(hass, remote) -> MockConfigEntry:
    e = make_entry()
    e.add_to_hass(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    return e


def b64(packet: bytes) -> str:
    return base64.b64encode(packet).decode()
