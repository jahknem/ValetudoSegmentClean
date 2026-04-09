"""MQTT-backed segment discovery and command publishing."""

from __future__ import annotations

import json
import logging
from typing import Any

from homeassistant.components import mqtt
from homeassistant.components.mqtt.models import ReceiveMessage
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from .const import (
    CONF_MQTT_COMMAND_TOPIC_SUFFIX,
    CONF_MQTT_SEGMENT_TOPIC_SUFFIX,
    CONF_MQTT_TOPIC_PREFIX,
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
        self._topic_prefix = str(config.get(CONF_MQTT_TOPIC_PREFIX, DEFAULT_MQTT_TOPIC_PREFIX)).strip("/")
        self._segment_suffix = str(
            config.get(CONF_MQTT_SEGMENT_TOPIC_SUFFIX, DEFAULT_SEGMENT_TOPIC_SUFFIX)
        ).strip("/")
        self._command_suffix = str(
            config.get(CONF_MQTT_COMMAND_TOPIC_SUFFIX, DEFAULT_COMMAND_TOPIC_SUFFIX)
        ).strip("/")

        self._name_maps: dict[str, dict[str, int]] = {}
        self._unsubscribers: list[Any] = []

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

        self._name_maps[robot_id] = name_map
        _LOGGER.debug("Updated segment cache for robot %s with %d entries", robot_id, len(name_map))

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
