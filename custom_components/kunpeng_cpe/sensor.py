from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfDataRate,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import KunpengCpeCoordinator

# 协调器统一管理更新频率，平台层不再并行发起请求
PARALLEL_UPDATES = 0


def _as_int(value: Any) -> int | None:
    """安全转为 int；设备常把数字以字符串返回。"""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    """安全转为 float；设备常把数字以字符串返回。"""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True, kw_only=True)
class KunpengCpeSensorEntityDescription(SensorEntityDescription):
    """扩展 SensorEntityDescription，加入从协调器数据取值的方法。"""

    value_fn: Callable[[dict[str, Any]], Any]


SENSORS: tuple[KunpengCpeSensorEntityDescription, ...] = (
    # ---- 温度 ----
    KunpengCpeSensorEntityDescription(
        key="device_temp",
        translation_key="device_temp",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
        value_fn=lambda data: _as_float(data.get("device_temp")),
    ),
    KunpengCpeSensorEntityDescription(
        key="module_temp",
        translation_key="module_temp",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-high",
        value_fn=lambda data: _as_float(data.get("module_temp")),
    ),
    KunpengCpeSensorEntityDescription(
        key="wifi_temp",
        translation_key="wifi_temp",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-low",
        entity_registry_enabled_default=False,
        value_fn=lambda data: _as_float(data.get("wifi_temp")),
    ),
    # ---- 资源占用 ----
    KunpengCpeSensorEntityDescription(
        key="cpu_usage",
        translation_key="cpu_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:cpu-64-bit",
        value_fn=lambda data: _as_float(data.get("cpu_usage")),
    ),
    KunpengCpeSensorEntityDescription(
        key="memory_usage",
        translation_key="memory_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:memory",
        value_fn=lambda data: _as_float(data.get("memory_usage")),
    ),
    # ---- 信号质量 ----
    KunpengCpeSensorEntityDescription(
        key="rsrp",
        translation_key="rsrp",
        native_unit_of_measurement="dBm",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:signal-cellular-3",
        value_fn=lambda data: _as_float(data.get("rsrp")),
    ),
    KunpengCpeSensorEntityDescription(
        key="rsrq",
        translation_key="rsrq",
        native_unit_of_measurement="dB",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:signal-cellular-2",
        value_fn=lambda data: _as_float(data.get("rsrq")),
    ),
    KunpengCpeSensorEntityDescription(
        key="sinr",
        translation_key="sinr",
        native_unit_of_measurement="dB",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:signal-cellular-1",
        value_fn=lambda data: _as_float(data.get("sinr")),
    ),
    # ---- 网络信息（文本）----
    KunpengCpeSensorEntityDescription(
        key="band",
        translation_key="band",
        icon="mdi:radio-tower",
        value_fn=lambda data: data.get("band"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    KunpengCpeSensorEntityDescription(
        key="cell_id",
        translation_key="cell_id",
        icon="mdi:cellphone-arrow-down",
        value_fn=lambda data: data.get("cell_id"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    KunpengCpeSensorEntityDescription(
        key="mode",
        translation_key="mode",
        icon="mdi:access-point-network",
        value_fn=lambda data: data.get("mode"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    KunpengCpeSensorEntityDescription(
        key="isp",
        translation_key="isp",
        icon="mdi:sim",
        value_fn=lambda data: data.get("isp"),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # ---- 终端与运行时长 ----
    KunpengCpeSensorEntityDescription(
        key="connected_devices",
        translation_key="connected_devices",
        native_unit_of_measurement="台",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:devices",
        value_fn=lambda data: _as_int(data.get("connected_devices")),
    ),
    KunpengCpeSensorEntityDescription(
        key="uptime",
        translation_key="uptime",
        native_unit_of_measurement="s",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:timer-outline",
        value_fn=lambda data: _as_int(data.get("uptime")),
    ),
    # ---- 诊断 ----
    KunpengCpeSensorEntityDescription(
        key="firmware_version",
        translation_key="firmware_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:information-outline",
        value_fn=lambda data: data.get("firmware_version"),
    ),
    KunpengCpeSensorEntityDescription(
        key="imei",
        translation_key="imei",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:identifier",
        value_fn=lambda data: data.get("imei"),
    ),
    KunpengCpeSensorEntityDescription(
        key="iccid",
        translation_key="iccid",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:card-account-details",
        value_fn=lambda data: data.get("iccid"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """根据 SENSORS 描述创建传感器实体。"""
    coordinator: KunpengCpeCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        KunpengCpeSensor(coordinator, entry, description)
        for description in SENSORS
    )


class KunpengCpeSensor(CoordinatorEntity[KunpengCpeCoordinator], SensorEntity):
    """鲲鹏 5G CPE 传感器实体。"""

    entity_description: KunpengCpeSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: KunpengCpeCoordinator,
        entry: ConfigEntry,
        description: KunpengCpeSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Kunpeng",
            model="5G CPE",
            configuration_url=f"http://{entry.data['host']}",
        )

    @property
    def native_value(self) -> Any:
        """从协调器缓存的数据中取出该实体的值。"""
        return self.entity_description.value_fn(self.coordinator.data)