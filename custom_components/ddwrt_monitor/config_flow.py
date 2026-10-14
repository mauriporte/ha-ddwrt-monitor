from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME

from . import DOMAIN
from .api import AuthError, ConnectError, DdwrtClient

SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME, default="admin"): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_PORT, default=80): int,
    }
)


class DdwrtConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            client = DdwrtClient(user_input[CONF_HOST], user_input[CONF_USERNAME], user_input[CONF_PASSWORD], user_input[CONF_PORT])
            try:
                data = await client.fetch()
            except AuthError:
                errors["base"] = "invalid_auth"
            except ConnectError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id((data.router.get("lan_mac") or user_input[CONF_HOST]).lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=f"DD-WRT {user_input[CONF_HOST]}", data=user_input)
        return self.async_show_form(step_id="user", data_schema=SCHEMA, errors=errors)
