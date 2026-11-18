"""Recording buttons, sending them, and what the Recording sensor says."""
import asyncio
from datetime import timedelta

from broadlink_async.exceptions import AuthorizationError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.better_broadlink.const import DOMAIN
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .conftest import TURBO_OFF, TURBO_ON, WAIT, b64, make_entry

SENSOR = "sensor.rainbowremote_recording"


async def record(hass, name, toggle=False, **extra):
    return await hass.services.async_call(DOMAIN, "record", {"name": name, "toggle": toggle, **extra},
                                          blocking=True, return_response=True)


async def test_the_recording_sensor_starts_idle(hass, entry):
    state = hass.states.get(SENSOR)
    assert state.state == "idle"
    assert state.attributes["prompt"] is None


async def test_a_press_becomes_a_button_that_sends_it(hass, entry, remote, hass_storage):
    remote.heard = [TURBO_ON]
    response = await record(hass, "Aircon display", icon="mdi:monitor")
    assert response == {"command": "aircon_display", "name": "Aircon display", "platform": "button", "codes": 1}
    await hass.async_block_till_done()

    state = hass.states.get("button.rainbowremote_aircon_display")
    assert state is not None and state.attributes["icon"] == "mdi:monitor"
    assert hass.states.get(SENSOR).state == "recorded"
    assert hass.states.get(SENSOR).attributes["prompt"] == "Aircon display recorded"
    assert remote.windows[0]["window"] == 45 and remote.windows[0]["rearm_interval"] == 10.0

    await hass.services.async_call("button", "press", {"entity_id": "button.rainbowremote_aircon_display"}, blocking=True)
    assert remote.sent == [TURBO_ON]
    stored = hass_storage[f"{DOMAIN}.{entry.entry_id}"]["data"]["commands"]
    assert stored[0]["slug"] == "aircon_display" and stored[0]["codes"] == [b64(TURBO_ON)]


async def test_two_presses_become_a_switch(hass, entry, remote):
    remote.heard = [TURBO_ON, TURBO_OFF]
    response = await record(hass, "Aircon turbo", toggle=True)
    assert response["platform"] == "switch" and response["codes"] == 2
    await hass.async_block_till_done()

    switch = "switch.rainbowremote_aircon_turbo"
    assert hass.states.get(switch).state == "off"
    assert hass.states.get(switch).attributes["assumed_state"] is True
    await hass.services.async_call("switch", "turn_on", {"entity_id": switch}, blocking=True)
    assert hass.states.get(switch).state == "on"
    await hass.services.async_call("switch", "turn_off", {"entity_id": switch}, blocking=True)
    assert hass.states.get(switch).state == "off"
    assert remote.sent == [TURBO_ON, TURBO_OFF]


async def test_the_sensor_says_what_to_press(hass, entry, remote):
    remote.heard = [WAIT]
    task = hass.async_create_task(record(hass, "Aircon turbo", toggle=True))
    await asyncio.sleep(0.05)
    state = hass.states.get(SENSOR)
    assert state.state == "waiting"
    assert state.attributes["prompt"] == "Press Aircon turbo on the remote (on, 1 of 2)"
    assert state.attributes["command"] == "Aircon turbo" and state.attributes["ends_at"]

    await hass.services.async_call(DOMAIN, "cancel_recording", {}, blocking=True)
    with pytest.raises(asyncio.CancelledError):
        await task
    assert hass.states.get(SENSOR).state == "cancelled"
    assert hass.states.get("switch.rainbowremote_aircon_turbo") is None


async def test_nothing_heard(hass, entry, remote):
    remote.heard = [None]
    with pytest.raises(HomeAssistantError, match="Nothing was heard for Aircon eco within 20 seconds"):
        await record(hass, "Aircon eco", window=20)
    assert hass.states.get(SENSOR).state == "nothing_heard"
    assert entry.runtime_data.commands == {}

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()
    assert hass.states.get(SENSOR).state == "idle"
    assert hass.states.get(SENSOR).attributes["prompt"] is None


async def test_a_missed_second_press_keeps_nothing(hass, entry, remote):
    remote.heard = [TURBO_ON, None]
    with pytest.raises(HomeAssistantError):
        await record(hass, "Aircon turbo", toggle=True)
    assert entry.runtime_data.commands == {}
    assert hass.states.get(SENSOR).attributes["press"] == 2


