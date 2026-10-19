from __future__ import annotations

import logging
from datetime import timedelta

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import KunpengCpeApi, KunpengCpeApiError, create_cpe_session
from .const import (
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class KunpengCpeCoordinator(DataUpdateCoordinator[dict]):
    """调度 api.py 轮询"""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._entry = entry
        self._session: aiohttp.ClientSession | None = None
        self._api: KunpengCpeApi | None = None

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

    async def async_setup(self) -> None:
        """创建HTTP会话并完成首次登录。"""
        self._session = create_cpe_session()
        self._api = KunpengCpeApi(
            host=self._entry.data[CONF_HOST],
            port=self._entry.data.get(CONF_PORT, DEFAULT_PORT),
            username=self._entry.data[CONF_USERNAME],
            password=self._entry.data[CONF_PASSWORD],
            session=self._session,
        )

        interval = self._entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        self.update_interval = timedelta(seconds=interval)

        try:
            await self._api.login()
        except KunpengCpeApiError as err:
            await self._session.close()
            self._session = None
            self._api = None
            raise ConfigEntryNotReady(str(err)) from err

    async def _async_update_data(self) -> dict:
        """轮询调用 api.fetch_status()

        CPE 的 LuCI 会话经常在空闲后失效，表现为状态接口返回登录页 HTML。
        这里在失败时尝试重新登录一次，仍失败才向 HA 报 UpdateFailed，
        避免一个偶发的会话过期就让实体显示为不可用。
        """
        if self._api is None:
            raise UpdateFailed("API 客户端尚未初始化")

        try:
            return await self._api.fetch_status()
        except KunpengCpeApiError as err:
            _LOGGER.debug("状态请求失败，尝试重新登录后重试: %s", err)

        try:
            await self._api.login()
            return await self._api.fetch_status()
        except KunpengCpeApiError as err:
            raise UpdateFailed(f"获取数据失败: {err}") from err

    async def async_close(self) -> None:
        """卸载集成时关闭会话"""
        if self._api is not None:
            await self._api.close()
            self._api = None
        elif self._session is not None:
            await self._session.close()
        self._session = None