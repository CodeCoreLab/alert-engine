"""
时间窗口聚合（Time-Window Aggregation）
同一 cluster/service 在窗口内合并为 Incident，下游告警不单独成组。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


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
