# Valetudo Segment Cleaner (HACS Custom Integration)

This repository contains a Home Assistant custom integration that allows segment cleaning by **segment name** (multi-select list) instead of raw segment IDs.

It is designed to be safe while testing:
- The service defaults to `execute: false`.
- If `execute: true`, it can automatically stop and send the vacuum back to dock (`stop_and_dock_after_start: true`).

## What this adds

- A new domain: `valetudo_segment_cleaner`
- Service: `valetudo_segment_cleaner.refresh_segments`
- Service: `valetudo_segment_cleaner.clean_segments_by_name`

The integration uses **MQTT autodiscovery**:
- Subscribes to `valetudo/+/MapData/map-data-hass` (and fallback `valetudo/+/map_data`)
- Learns robot IDs and segment names automatically
- Resolves names to IDs and publishes a segment clean MQTT command

## HACS installation

1. Put this repository on GitHub.
2. In HACS, open Custom repositories.
3. Add your repo URL and select category **Integration**.
4. Install **Valetudo Segment Cleaner**.
5. Restart Home Assistant.

## MQTT broker in Home Assistant

If MQTT is not configured yet in Home Assistant, configure broker credentials in the MQTT integration first.

## Home Assistant configuration for this integration

Add this to `configuration.yaml`:

```yaml
valetudo_segment_cleaner:
	mqtt_topic_prefix: "valetudo"
	mqtt_segment_topic_suffix: "MapData/#"
	mqtt_command_topic_suffix: "MapSegmentationCapability/clean"
```

Restart Home Assistant after adding configuration.

## Example automation/service call (multi-name list)

Use action `valetudo_segment_cleaner.clean_segments_by_name` with:

```yaml
action: valetudo_segment_cleaner.clean_segments_by_name
data:
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
- `command` is informational in MQTT mode right now; publish payload is `{ "segment_ids": [...] }`.

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