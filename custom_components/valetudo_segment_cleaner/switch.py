"""Switch platform for selecting Valetudo segments in UI."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import slugify

from .const import DATA_ENTRIES, DOMAIN
from .mqtt_store import MqttSegmentStore


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up dynamic segment selection switches for a config entry."""
    store: MqttSegmentStore = hass.data[DOMAIN][DATA_ENTRIES][entry.entry_id]
    entities: dict[str, ValetudoSegmentSelectionSwitch] = {}

    def _sync_entities() -> None:
        new_entities: list[ValetudoSegmentSelectionSwitch] = []
        for robot_id in store.discovered_robot_ids:
            catalog = store.get_segment_catalog(robot_id)
            for segment_id, segment_name in catalog.items():
                key = f"{entry.entry_id}:{robot_id}:{segment_id}"
                if key in entities:
                    continue
                entity = ValetudoSegmentSelectionSwitch(entry, store, robot_id, segment_id, segment_name)
                entities[key] = entity
                new_entities.append(entity)

        if new_entities:
            async_add_entities(new_entities)

    _sync_entities()

    def _listener() -> None:
        _sync_entities()

    store.add_listener(_listener)


class ValetudoSegmentSelectionSwitch(SwitchEntity):
    """Switch that marks a discovered segment as selected for cleaning."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:floor-plan"

    def __init__(
        self,
        entry: ConfigEntry,
        store: MqttSegmentStore,
        robot_id: str,
        segment_id: int,
        segment_name: str,
    ) -> None:
        self._entry = entry
        self._store = store
        self._robot_id = robot_id
        self._segment_id = segment_id
        self._segment_name_fallback = segment_name
        self._remove_listener: Callable[[], None] | None = None

        robot_slug = slugify(robot_id)
        segment_slug = slugify(segment_name)
        self._attr_unique_id = (
            f"{entry.entry_id}_{robot_slug}_segment_{segment_id}_{segment_slug}_selected"
        )

    @property
    def name(self) -> str:
        """Return entity name."""
        segment_name = self._store.get_segment_catalog(self._robot_id).get(
            self._segment_id,
            self._segment_name_fallback,
        )
        return f"{self._robot_id} {segment_name} selected"

    @property
    def available(self) -> bool:
        """Return whether segment is still present in discovery."""
        return self._segment_id in self._store.get_segment_catalog(self._robot_id)

    @property
    def is_on(self) -> bool:
        """Return selected state."""
        return self._store.is_segment_selected(self._robot_id, self._segment_id)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional diagnostics attributes."""
        return {
            "entry_id": self._entry.entry_id,
            "robot_id": self._robot_id,
            "segment_id": self._segment_id,
            "segment_name": self._store.get_segment_catalog(self._robot_id).get(
                self._segment_id,
                self._segment_name_fallback,
            ),
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn switch on to mark segment selected."""
        del kwargs
        self._store.set_segment_selected(self._robot_id, self._segment_id, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn switch off to unselect segment."""
        del kwargs
        self._store.set_segment_selected(self._robot_id, self._segment_id, False)

    async def async_added_to_hass(self) -> None:
        """Subscribe to updates."""
        self._remove_listener = self._store.add_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe from updates."""
        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None
