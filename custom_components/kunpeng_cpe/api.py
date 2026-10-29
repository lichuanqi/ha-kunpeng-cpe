"""鲲鹏C2000pro 5G CPE API。

接口1 登录：
POST http://<设备IP>/cgi-bin/luci
表单 luci_username=<用户名> & luci_password=<密码> & luci_channel=simple
成功后服务端下发 sysauth cookie, aiohttp 的 session 会自动保存并在后续请求携带。

接口2 状态数据：
GET http://<设备IP>/cgi-bin/luci/nradio/status/runtime/wan,cpe_4
请求头需带 X-Requested-With: XMLHttpRequest
返回JSON: {"result": {"global": {...}, "cpe": [{...}], "terminal_all": {...}, ...}}
"""

from __future__ import annotations

import logging
import re
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

LOGIN_PATH = "/cgi-bin/luci"
STATUS_PATH = "/cgi-bin/luci/nradio/status/runtime/wan,cpe_4"

# 单个请求 10 秒超时，避免配置流长时间卡住
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=10)


class KunpengCpeApiError(Exception):
    """设备 API 请求失败（网络错误、鉴权失败、返回格式异常等）。"""


def _to_int(value: Any) -> int | None:
    """安全转为 int；设备常把数字以字符串返回（如 download: "57751418752"）。"""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    """安全转为 float；rsrp / rsrq / sinr / model_temp 均以字符串返回。"""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def create_cpe_session() -> aiohttp.ClientSession:
    """创建集成专用的 HTTP 会话。

    aiohttp 默认的 cookie 罐会拒绝来自 IP 地址主机的 cookie
    CPE 通常通过 192.168.x.x 访问，导致登录 cookie 被丢弃、状态接口 403。
    这里用 unsafe=True 的 cookie 罐，允许接收 IP 主机的 cookie。
    """
    return aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True))


class KunpengCpeApi:
    """鲲鹏 CPE 的 LuCI HTTP API 客户端。"""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
    ) -> None:
        # 容错
        host = re.sub(r"^https?://", "", host).rstrip("/")
        if ":" in host and port in (80, None) and not host.startswith("["):
            maybe_host, _, maybe_port = host.rpartition(":")
            if maybe_port.isdigit():
                host, port = maybe_host, int(maybe_port)
        self._base_url = (
            f"http://{host}:{port}" if port not in (80, None) else f"http://{host}"
        )
        self._username = username
        self._password = password
        self._session = session

    async def _get_json(
        self, path: str, headers: dict[str, str] | None = None
    ) -> Any:
        """GET 并解析 JSON"""
        url = f"{self._base_url}{path}"
        try:
            async with self._session.get(
                url, headers=headers, timeout=REQUEST_TIMEOUT
            ) as resp:
                resp.raise_for_status()
                return await resp.json()
        except aiohttp.ClientError as err:
            raise KunpengCpeApiError(f"GET {path} 失败: {err}") from err
        except ValueError as err:
            raise KunpengCpeApiError(
                f"GET {path} 返回的不是 JSON（可能是会话过期被跳转到登录页）: {err}"
            ) from err

    async def login(self) -> None:
        """获取sysauth cookie。"""
        data = {
            "luci_username": self._username,
            "luci_password": self._password,
            "luci_channel": "simple",
        }

        try:
            async with self._session.post(
                f"{self._base_url}{LOGIN_PATH}", data=data, timeout=REQUEST_TIMEOUT
            ) as resp:
                resp.raise_for_status()
        except aiohttp.ClientError as err:
            raise KunpengCpeApiError(f"登录失败: {err}") from err

        # 用状态接口的 URL 校验 cookie
        cookies = self._session.cookie_jar.filter_cookies(
            f"{self._base_url}{STATUS_PATH}"
        )
        if "sysauth" not in cookies:
            raise KunpengCpeApiError(
                f"登录失败：未获得 sysauth cookie，"
                f"当前 filter 结果={dict(cookies)}，"
                f"cookie jar 全量={dict(self._session.cookie_jar)}。"
                f"请检查用户名/密码，或固件登录方式已变化，"
                f"用 scripts/test_kunpeng_api.py 复现）"
            )
        _LOGGER.debug("登录成功，已取得 sysauth cookie")

    async def close(self) -> None:
        """关闭集成专用会话 卸载集成时调用"""
        await self._session.close()

    async def fetch_status(self) -> dict[str, Any]:
        """拉取设备状态"""
        payload = await self._get_json(
            STATUS_PATH, headers={"X-Requested-With": "XMLHttpRequest"}
        )

        result = (payload or {}).get("result") or {}
        global_info = result.get("global") or {}

        # cpe 是数组；设备异常时可能为空
        cpe_list = result.get("cpe") or []
        cpe = cpe_list[0] if cpe_list else {}

        terminal_all = result.get("terminal_all") or {}

        data: dict[str, Any] = {}

        # ---- 温度 ----
        data["device_temp"] = _to_float(global_info.get("device_temp"))
        data["module_temp"] = _to_float(cpe.get("model_temp"))

        # ---- 资源占用 ----
        data["cpu_usage"] = _to_float(global_info.get("cpu_percent"))
        data["memory_usage"] = _to_float(global_info.get("mem_percent"))

        # ---- 信号质量 字符串 ----
        data["rsrp"] = _to_float(cpe.get("rsrp"))
        data["rsrq"] = _to_float(cpe.get("rsrq"))
        data["sinr"] = _to_float(cpe.get("sinr"))

        # ---- 网络信息 文本 ----
        data["band"] = cpe.get("band")  # "28"
        data["cell_id"] = cpe.get("cell")  # "15681D02B"
        data["mode"] = cpe.get("mode")  # "NR SA"
        data["isp"] = cpe.get("isp")  # "China Mobile"

        # ---- 诊断信息 ----
        data["firmware_version"] = cpe.get("revision")
        data["imei"] = cpe.get("imei")
        data["iccid"] = cpe.get("iccid")

        # ---- 接入终端数（terminal_all.count 是 int）----
        data["connected_devices"] = _to_int(terminal_all.get("count"))

        # ---- 运行时长（global.uptime 是 int，单位秒）----
        data["uptime"] = _to_int(global_info.get("uptime"))

        return data