"""alert-engine 基础测试。"""

import time

import pytest

from alert_engine.types import Alert, Incident, TimeWindowAggregator, AlertScorer
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


class TestMuteTiming:
    def test_cron_matches(self):
        engine = AlertEngine()
        engine.add_mute_timing({
            "cron": "0 2 * * *",
            "match": {"service": "backup"},
        })
        # 02:00 的告警应被静默
        alert = Alert(id="1", alert_name="BackupFail", service="backup", cluster="prod",
                      severity="p3", timestamp=__import__("datetime").datetime(2025, 1, 1, 2, 0).timestamp())
        r = engine.feed(alert)
        assert not r.passed
        assert r.suppressed_by == "mute_timing"

    def test_cron_no_match_wrong_time(self):
        engine = AlertEngine()
        engine.add_mute_timing({
            "cron": "0 2 * * *",
            "match": {"service": "backup"},
        })
        # 03:00 的告警应通过
        alert = Alert(id="1", alert_name="BackupFail", service="backup", cluster="prod",
                      severity="p3", timestamp=__import__("datetime").datetime(2025, 1, 1, 3, 0).timestamp())
        r = engine.feed(alert)
        assert r.passed


class TestBaselineEWMA:
    def test_baseline_ewma_updates(self):
        engine = AlertEngine()
        engine.set_baseline("api:HighCPU", mean=70.0, std=15.0)
        # 80 在 3σ 内（(80-70)/15=0.67<3），应通过并更新基线
        a = Alert(id="1", alert_name="HighCPU", service="api", cluster="prod",
                  severity="p1", timestamp=time.time(), value=80.0)
        r = engine.feed(a)
        assert r.passed
        # 基线均值应向 80 靠近
        mean, std = engine._baselines["api:HighCPU"]
        assert mean > 70.0


class TestDependencyInhibitResolved:
    def test_resolved_parent_no_inhibit(self):
        engine = AlertEngine()
        engine.set_dependency("api-gateway", "db-primary")
        now = time.time()
        # 先喂入 parent，创建 incident
        parent = Alert(id="p1", alert_name="DBDown", service="db-primary", cluster="prod",
                       severity="p0", timestamp=now)
        engine.feed(parent)
        # 手动 resolve parent incident
        for inc in engine.aggregator._active_incidents.values():
            if inc.root_service == "db-primary":
                inc.resolved = True
                break
        # 现在喂入 child，不应被抑制
        child = Alert(id="c1", alert_name="DBDown", service="api-gateway", cluster="prod",
                      severity="p1", timestamp=now + 10)
        r = engine.feed(child)
        assert r.passed


class TestCleanupExpired:
    def test_cleanup_removes_resolved_incidents(self):
        engine = AlertEngine(window_seconds=1)
        now = time.time()
        a = Alert(id="1", alert_name="x", service="s", cluster="c",
                  severity="p1", timestamp=now)
        engine.feed(a)
        # 强制 resolve
        for inc in engine.aggregator._active_incidents.values():
            inc.resolved = True
        # 再喂一条触发清理
        b = Alert(id="2", alert_name="y", service="s2", cluster="c",
                  severity="p1", timestamp=now + 2)
        engine.feed(b)
        assert all(not inc.resolved for inc in engine.aggregator._active_incidents.values())

    def test_cleanup_removes_old_fingerprints(self):
        engine = AlertEngine()
        now = time.time()
        a = Alert(id="1", alert_name="z", service="s", cluster="c",
                  severity="p1", timestamp=now)
        engine.feed(a)
        assert len(engine._seen_fingerprints) > 0
        # 推进时间超过 TTL
        old_now = now + 601
        b = Alert(id="2", alert_name="w", service="s2", cluster="c",
                  severity="p1", timestamp=old_now)
        engine.feed(b)
        assert len(engine._fingerprint_ts) == 1  # 旧指纹已清理
