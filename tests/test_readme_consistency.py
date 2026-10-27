"""README 承诺与代码实现的一致性检查。

背景：v0.2.0 的 README 承诺了 register_adapter / run / set_escalation_policy
等 API 与 escalation / symptom_router 等模块，但代码里并不存在 —— 文档与实现脱节。
本测试把「README 里写的公开 API 必须真的能用」变成可检查的断言。

检查分两层：
  - 结构层：README 中「```python」代码块里 from alert_engine import X 的 X 必须可导入
  - 行为层：README 承诺的关键 API 必须真的能调用（不只 import 成功）
"""

from __future__ import annotations

import re
from pathlib import Path

README = Path(__file__).resolve().parent.parent / "README.md"


def _read_readme() -> str:
    return README.read_text(encoding="utf-8")


def _imported_names(text: str) -> set[str]:
    """提取所有 `from alert_engine import (...)` 里的名字。"""
    names: set[str] = set()
    for m in re.finditer(r"from\s+alert_engine\s+import\s+(.+)", text):
        chunk = m.group(1)
        # 去掉括号内换行后的说明
        chunk = chunk.split("#")[0]
        for part in chunk.replace("(", " ").replace(")", " ").split(","):
            part = part.strip()
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part):
                names.add(part)
    return names


class TestReadmeImportConsistency:
    def test_readme_exists(self):
        assert README.exists(), f"README 不存在: {README}"

    def test_all_readme_imports_resolve(self):
        """README 代码块里 import 的每个名字都必须真的能导入。"""
        import alert_engine

        names = _imported_names(_read_readme())
        assert names, "README 里没解析出任何 import 语句，检查测试正则"

        missing = sorted(n for n in names if not hasattr(alert_engine, n))
        assert not missing, f"README 提到但 alert_engine 未导出: {missing}"

    def test_package_all_entries_importable(self):
        """__all__ 里列的每个名字都必须真的存在。"""
        import alert_engine

        missing = sorted(n for n in alert_engine.__all__ if not hasattr(alert_engine, n))
        assert not missing, f"__all__ 列了不存在的名字: {missing}"

    def test_all_covers_public_modules(self):
        """所有模块的公共类都应出现在 __all__ 里。"""
        import alert_engine

        for mod in ("types", "engine", "escalation", "symptom_router",
                    "incident_summary", "patch_orchestrator", "adapters", "memory"):
            m = __import__(f"alert_engine.{mod}", fromlist=["*"])
            for name in getattr(m, "__all__", []) or []:
                assert name in alert_engine.__all__, f"{mod}.{name} 未导出到 __all__"


class TestReadmeApiBehaves:
    """README 承诺的关键 API 必须真的能调用（不只 import 成功）。"""

    def test_register_adapter_run_health(self):
        """README「接入采集适配器」一节承诺的三个 API。"""
        from alert_engine import AlertEngine

        class _A:
            def fetch(self, since=None):
                import time

                from alert_engine import Alert
                return [Alert(id="1", alert_name="x", service="s", cluster="c",
                              severity="p1", timestamp=time.time())]

            def health(self):
                return {"status": "ok"}

        engine = AlertEngine()
        engine.register_adapter("a", _A())
        results = engine.run()
        assert len(results) == 1
        h = engine.health()
        assert h["status"] == "ok"
        assert "a" in h["adapters"]

    def test_set_escalation_policy(self):
        from alert_engine import AlertEngine, EscalationPolicy

        engine = AlertEngine()
        policy = EscalationPolicy.default()
        engine.set_escalation_policy(policy)
        assert engine.escalation_policy is policy

    def test_set_dependency_and_baseline(self):
        from alert_engine import AlertEngine

        engine = AlertEngine()
        engine.set_dependency("db", "api")
        engine.set_baseline("api:HighCPU", mean=70.0, std=15.0)
        assert engine._dependency_map["api"] == "db"
        assert engine._baselines["api:HighCPU"] == (70.0, 15.0)

    def test_pipeline_result_fields(self):
        """README 示例里用到的 PipelineResult 字段必须存在。"""
        import time

        from alert_engine import Alert, AlertEngine

        engine = AlertEngine()
        r = engine.feed(Alert(id="1", alert_name="HighCPU", service="api",
                              cluster="prod", severity="p1",
                              timestamp=time.time(), value=85.0))
        for attr in ("passed", "action", "score", "suppressed_by"):
            assert hasattr(r, attr), f"PipelineResult 缺字段 {attr}"

    def test_score_thresholds_match_readme(self):
        """README 声称 ≥7.0 → immediate、≥4.0 → incident。"""
        from alert_engine.types import action_for_score

        assert action_for_score(7.0) == "immediate"
        assert action_for_score(4.0) == "incident"
        assert action_for_score(3.99) == "observe"

    def test_readme_does_not_claim_unimplemented_paths(self):
        """README 不该再出现「python -m alert_engine.examples.demo」这类不存在的路径。"""
        text = _read_readme()
        assert "alert_engine.examples" not in text, (
            "README 引用了不存在的 examples 模块路径"
        )