async def test_one_recording_at_a_time(hass, entry, remote):
    remote.heard = [WAIT]
    task = hass.async_create_task(record(hass, "Aircon turbo"))
    await asyncio.sleep(0.05)
    with pytest.raises(ServiceValidationError, match="already recording"):
        await record(hass, "Aircon eco")
    entry.runtime_data.async_cancel_recording()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_recording_again_as_a_pair_swaps_the_button_for_a_switch(hass, entry, remote):
    remote.heard = [TURBO_ON]
    await record(hass, "Aircon turbo")
    await hass.async_block_till_done()
    assert hass.states.get("button.rainbowremote_aircon_turbo") is not None

    remote.heard = [TURBO_ON, TURBO_OFF]
    await record(hass, "Aircon turbo", toggle=True)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    assert registry.async_get("button.rainbowremote_aircon_turbo") is None
    assert hass.states.get("switch.rainbowremote_aircon_turbo") is not None


async def test_codes_recorded_elsewhere_can_be_added(hass, entry, remote):
    response = await hass.services.async_call(
        DOMAIN, "add", {"name": "Aircon health", "codes": ["b64:" + b64(TURBO_ON), b64(TURBO_OFF).rstrip("=")]},
        blocking=True, return_response=True)
    assert response["platform"] == "switch"
    await hass.async_block_till_done()
    await hass.services.async_call("switch", "turn_off", {"entity_id": "switch.rainbowremote_aircon_health"}, blocking=True)
    assert remote.sent == [TURBO_OFF]

    with pytest.raises(ServiceValidationError, match="isn't a Broadlink code"):
        await hass.services.async_call(DOMAIN, "add", {"name": "Bad", "codes": ["not base64!"]}, blocking=True)
    with pytest.raises(ServiceValidationError, match="one code"):
        await hass.services.async_call(DOMAIN, "add", {"name": "Three", "codes": [b64(TURBO_ON)] * 3}, blocking=True)


async def test_send_and_forget_by_name(hass, entry, remote):
    remote.heard = [TURBO_ON]
    await record(hass, "Aircon clean")
    await hass.services.async_call(DOMAIN, "send", {"name": "Aircon clean"}, blocking=True)
    assert remote.sent == [TURBO_ON]

    await hass.services.async_call(DOMAIN, "forget", {"name": "aircon_clean"}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get("button.rainbowremote_aircon_clean") is None
    with pytest.raises(ServiceValidationError, match="Nothing is recorded under Aircon clean"):
        await hass.services.async_call(DOMAIN, "send", {"name": "Aircon clean"}, blocking=True)


async def test_commands_come_back_after_a_restart(hass, remote):
    entry = make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    remote.heard = [TURBO_ON, TURBO_OFF]
    await record(hass, "Aircon sleep", toggle=True)
    await hass.services.async_call("switch", "turn_on", {"entity_id": "switch.rainbowremote_aircon_sleep"}, blocking=True)

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get("switch.rainbowremote_aircon_sleep")
    assert state.state == "on"
    assert "aircon_sleep" in entry.runtime_data.commands


async def test_a_lapsed_session_is_renewed_and_the_code_still_sent(hass, entry, remote):
    remote.heard = [TURBO_ON]
    await record(hass, "Aircon mute")
    auths = remote.auths
    remote.fail_next_send_with = AuthorizationError(-7, "Authentication error", "lapsed")
    await hass.services.async_call(DOMAIN, "send", {"name": "Aircon mute"}, blocking=True)
    assert remote.auths == auths + 1 and remote.sent == [TURBO_ON]


async def test_a_device_of_its_own_beside_the_core_integrations(hass, remote):
    core = MockConfigEntry(domain="broadlink", data={})
    core.add_to_hass(hass)
    devices = dr.async_get(hass)
    theirs = devices.async_get_or_create(
        config_entry_id=core.entry_id, connections={(dr.CONNECTION_NETWORK_MAC, "e8:16:56:b7:ea:95")},
        identifiers={("broadlink", "e81656b7ea95")}, name="RainbowRemote")
    entry = make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    ours = devices.async_get(er.async_get(hass).async_get(SENSOR).device_id)
    assert ours.id != theirs.id
    assert ours.identifiers == {(DOMAIN, "e8:16:56:b7:ea:95")} and not ours.connections
    assert ours.name == "RainbowRemote" and ours.model == "RM4 pro"
    assert devices.async_get(theirs.id).connections == {(dr.CONNECTION_NETWORK_MAC, "e8:16:56:b7:ea:95")}


async def test_diagnostics_leave_the_codes_out(hass, entry, remote):
    from custom_components.better_broadlink.diagnostics import async_get_config_entry_diagnostics

    remote.heard = [TURBO_ON]
    await record(hass, "Aircon display")
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["commands"][0]["codes"] == [{"bytes": len(TURBO_ON), "type": "0x26"}]
    assert b64(TURBO_ON) not in str(diag)
