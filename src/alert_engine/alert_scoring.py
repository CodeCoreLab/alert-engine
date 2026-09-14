"""
告警评分（Alert Scoring）

综合 severity + 影响面 + 偏离基线幅度 + 历史同类型告警解决率，量化优先级。

评分公式：
    total_score = severity_weight * 0.3 + blast_radius * 0.3 + baseline_deviation * 0.2 + historical * 0.2

阈值：
    score >= 8 → 立即推送（P0/P1 级别）
    4 <= score < 8 → 加入 Incident 组（P2 级别）
    score < 4 → 静默观察（P3/info 级别）
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Optional


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


# 延迟导入避免循环
from alert_engine.aggregation import Alert  # noqa: E402
