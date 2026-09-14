"""
alert-engine — CLI 入口

用法:
    alert-engine demo                     # 运行演示
    alert-engine score --alert "HighCPU"  # 单条告警评分
"""

from __future__ import annotations

import json
import time

import click
from rich.console import Console
from rich.table import Table

from alert_engine.aggregation import Alert, TimeWindowAggregator
from alert_engine.alert_scoring import AlertScorer
from alert_engine.escalation import EscalationPolicy
from alert_engine.engine import AlertEngine
from alert_engine.symptom_router import SymptomRouter

console = Console()


@click.group()
def cli():
    """alert-engine — 运维告警降噪引擎 CLI"""
    pass


@cli.command()
def demo():
    """运行完整演示（8 阶段管线 + 聚合 + 评分 + 升级）"""
    engine = AlertEngine(window_seconds=300)
    engine.set_dependency("db-primary", "api-gateway")
    engine.set_baseline("api:HighCPU", mean=70.0, std=15.0)

    now = time.time()
    alerts = [
        Alert(id="a1", alert_name="HighCPU", service="api", cluster="prod", severity="p1",
              timestamp=now, labels={"host": "web-01"}, value=85.0),
        Alert(id="a2", alert_name="HighCPU", service="api", cluster="prod", severity="p1",
              timestamp=now + 10, labels={"host": "web-02"}, value=82.0),
        Alert(id="a3", alert_name="DiskFull", service="db-primary", cluster="prod", severity="p2",
              timestamp=now + 30, labels={"mount": "/data"}, value=95.0),
        Alert(id="a4", alert_name="OOM", service="api-gateway", cluster="prod", severity="p0",
              timestamp=now + 60, labels={"pod": "api-7x8dq"}, value=100.0),
    ]

    console.print("[bold cyan]Alert Engine Demo — 8-Stage Pipeline[/bold cyan]\n")
    results = engine.run_pipeline(alerts)

    t = Table(title="Pipeline Results")
    t.add_column("Alert", style="cyan")
    t.add_column("Passed", style="green")
    t.add_column("Action", style="yellow")
    t.add_column("Score", style="magenta")
    t.add_column("Suppressed", style="red")
    for r in results:
        t.add_row(
            r.alert.alert_name,
            "✅" if r.passed else "❌",
            r.action,
            str(r.score) if r.score else "-",
            r.suppressed_by or "-",
        )
    console.print(t)

    # 评分详情
    console.print("\n[bold]Alert Scoring Details[/bold]")
    scorer = AlertScorer()
    for a in alerts:
        s = scorer.score(a)
        console.print(f"  {a.alert_name}: score={s.total_score} action={s.action} confidence={s.confidence}")

    # 升级策略
    console.print("\n[bold]Escalation Policy[/bold]")
    policy = EscalationPolicy.default()
    for sev in ["p0", "p1", "p2"]:
        contact = policy.notify(f"alert-{sev}", sev)
        if contact:
            console.print(f"  {sev.upper()} -> {contact.name} ({contact.channel})")

    # 症状路由
    console.print("\n[bold]Symptom Routing[/bold]")
    router = SymptomRouter.default()
    for a in alerts:
        group = router.route(a.alert_name, a.labels, a.severity)
        if group:
            console.print(f"  {a.alert_name} -> {group.name}: {', '.join(group.members)}")

    # 压缩比
    agg = engine.aggregator
    console.print(f"\n[bold]Compression Ratio: {agg.get_compression_ratio():.1f}x[/bold]")


@cli.command()
@click.option("--alert", required=True, help="Alert name")
@click.option("--severity", default="p1", help="Severity: p0/p1/p2/p3")
@click.option("--service", default="unknown", help="Service name")
@click.option("--value", default=0.0, help="Metric value")
def score(alert: str, severity: str, service: str, value: float):
    """单条告警评分"""
    scorer = AlertScorer()
    a = Alert(id="1", alert_name=alert, service=service, cluster="test",
              severity=severity, timestamp=time.time(), value=value)
    s = scorer.score(a)
    console.print(json.dumps({
        "alert": alert,
        "severity": severity,
        "total_score": s.total_score,
        "action": s.action,
        "confidence": s.confidence,
        "breakdown": {
            "severity": s.severity_score,
            "blast_radius": s.blast_radius_score,
            "baseline": s.baseline_deviation_score,
            "historical": s.historical_score,
        },
    }, indent=2))


def main():
    cli()


if __name__ == "__main__":
    main()
