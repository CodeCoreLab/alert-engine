"""
告警事故摘要（Incident Summary）

基于告警聚合结果生成结构化摘要，支持 LLM 增强。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from alert_engine.aggregation import Alert, Incident


@dataclass
class IncidentSummary:
    """事故摘要"""
    incident_id: str
    title: str
    severity: str
    affected_services: List[str]
    alert_count: int
    first_alert: str
    last_alert: str
    duration_seconds: float
    root_cause: Optional[str] = None
    llm_summary: Optional[str] = None


class IncidentSummarizer:
    """
    事故摘要生成器。
    不依赖外部 LLM 时，生成结构化摘要；
    传入 llm_client 时，可生成 LLM 增强摘要。
    """

    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    def summarize(self, incident: Incident) -> IncidentSummary:
        first = incident.first_alert_time
        last = incident.last_alert_time
        duration = last - first if last > first else 0
        title = f"{incident.root_service} {incident.severity.upper()} - {incident.alert_count} alerts"
        summary = IncidentSummary(
            incident_id=incident.root_key,
            title=title,
            severity=incident.severity,
            affected_services=list(incident.affected_services),
            alert_count=incident.alert_count,
            first_alert=_format_ts(first),
            last_alert=_format_ts(last),
            duration_seconds=round(duration, 1),
        )
        if self.llm_client:
            summary.llm_summary = self._llm_summarize(incident)
        return summary

    def _llm_summarize(self, incident: Incident) -> str:
        """调用 LLM 生成摘要（需要外部实现 llm_client）。"""
        try:
            prompt = (
                f"Summarize this incident:\n"
                f"Service: {incident.root_service}\n"
                f"Severity: {incident.severity}\n"
                f"Alerts: {incident.alert_count}\n"
                f"Affected: {', '.join(incident.affected_services)}\n"
            )
            return self.llm_client(prompt)
        except Exception:
            return "LLM summary unavailable"


def _format_ts(ts: float) -> str:
    from datetime import datetime
    return datetime.fromtimestamp(ts).isoformat() if ts else "N/A"
