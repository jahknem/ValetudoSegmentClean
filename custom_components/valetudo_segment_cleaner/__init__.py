"""Valetudo Segment Cleaner custom integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_COMMAND,
    ATTR_ENTRY_ID,
    ATTR_EXECUTE,
    ATTR_ROBOT_ID,
    ATTR_SEGMENT_NAMES,
    ATTR_STOP_AND_DOCK_AFTER_START,
    ATTR_VACUUM_ENTITY_ID,
    CONF_DEFAULT_ROBOT_ID,
    CONF_DEFAULT_VACUUM_ENTITY_ID,
    DATA_ENTRIES,
    DATA_SERVICES_REGISTERED,
    DEFAULT_SEGMENT_COMMAND,
    DOMAIN,
    EVENT_SEGMENT_CLEAN_REQUEST,
    SERVICE_CLEAN_SEGMENTS_BY_NAME,
    SERVICE_CLEAN_SELECTED_SEGMENTS,
    SERVICE_REFRESH_SEGMENTS,
)
from .helpers import resolve_segment_ids
from .mqtt_store import MqttSegmentStore

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SWITCH, Platform.BUTTON]

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_DEFAULT_VACUUM_ENTITY_ID): cv.entity_id,
                vol.Optional(CONF_DEFAULT_ROBOT_ID): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


def _domain_data(hass: HomeAssistant) -> dict[str, Any]:
    data = hass.data.setdefault(DOMAIN, {})
    data.setdefault(DATA_ENTRIES, {})
    data.setdefault(DATA_SERVICES_REGISTERED, False)
    return data


def _entry_config(entry: ConfigEntry) -> dict[str, Any]:
    merged = {
        CONF_DEFAULT_VACUUM_ENTITY_ID: entry.data.get(CONF_DEFAULT_VACUUM_ENTITY_ID),
        CONF_DEFAULT_ROBOT_ID: entry.data.get(CONF_DEFAULT_ROBOT_ID),
    }
    merged.update(entry.options)
    return merged


def _resolve_store_for_call(
    hass: HomeAssistant,
    call: ServiceCall,
) -> tuple[str, MqttSegmentStore]:
    entries: dict[str, MqttSegmentStore] = _domain_data(hass)[DATA_ENTRIES]
    requested_entry_id = call.data.get(ATTR_ENTRY_ID)

    if requested_entry_id:
        store = entries.get(requested_entry_id)
        if store is None:
            raise HomeAssistantError(f"Unknown entry_id '{requested_entry_id}'")
        return requested_entry_id, store

    if not entries:
        raise HomeAssistantError("No active integration entries are loaded")

    if len(entries) == 1:
        entry_id, store = next(iter(entries.items()))
        return entry_id, store

    raise HomeAssistantError(
        "Multiple integration entries loaded. Please provide entry_id in service data."
    )


async def _register_services(hass: HomeAssistant) -> None:
    async def _async_execute_clean(
        *,
        entry_id: str,
        store: MqttSegmentStore,
        vacuum_entity_id: str,
        robot_id: str,
        segment_ids: list[int],
        segment_names: list[str],
        execute: bool,
        command: str,
        stop_and_dock_after_start: bool,
    ) -> None:
        hass.bus.async_fire(
            EVENT_SEGMENT_CLEAN_REQUEST,
            {
                "entry_id": entry_id,
                "vacuum_entity_id": vacuum_entity_id,
                "robot_id": robot_id,
                "segment_names": segment_names,
                "segment_ids": segment_ids,
                "execute": execute,
                "command": command,
            },
        )

        _LOGGER.info(
            "Entry %s segment clean request for %s robot=%s names=%s ids=%s execute=%s",
            entry_id,
            vacuum_entity_id,
            robot_id,
            segment_names,
            segment_ids,
            execute,
        )

        if not execute:
            return

        await store.async_publish_segment_clean(robot_id, segment_ids)

        if stop_and_dock_after_start:
            # Safety behavior for testing and validation.
            await asyncio.sleep(1.0)
            await hass.services.async_call(
                "vacuum",
                "stop",
                {"entity_id": vacuum_entity_id},
                blocking=True,
            )
            await hass.services.async_call(
                "vacuum",
                "return_to_base",
                {"entity_id": vacuum_entity_id},
                blocking=True,
            )

    domain_data = _domain_data(hass)
    if domain_data[DATA_SERVICES_REGISTERED]:
        return

    async def _service_refresh_segments(call: ServiceCall) -> None:
        entry_id, store = _resolve_store_for_call(hass, call)
        _LOGGER.info(
            "Entry %s discovered robot IDs from MQTT: %s",
            entry_id,
            store.discovered_robot_ids,
        )

    async def _service_clean_segments_by_name(call: ServiceCall) -> None:
        entry_id, store = _resolve_store_for_call(hass, call)

        requested_names: list[str] = call.data[ATTR_SEGMENT_NAMES]
        vacuum_entity_id: str | None = (
            call.data.get(ATTR_VACUUM_ENTITY_ID) or store.default_vacuum_entity_id
        )
        preferred_robot_id: str | None = call.data.get(ATTR_ROBOT_ID) or store.default_robot_id

        if not vacuum_entity_id:
            raise HomeAssistantError(
                "vacuum_entity_id is required when no default_vacuum_entity_id is configured"
            )

        execute: bool = call.data.get(ATTR_EXECUTE, False)
        command: str = call.data.get(ATTR_COMMAND, DEFAULT_SEGMENT_COMMAND)
        stop_and_dock_after_start: bool = call.data.get(ATTR_STOP_AND_DOCK_AFTER_START, True)

        selected_robot_id = store.resolve_robot_id(preferred_robot_id)
        name_to_id_map: dict[str, int] = store.get_name_map(selected_robot_id)
        resolved_ids, unresolved_names = resolve_segment_ids(requested_names, name_to_id_map)

        if unresolved_names:
            raise HomeAssistantError("Unknown segment names: " + ", ".join(unresolved_names))

        if not resolved_ids:
            raise HomeAssistantError("No valid segment IDs resolved from provided names")

        if command != DEFAULT_SEGMENT_COMMAND:
            _LOGGER.warning(
                "Service field 'command' is informational in MQTT mode and is not sent; "
                "requested command was '%s'",
                command,
            )

        await _async_execute_clean(
            entry_id=entry_id,
            store=store,
            vacuum_entity_id=vacuum_entity_id,
            robot_id=selected_robot_id,
            segment_ids=resolved_ids,
            segment_names=requested_names,
            execute=execute,
            command=command,
            stop_and_dock_after_start=stop_and_dock_after_start,
        )

    async def _service_clean_selected_segments(call: ServiceCall) -> None:
        entry_id, store = _resolve_store_for_call(hass, call)

        vacuum_entity_id: str | None = (
            call.data.get(ATTR_VACUUM_ENTITY_ID) or store.default_vacuum_entity_id
        )
        preferred_robot_id: str | None = call.data.get(ATTR_ROBOT_ID) or store.default_robot_id

        if not vacuum_entity_id:
            raise HomeAssistantError(
                "vacuum_entity_id is required when no default_vacuum_entity_id is configured"
            )

        execute: bool = call.data.get(ATTR_EXECUTE, True)
        command: str = call.data.get(ATTR_COMMAND, DEFAULT_SEGMENT_COMMAND)
        stop_and_dock_after_start: bool = call.data.get(ATTR_STOP_AND_DOCK_AFTER_START, True)

        if command != DEFAULT_SEGMENT_COMMAND:
            _LOGGER.warning(
                "Service field 'command' is informational in MQTT mode and is not sent; "
                "requested command was '%s'",
                command,
            )

        selected_robot_id, segment_ids, segment_names = store.resolve_selected_segments(
            preferred_robot_id
        )

        await _async_execute_clean(
            entry_id=entry_id,
            store=store,
            vacuum_entity_id=vacuum_entity_id,
            robot_id=selected_robot_id,
            segment_ids=segment_ids,
            segment_names=segment_names,
            execute=execute,
            command=command,
            stop_and_dock_after_start=stop_and_dock_after_start,
        )

    refresh_service_schema = vol.Schema(
        {
            vol.Optional(ATTR_ENTRY_ID): cv.string,
        }
    )

    clean_service_schema = vol.Schema(
        {
            vol.Optional(ATTR_ENTRY_ID): cv.string,
            vol.Optional(ATTR_VACUUM_ENTITY_ID): cv.entity_id,
            vol.Required(ATTR_SEGMENT_NAMES): vol.All(cv.ensure_list, [cv.string]),
            vol.Optional(ATTR_ROBOT_ID): cv.string,
            vol.Optional(ATTR_EXECUTE, default=False): cv.boolean,
            vol.Optional(ATTR_COMMAND, default=DEFAULT_SEGMENT_COMMAND): cv.string,
            vol.Optional(ATTR_STOP_AND_DOCK_AFTER_START, default=True): cv.boolean,
        }
    )

    clean_selected_service_schema = vol.Schema(
        {
            vol.Optional(ATTR_ENTRY_ID): cv.string,
            vol.Optional(ATTR_VACUUM_ENTITY_ID): cv.entity_id,
            vol.Optional(ATTR_ROBOT_ID): cv.string,
            vol.Optional(ATTR_EXECUTE, default=True): cv.boolean,
            vol.Optional(ATTR_COMMAND, default=DEFAULT_SEGMENT_COMMAND): cv.string,
            vol.Optional(ATTR_STOP_AND_DOCK_AFTER_START, default=True): cv.boolean,
        }
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH_SEGMENTS,
        _service_refresh_segments,
        schema=refresh_service_schema,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAN_SEGMENTS_BY_NAME,
        _service_clean_segments_by_name,
        schema=clean_service_schema,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAN_SELECTED_SEGMENTS,
        _service_clean_selected_segments,
        schema=clean_selected_service_schema,
    )

    domain_data[DATA_SERVICES_REGISTERED] = True


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up integration and import YAML config if present."""
    _domain_data(hass)
    await _register_services(hass)

    domain_config = config.get(DOMAIN)
    if domain_config:
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": "import"},
                data=dict(domain_config),
            )
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up integration from a config entry."""
    await _register_services(hass)

    mqtt_store = MqttSegmentStore(hass, _entry_config(entry))
    await mqtt_store.async_start()

    _domain_data(hass)[DATA_ENTRIES][entry.entry_id] = mqtt_store

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.info("Valetudo Segment Cleaner entry %s initialized", entry.entry_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    entries: dict[str, MqttSegmentStore] = _domain_data(hass)[DATA_ENTRIES]
    mqtt_store = entries.pop(entry.entry_id, None)
    if mqtt_store is not None:
        await mqtt_store.async_stop()

    if not entries and _domain_data(hass).get(DATA_SERVICES_REGISTERED):
        hass.services.async_remove(DOMAIN, SERVICE_REFRESH_SEGMENTS)
        hass.services.async_remove(DOMAIN, SERVICE_CLEAN_SEGMENTS_BY_NAME)
        hass.services.async_remove(DOMAIN, SERVICE_CLEAN_SELECTED_SEGMENTS)
        _domain_data(hass)[DATA_SERVICES_REGISTERED] = False

    _LOGGER.info("Valetudo Segment Cleaner entry %s unloaded", entry.entry_id)
    return True
