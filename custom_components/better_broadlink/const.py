"""Constants for Better Broadlink."""
from enum import StrEnum

DOMAIN = "better_broadlink"

CONF_MAC = "mac"
CONF_DEVTYPE = "devtype"
CONF_MODEL = "model"

ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_NAME = "name"
ATTR_TOGGLE = "toggle"
ATTR_WINDOW = "window"
ATTR_ICON = "icon"
ATTR_CODES = "codes"

# How long each press is waited for, in seconds.
DEFAULT_WINDOW = 45
MIN_WINDOW = 10
MAX_WINDOW = 120
# The RM4 Pro drops out of learning mode on its own, without saying so, and Home Assistant's own
# Broadlink integration polls it once a minute on another session; re-arming this often keeps it listening.
REARM_INTERVAL = 10.0
# Between the two presses of an on/off pair, so the second window doesn't open on the tail of the first press.
PAUSE_BETWEEN_PRESSES = 1.5

STORAGE_VERSION = 1

# Dispatcher signal, per config entry: a recorded command was added, changed or forgotten.
SIGNAL_COMMANDS = f"{DOMAIN}_commands_{{}}"


class RecordingStatus(StrEnum):
    """Where a recording is up to, shown by the Recording sensor."""

    IDLE = "idle"
    WAITING = "waiting"
    RECORDED = "recorded"
    NOTHING_HEARD = "nothing_heard"
    CANCELLED = "cancelled"
