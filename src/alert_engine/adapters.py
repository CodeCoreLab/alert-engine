"""
alert-engine — 多源采集适配器接口

吸收 alertmanager/n9e 的 adapter 模式，支持：
  - ZabbixAdapter
  - N9eAdapter
  - InfluxDBAdapter
  - GenericJSONAdapter

使用方式:
    engine = AlertEngine()
    engine.register_adapter("zabbix", ZabbixAdapter(config))
    engine.run()
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from alert_engine.types import Alert


class BaseAdapter(ABC):
    """采集适配器基类"""

    @abstractmethod
    def fetch(self, since: float | None = None) -> list[Alert]:
        """拉取告警列表"""
        raise NotImplementedError

    @abstractmethod
    def health(self) -> dict[str, Any]:
        """健康检查"""
        raise NotImplementedError


class ZabbixAdapter(BaseAdapter):
    """Zabbix 采集适配器（占位实现）"""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def fetch(self, since: float | None = None) -> list[Alert]:
        # TODO: 对接 Zabbix API
        return []

    def health(self) -> dict[str, Any]:
        return {"status": "ok", "source": "zabbix"}


class N9eAdapter(BaseAdapter):
    """N9e 采集适配器（占位实现）"""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def fetch(self, since: float | None = None) -> list[Alert]:
        # TODO: 对接 N9e API
        return []

    def health(self) -> dict[str, Any]:
        return {"status": "ok", "source": "n9e"}


class InfluxDBAdapter(BaseAdapter):
    """InfluxDB 采集适配器（占位实现）"""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def fetch(self, since: float | None = None) -> list[Alert]:
        # TODO: 对接 InfluxDB Flux 查询
        return []

    def health(self) -> dict[str, Any]:
        return {"status": "ok", "source": "influxdb"}


class GenericJSONAdapter(BaseAdapter):
    """通用 JSON 采集适配器（从 HTTP endpoint 拉取）"""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.url = config.get("url", "")
        self.headers = config.get("headers", {})

    def fetch(self, since: float | None = None) -> list[Alert]:
        # TODO: 实现 HTTP 拉取 + JSON 映射
        return []

    def health(self) -> dict[str, Any]:
        return {"status": "ok", "source": "generic_json", "url": self.url}
