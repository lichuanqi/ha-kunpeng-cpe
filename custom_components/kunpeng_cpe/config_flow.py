"""配置流：在 HA 界面里添加集成时填写设备地址与登录信息。"""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import KunpengCpeApi, KunpengCpeApiError, create_cpe_session
from .const import (
    CONF_HOST,
    CONF_PORT,
    CONF_USERNAME,
    CONF_SCAN_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN
)

_LOGGER = logging.getLogger(__name__)

SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default="192.168.66.1"): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_USERNAME, default="root"): str,
        vol.Optional(CONF_PASSWORD, default="admin"): str,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): int,
    }
)


class KunpengCpeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """UI配置流"""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            session = create_cpe_session()

            api = KunpengCpeApi(
                user_input[CONF_HOST],
                user_input.get(CONF_PORT),
                user_input.get(CONF_USERNAME),
                user_input.get(CONF_PASSWORD),
                session,
            )
            try:
                await api.login()
                await api.fetch_status()
            except KunpengCpeApiError as err:
                _LOGGER.error("连接鲲鹏 CPE 失败: %s", err)
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=f"鲲鹏 5G CPE ({user_input[CONF_HOST]})",
                    data=user_input,
                )
            finally:
                session.close()

        return self.async_show_form(
            step_id="user",
            data_schema=SCHEMA,
            errors=errors,
        )