"""
alert-engine — 运维告警降噪引擎

8 阶段管线：for_min → dedup → silence → mute_timing → dependency_inhibit → inhibit → baseline → event_bus

快速开始:
    from alert_engine import AlertEngine, Alert

    engine = AlertEngine()
    engine.feed(Alert(id="1", alert_name="HighCPU", service="api", severity="p1", timestamp=time.time()))
    engine.run_pipeline()
"""

from alert_engine.engine import AlertEngine
from alert_engine.aggregation import Alert, Incident, TimeWindowAggregator
from alert_engine.alert_scoring import AlertScorer, AlertScore
from alert_engine.escalation import EscalationPolicy, EscalationContact
from alert_engine.symptom_router import SymptomRouter

__all__ = [
    "AlertEngine",
    "Alert",
    "Incident",
    "TimeWindowAggregator",
    "AlertScorer",
    "AlertScore",
    "EscalationPolicy",
    "EscalationContact",
    "SymptomRouter",
]
__version__ = "0.1.0"
