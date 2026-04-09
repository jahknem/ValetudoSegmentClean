"""Sensor platform for Valetudo Segment Cleaner."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DATA_ENTRIES, DEFAULT_MQTT_TOPIC_PREFIX, DOMAIN
from .mqtt_store import MqttSegmentStore


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensor entities from config entry."""
    store: MqttSegmentStore = hass.data[DOMAIN][DATA_ENTRIES][entry.entry_id]
    async_add_entities([ValetudoDiscoveryOverviewSensor(entry, store)])


class ValetudoDiscoveryOverviewSensor(SensorEntity):
    """Show discovery overview for dashboard and diagnostics."""

    _attr_has_entity_name = True
    _attr_name = "Discovery Overview"
    _attr_icon = "mdi:robot-vacuum"

    def __init__(self, entry: ConfigEntry, store: MqttSegmentStore) -> None:
        self._entry = entry
        self._store = store
        self._remove_listener: Callable[[], None] | None = None
        self._attr_unique_id = f"{entry.entry_id}_discovery_overview"

    @property
    def native_value(self) -> int:
        """Return count of discovered robots."""
        return len(self._store.discovered_robot_ids)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return details for UI diagnostics and dashboard cards."""
        snapshot = self._store.get_discovery_snapshot()
        return {
            "entry_id": self._entry.entry_id,
            "mqtt_topic_prefix": DEFAULT_MQTT_TOPIC_PREFIX,
            "default_robot_id": snapshot.get("default_robot_id"),
            "default_vacuum_entity_id": snapshot.get("default_vacuum_entity_id"),
            "discovered_robot_ids": self._store.discovered_robot_ids,
            "robots": snapshot.get("robots", {}),
        }

    async def async_added_to_hass(self) -> None:
        """Subscribe to MQTT store updates."""
        self._remove_listener = self._store.add_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe from MQTT store updates."""
        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None
