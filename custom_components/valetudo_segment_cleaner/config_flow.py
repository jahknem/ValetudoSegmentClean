"""Config flow for Valetudo Segment Cleaner."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    CONF_DEFAULT_ROBOT_ID,
    CONF_DEFAULT_VACUUM_ENTITY_ID,
    DEFAULT_CONFIG_TITLE,
    DOMAIN,
)


def _flow_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Build user/options flow schema."""
    return vol.Schema(
        {
            vol.Optional(
                CONF_DEFAULT_VACUUM_ENTITY_ID,
                default=defaults.get(CONF_DEFAULT_VACUUM_ENTITY_ID, ""),
            ): str,
            vol.Optional(
                CONF_DEFAULT_ROBOT_ID,
                default=defaults.get(CONF_DEFAULT_ROBOT_ID, ""),
            ): str,
        }
    )


class ValetudoSegmentCleanerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            data: dict[str, Any] = {}

            default_vacuum = user_input.get(CONF_DEFAULT_VACUUM_ENTITY_ID, "").strip()
            default_robot = user_input.get(CONF_DEFAULT_ROBOT_ID, "").strip()

            if default_vacuum:
                data[CONF_DEFAULT_VACUUM_ENTITY_ID] = default_vacuum
            if default_robot:
                data[CONF_DEFAULT_ROBOT_ID] = default_robot

            return self.async_create_entry(title=DEFAULT_CONFIG_TITLE, data=data)

        return self.async_show_form(step_id="user", data_schema=_flow_schema({}))

    async def async_step_import(self, import_input: dict[str, Any]):
        """Import configuration from YAML."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        data: dict[str, Any] = {}

        default_vacuum = import_input.get(CONF_DEFAULT_VACUUM_ENTITY_ID)
        default_robot = import_input.get(CONF_DEFAULT_ROBOT_ID)
        if isinstance(default_vacuum, str) and default_vacuum:
            data[CONF_DEFAULT_VACUUM_ENTITY_ID] = default_vacuum
        if isinstance(default_robot, str) and default_robot:
            data[CONF_DEFAULT_ROBOT_ID] = default_robot

        return self.async_create_entry(title=DEFAULT_CONFIG_TITLE, data=data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Return options flow."""
        return ValetudoSegmentCleanerOptionsFlow(config_entry)


class ValetudoSegmentCleanerOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Manage integration options."""
        if user_input is not None:
            options: dict[str, Any] = {}

            default_vacuum = user_input.get(CONF_DEFAULT_VACUUM_ENTITY_ID, "").strip()
            default_robot = user_input.get(CONF_DEFAULT_ROBOT_ID, "").strip()

            if default_vacuum:
                options[CONF_DEFAULT_VACUUM_ENTITY_ID] = default_vacuum
            if default_robot:
                options[CONF_DEFAULT_ROBOT_ID] = default_robot

            return self.async_create_entry(title="", data=options)

        defaults = dict(self._entry.data)
        defaults.update(self._entry.options)
        return self.async_show_form(step_id="init", data_schema=_flow_schema(defaults))
