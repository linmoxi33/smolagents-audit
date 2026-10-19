"""宣传声明核验：把 README 的每句话变成可执行的断言。

原则：
  * 每条声明都给出「源码位置」或「运行结果」二选一的硬证据
  * 不做主观评价，只标注 IMPLEMENTED / PARTIAL / MISMATCH / UNVERIFIABLE
  * 宣传语与源码冲突时，以源码为准
"""

from __future__ import annotations

import importlib
import inspect
import os
import re
from pathlib import Path

from .model import CaseResult, Status


def _pkg_dir() -> Path:
    import smolagents

    return Path(smolagents.__file__).parent


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _count_code_lines(path: Path) -> dict:
    """统计真实代码行（去空行/注释/文档字符串）。"""
    import ast

    src = _read(path)
    lines = src.splitlines()
    tree = ast.parse(src)
    doc = 0
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(n, "body", [])
            if body and isinstance(body[0], ast.Expr):
                v = body[0].value
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    doc += body[0].end_lineno - body[0].lineno + 1
    blank = sum(1 for ln in lines if not ln.strip())
    comment = sum(1 for ln in lines if ln.strip().startswith("#"))
    return {
        "total": len(lines),
        "blank": blank,
        "comment": comment,
        "docstring": doc,
        "code": len(lines) - blank - comment - doc,
    }


