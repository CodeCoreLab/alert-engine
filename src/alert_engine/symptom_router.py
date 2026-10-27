"""
症状路由（Symptom Router）

根据告警症状特征自动路由到对应处理人/OnCall。
支持基于关键词匹配和 severity 权重路由。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OnCallGroup:
    """OnCall 组"""
    name: str
    members: list[str]
    keywords: list[str]
    severity_priority: list[str]  # ["p0", "p1", "p2", "p3"]


class SymptomRouter:
    """
    症状路由器。
    根据告警名称/labels 中的关键词匹配 OnCall 组。
    """

    def __init__(self):
        self._groups: list[OnCallGroup] = []

    def register_group(self, group: OnCallGroup):
        self._groups.append(group)

    def route(self, alert_name: str, labels: dict[str, str], severity: str) -> OnCallGroup | None:
        """
        路由到最匹配的 OnCall 组。
        返回匹配度最高的组，或 None（无匹配）。
        """
        candidates = []
        text = f"{alert_name} {' '.join(str(v) for v in labels.values())}".lower()
        for group in self._groups:
            score = sum(1 for kw in group.keywords if kw.lower() in text)
            if score > 0:
                candidates.append((score, group))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    @staticmethod
    def default() -> SymptomRouter:
        router = SymptomRouter()
        router.register_group(OnCallGroup(
            name="platform",
            members=["alice", "bob"],
            keywords=["api", "gateway", "service", "deploy"],
            severity_priority=["p0", "p1", "p2", "p3"],
        ))
        router.register_group(OnCallGroup(
            name="data",
            members=["charlie", "dave"],
            keywords=["database", "mysql", "redis", "influxdb", "zabbix"],
            severity_priority=["p0", "p1", "p2", "p3"],
        ))
        router.register_group(OnCallGroup(
            name="infra",
            members=["eve", "frank"],
            keywords=["network", "disk", "cpu", "memory", "node"],
            severity_priority=["p0", "p1", "p2", "p3"],
        ))
        return router
