"""
告警升级策略（Escalation Policy）

按 severity 分级升级，未确认自动升级到更高层级联系人。

升级规则：
- P0: 电话+短信 → 5min 未确认 → 总监 → 1h 未确认 → CTO
- P1: 电话 → 15min 未确认 → 经理 → 2h 未确认 → 总监
- P2: 企微 → 30min 未确认 → 电话 → 2h 未确认 → 经理
- P3: 企微 → 1h 未确认 → 邮件 → 4h 未确认 → 经理
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class EscalationContact:
    """升级联系人"""
    name: str
    wecom_userid: str
    phone: str = ""
    email: str = ""
    channel: str = "wecom"  # wecom / phone / sms / email


@dataclass
class EscalationRule:
    """升级规则"""
    severity: str  # p0/p1/p2/p3
    steps: list[EscalationContact]
    step1_timeout: int = 5
    step2_timeout: int = 15
    step3_timeout: int = 60
    repeat_interval: int = 300


@dataclass
class AlertEscalationState:
    """单条告警的升级状态"""
    alert_id: str
    severity: str
    current_step: int = 0
    first_alert_time: float = 0.0
    last_contact_time: float = 0.0
    current_contact: EscalationContact | None = None
    escalated: bool = False
    acknowledged: bool = False
    acknowledged_time: float = 0.0


class EscalationPolicy:
    """
    告警升级策略引擎。
    """

    def __init__(self, rules: dict[str, EscalationRule] | None = None):
        self.rules = rules or self._default_rules()
        self._states: dict[str, AlertEscalationState] = {}

    @staticmethod
    def default() -> EscalationPolicy:
        return EscalationPolicy(EscalationPolicy._default_rules())

    @staticmethod
    def _default_rules() -> dict[str, EscalationRule]:
        return {
            "p0": EscalationRule(
                severity="p0",
                steps=[
                    EscalationContact(name="OnCall", wecom_userid="oncall_p0", phone="+86-xxx", channel="phone"),
                    EscalationContact(name="Manager", wecom_userid="mgr_p0", channel="wecom"),
                    EscalationContact(name="CTO", wecom_userid="cto", channel="phone"),
                ],
                step1_timeout=5,
                step2_timeout=15,
                step3_timeout=60,
            ),
            "p1": EscalationRule(
                severity="p1",
                steps=[
                    EscalationContact(name="OnCall", wecom_userid="oncall_p1", channel="wecom"),
                    EscalationContact(name="Manager", wecom_userid="mgr_p1", channel="phone"),
                ],
                step1_timeout=15,
                step2_timeout=120,
            ),
            "p2": EscalationRule(
                severity="p2",
                steps=[
                    EscalationContact(name="OnCall", wecom_userid="oncall_p2", channel="wecom"),
                    EscalationContact(name="Manager", wecom_userid="mgr_p2", channel="phone"),
                ],
                step1_timeout=30,
                step2_timeout=120,
            ),
            "p3": EscalationRule(
                severity="p3",
                steps=[
                    EscalationContact(name="OnCall", wecom_userid="oncall_p3", channel="wecom"),
                    EscalationContact(name="Manager", wecom_userid="mgr_p3", channel="email"),
                ],
                step1_timeout=60,
                step2_timeout=240,
            ),
        }

    def get_rule(self, severity: str) -> EscalationRule | None:
        return self.rules.get(severity)

    def notify(self, alert_id: str, severity: str) -> EscalationContact | None:
        """获取当前应通知的联系人，返回 None 表示已确认/无需升级。"""
        if alert_id not in self._states:
            rule = self.get_rule(severity)
            if not rule or not rule.steps:
                return None
            self._states[alert_id] = AlertEscalationState(
                alert_id=alert_id,
                severity=severity,
                current_step=0,
                first_alert_time=time.time(),
                last_contact_time=time.time(),
                current_contact=rule.steps[0],
            )
        state = self._states[alert_id]
        if state.acknowledged:
            return None
        rule = self.get_rule(severity)
        if not rule:
            return None
        elapsed = time.time() - state.first_alert_time
        timeouts = [rule.step1_timeout * 60, rule.step2_timeout * 60, rule.step3_timeout * 60]
        for i, t in enumerate(timeouts):
            if elapsed < t and i < len(rule.steps):
                state.current_step = i
                state.current_contact = rule.steps[i]
                return rule.steps[i]
        # 全部超时，返回最高级
        state.escalated = True
        return rule.steps[-1] if rule.steps else None