class ClaimSuite:
    """逐条核验 README 宣传声明。"""

    def __init__(self, readme_path: str | None = None) -> None:
        self.pkg = _pkg_dir()
        self.readme = Path(readme_path) if readme_path else None
        self.results: list[CaseResult] = []

    def _add(self, cid: str, claim: str, status: Status, evidence: str, **detail) -> None:
        self.results.append(
            CaseResult(case_id=cid, claim=claim, status=status, evidence=evidence, detail=detail)
        )

    def run(self) -> list[CaseResult]:
        self._claim_simplicity()
        self._claim_sandboxes()
        self._claim_hub()
        self._claim_model_agnostic()
        self._claim_modality()
        self._claim_tool_agnostic()
        self._claim_cli()
        self._claim_blacklist()
        return self.results

    # ---------- 1. "~1,000 lines" ----------
    def _claim_simplicity(self) -> None:
        agents_py = self.pkg / "agents.py"
        if not agents_py.exists():
            self._add("C1", "agents.py 逻辑约 1000 行", Status.UNVERIFIABLE, "agents.py 不存在")
            return
        m = _count_code_lines(agents_py)
        code = m["code"]
        # 允许 ±10% 视为「约」
        if code <= 1100:
            status = Status.IMPLEMENTED
            ev = f"有效代码 {code} 行（总 {m['total']}，去空行/注释/docstring）"
        elif code <= 1400:
            status = Status.PARTIAL
            ev = f"有效代码 {code} 行，超出「约1000行」{code - 1000} 行（+{round((code/1000-1)*100)}%）"
        else:
            status = Status.MISMATCH
            ev = f"有效代码 {code} 行，远超「约1000行」"
        self._add("C1", "「agents.py 逻辑约 1,000 行」", status, ev, metrics=m)

    # ---------- 2. 沙箱 ----------
    def _claim_sandboxes(self) -> None:
        mod = importlib.import_module("smolagents.remote_executors")
        existing = {n for n in dir(mod) if n.endswith("Executor")}
        advertised = ["BlaxelExecutor", "E2BExecutor", "ModalExecutor", "DockerExecutor"]

        missing = [a for a in advertised if a not in existing]
        if missing:
            self._add(
                "C2",
                "支持 Blaxel / E2B / Modal / Docker 四种沙箱",
                Status.MISMATCH,
                f"宣传 4 种，实际缺失 {missing}；模块内仅有 {sorted(existing)}",
            )
        else:
            self._add(
                "C2",
                "支持 Blaxel / E2B / Modal / Docker 四种沙箱",
                Status.IMPLEMENTED,
                f"四个类均存在于 remote_executors：{sorted(existing)}",
            )

        # 每个执行器的依赖 extras
        from importlib.metadata import metadata

        md = metadata("smolagents")
        extras = set()
        for req in md.get_all("Requires-Dist") or []:
            if 'extra == "' in req:
                extras.add(req.split('extra == "')[1].rstrip('"'))

        detail = {}
        for name, extra in [
            ("BlaxelExecutor", "blaxel"),
            ("E2BExecutor", "e2b"),
            ("ModalExecutor", "modal"),
            ("DockerExecutor", "docker"),
        ]:
            detail[name] = extra in extras
        ok = all(detail.values())
        self._add(
            "C3",
            "每种沙箱都有对应安装 extras",
            Status.IMPLEMENTED if ok else Status.PARTIAL,
            f"extras 覆盖情况：{detail}",
            extras=sorted(extras),
        )

        # 云端沙箱本机能否验证
        has_docker = shutil_which("docker")
        has_deno = shutil_which("deno")
        self._add(
            "C4",
            "沙箱隔离可实机验证",
            Status.UNVERIFIABLE,
            f"本机 docker={bool(has_docker)} deno={bool(has_deno)}；"
            "E2B/Modal/Blaxel 需云端凭证，未配置。仅做静态核查",
            docker=bool(has_docker),
            deno=bool(has_deno),
        )

        # Docker 容器加固参数（静态）
        src = _read(self.pkg / "remote_executors.py")
        hardening = {
            "network_disabled": "network_disabled" in src,
            "mem_limit": "mem_limit" in src,
            "read_only": '"read_only"' in src or "'read_only'" in src,
            "cap_drop": "cap_drop" in src,
            "no_new_privileges": "no-new-privileges" in src or "no_new_privileges" in src,
            "user": re.search(r'"user"\s*:', src) is not None,
        }
        hard_ok = sum(hardening.values())
        self._add(
            "C5",
            "Docker 沙箱默认做容器加固",
            Status.PARTIAL if hard_ok == 0 else Status.IMPLEMENTED,
            f"默认加固项 {hard_ok}/6：{hardening}。"
            "均未设置时容器以默认权限运行，隔离依赖容器本身而非参数",
            hardening=hardening,
        )

    # ---------- 3. Hub ----------
    def _claim_hub(self) -> None:
        from smolagents import Tool
        from smolagents.agents import MultiStepAgent

        checks = {
            "Tool.from_hub": hasattr(Tool, "from_hub"),
            "Tool.push_to_hub": hasattr(Tool, "push_to_hub"),
            "Tool.from_space": hasattr(Tool, "from_space"),
            "Agent.from_hub": hasattr(MultiStepAgent, "from_hub"),
            "Agent.push_to_hub": hasattr(MultiStepAgent, "push_to_hub"),
        }
        ok = all(checks.values())
        self._add(
            "C6",
            "支持与 Hub 共享/拉取 tool 与 agent",
            Status.IMPLEMENTED if ok else Status.PARTIAL,
            f"方法存在性：{checks}",
            checks=checks,
        )

    # ---------- 4. 模型无关 ----------
    def _claim_model_agnostic(self) -> None:
        import smolagents.models as m

        models = [n for n, o in inspect.getmembers(m, inspect.isclass) if n.endswith("Model")]
        models = [n for n in models if getattr(m, n).__module__ == m.__name__]
        need = ["LiteLLMModel", "OpenAIModel", "TransformersModel", "InferenceClientModel"]
        missing = [n for n in need if n not in models]
        self._add(
            "C7",
            "支持任意 LLM（本地 transformers / ollama / 各云厂商）",
            Status.IMPLEMENTED if not missing else Status.PARTIAL,
            f"models.py 中定义 {len(models)} 个 Model 类：{sorted(models)}"
            + (f"；缺 {missing}" if missing else ""),
            models=sorted(models),
        )

    # ---------- 5. 多模态 ----------
    def _claim_modality(self) -> None:
        src_all = "\n".join(
            _read(p) for p in self.pkg.glob("*.py")
        )
        has_image = "AgentImage" in src_all
        has_audio = "AgentAudio" in src_all
        video_hits = len(re.findall(r"\bvideo\b", src_all, flags=re.I))

        if video_hits == 0:
            status = Status.MISMATCH
            ev = (
                f"text={True}, image={has_image}, audio={has_audio}, "
                f"但整个包源码中 'video' 出现 {video_hits} 次 —— 宣传的 video 输入无任何实现"
            )
        else:
            status = Status.IMPLEMENTED
            ev = f"image={has_image}, audio={has_audio}, video 关键词命中 {video_hits} 次"
        self._add("C8", "支持 text / vision / video / audio 输入", status, ev,
                  image=has_image, audio=has_audio, video_hits=video_hits)

    # ---------- 6. 工具无关 ----------
    def _claim_tool_agnostic(self) -> None:
        from smolagents import ToolCollection
        from smolagents.tools import Tool

        checks = {
            "MCP (ToolCollection.from_mcp)": hasattr(ToolCollection, "from_mcp"),
            "LangChain (Tool.from_langchain)": hasattr(Tool, "from_langchain"),
            "Hub Space (Tool.from_space)": hasattr(Tool, "from_space"),
        }
        self._add(
            "C9",
            "可用任意 MCP / LangChain / Hub Space 作为工具",
            Status.IMPLEMENTED if all(checks.values()) else Status.PARTIAL,
            f"入口存在性：{checks}",
            checks=checks,
        )

    # ---------- 7. CLI ----------
    def _claim_cli(self) -> None:
        import shutil

        found = {name: shutil.which(name) for name in ["smolagent", "webagent"]}
        # 退而检查 entry_points 声明
        from importlib.metadata import distribution

        dist = distribution("smolagents")
        eps = [e.name for e in dist.entry_points if e.group == "console_scripts"]
        self._add(
            "C10",
            "提供 smolagent / webagent 两个 CLI",
            Status.IMPLEMENTED if set(["smolagent", "webagent"]) & set(eps) else Status.PARTIAL,
            f"console_scripts={eps}；本机 PATH 可执行={ {k: bool(v) for k, v in found.items()} }",
            entry_points=eps,
        )

    # ---------- 8. 危险函数黑名单的覆盖范围 ----------
    def _claim_blacklist(self) -> None:
        """黑名单是否真的覆盖了危险函数。

        关键洞察：拦截靠 `result.__module__ == module_name` 精确匹配，
        而模块归属随平台变化（Windows: os.system.__module__ == 'nt'）。
        """
        import os
        import subprocess

        from smolagents.local_python_executor import DANGEROUS_FUNCTIONS

        probes = [
            ("os.system", os.system),
            ("os.popen", os.popen),
            ("subprocess.run", subprocess.run),
            ("subprocess.Popen", subprocess.Popen),
            ("subprocess.check_output", subprocess.check_output),
        ]
        coverage = {}
        for label, fn in probes:
            mod = getattr(fn, "__module__", "?")
            name = getattr(fn, "__name__", "?")
            coverage[label] = {
                "actual_module": mod,
                "qualified": f"{mod}.{name}",
                "in_blacklist": f"{mod}.{name}" in DANGEROUS_FUNCTIONS,
            }

        uncovered = [k for k, v in coverage.items() if not v["in_blacklist"]]
        if uncovered:
            status = Status.MISMATCH
            ev = (
                f"黑名单 {len(DANGEROUS_FUNCTIONS)} 条，但下列危险函数的实际限定名不在其中：{uncovered}。"
                f"拦截逻辑用 `__module__` 精确匹配，模块归属随平台变化"
                f"（本机 os.system.__module__={coverage['os.system']['actual_module']!r}）"
            )
        else:
            status = Status.IMPLEMENTED
            ev = f"全部覆盖：{coverage}"

        self._add("C11", "危险函数黑名单覆盖系统命令执行入口", status, ev, coverage=coverage)


def shutil_which(x: str):
    import shutil

    return shutil.which(x)
