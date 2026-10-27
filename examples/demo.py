"""alert-engine 完整演示。

展示 8 阶段降噪管线 + 聚合 + 评分 + 升级 + 症状路由的实际效果。

运行:
    python examples/demo.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# 允许直接从源码树运行（未安装包时）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from alert_engine import (
    Alert,
    AlertEngine,
    AlertScorer,
    EscalationPolicy,
    SymptomRouter,
)


def build_engine() -> AlertEngine:
    engine = AlertEngine(window_seconds=300)

    # 根因压制：db-primary 故障时抑制下游 api-gateway
    engine.set_dependency("db-primary", "api-gateway")

    # 3σ 基线：api 的 HighCPU 正常在 70±15
    engine.set_baseline("api:HighCPU", mean=70.0, std=15.0)

    # 维护窗口静默（14:00 前静默 backup 服务）
    engine.add_silence_rule({
        "match": {"service": "backup"},
        "until": time.time() + 3600,
    })

    return engine


def sample_alerts(now: float) -> list[Alert]:
    return [
        # 正常波动（70±15 内，z=1.0）→ 被 baseline 拦截
        Alert(id="a1", alert_name="HighCPU", service="api", cluster="prod",
              severity="p1", timestamp=now, labels={"host": "web-01"}, value=85.0),
        # 同样 HighCPU，但 1 分钟内重复 → 被 for_min 拦截
        Alert(id="a2", alert_name="HighCPU", service="api", cluster="prod",
              severity="p1", timestamp=now + 10, labels={"host": "web-02"}, value=82.0),
        # 完全相同的 labels → 被 dedup 拦截
        Alert(id="a3", alert_name="HighCPU", service="api", cluster="prod",
              severity="p1", timestamp=now + 20, labels={"host": "web-01"}, value=85.0),
        # 维护窗口内 → 被 silence 拦截
        Alert(id="a4", alert_name="BackupFail", service="backup", cluster="prod",
              severity="p2", timestamp=now + 30, labels={"host": "bk-01"}),
        # 根因告警 → 放行，产出 Incident
        Alert(id="a5", alert_name="DBDown", service="db-primary", cluster="prod",
              severity="p0", timestamp=now + 40, labels={"host": "db-01"}),
        # 下游级联告警 → 被 dependency_inhibit 拦截
        Alert(id="a6", alert_name="DBDown", service="api-gateway", cluster="prod",
              severity="p1", timestamp=now + 50, labels={"host": "gw-01"}),
        # 真实异常（z=2.0，在 3σ 内但更远）→ 放行
        Alert(id="a7", alert_name="OOM", service="api-gateway", cluster="prod",
              severity="p0", timestamp=now + 60, labels={"pod": "api-7x8dq"}, value=100.0),
    ]


def main() -> None:
    engine = build_engine()
    alerts = sample_alerts(time.time())

    print("=" * 72)
    print("8 阶段降噪管线演示")
    print("=" * 72)

    results = engine.run_pipeline(alerts)

    print(f"\n{'告警':<12} {'服务':<14} {'级别':<5} {'放行':<6} {'动作':<10} {'分数':<6} 拦截原因")
    print("-" * 72)
    for r in results:
        score = f"{r.score:.2f}" if r.score is not None else "-"
        print(
            f"{r.alert.alert_name:<12} {r.alert.service:<14} {r.alert.severity:<5} "
            f"{'✅' if r.passed else '❌':<6} {r.action:<10} {score:<6} "
            f"{r.suppressed_by or '-'}"
        )

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    ratio = engine.aggregator.get_compression_ratio()

    print("\n" + "=" * 72)
    print(f"接收 {total} 条 → 放行 {passed} 条，抑制 {total - passed} 条")
    print(f"压缩比 {ratio:.2f}x（告警数 / Incident 数）")
    print(f"活跃 Incident {len(engine.get_incidents())} 个")
    print("=" * 72)

    # ---- 评分明细 ----
    print("\n【评分明细】")
    scorer = AlertScorer()
    for a in alerts:
        s = scorer.score(a)
        print(f"  {a.alert_name:<12} score={s.total_score:<6} action={s.action:<10} confidence={s.confidence}")

    # ---- 升级策略 ----
    print("\n【分级升级】")
    policy = EscalationPolicy.default()
    for sev in ("p0", "p1", "p2"):
        contact = policy.notify(f"alert-{sev}", sev)
        if contact:
            print(f"  {sev.upper():<4} → {contact.name}（{contact.channel}）")

    # ---- 症状路由 ----
    print("\n【症状路由】")
    router = SymptomRouter.default()
    for a in alerts:
        group = router.route(a.alert_name, a.labels, a.severity)
        if group:
            print(f"  {a.alert_name:<12} → {group.name}: {', '.join(group.members)}")

    # ---- 引擎健康 ----
    print("\n【引擎健康】")
    print(f"  {engine.health()}")


if __name__ == "__main__":
    main()
