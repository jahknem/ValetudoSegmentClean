"""Button platform to trigger cleaning selected segments per robot."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import slugify

from .const import ATTR_ENTRY_ID, ATTR_ROBOT_ID, DATA_ENTRIES, DOMAIN, SERVICE_CLEAN_SELECTED_SEGMENTS
from .mqtt_store import MqttSegmentStore


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up dynamic clean-selected buttons for each discovered robot."""
    store: MqttSegmentStore = hass.data[DOMAIN][DATA_ENTRIES][entry.entry_id]
    entities: dict[str, ValetudoCleanSelectedButton] = {}

    def _sync_entities() -> None:
        new_entities: list[ValetudoCleanSelectedButton] = []
        for robot_id in store.discovered_robot_ids:
            key = f"{entry.entry_id}:{robot_id}"
            if key in entities:
                continue
            entity = ValetudoCleanSelectedButton(hass, entry, store, robot_id)
            entities[key] = entity
            new_entities.append(entity)

        if new_entities:
            async_add_entities(new_entities)

    _sync_entities()

    def _listener() -> None:
        _sync_entities()

    store.add_listener(_listener)


class ValetudoCleanSelectedButton(ButtonEntity):
    """Button entity to clean currently selected segment switches for a robot."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:robot-vacuum"

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        store: MqttSegmentStore,
        robot_id: str,
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._store = store
        self._robot_id = robot_id
        self._remove_listener: Callable[[], None] | None = None
        self._attr_unique_id = f"{entry.entry_id}_{slugify(robot_id)}_clean_selected"

    @property
    def name(self) -> str:
        """Return entity name."""
        return f"{self._robot_id} clean selected segments"

    @property
    def available(self) -> bool:
        """Button available when robot is discovered."""
        return self._robot_id in self._store.discovered_robot_ids

    async def async_press(self) -> None:
        """Run clean_selected_segments service for this robot."""
        await self._hass.services.async_call(
            DOMAIN,
            SERVICE_CLEAN_SELECTED_SEGMENTS,
            {
                ATTR_ENTRY_ID: self._entry.entry_id,
                ATTR_ROBOT_ID: self._robot_id,
                "execute": True,
            },
            blocking=True,
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to updates for attributes and availability."""
        self._remove_listener = self._store.add_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe from updates."""
        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None
