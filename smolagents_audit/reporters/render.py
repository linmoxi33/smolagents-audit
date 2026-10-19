"""报告渲染：终端友好 + Markdown + JSON。"""

from __future__ import annotations

from ..model import Report, Status

ICON = {
    Status.IMPLEMENTED: "OK",
    Status.PARTIAL: "PART",
    Status.INTERFACE_ONLY: "SHELL",
    Status.UNVERIFIABLE: "N/A",
    Status.MISMATCH: "FAIL",
    Status.GAP: "GAP",
}

WIDTH = 78


def render_console(report: Report) -> str:
    out = []
    bar = "=" * WIDTH
    out.append(bar)
    out.append(f"  smolagents 能力核验  |  {report.subject}  |  v{report.version}")
    out.append(bar)

    env = report.environment
    out.append(
        f"  环境: Python {env.get('python')} / {env.get('platform')} / "
        f"docker={env.get('docker')} deno={env.get('deno')}"
    )
    out.append(f"  结论: {report.verdict()}    " + "  ".join(f"{k}={v}" for k, v in report.counts().items()))
    out.append("")

    current = None
    for c in report.cases:
        group = c.case_id[0]
        if group != current:
            current = group
            title = {
                "C": "宣传声明核验",
                "A": "基础隔离（未授权）",
                "B": "授权第三方库后的隔离衰减",
                "E": "授权 os / subprocess（系统命令）",
                "D": "资源限制",
                "X": "授权升级链（框架提示是否引向不安全配置）",
            }.get(group, "")
            out.append(f"-- {title} " + "-" * max(0, WIDTH - len(title) - 6))

        out.append(f"[{ICON[c.status]:5}] {c.case_id:4} {c.claim}")
        out.append(f"        {c.evidence}")

    out.append("")
    out.append(bar)
    return "\n".join(out)


def render_markdown(report: Report) -> str:
    lines = []
    lines.append(f"# smolagents 能力核验报告\n")
    lines.append(f"- 对象：`{report.subject}` **v{report.version}**")
    env = report.environment
    lines.append(f"- 环境：Python {env.get('python')} / {env.get('platform')} / docker={env.get('docker')} deno={env.get('deno')}")
    lines.append(f"- 整体结论：**{report.verdict()}**")
    lines.append(f"- 统计：" + " · ".join(f"{k} {v}" for k, v in report.counts().items()))
    lines.append("")
    lines.append("| ID | 声明 / 能力 | 状态 | 证据 |")
    lines.append("|---|---|---|---|")
    for c in report.cases:
        ev = c.evidence.replace("|", "\\|")
        claim = c.claim.replace("|", "\\|")
        lines.append(f"| {c.case_id} | {claim} | **{c.status.value}** | {ev} |")
    lines.append("")
    return "\n".join(lines)
