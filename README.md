# Better Broadlink

Record the buttons of any infrared remote with a Broadlink universal remote (RM4 Pro, RM4 mini, RM mini 3 and the
like) and use them in Home Assistant: each recorded button becomes a **button** entity, and a button recorded as an
on/off pair becomes a **switch**. A **Recording** sensor says what to press, so you can record from a dashboard on your
phone while you stand at the Broadlink with the remote.

<img src="custom_components/better_broadlink/brand/icon@2x.png" alt="Better Broadlink icon: a remote sending a signal" width="128">

## Why

Home Assistant's own Broadlink integration can learn codes, but it puts the remote into learning mode once and waits.
An RM4 Pro can drop out of learning mode on its own without saying so, so a press can go unheard and the learn ends
with "No infrared code received". Better Broadlink records through the capture window in
[broadlink-async](https://github.com/DAB-LABS/broadlink-async) (the library Home Assistant's integration uses), which
re-arms the remote every 10 seconds while it waits, and it waits 45 seconds a press by default.

It works alongside Home Assistant's Broadlink integration: keep that for the remote's temperature sensor and its own
entities, and use Better Broadlink for recorded buttons.

## What you get

For each remote you add, a device with:

| Entity | What it is |
|---|---|
| Recording (sensor) | Idle, Waiting for a press, Recorded, Nothing heard or Cancelled. Its `prompt` attribute says what to press ("Press Aircon turbo on the remote (on, 1 of 2)"), `ends_at` when the wait runs out |
| A button per recorded button | Sends the code |
| A switch per on/off pair | Turn on sends the first code, turn off the second. Infrared has no answer back, so the state is the last one sent (kept across restarts) |

And these actions:

| Action | What it does |
|---|---|
| `better_broadlink.record` | Waits for a press and keeps it under a name. `toggle: true` waits for two presses (on, then off) and makes a switch. Recording a name again replaces it |
| `better_broadlink.add` | Keeps a code recorded somewhere else (Broadlink base64, with or without `b64:`): one code for a button, two for a switch |
| `better_broadlink.send` | Sends a recorded code by name (the first one, for a pair) |
| `better_broadlink.forget` | Deletes a recorded command and its entity |
| `better_broadlink.cancel_recording` | Stops waiting |

## Install

**Home Assistant Marketplace (or HACS):** open the Marketplace, choose **⋮ → Custom repositories**, add
`https://github.com/ClermontDigital/better-broadlink` as an **Integration**, then install **Better Broadlink** and
restart Home Assistant.

**By hand:** copy `custom_components/better_broadlink` into your configuration's `custom_components` folder and restart.

Needs Home Assistant 2026.11 or later (the release that moved its Broadlink integration to broadlink-async).

## Set up

**Settings → Devices & services → Add integration → Better Broadlink**, and give the remote's address. If Home
Assistant's Broadlink integration already has one, its address is filled in.

## Record a button

1. Hold the remote a hand's width from the Broadlink, pointing at it.
2. Run the action (Developer tools → Actions, or from a dashboard button):

   ```yaml
   action: better_broadlink.record
   data:
     name: Aircon turbo
     toggle: true        # two presses: on, then off
     icon: mdi:rocket-launch-outline
   ```

3. When the Broadlink's light comes on (and the Recording sensor says so), press the button. For a pair, press it
   again when the light comes back on.

The recorded button is then `switch.<remote>_aircon_turbo` (or `button.<remote>_...` for a single press).

A card to put beside it on a dashboard, so you can see the prompt from the remote:

```yaml
type: conditional
conditions:
  - condition: state
    entity: sensor.ir_remote_recording
    state: waiting
card:
  type: markdown
  content: "**{{ state_attr('sensor.ir_remote_recording', 'prompt') }}**"
```

## Send from an automation

```yaml
actions:
  - action: switch.turn_on
    target:
      entity_id: switch.ir_remote_aircon_turbo
  - action: better_broadlink.send
    data:
      name: Aircon display
```

## Notes

- Infrared only for now. The codes are kept in `.storage/better_broadlink.<entry id>` and go with Home Assistant's backups.
- Air conditioner remotes send their whole setting with every press, so a recorded Turbo also sends the mode, fan and
  temperature the remote showed while it was recorded.
- Diagnostics list what's recorded (names, sizes) without the codes themselves.

## Help and ideas

[Open an issue](https://github.com/ClermontDigital/better-broadlink/issues).

Made by [Clermont Digital](https://clermont.digital).

## Licence

Apache 2.0. See [LICENSE](LICENSE).
