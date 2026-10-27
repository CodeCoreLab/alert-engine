# 贡献指南

感谢你愿意为 alert-engine 出力。这份文档说明**怎么把改动送进主干**。

## 快速判断表

| 你的改动 | 需要做什么 |
|---|---|
| 修 Bug | 先写一个会失败的测试，再改实现。提交信息写「现象 → 根因 → 修法」 |
| 加功能 | 先在 Issue 里说清「想解决什么问题」，避免方向跑偏后返工 |
| 改降噪阈值 / 匹配规则 / 基线算法 | **必须在 PR 里说明行为差异与依据** —— 这直接影响线上告警量 |
| 改文档 | 同步检查 README 承诺的 API 与实际是否一致（历史上出过一次不一致） |
| 只想改措辞 | 直接改，不必先开 Issue |

## 开发环境

```bash
git clone https://github.com/CodeCoreLab/alert-engine.git
cd alert-engine
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -e ".[dev]"
```

需要 Python **3.10+**（用了 `X | Y` 类型语法与 `tuple[...]` 泛型下标）。

## 跑测试与静态检查

```bash
pytest tests/ -v --tb=short   # 全部测试
pytest tests/ -v -k baseline   # 只跑某个主题
ruff check src/ tests/         # 静态检查
```

**两条命令都必须通过**再提 PR。CI 用的就是这两条。

## 架构约定

```
src/alert_engine/
├── types.py              # 数据模型 + 评分器（Alert/Incident/AlertScorer/action_for_score）
├── engine.py             # 8 阶段管线编排
├── escalation.py         # 升级策略
├── symptom_router.py     # 症状路由
├── incident_summary.py   # 事故摘要
├── patch_orchestrator.py # 补丁编排
├── adapters.py           # 采集适配器接口
├── memory.py             # SQLite 记忆存储
└── cli.py                # CLI 入口
```

### 三条硬约定

1. **action 判定只有一处**：`types.action_for_score()`。
   不要在任何模块里另写阈值 —— 历史上 `scorer` 用 7.0、`engine` 用 8.0，
   同一条告警在两处得到不同 action。
2. **规则匹配走 `AlertEngine._match_rule()`**：
   顶层字段（service/alert_name/cluster/severity/host）优先于 labels。
   新增匹配能力改这一个方法，不要各阶段各写一套。
3. **模块导入方向单向**：`types.py` 不导入任何其他模块；
   其他模块可导入 `types.py`。`types.py` 保持零内部依赖。

## 提交信息

用中文，格式：

```
<type>(<scope>): <一句话>

<为什么改 / 现象是什么>
```

`type` 取值：`fix` / `feat` / `refactor` / `docs` / `test` / `chore` / `perf`

例：

```
fix(engine): 修复规则匹配无法命中告警顶层字段

match 条件原先只在 alert.labels 里查找，
写 {"service": "backup"} 永远匹配不到 —— 静默规则形同虚设。
现同时支持 service/alert_name/cluster/severity/host。
```

**描述当前行为，不写「移除了之前的……」**。

## PR 要求

- 关联 Issue 编号（`Closes #123`）
- 破坏性变更用 `BREAKING CHANGE:` 开头单独一段
- 改降噪行为时贴出改动前后的对比数据
- 勾选 PR 模板里的自检项

## 报告 Bug

用 [Bug 反馈模板](.github/ISSUE_TEMPLATE/bug_report.yml)。
降噪行为异常时，请附上告警样本（`labels` / `severity` / `value`）——
没有样本的降噪问题很难定位。

**安全问题不要用公开 Issue**，见 [SECURITY.md](SECURITY.md)。

## 行为准则

参与即表示同意 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。
