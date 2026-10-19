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


# ---------- 跨平台输出编码 ----------


class _NarrowStream:
    """只接受 ASCII 的输出流，模拟 Windows CI 的 cp1252 控制台。

    真实 stdout 是 TextIOWrapper；这里故意在 write 时抛 UnicodeEncodeError，
    因为 reconfigure() 无法作用于自定义流，正好用来验证兜底路径。
    """

    encoding = "ascii"

    def __init__(self) -> None:
        self.chunks: list[str] = []

    def write(self, s: str) -> int:
        s.encode("ascii")  # 非 ASCII 就抛 UnicodeEncodeError
        self.chunks.append(s)
        return len(s)

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False

    def reconfigure(self, **kwargs) -> None:
        # 自定义流不支持 reconfigure，模拟 AttributeError 分支
        raise AttributeError("cannot reconfigure")


def test_cli_survives_non_utf8_console(monkeypatch):
    """报告含中文，必须能在窄编码控制台下打印而不崩。

    Windows CI 默认代码页 cp1252，曾因此让 audit 整体退出 1 —— 一个与被审计
    对象完全无关的失败。这里用只接受 ASCII 的流复现。
    """
    from smolagents_audit.cli import main

    narrow = _NarrowStream()
    monkeypatch.setattr("sys.stdout", narrow)

    # 不传 --quiet：必须真的走打印路径
    rc = main(["--claims"])
    assert rc == 0
    assert narrow.chunks, "应当有输出；否则没测到打印路径"
    # 兜底后写出的内容必须能过 ASCII 编码
    "".join(narrow.chunks).encode("ascii")


def test_narrow_stream_would_break_without_guard():
    """对照组：证明上面的测试有区分力。

    直接往窄流写中文必须抛错，否则 test_cli_survives_non_utf8_console 是空转。
    """
    import pytest

    narrow = _NarrowStream()
    with pytest.raises(UnicodeEncodeError):
        narrow.write("有效代码 1255 行")


def test_render_console_contains_non_ascii():
    """确认报告里确实有非 ASCII 内容——否则编码测试无意义。"""
    from smolagents_audit.model import CaseResult, Report, Status
    from smolagents_audit.reporters.render import render_console

    r = Report(subject="x", version="1", environment={"python": "3.13", "platform": "w", "docker": False, "deno": False})
    r.add(CaseResult("C1", "「约 1,000 行」", Status.PARTIAL, "有效代码 1255 行"))
    text = render_console(r)
    assert any(ord(ch) > 127 for ch in text), "报告应含中文，否则编码测试无意义"


# ---------- 回归门禁 ----------


def test_baseline_lists_all_current_mismatches():
    """基线必须覆盖当前所有 MISMATCH，否则 CI 首次就会误报为回归。"""
    from smolagents_audit.baseline import load
    from smolagents_audit.claim_suite import ClaimSuite
    from smolagents_audit.sandbox_suite import SandboxSuite

    known = set(load()["known_mismatches"])

    claims = ClaimSuite().run()
    suite = SandboxSuite()
    try:
        sandbox = suite.run()
    finally:
        suite.cleanup()

    current = {c.case_id for c in claims + sandbox if c.status.value == "MISMATCH"}
    unregistered = current - known
    assert not unregistered, (
        f"以下 MISMATCH 未登记到 baseline.json，CI 会误报为回归：{sorted(unregistered)}"
    )


def test_baseline_has_no_stale_entries():
    """基线不应包含已经不存在的用例 ID，否则会掩盖同名新问题。"""
    from smolagents_audit.baseline import load
    from smolagents_audit.claim_suite import ClaimSuite
    from smolagents_audit.sandbox_suite import SandboxSuite

    known = set(load()["known_mismatches"])
    suite = SandboxSuite()
    try:
        ids = {c.case_id for c in ClaimSuite().run() + suite.run()}
    finally:
        suite.cleanup()

    stale = known - ids
    assert not stale, f"baseline.json 中有已不存在的用例：{sorted(stale)}"
