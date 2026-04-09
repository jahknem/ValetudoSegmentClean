"""Constants for Valetudo Segment Cleaner."""

from __future__ import annotations

DOMAIN = "valetudo_segment_cleaner"
DEFAULT_SEGMENT_COMMAND = "app_segment_clean"
DEFAULT_MQTT_TOPIC_PREFIX = "valetudo"
DEFAULT_SEGMENT_TOPIC_SUFFIX = "MapData/#"
DEFAULT_COMMAND_TOPIC_SUFFIX = "MapSegmentationCapability/clean"

SERVICE_CLEAN_SEGMENTS_BY_NAME = "clean_segments_by_name"
SERVICE_REFRESH_SEGMENTS = "refresh_segments"

ATTR_VACUUM_ENTITY_ID = "vacuum_entity_id"
ATTR_SEGMENT_NAMES = "segment_names"
ATTR_EXECUTE = "execute"
ATTR_STOP_AND_DOCK_AFTER_START = "stop_and_dock_after_start"
ATTR_COMMAND = "command"
ATTR_ROBOT_ID = "robot_id"

EVENT_SEGMENT_CLEAN_REQUEST = "valetudo_segment_clean_request"

CONF_MQTT_TOPIC_PREFIX = "mqtt_topic_prefix"
CONF_MQTT_SEGMENT_TOPIC_SUFFIX = "mqtt_segment_topic_suffix"
CONF_MQTT_COMMAND_TOPIC_SUFFIX = "mqtt_command_topic_suffix"
