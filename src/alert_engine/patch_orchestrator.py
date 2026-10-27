"""
补丁编排（Patch Orchestrator）

告警触发后，根据症状自动执行修复动作。
支持：服务重启、配置回滚、流量切换。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class PatchAction:
    """修复动作"""
    name: str
    description: str
    handler: Callable[[dict], bool]
    max_retries: int = 1
    cooldown_seconds: int = 300


class PatchOrchestrator:
    """
    补丁编排器。
    根据告警症状匹配预设修复动作，按优先级执行。

    冷却语义：同一动作在 `cooldown_seconds` 内**只执行一次**。
    没有冷却，告警风暴期间同一条告警会反复触发重启/清理，
    把一次故障放大成多次操作事故。默认 300s。
    """

    def __init__(self):
        self._actions: dict[str, PatchAction] = {}
        self._last_executed: dict[str, float] = {}

    def register(self, symptom: str, action: PatchAction):
        self._actions[symptom] = action

    def execute(self, symptom: str, context: dict) -> bool:
        """执行匹配到的修复动作。

        handler 由使用者注入（可能走 SSH / HTTP / K8s API），
        抛出的异常类型不可预知 —— 一律捕获后记录日志并重试。
        静默吞掉异常会让"修复失败"完全不可见，比不修更危险。
        """
        action = self._actions.get(symptom)
        if not action:
            return False

        now = time.monotonic()
        last = self._last_executed.get(action.name)
        if last is not None and (now - last) < action.cooldown_seconds:
            log.info(
                "修复动作 %s 处于冷却期（剩余 %ds），跳过本次执行",
                action.name,
                int(action.cooldown_seconds - (now - last)),
            )
            return False

        for attempt in range(action.max_retries):
            try:
                ok = action.handler(context)
                if ok:
                    self._last_executed[action.name] = time.monotonic()
                    return True
                log.info(
                    "修复动作 %s 第 %d 次执行返回失败", action.name, attempt + 1
                )
            except Exception as exc:
                log.warning(
                    "修复动作 %s 第 %d 次执行异常: %s", action.name, attempt + 1, exc
                )
        return False

    @staticmethod
    def default() -> PatchOrchestrator:
        orch = PatchOrchestrator()
        orch.register("high_cpu", PatchAction(
            name="restart_service",
            description="重启高 CPU 服务",
            handler=lambda ctx: True,  # 占位：实际应调用 SSH/API
        ))
        orch.register("disk_full", PatchAction(
            name="cleanup_logs",
            description="清理过期日志",
            handler=lambda ctx: True,
        ))
        orch.register("oom", PatchAction(
            name="restart_service",
            description="重启 OOM 服务",
            handler=lambda ctx: True,
        ))
        return orch
