# Alert Engine

> 运维告警降噪引擎 — 8 阶段管线 + 评分 + 分级升级 + 症状路由

[![CI](https://github.com/CodeCoreLab/alert-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/CodeCoreLab/alert-engine/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache--2.0-blue)](./LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)

把原始告警按 8 层管线逐层过滤，从"接收量"压到"推送量"，在**零误杀优先**的前提下最大化降噪率。

```
for_min → dedup → silence → mute_timing → dependency_inhibit → inhibit → baseline → event_bus
 (防抖)   (指纹   (时间   (周期条件   (根因压制下游   (级别   (3σ基线   (异步发布
         去重)    静默)    静默)         告警)            抑制)     预判)      事件)
```

---

## 核心特性

| 特性 | 说明 | 状态 |
|------|------|:----:|
| **8 阶段降噪管线** | for_min → dedup → silence → mute_timing → dependency_inhibit → inhibit → baseline → event_bus | ✅ |
| **时间窗口聚合** | 同一 cluster/service 在窗口内合并为 Incident | ✅ |
| **告警评分** | severity + 影响面 + 基线偏离 + 历史解决率，量化优先级 | ✅ |
| **分级升级策略** | P0/P1/P2/P3 分级升级（企微 → 电话 → 短信 → 邮件） | ✅ |
| **症状路由** | 根据症状特征自动路由到对应 OnCall 组 | ✅ |
| **事故摘要** | Incident 结构化摘要接口（LLM 接入位已预留） | ⚠️ 接口就绪，未接具体模型 |
| **补丁编排** | 预定义修复动作的编排执行（含冷却期防抖） | ✅ |
| **多源 Adapter** | Zabbix / n9e / InfluxDB / GenericJSON | ⚠️ 接口 + 占位实现，未接真实 API |
| **记忆存储** | SQLite 持久化告警处理历史 | ✅ |
| **压缩比指标** | 可解释的降噪率统计 | ✅ |

> ⚠️ 标记「接口就绪 / 占位实现」的条目尚未对接真实后端，
> 接入前请看 [ROADMAP.md](ROADMAP.md) 的计划方向。

---

## 快速开始

```bash
pip install alert-engine
```

### 作为库使用

```python
from alert_engine import AlertEngine, Alert

engine = AlertEngine(window_seconds=300)
engine.set_dependency("db-primary", "api-gateway")   # 上游故障时抑制下游
engine.set_baseline("api:HighCPU", mean=70.0, std=15.0)

alert = Alert(
    id="a1", alert_name="HighCPU", service="api", cluster="prod",
    severity="p1", timestamp=time.time(),
    labels={"host": "web-01"}, value=85.0,
)
result = engine.feed(alert)

print(result.passed, result.action, result.score, result.suppressed_by)
# True incident 6.7 None
```

### 接入采集适配器

```python
from alert_engine import AlertEngine, GenericJSONAdapter

engine = AlertEngine()
engine.register_adapter("json", GenericJSONAdapter({
    "url": "http://monitor.internal/api/alerts",
    "headers": {"Authorization": f"Bearer {os.environ['ALERT_API_TOKEN']}"},
}))

results = engine.run()          # 拉取 → 过滤 → 聚合 → 评分
print(engine.health())          # 各适配器自检 + 活跃 Incident 数
```

单个适配器拉取失败**不影响**其余适配器 —— 一个数据源挂掉不该让整轮采集归零。

### CLI

```bash
alert-engine demo                        # 完整演示
alert-engine score --alert HighCPU --severity p0
```

---

## 8 阶段管线详解

### Stage 0: for_min 差异化防抖

| Severity | 默认防抖 |
|---|---|
| P0 (critical) | 1 min |
| P1 (warning) | 2 min |
| P2 (major) | 5 min |
| P3 (minor) | 10 min |
| info | 15 min |

### Stage 1: fingerprint 去重

- SHA1 指纹（`alert_name` + `host`/`service` + labels 排序拼接）
- 5 分钟去重窗口，同指纹仅放行 1 条

### Stage 2: 时间静默 (Silence)

- 维护窗口自动静默（`until` 时间戳）
- 规则匹配支持告警顶层字段与 labels

### Stage 3: 周期条件静默 (mute_timing)

- 备份 / 维护窗口静默
- cron 表达式（支持 `*` / `,` / `-` / `/` 的分位匹配）+ 条件过滤

### Stage 4: 根因压制下游 (dependency_inhibit)

- 上游故障 → 下游级联告警自动抑制
- 依赖拓扑由 `set_dependency(parent, child)` 声明

### Stage 5: 级别抑制 (inhibit)

- 同名告警存在未 resolved 的更高等级时，抑制低等级

### Stage 6: 3σ 基线预判 (baseline)

- 指标历史基线，3σ **内**判为正常波动（拦截），3σ 外才告警
- EWMA 动态更新（α=0.1）。被拦截的正常样本**同样参与**基线更新 ——
  否则基线只会被异常值污染

### Stage 7: 异步发布事件 (event_bus)

- 通过全部阶段的告警进入聚合与评分，产出 `action`

---

## 规则匹配语义

静默与周期静默的 `match` 条件同时支持**告警顶层字段**与 **labels**：

```python
# 顶层字段（service / alert_name / cluster / severity / host）
{"match": {"service": "backup"}}

# labels
{"match": {"mount": "/data"}}
```

同名键**顶层字段优先** —— 避免「规则写 service 却被 labels 里的同名标签覆盖」。

---

## 评分与 action

| 分数 | action | 含义 |
|---|---|---|
| ≥ 7.0 | `immediate` | 立即处理 |
| ≥ 4.0 | `incident` | 进入事件流程 |
| < 4.0 | `observe` | 观察 |

阈值只有一处定义：`types.action_for_score()`。评分器与管线都调它 ——
避免两处阈值漂移导致同一条告警得到不同的 action。

---

## Python API

```python
from alert_engine import (
    AlertEngine, Alert, Incident, AlertScorer,
    EscalationPolicy, SymptomRouter, IncidentSummarizer, PatchOrchestrator,
)
```

| 导出 | 用途 |
|------|------|
| `AlertEngine` | 主引擎，8 阶段管线编排 |
| `Alert` / `Incident` | 数据模型 |
| `TimeWindowAggregator` | 时间窗口聚合 |
| `AlertScorer` | 告警评分 |
| `EscalationPolicy` | 分级升级策略 |
| `SymptomRouter` | 症状路由 |
| `IncidentSummarizer` | 事故摘要 |
| `PatchOrchestrator` | 补丁编排 |
| `BaseAdapter` 及 4 个实现 | 采集适配器 |
| `AlertMemory` | SQLite 记忆存储 |

---

## 补丁编排：冷却期防抖

告警风暴期间，同一条告警会反复触发修复动作（重启、清理），
把一次故障放大成多次操作事故。`PatchOrchestrator` 按动作名做冷却：

```python
from alert_engine import PatchOrchestrator
from alert_engine.patch_orchestrator import PatchAction

orch = PatchOrchestrator()
orch.register("high_cpu", PatchAction(
    name="restart_service",
    description="重启高 CPU 服务",
    handler=my_restart_fn,      # 你自己的实现：SSH / HTTP / K8s API
    max_retries=2,
    cooldown_seconds=300,       # 同名动作 300s 内只执行一次
))

orch.execute("high_cpu", {"service": "api"})   # → True，handler 被调用
orch.execute("high_cpu", {"service": "api"})   # → False，冷却期内跳过
```

| 行为 | 说明 |
|------|------|
| 冷却键 | **动作名**（不是症状名）—— 同一动作跨症状也互斥 |
| 冷却计时 | 从**执行成功**那一刻起算；执行失败不占用冷却 |
| 异常处理 | handler 抛出的异常被捕获并记录日志，返回 `False`，不向上抛穿 |
| 重试 | 单次 `execute` 内最多 `max_retries` 次，失败可重试 |
| 默认值 | `max_retries=1`、`cooldown_seconds=300` |

> ⚠️ `PatchOrchestrator.default()` 里的 handler 是**占位实现**（直接返回 `True`），
> 仅用于演示编排流程。接入真实环境必须替换成你自己的执行逻辑 ——
> 见 [ROADMAP.md](ROADMAP.md)。

---

## 架构

```
alert-engine/
├── src/alert_engine/
│   ├── types.py              # 数据模型 + 评分器 + action 判定
│   ├── engine.py             # 主引擎（8 阶段管线编排）
│   ├── escalation.py         # 升级策略（分级联系人链）
│   ├── symptom_router.py     # 症状路由（自动分配 OnCall）
│   ├── incident_summary.py   # 事故摘要
│   ├── patch_orchestrator.py # 补丁编排
│   ├── adapters.py           # 采集适配器接口
│   ├── memory.py             # SQLite 记忆存储
│   └── cli.py                # CLI 入口
├── tests/
│   ├── test_alert_engine.py       # 管线 / 评分 / 升级 / 路由 / 补丁编排
│   └── test_readme_consistency.py # README 与实现的一致性契约
├── examples/
│   └── demo.py                    # 可直接运行的 8 阶段降噪演示
└── .github/
    ├── workflows/ci.yml
    └── ISSUE_TEMPLATE/
```

---

## 开发

```bash
pip install -e ".[dev]"
pytest tests/ -v
ruff check src/ tests/
```

详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## 与同类工具对比

| 工具 | 定位 | 差异 |
|------|------|------|
| **alertmanager** | 告警路由/抑制 | 无评分、无症状路由；本引擎可嵌入任意系统 |
| **n9e** | 告警规则引擎 | 需完整部署；本引擎是库 |
| **pagerduty** | 商业 OnCall | 付费；本引擎开源 + 可扩展 |
| **opsgenie** | 商业告警 | 付费；本引擎支持私有化部署 |

---

## 安全须知

降噪引擎会**丢弃**告警。生产部署前请读 [SECURITY.md](SECURITY.md)：
务必保留原始告警通道，关键业务建议旁路一份不降噪的流。

## License

[Apache-2.0](./LICENSE)
