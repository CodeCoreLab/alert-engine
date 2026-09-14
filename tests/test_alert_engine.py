"""alert-engine 基础测试。"""

import time

import pytest

from alert_engine.aggregation import Alert, Incident, TimeWindowAggregator
from alert_engine.alert_scoring import AlertScorer
from alert_engine.escalation import EscalationPolicy
from alert_engine.engine import AlertEngine, PipelineResult
from alert_engine.symptom_router import SymptomRouter


class TestAggregation:
    def test_alert_creation(self):
        a = Alert(id="1", alert_name="HighCPU", service="api", cluster="prod",
                  severity="p1", timestamp=time.time())
        assert a.severity == "p1"
        assert a.service == "api"

    def test_incident_severity(self):
        inc = Incident(root_key="k", root_service="api", cluster="prod")
        inc.alerts = [
            Alert(id="1", alert_name="x", service="api", cluster="prod", severity="p2", timestamp=time.time()),
            Alert(id="2", alert_name="x", service="api", cluster="prod", severity="p0", timestamp=time.time()),
        ]
        assert inc.severity == "p0"

    def test_aggregator_add_alert(self):
        agg = TimeWindowAggregator(window_seconds=60)
        a = Alert(id="1", alert_name="x", service="api", cluster="prod", severity="p1", timestamp=time.time())
        inc = agg.add_alert(a)
        assert inc is not None
        assert inc.alert_count == 1


class TestScoring:
    def test_p0_score(self):
        scorer = AlertScorer()
        a = Alert(id="1", alert_name="HighCPU", service="api", cluster="prod",
                  severity="p0", timestamp=time.time(), value=100.0, labels={"host": "web-01", "pod": "api-1"})
        s = scorer.score(a)
        # p0 权重高，确保 immediate
        assert s.action == "immediate"

    def test_p3_score(self):
        scorer = AlertScorer()
        a = Alert(id="1", alert_name="Info", service="api", cluster="prod",
                  severity="p3", timestamp=time.time(), value=0.0)
        s = scorer.score(a)
        assert s.total_score < 4.0
        assert s.action == "observe"


class TestEscalation:
    def test_default_rules(self):
        policy = EscalationPolicy.default()
        assert "p0" in policy.rules
        assert "p1" in policy.rules
        assert len(policy.rules["p0"].steps) >= 3

    def test_notify_p0(self):
        policy = EscalationPolicy.default()
        contact = policy.notify("alert-1", "p0")
        assert contact is not None
        assert contact.channel == "phone"

    def test_acknowledged_no_more_notify(self):
        policy = EscalationPolicy.default()
        policy.notify("alert-1", "p0")
        policy._states["alert-1"].acknowledged = True
        assert policy.notify("alert-1", "p0") is None


class TestEngine:
    def test_for_min_dedup(self):
        engine = AlertEngine()
        now = time.time()
        a1 = Alert(id="1", alert_name="HighCPU", service="api", cluster="prod",
                   severity="p1", timestamp=now)
        a2 = Alert(id="2", alert_name="HighCPU", service="api", cluster="prod",
                   severity="p1", timestamp=now + 200)  # 超过 for_min (120s)
        r1 = engine.feed(a1)
        r2 = engine.feed(a2)
        assert r1.passed
        assert not r2.passed
        assert r2.suppressed_by == "dedup"

    def test_baseline_filter(self):
        engine = AlertEngine()
        engine.set_baseline("api:HighCPU", mean=70.0, std=15.0)
        # 在 3σ 内 → 被过滤
        a = Alert(id="1", alert_name="HighCPU", service="api", cluster="prod",
                  severity="p1", timestamp=time.time(), value=72.0)
        r = engine.feed(a)
        assert not r.passed
        assert r.suppressed_by == "baseline"

    def test_run_pipeline(self):
        engine = AlertEngine()
        alerts = [
            Alert(id="1", alert_name="HighCPU", service="api", cluster="prod",
                  severity="p1", timestamp=time.time(), value=100.0),
            Alert(id="2", alert_name="Info", service="api", cluster="prod",
                  severity="p3", timestamp=time.time()),
        ]
        results = engine.run_pipeline(alerts)
        assert len(results) == 2


class TestSymptomRouter:
    def test_route_match(self):
        router = SymptomRouter.default()
        group = router.route("HighCPU", {"host": "web-01"}, "p1")
        assert group is not None
        assert group.name in ("platform", "infra")

    def test_route_no_match(self):
        router = SymptomRouter.default()
        group = router.route("UnknownAlertXYZ", {}, "p3")
        assert group is None
