"""命令行入口。

设计目标：用户 clone 下来一条命令就能跑，不需要 LLM API key。

    python -m smolagents_audit              # 全部核验
    python -m smolagents_audit --claims     # 只核验宣传声明
    python -m smolagents_audit --sandbox    # 只测沙箱隔离
    python -m smolagents_audit --json out.json --md out.md
    python -m smolagents_audit --fail-on MISMATCH,GAP   # CI 门禁
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys

from .claim_suite import ClaimSuite
from .model import Report, Status
from .reporters.render import render_console, render_markdown
from .sandbox_suite import SandboxSuite


def _env() -> dict:
    try:
        import smolagents

        ver = smolagents.__version__
    except Exception:  # noqa: BLE001
        ver = "unknown"
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "docker": bool(shutil.which("docker")),
        "deno": bool(shutil.which("deno")),
        "_version": ver,
    }


def _ensure_utf8_stdio() -> None:
    """Make stdout/stderr survive non-UTF-8 consoles.

    On Windows CI the default code page is cp1252, and this report contains
    Chinese text in its evidence strings. Without this, printing the report
    raises UnicodeEncodeError and the whole audit exits 1 — a failure that has
    nothing to do with the thing being audited.
    """
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            # Streams that cannot be reconfigured are handled at print time by
            # _safe_print below.
            pass


def _safe_print(text: str, stream=None) -> None:
    """Print without ever dying on an unencodable character.

    Falls back to backslash-escaped ASCII so the audit's own exit code always
    reflects the audited package, never the console's code page.
    """
    out = stream or sys.stdout
    try:
        print(text, file=out)
    except UnicodeEncodeError:
        enc = getattr(out, "encoding", None) or "ascii"
        print(text.encode(enc, errors="backslashreplace").decode(enc, errors="replace"), file=out)


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdio()
    ap = argparse.ArgumentParser(
        prog="smolagents_audit",
        description="核验 smolagents 的宣传声明与真实能力，并给出可复现证据。",
    )
    ap.add_argument("--claims", action="store_true", help="只核验宣传声明")
    ap.add_argument("--sandbox", action="store_true", help="只测沙箱隔离")
    ap.add_argument("--json", metavar="PATH", help="写出 JSON 报告")
    ap.add_argument("--md", metavar="PATH", help="写出 Markdown 报告")
    ap.add_argument(
        "--fail-on",
        default="",
        metavar="LIST",
        help="命中这些状态时退出码为 1，逗号分隔，如 MISMATCH,GAP",
    )
    ap.add_argument(
        "--fail-on-new",
        action="store_true",
        help="只对 baseline.json 未登记的 MISMATCH 失败（已知问题不算回归）",
    )
    ap.add_argument("--quiet", action="store_true", help="不打印终端报告")
    args = ap.parse_args(argv)

    # 默认全跑
    do_all = not (args.claims or args.sandbox)
    env = _env()
    report = Report(subject="smolagents", version=env.pop("_version"), environment=env)

    if do_all or args.claims:
        report.cases.extend(ClaimSuite().run())

    sandbox = None
    if do_all or args.sandbox:
        sandbox = SandboxSuite()
        try:
            report.cases.extend(sandbox.run())
        finally:
            sandbox.cleanup()

    if not args.quiet:
        _safe_print(render_console(report))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            f.write(report.to_json())
        _safe_print(f"[写出] {args.json}")

    if args.md:
        with open(args.md, "w", encoding="utf-8") as f:
            f.write(render_markdown(report))
        _safe_print(f"[写出] {args.md}")

    # CI 门禁
    if args.fail_on:
        watch = {s.strip().upper() for s in args.fail_on.split(",") if s.strip()}
        hit = [c for c in report.cases if c.status.value in watch]
        if hit:
            _safe_print(f"\n[门禁] 命中 {len(hit)} 项 {sorted(watch)}：", stream=sys.stderr)
            for c in hit:
                _safe_print(f"  - {c.case_id} {c.claim}", stream=sys.stderr)
            return 1

    # 回归门禁：已知问题不算失败，只抓新增
    if args.fail_on_new:
        from .baseline import load

        known = set(load().get("known_mismatches", []))
        new = [c for c in report.cases if c.status.value == "MISMATCH" and c.case_id not in known]
        if new:
            _safe_print(
                f"\n[回归] 发现 {len(new)} 项未登记的新 MISMATCH：",
                stream=sys.stderr,
            )
            for c in new:
                _safe_print(f"  - {c.case_id} {c.claim}", stream=sys.stderr)
            _safe_print(
                "  若属预期，请更新 baseline.json 并在提交信息里说明原因。",
                stream=sys.stderr,
            )
            return 1
        _safe_print(
            f"[回归] 无新增 MISMATCH（已登记 {len(known)} 项已知问题）",
            stream=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
