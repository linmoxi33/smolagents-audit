"""核心数据结构：判定结果、证据、报告。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class Status(str, Enum):
    """能力核验状态。

    刻意区分「实现」与「有效」——这是本项目存在的理由。
    """

    IMPLEMENTED = "IMPLEMENTED"
    """源码有实现，且行为符合声明，有测试保护。"""

    PARTIAL = "PARTIAL"
    """有实现，但只在部分条件下成立（如仅特定平台 / 特定参数）。"""

    INTERFACE_ONLY = "INTERFACE_ONLY"
    """只有 API 壳子 / 抛 NotImplementedError / 依赖外部服务未配置。"""

    UNVERIFIABLE = "UNVERIFIABLE"
    """本机环境无法验证（缺 docker / 无凭证），且无法用静态证据替代。"""

    MISMATCH = "MISMATCH"
    """源码与宣传直接矛盾（如宣传的类不存在、宣称的行数不符）。"""

    GAP = "GAP"
    """实现存在且有效，但缺少测试保护（变异测试未被捕获）。"""


@dataclass
class CaseResult:
    """单个核验用例的结果。"""

    case_id: str
    claim: str
    status: Status
    evidence: str
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class Report:
    """一次完整核验的报告。"""

    subject: str
    version: str
    environment: dict[str, Any]
    cases: list[CaseResult] = field(default_factory=list)

    def add(self, r: CaseResult) -> None:
        self.cases.append(r)

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for c in self.cases:
            out[c.status.value] = out.get(c.status.value, 0) + 1
        return out

    def verdict(self) -> str:
        """整体结论。

        FAIL           —— 存在与宣传直接矛盾的能力（MISMATCH）
        PASS_WITH_GAPS —— 无矛盾，但有未验证/部分实现/缺测试保护的项
        PASS           —— 全部 IMPLEMENTED
        """
        s = {c.status for c in self.cases}
        if Status.MISMATCH in s:
            return "FAIL"
        if s & {Status.GAP, Status.PARTIAL, Status.UNVERIFIABLE, Status.INTERFACE_ONLY}:
            return "PASS_WITH_GAPS"
        return "PASS"

    def to_dict(self) -> dict:
        return {
            "subject": self.subject,
            "version": self.version,
            "environment": self.environment,
            "verdict": self.verdict(),
            "counts": self.counts(),
            "cases": [c.to_dict() for c in self.cases],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)
