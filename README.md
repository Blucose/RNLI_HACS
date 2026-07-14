# RNLI Lifeboat Launches

A Home Assistant integration that gives you information about the most recent
[RNLI](https://rnli.org) lifeboat launches from a station of your choice.

It creates a sensor whose state is the timestamp of the station's latest
launch, with details of the launch (lifeboat ID, station website, etc.) as
attributes. Data comes from the public RNLI launches feed and is refreshed
every 5 minutes.

## Installation

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

You can add the integration multiple times to monitor several stations.

## Sensor

Each configured station gets a sensor like `sensor.rnli_tower_latest_launch`:

- **State** — timestamp of the most recent launch (or unknown if the station
  has no launches in the recent feed).
- **Attributes** — `lifeboat_id`, `station_title`, `station_website`,
  `launch_id`, `recent_launch_count`, and any other fields the feed provides.
  Known stations also get `latitude`/`longitude` (so the sensor appears at
  the station's location on the Home Assistant map), `station_url`,
  `what3words`, and `station_type` (ALB/ILB) from RNLI open data.

## Example automation

```yaml
automation:
  - alias: Notify on lifeboat launch
    trigger:
      - platform: state
        entity_id: sensor.rnli_tower_latest_launch
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "Lifeboat launched!"
          message: >
            {{ state_attr('sensor.rnli_tower_latest_launch', 'station_title') }}
            launched lifeboat
            {{ state_attr('sensor.rnli_tower_latest_launch', 'lifeboat_id') }}
```
