"""
alert-engine — 运维告警降噪引擎

核心 API:
    from alert_engine import AlertEngine, Alert, AlertScore
    engine = AlertEngine()
    result = engine.feed(alert)
"""

from alert_engine.engine import AlertEngine, PipelineResult
from alert_engine.types import Alert, Incident, TimeWindowAggregator, AlertScore, AlertScorer
from alert_engine.adapters import (
    BaseAdapter,
    ZabbixAdapter,
    N9eAdapter,
    InfluxDBAdapter,
    GenericJSONAdapter,
)
from alert_engine.memory import AlertMemory

__all__ = [
    "AlertEngine",
    "PipelineResult",
    "Alert",
    "Incident",
    "TimeWindowAggregator",
    "AlertScore",
    "AlertScorer",
    "BaseAdapter",
    "ZabbixAdapter",
    "N9eAdapter",
    "InfluxDBAdapter",
    "GenericJSONAdapter",
    "AlertMemory",
]

__version__ = "0.2.0"
