# RNLI Lifeboat Launches

An unofficial Home Assistant integration that gives you information about the most recent
[RNLI](https://rnli.org) lifeboat launches from a station of your choice.

For each station it creates a sensor whose state is the timestamp of the
station's latest launch, with details of the launch (lifeboat ID, station
website, etc.) as attributes, and an event entity that fires when a new launch
comes in. Data comes from the public RNLI launches feed and is refreshed every
5 minutes.

> ❤️ **Enjoying this integration?** The RNLI is a charity that saves lives at
> sea, funded almost entirely by voluntary donations. If this is useful to you,
> please consider giving something back to the volunteers whose work makes the
> data possible: **[Donate to the RNLI »](https://rnli.org/support-us/give-money/donate)**

## Installation

Requires Home Assistant 2024.11 or newer.

### HACS (recommended)

1. In HACS, add this repository (`Blucose/RNLI_HACS`) as a custom repository
   of type **Integration**.
2. Install **RNLI Lifeboat Launches**.
3. Restart Home Assistant.

### Manual

1. Copy the `custom_components/rnli_launches` folder into your Home Assistant
   `config/custom_components/` directory.
2. Restart Home Assistant.

## Setup

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **RNLI Lifeboat Launches**.
3. Pick your lifeboat station from the dropdown. All 238 RNLI stations are
   listed (sourced from RNLI open data, with names refreshed from the live
   launches feed), sorted by distance from your Home Assistant home location
   so your nearest station appears first. You can also type a name manually.

You can add the integration multiple times to monitor several stations; they
all share one request to the RNLI feed.

To monitor a different station later, open the station's entry under
**Settings → Devices & Services → RNLI Lifeboat Launches** and choose
**Reconfigure**. The old station's entities are replaced with ones for the new
station.

## Entities

Each configured station gets a device with two entities, for example:

### `event.rnli_tower_launch` — launch event

Fires once for each new launch from the station, with the attributes
`launch_id`, `lifeboat_id`, `launch_time`, `station_title` and
`station_website`. It does not fire for:

- launches already in the feed when you add the station,
- feed outages, restarts or reloads, or
- launches more than 24 hours old, for example after Home Assistant has been
  offline for a while.

If several launches arrive in the same 5-minute refresh (both of a station's
lifeboats going out, say), it fires once, for the newest.

### `sensor.rnli_tower_latest_launch` — latest launch

- **State** — timestamp of the most recent launch. Once a launch has been
  seen it is remembered and persists across Home Assistant restarts, even after
  it scrolls out of the API's recent window; it only ever advances to a newer
  launch. It reads `unknown` only until the station's first launch is seen.
  Once a launch is known, the sensor stays available even while the feed is
  unreachable.
- **Attributes** — `lifeboat_id`, `station_title`, `station_website`,
  `launch_id`, `cOACS` (as reported by the feed), and `recent_launch_count`
  (how many of the station's launches are in the feed's current window).
  Known stations also get `latitude`/`longitude` (so the sensor appears at
  the station's location on the Home Assistant map), `station_url`,
  `what3words`, and `station_type` (ALB/ILB) from RNLI open data.

## Example automation

Trigger on the event entity to be notified of each new launch:

```yaml
automation:
  - alias: Notify on lifeboat launch
    triggers:
      - trigger: state
        entity_id: event.rnli_tower_launch
        not_from: unavailable
        not_to: unavailable
    actions:
      - action: notify.mobile_app_your_phone
        data:
          title: "Lifeboat launched!"
          message: >
            {{ trigger.to_state.attributes.station_title }}
            launched lifeboat
            {{ trigger.to_state.attributes.lifeboat_id }}
```

If you trigger on the sensor instead, include `not_from` and `not_to` as
below. Without them the trigger also fires when only an attribute changes (for
example when an older launch drops out of the feed) and when the sensor goes
unavailable and back, such as during a reload.

```yaml
    triggers:
      - trigger: state
        entity_id: sensor.rnli_tower_latest_launch
        not_from: [unknown, unavailable]
        not_to: [unknown, unavailable]
```

## Troubleshooting

If a station never shows any launches, download the diagnostics from the
station's entry (**⋮ → Download diagnostics**). They list the station names
in the current feed, which shows whether the feed spells your station's name
differently. They contain no personal data.

## Support the RNLI

Every launch this integration reports is a crew of volunteers heading out to
help someone in trouble. The RNLI relies on donations to keep those lifeboats
crewed, fuelled, and ready — around the clock, all year round.

If you like this integration, the best thank-you isn't to me — it's to them:

### 👉 [Donate to the RNLI](https://rnli.org/support-us/give-money/donate)

Every little helps keep a lifeboat afloat. ⛑️🌊

## License

The code is released under the [MIT License](LICENSE). The RNLI logo images
(in `custom_components/rnli_launches/brand/` and `images/`) are not covered
by that license.
