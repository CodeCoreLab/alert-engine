"""alert-engine 基础测试。"""

import time

from alert_engine.engine import AlertEngine
from alert_engine.escalation import EscalationPolicy
from alert_engine.symptom_router import SymptomRouter
from alert_engine.types import Alert, AlertScorer, Incident, TimeWindowAggregator


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

    def test_scorer_and_engine_action_agree(self):
        """评分器与管线的 action 判定必须一致（同一权威源）。

        曾出现 scorer 阈值 7.0、engine 阈值 8.0，
        同一条告警在评分器里是 immediate、在管线里是 incident。
        """
        from alert_engine.types import action_for_score
        for severity, value, labels in [
            ("p0", 100.0, {"host": "web-01", "pod": "api-1"}),
            ("p1", 85.0, {"host": "web-02"}),
            ("p2", 50.0, {"host": "web-03"}),
            ("p3", 0.0, {}),
        ]:
            a = Alert(id="1", alert_name="X", service="api", cluster="prod",
                      severity=severity, timestamp=time.time(), value=value, labels=labels)
            s = AlertScorer().score(a)
            engine_action = AlertEngine()._determine_action(s)
            assert s.action == engine_action, (
                f"{severity}: scorer={s.action} vs engine={engine_action}"
            )
            assert s.action == action_for_score(s.total_score)

    def test_threshold_single_source(self):
        """阈值只在 types.action_for_score 一处定义。"""
        from alert_engine.types import SCORE_IMMEDIATE, SCORE_INCIDENT, action_for_score
        assert action_for_score(SCORE_IMMEDIATE) == "immediate"
        assert action_for_score(SCORE_IMMEDIATE - 0.01) == "incident"
        assert action_for_score(SCORE_INCIDENT) == "incident"
        assert action_for_score(SCORE_INCIDENT - 0.01) == "observe"


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
    def test_baseline_blocks_within_3sigma(self):
        """3σ 内的样本属正常波动 → 拦截（与 README「3σ 外才告警」一致）。"""
        engine = AlertEngine()
        engine.set_baseline("api:HighCPU", mean=70.0, std=15.0)
        a = Alert(id="1", alert_name="HighCPU", service="api", cluster="prod",
                  severity="p1", timestamp=time.time(), value=80.0)
        r = engine.feed(a)
        assert not r.passed
        assert r.suppressed_by == "baseline"

    def test_baseline_passes_outside_3sigma(self):
        """3σ 外的样本是异常 → 放行。"""
        engine = AlertEngine()
        engine.set_baseline("api:HighCPU", mean=70.0, std=15.0)
        a = Alert(id="1", alert_name="HighCPU", service="api", cluster="prod",
                  severity="p1", timestamp=time.time(), value=200.0)
        r = engine.feed(a)
        assert r.passed

    def test_baseline_ewma_updates_on_blocked_sample(self):
        """被 3σ 拦截的正常样本也必须参与 EWMA 更新。

        否则基线只被异常值污染（正常样本从不参与），均值持续漂移。
        """
        engine = AlertEngine()
        engine.set_baseline("api:HighCPU", mean=70.0, std=15.0)
        a = Alert(id="1", alert_name="HighCPU", service="api", cluster="prod",
                  severity="p1", timestamp=time.time(), value=80.0)
        engine.feed(a)
        mean, _std = engine._baselines["api:HighCPU"]
        assert mean > 70.0, f"均值应向样本靠近，实际 {mean}"


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

    def test_p0_never_suppressed_by_dependency(self):
        """P0 永不被根因抑制。

        根因抑制按 service 匹配、不区分告警类型，
        上游故障会连带压掉下游的独立 P0 故障 —— 漏报代价远高于降噪收益。
        """
        engine = AlertEngine()
        engine.set_dependency("db-primary", "api-gateway")
        now = time.time()
        parent = Alert(id="p1", alert_name="DBDown", service="db-primary", cluster="prod",
                       severity="p0", timestamp=now)
        engine.feed(parent)
        # 下游的 P0（与根因告警名不同，是独立故障）
        child = Alert(id="c1", alert_name="OOM", service="api-gateway", cluster="prod",
                      severity="p0", timestamp=now + 10, value=100.0)
        r = engine.feed(child)
        assert r.passed, "P0 不应被根因抑制"
        assert r.suppressed_by != "dependency_inhibit"

    def test_p1_still_suppressed_by_dependency(self):
        """P1 仍受根因抑制（只豁免 P0，不是一律放行）。"""
        engine = AlertEngine()
        engine.set_dependency("db-primary", "api-gateway")
        now = time.time()
        engine.feed(Alert(id="p1", alert_name="DBDown", service="db-primary", cluster="prod",
                          severity="p0", timestamp=now))
        child = Alert(id="c1", alert_name="DBDown", service="api-gateway", cluster="prod",
                      severity="p1", timestamp=now + 10)
        r = engine.feed(child)
        assert not r.passed
        assert r.suppressed_by == "dependency_inhibit"


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


