"""
alert-engine — 记忆桥接模块

可选依赖 mnemosyne，将告警处理结果写入记忆库。
吸收 WorkBuddy 记忆模块思路，实现告警处理历史持久化。

使用方式:
    memory = AlertMemory(path="./alerts.db")
    memory.remember(result)
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from alert_engine.types import Alert, AlertScore, Incident


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class AlertMemoryRecord:
    """告警处理记录"""
    alert_id: str
    alert_name: str
    service: str
    cluster: str
    severity: str
    passed: bool
    suppressed_by: Optional[str]
    score: Optional[float]
    action: str
    stages: List[str]
    incident_key: Optional[str]
    created_at: str = ""


# ---------------------------------------------------------------------------
# 记忆存储
# ---------------------------------------------------------------------------

_DEFAULT_SCHEMA = """\
CREATE TABLE IF NOT EXISTS alert_memories (
    id TEXT PRIMARY KEY,
    alert_id TEXT NOT NULL,
    alert_name TEXT NOT NULL,
    service TEXT NOT NULL,
    cluster TEXT NOT NULL,
    severity TEXT NOT NULL,
    passed INTEGER DEFAULT 0,
    suppressed_by TEXT DEFAULT '',
    score REAL DEFAULT 0,
    action TEXT DEFAULT 'observe',
    stages TEXT DEFAULT '[]',
    incident_key TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_alert_memories_service ON alert_memories(service);
CREATE INDEX IF NOT EXISTS idx_alert_memories_severity ON alert_memories(severity);
CREATE INDEX IF NOT EXISTS idx_alert_memories_created ON alert_memories(created_at);
"""


def _get_conn(db_path: str | Path) -> sqlite3.Connection:
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


class AlertMemory:
    """
    告警记忆存储。

    参数:
        path: SQLite 数据库路径
    """

    def __init__(self, path: str | Path = "./alert_memory.db"):
        self.db_path = Path(path)
        with _get_conn(self.db_path) as c:
            c.executescript(_DEFAULT_SCHEMA)

    def remember(self, result: Any, incident: Optional[Incident] = None) -> str:
        """记录告警处理结果"""
        mem_id = f"alert_{int(time.time() * 1000)}_{result.alert.id}"
        now = datetime.now().isoformat()
        stages_json = json.dumps(result.stages_passed, ensure_ascii=False)
        incident_key = result.incident.root_key if result.incident else ""
        with _get_conn(self.db_path) as c:
            c.execute(
                "INSERT INTO alert_memories "
                "(id, alert_id, alert_name, service, cluster, severity, "
                "passed, suppressed_by, score, action, stages, incident_key, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    mem_id,
                    result.alert.id,
                    result.alert.alert_name,
                    result.alert.service,
                    result.alert.cluster,
                    result.alert.severity,
                    1 if result.passed else 0,
                    result.suppressed_by or "",
                    result.score or 0.0,
                    result.action,
                    stages_json,
                    incident_key,
                    now,
                ),
            )
        return mem_id

    def recall(self, service: str = "", severity: str = "", limit: int = 50) -> List[Dict]:
        """查询历史告警记录"""
        sql = "SELECT * FROM alert_memories WHERE 1=1"
        params: list = []
        if service:
            sql += " AND service=?"
            params.append(service)
        if severity:
            sql += " AND severity=?"
            params.append(severity)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with _get_conn(self.db_path) as c:
            return [dict(r) for r in c.execute(sql, params).fetchall()]

    def stats(self) -> Dict[str, Any]:
        """统计信息"""
        with _get_conn(self.db_path) as c:
            total = c.execute("SELECT COUNT(*) FROM alert_memories").fetchone()[0]
            by_sev = dict(c.execute("SELECT severity, COUNT(*) FROM alert_memories GROUP BY severity").fetchall())
            passed = c.execute("SELECT COUNT(*) FROM alert_memories WHERE passed=1").fetchone()[0]
        return {
            "total": total,
            "passed": passed,
            "suppressed": total - passed,
            "by_severity": by_sev,
        }
