"""
alert-engine — 8 阶段降噪管线主引擎
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from alert_engine.aggregation import Alert, Incident, TimeWindowAggregator
from alert_engine.alert_scoring import AlertScorer
from alert_engine.escalation import EscalationPolicy


def _cron_matches(expr: str, current_minute: int, current_hour: int) -> bool:
    """极简 cron 匹配：仅支持 minute 和 hour 字段（5 段式前两位）。"""
    parts = expr.strip().split()
    if len(parts) < 2:
        return False
    minute_part, hour_part = parts[0], parts[1]
    return _field_matches(minute_part, current_minute) and _field_matches(hour_part, current_hour)


def _field_matches(field: str, value: int) -> bool:
    field = field.strip()
    if field == "*":
        return True
    if "," in field:
        return any(_field_matches(f.strip(), value) for f in field.split(","))
    if "/" in field:
        base, step = field.split("/", 1)
        base = base.strip() or "*"
        step = int(step.strip())
        if base == "*":
            return value % step == 0
        values = [int(x) for x in base.split("-")]
        if len(values) == 1:
            return values[0] % step == 0 and value == values[0]
        start, end = values
        return start <= value <= end and (value - start) % step == 0
    if "-" in field:
        start, end = (int(x.strip()) for x in field.split("-", 1))
        return start <= value <= end
    return int(field) == value


@dataclass
class PipelineResult:
    """单条告警经管线处理后的结果"""
    alert: Alert
    passed: bool
    incident: Optional[Incident] = None
    score: Optional[float] = None
    action: str = "drop"  # drop / observe / incident / immediate
    stages_passed: List[str] = field(default_factory=list)
    suppressed_by: Optional[str] = None


class AlertEngine:
    """
    告警降噪引擎。

    8 阶段管线：
      0. for_min        — 差异化防抖
      1. dedup           — 指纹去重
      2. silence         — 时间静默
      3. mute_timing     — 周期条件静默
      4. dependency_inhibit — 根因压制下游
      5. inhibit         — 级别抑制
      6. baseline        — 3σ 基线预判
      7. event_bus       — 异步发布事件
    """

    def __init__(
        self,
        window_seconds: int = 300,
        dedup_window: int = 300,
        escalation_policy: Optional[EscalationPolicy] = None,
        scorer: Optional[AlertScorer] = None,
    ):
        self.aggregator = TimeWindowAggregator(window_seconds=window_seconds)
        self.scorer = scorer or AlertScorer()
        self.escalation_policy = escalation_policy or EscalationPolicy.default()
        self._silence_rules: List[Dict] = []
        self._mute_timing_rules: List[Dict] = []
        self._dependency_map: Dict[str, str] = {}  # parent -> child
        self._baselines: Dict[str, tuple[float, float]] = {}  # key -> (mean, std)
        self._seen_fingerprints: set = set()
        self._fingerprint_ts: Dict[str, float] = {}
        self._last_fire: Dict[str, float] = {}

    # ------------------------------------------------------------------
    # 配置
    # ------------------------------------------------------------------

    def add_silence_rule(self, rule: Dict):
        """添加静默规则: {"match": {"service": "backup"}, "until": timestamp}"""
        self._silence_rules.append(rule)

    def add_mute_timing(self, rule: Dict):
        """添加周期静默: {"cron": "0 2 * * *", "match": {...}}"""
        self._mute_timing_rules.append(rule)

    def set_dependency(self, parent: str, child: str):
        """设置依赖关系：parent 故障时抑制 child"""
        self._dependency_map[child] = parent

    def set_baseline(self, key: str, mean: float, std: float):
        """设置基线：key -> (mean, std)"""
        self._baselines[key] = (mean, std)

    # ------------------------------------------------------------------
    # 8 阶段管线
    # ------------------------------------------------------------------

    def feed(self, alert: Alert) -> PipelineResult:
        """单条告警进管"""
        stages: List[str] = []

        # Stage 0: for_min 防抖
        if not self._stage_for_min(alert):
            return PipelineResult(alert=alert, passed=False, stages_passed=["for_min"], suppressed_by="for_min")
        stages.append("for_min")

        # Stage 1: dedup 去重
        if not self._stage_dedup(alert):
            return PipelineResult(alert=alert, passed=False, stages_passed=stages, suppressed_by="dedup")
        stages.append("dedup")

        # Stage 2: silence 时间静默
        if self._stage_silence(alert):
            return PipelineResult(alert=alert, passed=False, stages_passed=stages, suppressed_by="silence")
        stages.append("silence")

        # Stage 3: mute_timing 周期静默
        if self._stage_mute_timing(alert):
            return PipelineResult(alert=alert, passed=False, stages_passed=stages, suppressed_by="mute_timing")
        stages.append("mute_timing")

        # Stage 4: dependency_inhibit 根因压制
        if self._stage_dependency_inhibit(alert):
            return PipelineResult(alert=alert, passed=False, stages_passed=stages, suppressed_by="dependency_inhibit")
        stages.append("dependency_inhibit")

        # Stage 5: inhibit 级别抑制
        if self._stage_inhibit(alert):
            return PipelineResult(alert=alert, passed=False, stages_passed=stages, suppressed_by="inhibit")
        stages.append("inhibit")

        # Stage 6: baseline 3σ 预判
        if not self._stage_baseline(alert):
            return PipelineResult(alert=alert, passed=False, stages_passed=stages, suppressed_by="baseline")
        stages.append("baseline")

        # Stage 7: 通过全部，进入聚合 + 评分
        stages.append("event_bus")
        incident = self.aggregator.add_alert(alert)
        score_result = self.scorer.score(alert)
        action = self._determine_action(score_result)

        self._cleanup_expired(alert.timestamp)

        return PipelineResult(
            alert=alert,
            passed=True,
            incident=incident,
            score=score_result.total_score,
            action=action,
            stages_passed=stages,
        )

    def _cleanup_expired(self, now: float):
        """清理过期指纹、基线快照和已 resolved 的 incidents。"""
        dedup_ttl = 600
        expired = [fp for fp, ts in self._fingerprint_ts.items() if now - ts > dedup_ttl]
        for fp in expired:
            self._seen_fingerprints.discard(fp)
            del self._fingerprint_ts[fp]
        for key in list(self._last_fire.keys()):
            if now - self._last_fire[key] > 1800:
                del self._last_fire[key]
        self.aggregator._active_incidents = {
            k: v for k, v in self.aggregator._active_incidents.items()
            if not v.resolved
        }

    def run_pipeline(self, alerts: List[Alert]) -> List[PipelineResult]:
        """批量处理"""
        return [self.feed(a) for a in alerts]

    def get_incidents(self) -> List[Incident]:
        """获取当前活跃 Incident 列表"""
        return self.aggregator.get_active_incidents()

    # ------------------------------------------------------------------
    # 8 阶段实现
    # ------------------------------------------------------------------

    def _stage_for_min(self, alert: Alert) -> bool:
        key = f"{alert.service}:{alert.alert_name}"
        last = self._last_fire.get(key, 0)
        now = alert.timestamp
        for_min = {"p0": 60, "p1": 120, "p2": 300, "p3": 600, "info": 900}.get(alert.severity, 300)
        if now - last < for_min:
            return False
        self._last_fire[key] = now
        return True

    def _stage_dedup(self, alert: Alert) -> bool:
        import hashlib
        raw = "|".join(f"{k}={v}" for k, v in sorted((alert.labels or {}).items()))
        raw = f"{alert.alert_name}|{alert.host or alert.service}|{raw}"
        fp = hashlib.sha1(raw.encode()).hexdigest()[:16]
        if fp in self._seen_fingerprints:
            return False
        self._seen_fingerprints.add(fp)
        self._fingerprint_ts[fp] = alert.timestamp
        return True

    def _stage_silence(self, alert: Alert) -> bool:
        now = alert.timestamp
        for rule in self._silence_rules:
            match = rule.get("match", {})
            if all(alert.labels.get(k) == v for k, v in match.items()):
                until = rule.get("until", 0)
                if now < until:
                    return True
        return False

    def _stage_mute_timing(self, alert: Alert) -> bool:
        """周期条件静默：基于 cron 表达式的分钟/小时匹配。"""
        from datetime import datetime
        now_dt = datetime.fromtimestamp(alert.timestamp)
        current_minute = now_dt.minute
        current_hour = now_dt.hour
        for rule in self._mute_timing_rules:
            cron_expr = rule.get("cron", "")
            match = rule.get("match", {})
            if not cron_expr or not match:
                continue
            if not _cron_matches(cron_expr, current_minute, current_hour):
                continue
            if all(alert.labels.get(k) == v for k, v in match.items()):
                return True
        return False

    def _stage_dependency_inhibit(self, alert: Alert) -> bool:
        """根因压制：上游未 resolved 时，抑制下游告警。"""
        parent = self._dependency_map.get(alert.service)
        if not parent:
            return False
        active_parents = [
            inc for inc in self.aggregator._active_incidents.values()
            if not inc.resolved and inc.root_service == parent
        ]
        return bool(active_parents)

    def _stage_inhibit(self, alert: Alert) -> bool:
        """级别抑制：同名告警存在未 resolved 的高等级时，抑制低等级。"""
        rank = {"p0": 0, "p1": 1, "p2": 2, "p3": 3, "info": 4}
        current_rank = rank.get(alert.severity, 4)
        for inc in self.aggregator._active_incidents.values():
            if inc.resolved:
                continue
            for a in inc.alerts:
                if a.alert_name == alert.alert_name and rank.get(a.severity, 4) < current_rank:
                    return True
        return False

    def _stage_baseline(self, alert: Alert) -> bool:
        """3σ 基线预判：支持 EWMA 动态基线更新。"""
        key = f"{alert.service}:{alert.alert_name}"
        if key in self._baselines:
            mean, std = self._baselines[key]
            if std > 0:
                z = abs(alert.value - mean) / std
                if z < 3.0:
                    return False
        # EWMA 更新基线
        alpha = 0.1
        if key in self._baselines:
            prev_mean, prev_std = self._baselines[key]
            new_mean = alpha * alert.value + (1 - alpha) * prev_mean
            new_std = abs(alert.value - new_mean) * alpha + (1 - alpha) * prev_std
            self._baselines[key] = (new_mean, new_std if new_std > 0.1 else prev_std)
        else:
            self._baselines[key] = (alert.value, 1.0)
        return True

    def _determine_action(self, score_result: AlertScore) -> str:
        if score_result.total_score >= 8.0:
            return "immediate"
        if score_result.total_score >= 4.0:
            return "incident"
        return "observe"