class TestAdapterIntegration:
    """README 承诺的 Adapter 接入 API 必须真实存在。"""

    class _FakeAdapter:
        def __init__(self, alerts=None, boom=False):
            self._alerts = alerts or []
            self._boom = boom

        def fetch(self, since=None):
            if self._boom:
                raise RuntimeError("数据源不可用")
            return list(self._alerts)

        def health(self):
            return {"status": "ok"}

    def test_register_and_collect(self):
        engine = AlertEngine()
        a = Alert(id="1", alert_name="x", service="s", cluster="c",
                  severity="p1", timestamp=time.time())
        engine.register_adapter("fake", self._FakeAdapter([a]))
        got = engine.collect()
        assert len(got) == 1
        assert got[0].id == "1"

    def test_run_pipeline_via_adapter(self):
        engine = AlertEngine()
        a = Alert(id="1", alert_name="x", service="s", cluster="c",
                  severity="p1", timestamp=time.time(), value=99.0)
        engine.register_adapter("fake", self._FakeAdapter([a]))
        results = engine.run()
        assert len(results) == 1
        assert results[0].passed

    def test_one_broken_adapter_does_not_break_others(self):
        """单个数据源挂掉不该让整轮采集归零。"""
        engine = AlertEngine()
        a = Alert(id="1", alert_name="x", service="s", cluster="c",
                  severity="p1", timestamp=time.time())
        engine.register_adapter("broken", self._FakeAdapter(boom=True))
        engine.register_adapter("ok", self._FakeAdapter([a]))
        got = engine.collect()
        assert len(got) == 1

    def test_no_adapter_returns_empty(self):
        engine = AlertEngine()
        assert engine.collect() == []
        assert engine.run() == []

    def test_health_reports_adapters(self):
        engine = AlertEngine()
        engine.register_adapter("fake", self._FakeAdapter())
        h = engine.health()
        assert h["status"] == "ok"
        assert "fake" in h["adapters"]

    def test_set_escalation_policy(self):
        engine = AlertEngine()
        policy = EscalationPolicy.default()
        engine.set_escalation_policy(policy)
        assert engine.escalation_policy is policy


class TestRuleMatch:
    """match 条件既能匹配 labels，也能匹配告警顶层字段。"""

    def test_match_top_level_service(self):
        engine = AlertEngine()
        engine.add_mute_timing({"cron": "0 2 * * *", "match": {"service": "backup"}})
        alert = Alert(id="1", alert_name="BackupFail", service="backup", cluster="prod",
                      severity="p3", timestamp=__import__("datetime").datetime(2025, 1, 1, 2, 0).timestamp())
        r = engine.feed(alert)
        assert not r.passed
        assert r.suppressed_by == "mute_timing"

    def test_match_labels_still_works(self):
        engine = AlertEngine()
        engine.add_mute_timing({"cron": "0 2 * * *", "match": {"mount": "/data"}})
        alert = Alert(id="1", alert_name="DiskFull", service="db", cluster="prod",
                      severity="p3", labels={"mount": "/data"},
                      timestamp=__import__("datetime").datetime(2025, 1, 1, 2, 0).timestamp())
        r = engine.feed(alert)
        assert not r.passed
        assert r.suppressed_by == "mute_timing"

    def test_match_value_mismatch(self):
        engine = AlertEngine()
        engine.add_mute_timing({"cron": "0 2 * * *", "match": {"service": "other"}})
        alert = Alert(id="1", alert_name="BackupFail", service="backup", cluster="prod",
                      severity="p3", timestamp=__import__("datetime").datetime(2025, 1, 1, 2, 0).timestamp())
        r = engine.feed(alert)
        assert r.passed


class TestPatchOrchestrator:
    """补丁编排：冷却语义 + 异常不静默。"""

    def test_cooldown_blocks_repeated_execution(self):
        from alert_engine.patch_orchestrator import PatchAction, PatchOrchestrator

        calls = []
        orch = PatchOrchestrator()
        orch.register("high_cpu", PatchAction(
            name="restart_service",
            description="重启服务",
            handler=lambda ctx: calls.append(ctx) or True,
            max_retries=1,
            cooldown_seconds=300,
        ))
        assert orch.execute("high_cpu", {"i": 1}) is True
        assert orch.execute("high_cpu", {"i": 2}) is False, "冷却期内不应重复执行"
        assert len(calls) == 1, f"冷却期内 handler 只应被调用一次，实际 {len(calls)} 次"

    def test_cooldown_expires(self):
        from alert_engine.patch_orchestrator import PatchAction, PatchOrchestrator

        calls = []
        orch = PatchOrchestrator()
        orch.register("oom", PatchAction(
            name="restart_service",
            description="重启服务",
            handler=lambda ctx: calls.append(ctx) or True,
            max_retries=1,
            cooldown_seconds=0,  # 无冷却，便于断言
        ))
        assert orch.execute("oom", {"i": 1}) is True
        assert orch.execute("oom", {"i": 2}) is True
        assert len(calls) == 2

    def test_handler_exception_returns_false_not_raise(self):
        from alert_engine.patch_orchestrator import PatchAction, PatchOrchestrator

        def boom(ctx):
            raise RuntimeError("ssh 不可达")

        orch = PatchOrchestrator()
        orch.register("disk_full", PatchAction(
            name="cleanup_logs",
            description="清理日志",
            handler=boom,
            max_retries=2,
            cooldown_seconds=0,
        ))
        # 异常应被吞掉并返回 False，而不是向上抛穿调用方
        assert orch.execute("disk_full", {}) is False

    def test_retries_until_success(self):
        from alert_engine.patch_orchestrator import PatchAction, PatchOrchestrator

        attempts = {"n": 0}

        def flaky(ctx):
            attempts["n"] += 1
            return attempts["n"] >= 2

        orch = PatchOrchestrator()
        orch.register("high_cpu", PatchAction(
            name="restart_service",
            description="重启服务",
            handler=flaky,
            max_retries=3,
            cooldown_seconds=0,
        ))
        assert orch.execute("high_cpu", {}) is True
        assert attempts["n"] == 2

    def test_unknown_symptom_returns_false(self):
        from alert_engine.patch_orchestrator import PatchOrchestrator

        assert PatchOrchestrator().execute("nonexistent", {}) is False
