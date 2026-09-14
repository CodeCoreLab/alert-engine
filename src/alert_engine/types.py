"""
alert-engine — 核心数据模型与类型定义

合并原 aggregation.py + alert_scoring.py，对外统一提供：
  - Alert / Incident / TimeWindowAggregator
  - AlertScore / AlertScorer
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


# ---------------------------------------------------------------------------
# 告警与 Incident
# ---------------------------------------------------------------------------

@dataclass
class Alert:
    """标准化告警对象"""
    id: str
    alert_name: str
    service: str
    cluster: str
    severity: str  # p0/p1/p2/p3
    timestamp: float  # epoch seconds
    labels: Dict[str, str] = field(default_factory=dict)
    host: str = ""
    value: float = 0.0


@dataclass
class Incident:
    """聚合后的事件"""
    root_key: str
    root_service: str
    cluster: str
    alerts: List[Alert] = field(default_factory=list)
    created_at: float = 0.0
    resolved: bool = False
    resolved_at: float = 0.0

    @property
    def severity(self) -> str:
        rank = {"p0": 0, "p1": 1, "p2": 2, "p3": 3, "info": 4}
        return min(self.alerts, key=lambda a: rank.get(a.severity, 4)).severity if self.alerts else "p3"

    @property
    def alert_count(self) -> int:
        return len(self.alerts)

    @property
    def affected_services(self) -> Set[str]:
        return {a.service for a in self.alerts}

    @property
    def first_alert_time(self) -> float:
        return min(a.timestamp for a in self.alerts) if self.alerts else 0.0

    @property
    def last_alert_time(self) -> float:
        return max(a.timestamp for a in self.alerts) if self.alerts else 0.0

    @property
    def compression_ratio(self) -> float:
        """压缩比 = 告警数 / Incident 数（越大说明降噪效果越好）"""
        return self.alert_count


class TimeWindowAggregator:
    """
    时间窗口聚合器。
    将同一 cluster/service 在窗口内的告警合并为 Incident。
    """

    def __init__(self, window_seconds: int = 300):
        self.window_seconds = window_seconds
        self._active_incidents: Dict[str, Incident] = {}

    def _make_key(self, alert: Alert) -> str:
        return f"{alert.cluster}:{alert.service}"

    def add_alert(self, alert: Alert) -> Optional[Incident]:
        key = self._make_key(alert)
        if key not in self._active_incidents:
            self._active_incidents[key] = Incident(
                root_key=key,
                root_service=alert.service,
                cluster=alert.cluster,
                created_at=alert.timestamp,
            )
        inc = self._active_incidents[key]
        inc.alerts.append(alert)
        # 窗口过期自动 resolve
        if alert.timestamp - inc.created_at > self.window_seconds:
            inc.resolved = True
            inc.resolved_at = alert.timestamp
        return inc

    def get_active_incidents(self) -> List[Incident]:
        now = time.time()
        active = []
        for inc in self._active_incidents.values():
            if not inc.resolved and now - inc.created_at <= self.window_seconds:
                active.append(inc)
        return active

    def get_compression_ratio(self) -> float:
        total_alerts = sum(len(inc.alerts) for inc in self._active_incidents.values())
        total_incidents = len(self._active_incidents)
        return total_alerts / total_incidents if total_incidents > 0 else 0.0


# ---------------------------------------------------------------------------
# 告警评分
# ---------------------------------------------------------------------------

SEVERITY_WEIGHT = {
    "p0": 10.0,
    "p1": 7.0,
    "p2": 4.0,
    "p3": 2.0,
    "info": 1.0,
}

SCORE_IMMEDIATE = 7.0
SCORE_INCIDENT = 4.0
SCORE_OBSERVE = 0.0


@dataclass
class AlertScore:
    total_score: float
    severity_score: float
    blast_radius_score: float
    baseline_deviation_score: float
    historical_score: float
    action: str  # "immediate" / "incident" / "observe"
    confidence: float  # 0-1


class AlertScorer:
    """
    告警评分器。

    参数:
        historical_data: 历史数据，格式：
            {"alert_name": {"resolution_rate": 0.7, "mttr_minutes": 15}}
    """

    def __init__(self, historical_data: Optional[Dict[str, Dict]] = None):
        self.historical_data = historical_data or {}

    def score(self, alert: Alert) -> AlertScore:
        sev = SEVERITY_WEIGHT.get(alert.severity, 1.0)
        sev_score = min(sev / 10.0, 1.0)

        # 影响面（基于 labels 数量 + host 数）
        blast = min((len(alert.labels) + 1) / 10.0, 1.0)

        # 基线偏离（value vs 历史均值）
        baseline_score = 0.5  # 默认中等
        key = f"{alert.service}:{alert.alert_name}"
        if key in self.historical_data:
            hist = self.historical_data[key]
            baseline_score = min(hist.get("resolution_rate", 0.5), 1.0)

        # 历史解决率
        hist_score = 0.5
        if key in self.historical_data:
            hist_score = min(self.historical_data[key].get("resolution_rate", 0.5), 1.0)

        total = (
            sev_score * 0.5
            + blast * 0.2
            + baseline_score * 0.15
            + hist_score * 0.15
        ) * 10.0

        if total >= SCORE_IMMEDIATE:
            action = "immediate"
        elif total >= SCORE_INCIDENT:
            action = "incident"
        else:
            action = "observe"

        confidence = min(sev_score + blast + baseline_score + hist_score, 1.0)
        return AlertScore(
            total_score=round(total, 2),
            severity_score=round(sev_score, 2),
            blast_radius_score=round(blast, 2),
            baseline_deviation_score=round(baseline_score, 2),
            historical_score=round(hist_score, 2),
            action=action,
            confidence=round(confidence, 2),
        )
