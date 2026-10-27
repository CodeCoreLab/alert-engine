"""
alert-engine — 运维告警降噪引擎

核心 API:
    from alert_engine import AlertEngine, Alert, AlertScore
    engine = AlertEngine()
    result = engine.feed(alert)
"""

from alert_engine.adapters import (
    BaseAdapter,
    GenericJSONAdapter,
    InfluxDBAdapter,
    N9eAdapter,
    ZabbixAdapter,
)
from alert_engine.engine import AlertEngine, PipelineResult
from alert_engine.escalation import (
    AlertEscalationState,
    EscalationContact,
    EscalationPolicy,
    EscalationRule,
)
from alert_engine.incident_summary import IncidentSummarizer, IncidentSummary
from alert_engine.memory import AlertMemory
from alert_engine.patch_orchestrator import PatchAction, PatchOrchestrator
from alert_engine.symptom_router import OnCallGroup, SymptomRouter
from alert_engine.types import Alert, AlertScore, AlertScorer, Incident, TimeWindowAggregator

__all__ = [
    "Alert",
    "AlertEngine",
    "AlertEscalationState",
    "AlertMemory",
    "AlertScore",
    "AlertScorer",
    "BaseAdapter",
    "EscalationContact",
    "EscalationPolicy",
    "EscalationRule",
    "GenericJSONAdapter",
    "Incident",
    "IncidentSummarizer",
    "IncidentSummary",
    "InfluxDBAdapter",
    "N9eAdapter",
    "OnCallGroup",
    "PatchAction",
    "PatchOrchestrator",
    "PipelineResult",
    "SymptomRouter",
    "TimeWindowAggregator",
    "ZabbixAdapter",
]

__version__ = "0.3.0"
