"""Valetudo Segment Cleaner custom integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_COMMAND,
    ATTR_EXECUTE,
    ATTR_ROBOT_ID,
    ATTR_SEGMENT_NAMES,
    ATTR_STOP_AND_DOCK_AFTER_START,
    ATTR_VACUUM_ENTITY_ID,
    CONF_MQTT_COMMAND_TOPIC_SUFFIX,
    CONF_MQTT_SEGMENT_TOPIC_SUFFIX,
    CONF_MQTT_TOPIC_PREFIX,
    DEFAULT_COMMAND_TOPIC_SUFFIX,
    DEFAULT_MQTT_TOPIC_PREFIX,
    DEFAULT_SEGMENT_TOPIC_SUFFIX,
    DEFAULT_SEGMENT_COMMAND,
    DOMAIN,
    EVENT_SEGMENT_CLEAN_REQUEST,
    SERVICE_CLEAN_SEGMENTS_BY_NAME,
    SERVICE_REFRESH_SEGMENTS,
)
from .helpers import resolve_segment_ids
from .mqtt_store import MqttSegmentStore

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = []

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_MQTT_TOPIC_PREFIX, default=DEFAULT_MQTT_TOPIC_PREFIX): cv.string,
                vol.Optional(
                    CONF_MQTT_SEGMENT_TOPIC_SUFFIX,
                    default=DEFAULT_SEGMENT_TOPIC_SUFFIX,
                ): cv.string,
                vol.Optional(
                    CONF_MQTT_COMMAND_TOPIC_SUFFIX,
                    default=DEFAULT_COMMAND_TOPIC_SUFFIX,
                ): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up integration from YAML config."""
    domain_config: dict[str, Any] = config.get(DOMAIN, {})

    mqtt_store = MqttSegmentStore(
        hass,
        {
            CONF_MQTT_TOPIC_PREFIX: domain_config.get(
                CONF_MQTT_TOPIC_PREFIX,
                DEFAULT_MQTT_TOPIC_PREFIX,
            ),
            CONF_MQTT_SEGMENT_TOPIC_SUFFIX: domain_config.get(
                CONF_MQTT_SEGMENT_TOPIC_SUFFIX,
                DEFAULT_SEGMENT_TOPIC_SUFFIX,
            ),
            CONF_MQTT_COMMAND_TOPIC_SUFFIX: domain_config.get(
                CONF_MQTT_COMMAND_TOPIC_SUFFIX,
                DEFAULT_COMMAND_TOPIC_SUFFIX,
            ),
        },
    )

    await mqtt_store.async_start()
    hass.data.setdefault(DOMAIN, {})["mqtt_store"] = mqtt_store

    async def _service_refresh_segments(call: ServiceCall) -> None:
        del call
        _LOGGER.info(
            "Known Valetudo robot IDs from MQTT discovery: %s",
            mqtt_store.discovered_robot_ids,
        )

    async def _service_clean_segments_by_name(call: ServiceCall) -> None:
        vacuum_entity_id: str = call.data[ATTR_VACUUM_ENTITY_ID]
        requested_names: list[str] = call.data[ATTR_SEGMENT_NAMES]
        robot_id: str | None = call.data.get(ATTR_ROBOT_ID)
        execute: bool = call.data.get(ATTR_EXECUTE, False)
        command: str = call.data.get(ATTR_COMMAND, DEFAULT_SEGMENT_COMMAND)
        stop_and_dock_after_start: bool = call.data.get(ATTR_STOP_AND_DOCK_AFTER_START, True)

        selected_robot_id = mqtt_store.resolve_robot_id(robot_id)
        name_to_id_map: dict[str, int] = mqtt_store.get_name_map(selected_robot_id)

        resolved_ids, unresolved_names = resolve_segment_ids(requested_names, name_to_id_map)

        if unresolved_names:
            raise HomeAssistantError(
                "Unknown segment names: " + ", ".join(unresolved_names)
            )

        if not resolved_ids:
            raise HomeAssistantError("No valid segment IDs resolved from provided names")

        if command != DEFAULT_SEGMENT_COMMAND:
            _LOGGER.warning(
                "Service field 'command' is currently informational in MQTT mode and is not sent "
                "to Valetudo; requested command was '%s'",
                command,
            )

        hass.bus.async_fire(
            EVENT_SEGMENT_CLEAN_REQUEST,
            {
                "vacuum_entity_id": vacuum_entity_id,
                "robot_id": selected_robot_id,
                "segment_names": requested_names,
                "segment_ids": resolved_ids,
                "execute": execute,
                "command": command,
            },
        )

        _LOGGER.info(
            "Segment clean request for %s names=%s ids=%s execute=%s",
            vacuum_entity_id,
            requested_names,
            resolved_ids,
            execute,
        )

        if not execute:
            return

        await mqtt_store.async_publish_segment_clean(selected_robot_id, resolved_ids)

        if stop_and_dock_after_start:
            # Safety behavior requested by user while validating automations.
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

    clean_service_schema = vol.Schema(
        {
            vol.Required(ATTR_VACUUM_ENTITY_ID): cv.entity_id,
            vol.Required(ATTR_SEGMENT_NAMES): vol.All(cv.ensure_list, [cv.string]),
            vol.Optional(ATTR_ROBOT_ID): cv.string,
            vol.Optional(ATTR_EXECUTE, default=False): cv.boolean,
            vol.Optional(ATTR_COMMAND, default=DEFAULT_SEGMENT_COMMAND): cv.string,
            vol.Optional(ATTR_STOP_AND_DOCK_AFTER_START, default=True): cv.boolean,
        }
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH_SEGMENTS,
        _service_refresh_segments,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAN_SEGMENTS_BY_NAME,
        _service_clean_segments_by_name,
        schema=clean_service_schema,
    )

    _LOGGER.info("Valetudo Segment Cleaner initialized")
    return True


async def async_unload_entry(hass: HomeAssistant, _entry: Any) -> bool:
    """Unload config entry (kept for compatibility if later migrated)."""
    mqtt_store = hass.data.get(DOMAIN, {}).get("mqtt_store")
    if mqtt_store is not None:
        await mqtt_store.async_stop()

    hass.services.async_remove(DOMAIN, SERVICE_REFRESH_SEGMENTS)
    hass.services.async_remove(DOMAIN, SERVICE_CLEAN_SEGMENTS_BY_NAME)
    hass.data.pop(DOMAIN, None)
    return True
