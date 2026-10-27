# Changelog

本文件记录 alert-engine 的重要变更。
格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [0.3.0] - 2026-10-27

### 修复

- **修复模块导入断裂导致包完全无法导入**：`engine.py` / `cli.py` 引用了
  `aggregation` / `alert_scoring` 两个已被重构删除的模块，`incident_summary.py`
  同理。0.2.0 之后 `import alert_engine` 直接抛 `ModuleNotFoundError`，
  项目处于不可运行状态。
- **恢复重构中被误删的 4 个模块**：`escalation`（升级策略）、`symptom_router`
  （症状路由）、`incident_summary`（事故摘要）、`patch_orchestrator`（补丁编排）。
  这四个模块是 README 明确承诺的能力，删除模块时未同步清理引用方。
- **修复规则匹配无法命中告警顶层字段**：`match` 条件原先只在 `alert.labels`
  里查找，写 `{"service": "backup"}` 永远匹配不到 —— 静默规则形同虚设。
  现同时支持 `service` / `alert_name` / `cluster` / `severity` / `host`
  五个顶层字段。
- **修复 action 判定阈值双轨**：`AlertScorer` 用 7.0/4.0 判定，
  `AlertEngine._determine_action` 用 8.0/4.0 判定，同一条告警在两处得到
  不同的 action。现统一由 `types.action_for_score` 一处定义。
- **修复基线 EWMA 只在放行时更新**：被 3σ 拦截的正常样本从不参与更新，
  基线只被异常值污染，均值持续漂移。现无论是否放行都更新。
- **P0 告警不再被根因抑制**：根因抑制按 service 匹配、不区分告警类型，
  上游 service 故障会连带压掉下游**所有**告警，包括与根因无关的独立 P0 故障
  （例：上游 DB 抖动掩盖下游 OOM）。P0 静默的代价（漏报最高级故障）
  远大于收益（少一条噪音），故 P0 豁免该阶段。P1 及以下维持原行为。

### 新增

- `AlertEngine.register_adapter()` / `collect()` / `run()` / `health()` ——
  补齐 README 承诺的 Adapter 接入链路。单适配器失败不影响其余适配器。
- `AlertEngine.set_escalation_policy()` —— 运行时替换升级策略。
- `types.action_for_score()` —— action 判定的唯一权威源。
- **`PatchOrchestrator` 冷却期防抖生效**：`cooldown_seconds` 此前是**声明了
  但从未被读取**的死字段 —— 使用者以为有冷却保护、实际没有，告警风暴期间
  会反复执行同一修复动作，把一次故障放大成多次操作事故。现按动作名
  生效：从执行成功起算 `cooldown_seconds` 内不再执行，失败不占冷却。
- 5 项补丁编排测试（冷却拦截 / 冷却到期 / 异常不抛穿 / 重试至成功 / 未知症状）。

### 变更

- `__version__` 提升至 0.3.0，`__all__` 补齐全部公共 API（23 项）。
- **`pyproject.toml` 显式锁定 ruff 规则集**：原先未声明 `select`，实际生效的
  规则集随 ruff 版本漂移（0.6 → 0.16 差异显著），CI 会出现"今天绿、
  升个 ruff 就红"。现固定为 `E/F/W/I/B/UP/C4/SIM/RUF`。
- 静默/摘要相关时间戳改用**带时区**的本地时间（`astimezone().isoformat()`），
  消除跨时区排障时的时间歧义。
- 事故摘要与补丁编排的异常处理补齐日志，不再静默吞掉异常 ——
  「修复失败完全不可见」比「不修」更危险。
- README 新增「补丁编排：冷却期防抖」一节。

## [0.2.0] - 2026-09-15

### 变更

- 重构：合并 `aggregation.py` + `alert_scoring.py` 为 `types.py`。
- 重构：新增 `adapters.py`（Zabbix / N9e / InfluxDB / GenericJSON）。
- 新增：`memory.py` —— SQLite 告警记忆持久化。
- 重构：简化 `engine.py`（8 阶段管线 + 过期清理）。
- **破坏性变更**：移除 `escalation` / `symptom_router` / `incident_summary` /
  `patch_orchestrator` 四个模块（**该次移除不完整，导致 0.2.0 不可运行，
  已在 0.3.0 修复**）。

## [0.1.0] - 2026-09-14

### 新增

- 初始版本 —— 8 阶段降噪管线 + 告警评分 / 升级策略 / 症状路由 +
  LLM 摘要 + 补丁编排，13 项测试通过。

[Unreleased]: https://github.com/CodeCoreLab/alert-engine/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/CodeCoreLab/alert-engine/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/CodeCoreLab/alert-engine/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/CodeCoreLab/alert-engine/releases/tag/v0.1.0
