"""套件自身的单元测试。

重点不是测 smolagents，而是测「判定逻辑是否可靠」——
否则套件给出的 PASS/FAIL 也不可信。
"""

from __future__ import annotations

import os

import pytest

from smolagents_audit.model import CaseResult, Report, Status
from smolagents_audit.sandbox_suite import SandboxSuite


@pytest.fixture(scope="module")
def suite():
    s = SandboxSuite()
    yield s
    s.cleanup()


@pytest.fixture(scope="module")
def results(suite):
    return {r.case_id: r for r in suite.run()}


# ---------- 判定逻辑 ----------


def test_basic_isolation_all_blocked(results):
    """A 组：未授权时的高危操作必须全部被拦。"""
    for cid in ["A1", "A2", "A3", "A4", "A5", "A6", "A7"]:
        assert cid in results, f"缺少用例 {cid}"
        assert results[cid].status == Status.IMPLEMENTED, (
            f"{cid} 未被拦截：{results[cid].evidence}"
        )


def test_authorized_lib_write_is_flagged(results):
    """B1/B2：授权 pandas/numpy 后能写任意路径，必须被标为 MISMATCH。"""
    for cid in ["B1", "B2"]:
        r = results[cid]
        assert r.detail["file_touched"] is True, f"{cid} 未真的写文件，用例失效"
        assert r.status == Status.MISMATCH, f"{cid} 应标 MISMATCH，实际 {r.status}"


def test_authorized_lib_read_is_flagged(results):
    """B3：授权 pandas 后能读任意文件。"""
    r = results["B3"]
    assert r.status == Status.MISMATCH
    assert "(1, 3)" in r.evidence


def test_submodule_access_still_blocked(results):
    """B4：pandas.io 子模块访问应被拦（与 B1-B3 形成对照）。"""
    r = results["B4"]
    assert r.status == Status.IMPLEMENTED


def test_os_system_executes(results):
    """E1/E2：授权后系统命令真的执行了，必须被标 MISMATCH。"""
    for cid in ["E1", "E2"]:
        r = results[cid]
        assert r.detail["cmd_ran"] is True, f"{cid} 命令未真的执行，用例失效"
        assert r.status == Status.MISMATCH


def test_memory_not_limited(results):
    """D1：1GB 分配成功，说明无内存上限。"""
    r = results["D1"]
    assert "1000000000" in r.evidence


def test_escalation_chain_complete(results):
    """X 组：授权升级链三步都要走通。"""
    assert results["X1"].detail["raw"]["ok"] is False, "X1 应被拦截"
    assert results["X2"].detail["raw"]["ok"] is True, "X2 授权后应放行"
    assert results["X3"].detail["cmd_ran"] is True, "X3 应真的执行命令"


# ---------- 报告逻辑 ----------


def test_report_verdict_fail_on_mismatch():
    r = Report(subject="x", version="1", environment={})
    r.add(CaseResult("A1", "c", Status.MISMATCH, "e"))
    assert r.verdict() == "FAIL"


def test_report_verdict_pass_with_gaps():
    r = Report(subject="x", version="1", environment={})
    r.add(CaseResult("A1", "c", Status.IMPLEMENTED, "e"))
    r.add(CaseResult("A2", "c", Status.GAP, "e"))
    assert r.verdict() == "PASS_WITH_GAPS"


def test_report_verdict_pass():
    r = Report(subject="x", version="1", environment={})
    r.add(CaseResult("A1", "c", Status.IMPLEMENTED, "e"))
    assert r.verdict() == "PASS"


def test_report_json_roundtrip():
    import json

    r = Report(subject="x", version="1", environment={"python": "3.13"})
    r.add(CaseResult("A1", "c", Status.PARTIAL, "e", {"k": "v"}))
    data = json.loads(r.to_json())
    assert data["cases"][0]["status"] == "PARTIAL"
    assert data["verdict"] == "PASS_WITH_GAPS"


# ---------- 用例集完整性 ----------


def test_no_duplicate_case_ids(results):
    assert len(results) == len(set(results)), "用例 ID 有重复"


def test_all_cases_have_evidence(results):
    for cid, r in results.items():
        assert r.evidence, f"{cid} 缺证据"
        assert len(r.evidence) > 20, f"{cid} 证据过短"
