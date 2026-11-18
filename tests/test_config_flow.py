"""Adding a remote."""
from unittest.mock import patch

from broadlink_async.exceptions import NetworkTimeoutError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.better_broadlink.const import CONF_DEVTYPE, CONF_MAC, CONF_MODEL, DOMAIN
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST
from homeassistant.data_entry_flow import FlowResultType

from .conftest import HOST, MAC, make_entry


async def test_the_core_integrations_remote_is_offered(hass, remote):
    MockConfigEntry(domain="broadlink", data={CONF_HOST: HOST}).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    host = next(k for k in result["data_schema"].schema if k == CONF_HOST)
    assert host.default() == HOST


async def test_a_remote_is_added(hass, remote):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: f" {HOST} "})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "RainbowRemote"
    assert result["data"] == {CONF_HOST: HOST, CONF_MAC: MAC, CONF_DEVTYPE: 0x520B, CONF_MODEL: "RM4 pro"}
    assert result["result"].unique_id == MAC
    assert remote.auths >= 1 and remote.closed   # checked in the flow (and again when the entry sets up)


async def test_nothing_at_the_address(hass):
    with patch("custom_components.better_broadlink.config_flow.blk.hello",
               side_effect=NetworkTimeoutError(-4000, "Network timeout", "no answer")):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: "192.168.1.99"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_a_broadlink_that_cant_record_is_refused(hass, remote):
    plug = type("Plug", (), {"mac": remote.mac, "devtype": 0x7547, "model": "SP4", "name": "Plug",
                              "auth": remote.auth, "aclose": remote.aclose})()
    with patch("custom_components.better_broadlink.config_flow.blk.hello", return_value=plug):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: HOST})
    assert result["errors"] == {"base": "not_a_remote"}


async def test_the_same_remote_twice_is_refused(hass, remote):
    make_entry().add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: HOST})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
