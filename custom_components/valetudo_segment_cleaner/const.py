"""Constants for Valetudo Segment Cleaner."""

from __future__ import annotations

DOMAIN = "valetudo_segment_cleaner"
DEFAULT_SEGMENT_COMMAND = "app_segment_clean"
DEFAULT_MQTT_TOPIC_PREFIX = "valetudo"
DEFAULT_SEGMENT_TOPIC_SUFFIX = "MapData/#"
DEFAULT_COMMAND_TOPIC_SUFFIX = "MapSegmentationCapability/clean"
DEFAULT_CONFIG_TITLE = "Valetudo Segment Cleaner"

SERVICE_CLEAN_SEGMENTS_BY_NAME = "clean_segments_by_name"
SERVICE_CLEAN_SELECTED_SEGMENTS = "clean_selected_segments"
SERVICE_REFRESH_SEGMENTS = "refresh_segments"

ATTR_VACUUM_ENTITY_ID = "vacuum_entity_id"
ATTR_SEGMENT_NAMES = "segment_names"
ATTR_EXECUTE = "execute"
ATTR_STOP_AND_DOCK_AFTER_START = "stop_and_dock_after_start"
ATTR_COMMAND = "command"
ATTR_ROBOT_ID = "robot_id"
ATTR_ENTRY_ID = "entry_id"
ATTR_SEGMENT_IDS = "segment_ids"

EVENT_SEGMENT_CLEAN_REQUEST = "valetudo_segment_clean_request"

CONF_DEFAULT_VACUUM_ENTITY_ID = "default_vacuum_entity_id"
CONF_DEFAULT_ROBOT_ID = "default_robot_id"

DATA_ENTRIES = "entries"
DATA_SERVICES_REGISTERED = "services_registered"
