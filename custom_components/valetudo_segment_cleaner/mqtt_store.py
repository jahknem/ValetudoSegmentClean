"""MQTT-backed segment discovery and command publishing."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from homeassistant.components import mqtt
from homeassistant.components.mqtt.models import ReceiveMessage
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from .const import (
    CONF_DEFAULT_ROBOT_ID,
    CONF_DEFAULT_VACUUM_ENTITY_ID,
    DEFAULT_COMMAND_TOPIC_SUFFIX,
    DEFAULT_MQTT_TOPIC_PREFIX,
    DEFAULT_SEGMENT_TOPIC_SUFFIX,
)
from .helpers import (
    extract_robot_id_from_topic,
    parse_segments_from_mqtt_payload,
    to_name_id_map,
)

_LOGGER = logging.getLogger(__name__)


class MqttSegmentStore:
    """Maintain discovered Valetudo segment maps keyed by robot ID."""

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        self._hass = hass
        self._topic_prefix = DEFAULT_MQTT_TOPIC_PREFIX
        self._segment_suffix = DEFAULT_SEGMENT_TOPIC_SUFFIX
        self._command_suffix = DEFAULT_COMMAND_TOPIC_SUFFIX
        self._default_vacuum_entity_id = config.get(CONF_DEFAULT_VACUUM_ENTITY_ID)
        self._default_robot_id = config.get(CONF_DEFAULT_ROBOT_ID)

        self._name_maps: dict[str, dict[str, int]] = {}
        self._segment_catalog: dict[str, dict[int, str]] = {}
        self._selected_segment_ids: dict[str, set[int]] = {}
        self._unsubscribers: list[Any] = []
        self._listeners: set[Callable[[], None]] = set()

    @property
    def default_vacuum_entity_id(self) -> str | None:
        """Return default vacuum entity id for this store."""
        value = self._default_vacuum_entity_id
        return str(value) if isinstance(value, str) and value else None

    @property
    def default_robot_id(self) -> str | None:
        """Return default robot id for this store."""
        value = self._default_robot_id
        return str(value) if isinstance(value, str) and value else None

    @property
    def discovered_robot_ids(self) -> list[str]:
        """Return currently discovered robot IDs."""
        return sorted(self._name_maps.keys())

    def _discovery_topics(self) -> tuple[str, str, str]:
        primary = f"{self._topic_prefix}/+/{self._segment_suffix}"
        fallback_legacy = f"{self._topic_prefix}/+/map_data"
        fallback_hass = f"{self._topic_prefix}/+/MapData/map-data-hass"
        return primary, fallback_legacy, fallback_hass

    async def async_start(self) -> None:
        """Start MQTT subscriptions for segment auto-discovery."""
        topics = self._discovery_topics()

        for topic in topics:
            self._unsubscribers.append(
                await mqtt.async_subscribe(self._hass, topic, self._message_received, qos=0)
            )

        _LOGGER.info("Subscribed to Valetudo segment discovery topics: %s", topics)

    async def async_stop(self) -> None:
        """Stop MQTT subscriptions."""
        for unsub in self._unsubscribers:
            unsub()
        self._unsubscribers.clear()

    @callback
    def _message_received(self, msg: ReceiveMessage) -> None:
        robot_id = extract_robot_id_from_topic(msg.topic, self._topic_prefix)
        if not robot_id:
            return

        segments = parse_segments_from_mqtt_payload(msg.payload)
        if not segments:
            return

        name_map = to_name_id_map(segments)
        if not name_map:
            return

        catalog: dict[int, str] = {}
        for segment in segments:
            seg_id = segment.get("id")
            seg_name = segment.get("name")
            if isinstance(seg_id, int) and isinstance(seg_name, str):
                catalog[seg_id] = seg_name

        if not catalog:
            return

        self._name_maps[robot_id] = name_map
        self._segment_catalog[robot_id] = catalog

        # Keep user selections only for segments that still exist.
        if robot_id not in self._selected_segment_ids:
            self._selected_segment_ids[robot_id] = set()
        existing_ids = set(catalog.keys())
        self._selected_segment_ids[robot_id].intersection_update(existing_ids)

        _LOGGER.debug("Updated segment cache for robot %s with %d entries", robot_id, len(name_map))
        self._notify_listeners()

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register listener callback for cache updates."""
        self._listeners.add(listener)

        def _remove_listener() -> None:
            self._listeners.discard(listener)

        return _remove_listener

    def _notify_listeners(self) -> None:
        for listener in tuple(self._listeners):
            listener()

    def resolve_robot_id(self, preferred_robot_id: str | None) -> str:
        """Resolve robot ID from preferred value or auto-discovery state."""
        if preferred_robot_id:
            if preferred_robot_id in self._name_maps:
                return preferred_robot_id
            raise HomeAssistantError(
                f"Robot ID '{preferred_robot_id}' has no discovered segment data yet"
            )

        robot_ids = self.discovered_robot_ids
        if len(robot_ids) == 1:
            return robot_ids[0]

        if not robot_ids:
            raise HomeAssistantError(
                "No Valetudo segment data discovered yet via MQTT. "
                "Run the vacuum once or publish map data first."
            )

        raise HomeAssistantError(
            "Multiple Valetudo robots discovered. Please provide robot_id in service data."
        )

    def get_name_map(self, robot_id: str) -> dict[str, int]:
        """Get name->id map for a robot."""
        return self._name_maps.get(robot_id, {})

    def get_segment_names(self, robot_id: str) -> list[str]:
        """Get sorted segment names for a robot id."""
        catalog = self._segment_catalog.get(robot_id, {})
        return sorted(catalog.values())

    def get_segment_catalog(self, robot_id: str) -> dict[int, str]:
        """Get segment catalog for robot where key is segment id and value is display name."""
        return dict(self._segment_catalog.get(robot_id, {}))

    def is_segment_selected(self, robot_id: str, segment_id: int) -> bool:
        """Check if segment is selected for robot."""
        return segment_id in self._selected_segment_ids.get(robot_id, set())

    def set_segment_selected(self, robot_id: str, segment_id: int, selected: bool) -> None:
        """Set selected state for segment and notify listeners."""
        if robot_id not in self._selected_segment_ids:
            self._selected_segment_ids[robot_id] = set()

        if selected:
            self._selected_segment_ids[robot_id].add(segment_id)
        else:
            self._selected_segment_ids[robot_id].discard(segment_id)

        self._notify_listeners()

    def get_selected_segment_ids(self, robot_id: str) -> list[int]:
        """Get selected segment IDs for robot sorted by ID."""
        return sorted(self._selected_segment_ids.get(robot_id, set()))

    def get_selected_segment_names(self, robot_id: str) -> list[str]:
        """Get selected segment names for robot sorted by segment ID."""
        catalog = self._segment_catalog.get(robot_id, {})
        names: list[str] = []
        for seg_id in self.get_selected_segment_ids(robot_id):
            if seg_id in catalog:
                names.append(catalog[seg_id])
        return names

    def get_discovery_snapshot(self) -> dict[str, Any]:
        """Return diagnostics snapshot for UI entities."""
        robots: dict[str, dict[str, Any]] = {}
        for robot_id in self.discovered_robot_ids:
            segment_names = self.get_segment_names(robot_id)
            robots[robot_id] = {
                "segment_count": len(segment_names),
                "segment_names": segment_names,
                "selected_segment_ids": self.get_selected_segment_ids(robot_id),
                "selected_segment_names": self.get_selected_segment_names(robot_id),
            }

        return {
            "default_robot_id": self.default_robot_id,
            "default_vacuum_entity_id": self.default_vacuum_entity_id,
            "robots": robots,
        }

    def resolve_selected_segments(self, preferred_robot_id: str | None) -> tuple[str, list[int], list[str]]:
        """Resolve selected segments for a robot; returns robot id, ids and names."""
        robot_id = self.resolve_robot_id(preferred_robot_id)
        segment_ids = self.get_selected_segment_ids(robot_id)
        if not segment_ids:
            raise HomeAssistantError(f"No selected segments for robot '{robot_id}'")
        return robot_id, segment_ids, self.get_selected_segment_names(robot_id)

    def build_command_topic(self, robot_id: str) -> str:
        """Build command topic for segment cleaning."""
        return f"{self._topic_prefix}/{robot_id}/{self._command_suffix}"

    async def async_publish_segment_clean(self, robot_id: str, segment_ids: list[int]) -> None:
        """Publish segment clean request over MQTT."""
        topic = self.build_command_topic(robot_id)
        payload = json.dumps(
            {
                "segment_ids": segment_ids,
                "iterations": 1,
                "customOrder": True,
            }
        )
        await mqtt.async_publish(self._hass, topic, payload, qos=0, retain=False)
        _LOGGER.info("Published segment clean command to %s for segment_ids=%s", topic, segment_ids)
