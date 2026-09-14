# Alert Engine

> 运维告警降噪引擎 — 8 阶段管线 + LLM 摘要 + 症状路由

[![CI](https://github.com/CodeCoreLab/alert-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/CodeCoreLab/alert-engine/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache--2.0-blue)](./LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)

把原始告警按 8 层管线逐层过滤，从"接收量"压到"推送量"，保持零误杀的前提下最大化降噪率。

```
for_min → dedup → silence → mute_timing → dependency_inhibit → inhibit → baseline → event_bus
 (防抖)   (指纹   (时间   (周期条件   (根因压制下游   (级别   (3σ基线   (异步发布
         去重)    静默)    静默)         告警)            抑制)     预判)      事件)
```

---

## 核心特性

| 特性 | 说明 |
|------|------|
| **8 阶段降噪管线** | for_min → dedup → silence → mute_timing → dependency_inhibit → inhibit → baseline → event_bus |
| **时间窗口聚合** | 同一 cluster/service 在窗口内合并为 Incident |
| **告警评分** | severity + 影响面 + 基线偏离 + 历史解决率，量化优先级 |
| **升级策略** | P0/P1/P2/P3 分级自动升级（企微 → 电话 → 短信 → 邮件） |
| **症状路由** | 根据症状特征自动路由到对应处理人/OnCall |
| **LLM 摘要** | 大模型生成事故摘要，支持值班交接 |
| **压缩比指标** | 可解释的降噪率统计 |
| **多源 Adapter** | 支持 Zabbix / n9e / VictoriaMetrics / InfluxDB |

---

## 快速开始

```bash
# 安装
pip install alert-engine

# 运行示例
python -m alert_engine.examples.demo

# 或作为模块使用
from alert_engine import AlertEngine

engine = AlertEngine()
engine.register_adapter("zabbix", ZabbixAdapter(...))
engine.run()
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
- SHA1 指纹（rule_id + host + labels）
- 5 分钟去重窗口，同指纹仅推 1 条

### Stage 2: 时间静默 (Silence)
- 维护窗口自动静默
- 支持 cron 表达式配置

### Stage 3: 周期条件静默 (mute_timing)
- 备份/维护窗口静默
- 条件表达式过滤

### Stage 4: 根因压制下游 (dependency_inhibit)
- 上游故障 → 下游级联告警自动抑制
- 拓扑感知

### Stage 5: 级别抑制 (inhibit)
- 高等级告警触发后，抑制同类型低等级告警

### Stage 6: 3σ 基线预判 (baseline)
- 指标历史基线，3σ 外才告警
- 减少瞬态波动误报

### Stage 7: 异步发布事件 (event_bus)
- 最终通过 event bus 推送
- 支持多渠道（企微/电话/短信/邮件）

---

## Python API

```python
from alert_engine import (
    AlertEngine,
    Alert,
    Incident,
    AlertScorer,
    EscalationPolicy,
    SymptomRouter,
)

# 1. 创建引擎
engine = AlertEngine()

# 2. 注册 Adapter
engine.register_adapter("zabbix", ZabbixAdapter(config))

# 3. 设置升级策略
engine.set_escalation_policy(EscalationPolicy.default())

# 4. 运行
engine.run()
```

---

## 架构

```
alert-engine/
├── src/alert_engine/
│   ├── __init__.py          # 公共 API
│   ├── engine.py            # 主引擎（8 阶段管线编排）
│   ├── aggregation.py       # 时间窗口聚合
│   ├── alert_scoring.py     # 告警评分（severity + 影响面 + 基线 + 历史）
│   ├── escalation.py        # 升级策略（分级联系人链）
│   ├── symptom_router.py    # 症状路由（自动分配 OnCall）
│   ├── incident_summary.py  # 事故摘要（LLM 生成）
│   ├── patch_orchestrator.py # 补丁编排（自动修复）
│   └── cli.py               # CLI 入口
├── tests/
│   ├── test_aggregation.py
│   ├── test_scoring.py
│   └── test_escalation.py
└── examples/
    └── demo.py               # 完整演示
```

---

## 与同类工具对比

| 工具 | 定位 | 差异 |
|------|------|------|
| **alertmanager** | 告警路由/抑制 | 无 LLM 摘要、无评分、无症状路由 |
| **n9e** | 告警规则引擎 | 需完整部署；本引擎可嵌入任意系统 |
| **pagerduty** | 商业 OnCall | 付费；本引擎开源 + 可扩展 |
| **opsgenie** | 商业告警 | 付费；本引擎支持私有化部署 |

---

## License

Apache-2.0
