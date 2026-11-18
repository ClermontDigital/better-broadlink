# Changelog

## 0.1.1 (18 Nov 2026)

- The Recording sensor goes back to Idle a minute after a recording is recorded, heard nothing or is cancelled,
  so a dashboard banner keyed on it doesn't stay up.

## 0.1.0 (18 Nov 2026)

First release.

- Add a Broadlink universal remote by its address (the one Home Assistant's Broadlink integration has is offered).
- `better_broadlink.record`: one press becomes a button, two (on, off) a switch; waits 45 s a press, re-arming the
  remote every 10 s; a Recording sensor with the prompt and deadline for dashboards.
- `better_broadlink.add`, `send`, `forget` and `cancel_recording`.
- Diagnostics without the codes.
