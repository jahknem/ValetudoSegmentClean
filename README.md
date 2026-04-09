# Valetudo Segment Cleaner (HACS Custom Integration)

This repository contains a Home Assistant custom integration that allows segment cleaning by **segment name** (multi-select list) instead of raw segment IDs.

It is designed to be safe while testing:
- The service defaults to `execute: false`.
- If `execute: true`, it can automatically stop and send the vacuum back to dock (`stop_and_dock_after_start: true`).

## What this adds

- A new domain: `valetudo_segment_cleaner`
- Service: `valetudo_segment_cleaner.refresh_segments`
- Service: `valetudo_segment_cleaner.clean_segments_by_name`
- Sensor entity: `sensor.valetudo_segment_cleaner_discovery_overview` (name in UI: "Discovery Overview")

The integration uses **MQTT autodiscovery**:
- Uses fixed topic patterns:
	- discovery: `valetudo/+/MapData/#` (plus internal fallbacks)
	- command: `valetudo/<robot_id>/MapSegmentationCapability/clean`
- Learns robot IDs and segment names automatically
- Resolves names to IDs and publishes a segment clean MQTT command

## HACS installation

1. Put this repository on GitHub.
2. In HACS, open Custom repositories.
3. Add your repo URL and select category **Integration**.
4. Install **Valetudo Segment Cleaner**.
5. Restart Home Assistant.

## UI setup (recommended)

1. Go to Settings -> Devices & Services -> Add Integration.
2. Search for `Valetudo Segment Cleaner`.
3. Configure values (defaults are pre-filled):
	- Optional default vacuum entity ID
	- Optional default robot ID
4. Save.

Most installations only need to set optional defaults.

## MQTT broker in Home Assistant

If MQTT is not configured yet in Home Assistant, configure broker credentials in the MQTT integration first.

## YAML import fallback (optional)

UI configuration is preferred. YAML can still be used once and imported into a config entry:

Add this to `configuration.yaml`:

```yaml
valetudo_segment_cleaner:
	default_vacuum_entity_id: "vacuum.my_robot"
	default_robot_id: "valetudo"
```

Restart Home Assistant after adding configuration.

## Example automation/service call (multi-name list)

Use action `valetudo_segment_cleaner.clean_segments_by_name` with:

```yaml
action: valetudo_segment_cleaner.clean_segments_by_name
data:
	entry_id: "<optional-config-entry-id>"
	vacuum_entity_id: vacuum.my_robot
	segment_names:
		- Kitchen
		- Hall
		- Dining
	robot_id: roborock
	execute: true
	command: app_segment_clean
	stop_and_dock_after_start: true
```

For safe dry-runs, keep `execute: false`.

Notes:
- `robot_id` is optional if only one Valetudo robot is auto-discovered.
- `entry_id` is optional if only one integration entry is configured.
- `vacuum_entity_id` is optional if `default_vacuum_entity_id` is set in integration options.
- `command` is informational in MQTT mode right now; publish payload is `{ "segment_ids": [...] }`.

## UI elements

The integration creates UI entities that can be used directly in dashboards:

- State: number of discovered robots
- Attributes include:
	- `discovered_robot_ids`
	- per-robot segment names and counts
	- configured defaults

Additionally, once segment data is discovered, it creates:

- Switch entities: one per discovered segment (`<robot> <segment> selected`)
- Button entities: one per robot (`<robot> clean selected segments`)

These are automatically populated from MQTT data.

This gives native multi-select in HA UI: turn on multiple segment switches, then press the
robot's "clean selected segments" button.

## Multi-select segment cleaning in Home Assistant UI

1. Let the vacuum publish map data so segments are discovered.
2. Open Entities and filter for `selected` and `clean selected segments`.
3. Add the generated switches and button to your dashboard.
4. Toggle any number of segment switches ON.
5. Press the robot button to start cleaning selected segments.

Tip: Segment names available for your robots are visible in the attributes of
`sensor.discovery_overview` from this integration.

You can also call service `valetudo_segment_cleaner.clean_selected_segments` directly.

## Extra safety automation

A standalone safety automation is included in `examples_safety_automation.yaml`.
Import or copy it and replace `vacuum.my_robot` with your entity.

## Local tests

Only parser/resolution unit tests are included locally (they do not call your Home Assistant).

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

## Live LAN validation harness

Use this script to validate Home Assistant API reachability, MQTT auth, live Valetudo topic traffic,
and segment payload parsing in one run.

```bash
python -m pip install -r requirements-dev.txt
python scripts/live_validate.py
```

The script defaults to your current environment:
- HA: `192.168.178.10:8123`
- MQTT: `192.168.178.10:1883`
- MQTT user: `zigbee2mqtt`
- MQTT pass: `wbV=.4zpPNL=3RZN:FTV`
- MQTT topic: `valetudo/#`

Override if needed:

```bash
python scripts/live_validate.py --ha-host 192.168.178.10 --mqtt-host 192.168.178.10 --listen-seconds 8
```

## Real-world verification in Home Assistant

1. Confirm your vacuum publishes map data on MQTT.
2. Restart Home Assistant and check logs for discovered robot IDs.
3. Run service `valetudo_segment_cleaner.refresh_segments`.
4. Run `valetudo_segment_cleaner.clean_segments_by_name` with `execute: false` first.
5. Run again with `execute: true` and verify:
	- MQTT publish to `valetudo/<robot_id>/MapSegmentationCapability/clean`
	- Vacuum starts
	- Vacuum is stopped and sent to dock immediately (safety behavior)

## Notes

- This integration does not delete entities, devices, or any Home Assistant data.
- It only registers services, publishes MQTT commands, and calls existing vacuum services.