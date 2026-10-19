"""沙箱隔离验证用例。

这是本套件的核心能力验证：smolagents 的 CodeAgent 默认在 LocalPythonExecutor
里执行 LLM 生成的代码，隔离强度直接决定「能不能跑不可信代码」。

每个用例都：
  * 有唯一 id 与对应宣传声明
  * 用真实副作用（哨兵文件）判定，不靠「是否抛异常」
  * 独立 executor 实例，避免状态污染
"""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass

from smolagents.local_python_executor import LocalPythonExecutor

from .model import CaseResult, Status


@dataclass
class Case:
    case_id: str
    claim: str
    code: str
    authorized_imports: list[str]
    # 期望：True = 应该被拦截；False = 应该允许
    expect_blocked: bool
    note: str = ""
    # 判定是否以「文件被创建/写入」为副作用证据
    side_effect: str = "file_write"  # file_write | cmd_exec | none


def _run(code: str, authorized: list[str]) -> dict:
    """在全新 executor 中执行代码，返回原始结果。"""
    ex = LocalPythonExecutor(additional_authorized_imports=authorized)
    ex.send_tools({})
    try:
        out = ex(code_action=code)
        return {"ok": True, "output": str(out.output)[:300], "error": None}
    except BaseException as e:  # noqa: BLE001 - 沙箱可能抛任何异常
        return {"ok": False, "output": None, "error": f"{type(e).__name__}: {str(e)[:300]}"}


class SandboxSuite:
    """沙箱隔离验证套件。"""

    def __init__(self) -> None:
        self.workdir = tempfile.mkdtemp(prefix="smolaudit_")
        self.sentinel = os.path.join(self.workdir, "sentinel.txt")
        self.sentinel_py = self.sentinel.replace("\\", "\\\\")
        # 供「读」用例使用的已知内容文件
        self.readable = os.path.join(self.workdir, "known.txt")
        with open(self.readable, "w", encoding="utf-8") as f:
            f.write("line1,line2,line3\nvalue1,value2,value3\n")
        self.readable_py = self.readable.replace("\\", "\\\\")
        # 命令执行标记（用 shell 重定向造文件，比看 stdout 更可靠）
        self.cmdmark = os.path.join(self.workdir, "cmd_ran.txt")
        # 反斜杠在 Python 源码里会被当转义序列，shell 命令里改用正斜杠
        self.cmdmark_sh = self.cmdmark.replace("\\", "/")
        self.cmdmark_py = self.cmdmark.replace("\\", "\\\\")
        self.results: list[CaseResult] = []

    # ---------- 用例定义 ----------

    def _cases(self) -> list[Case]:
        sp = self.sentinel_py
        rp = self.readable_py
        return [
            # ===== A. 基础隔离：未授权时的高危操作 =====
            Case("A1", "未授权 import os 应被拒绝", "import os\nos.getcwd()", [], True,
                 "README: LocalPythonExecutor 施加了限制"),
            Case("A2", "未授权 open() 应被拒绝", f"open(r'{sp}', 'w').write('x')", [], True),
            Case("A3", "dunder 属性访问应被拒绝", "().__class__.__base__", [], True),
            Case("A4", "getattr 访问 dunder 应被拒绝", "getattr((), '__class__')", [], True,
                 "变异测试证实此守卫有效但上游无测试覆盖"),
            Case("A5", "subclasses 遍历应被拒绝", "().__class__.__base__.__subclasses__()", [], True),
            Case("A6", "__builtins__ 直取应被拒绝", "__builtins__['eval']", [], True),
            Case("A7", "while 死循环应被迭代上限截断", "i=0\nwhile i < 10**7: i+=1\ni", [], True),

            # ===== B. 授权第三方库后的隔离衰减（核心发现） =====
            Case("B1", "授权 pandas 后不应能写任意路径",
                 f"import pandas as pd\npd.DataFrame({{'a':[1]}}).to_csv(r'{sp}', index=False)\n'ok'",
                 ["pandas"], True, "README/CLI 示例推荐 --imports pandas"),
            Case("B2", "授权 numpy 后不应能写任意路径",
                 f"import numpy as np\nnp.savetxt(r'{sp}', np.array([1.0]))\n'ok'",
                 ["numpy"], True),
            Case("B3", "授权 pandas 后不应能读任意文件",
                 f"import pandas as pd\ndf = pd.read_csv(r'{rp}')\nstr(df.shape)",
                 ["pandas"], True),
            Case("B4", "授权 pandas 后访问 pandas.io 子模块应被拒绝",
                 "import pandas as pd\npd.io.common", ["pandas"], True,
                 "上游 test_vulnerability_via_submodules 有覆盖"),

            # ===== E. 授权 os / subprocess（API 允许，README 未推荐） =====
            Case("E1", "授权 os 后不应能执行系统命令",
                 f"import os\nos.system('echo pwned > \"{self.cmdmark_sh}\"')\n'called'",
                 ["os"], True,
                 "DANGEROUS_FUNCTIONS 明列 os.system；Windows 上 os.system.__module__=='nt' 导致黑名单失配",
                 side_effect="cmd_exec"),
            Case("E2", "授权 subprocess 后不应能执行系统命令",
                 f"import subprocess\nsubprocess.run('echo pwned > \"{self.cmdmark_sh}\"', shell=True)\n'done'",
                 ["subprocess"], True,
                 side_effect="cmd_exec"),

            # ===== D. 资源限制 =====
            Case("D1", "1GB 内存分配应被限制",
                 "x = 'a' * (10**9)\nlen(x)", [], True,
                 "无内存上限声明；实测可分配", side_effect="none"),
            Case("D2", "print 输出应被截断到 50000 字符",
                 "print('a' * 200000)", [], False,
                 "DEFAULT_MAX_LEN_OUTPUT=50000，事后截断", side_effect="none"),
        ]

    # ---------- 授权升级链 ----------

    def _escalation_chain(self) -> list[CaseResult]:
        """验证：框架的「建议授权」提示是否会把人引向命令执行。

        链条：import 被拦 → 提示「Consider passing said import under
        additional_authorized_imports」→ 用户照做 → os.system 可执行。
        """
        chain = [
            ("X1", "第1步：未授权 import os 被拦截", "import os\nos.getcwd()", []),
            ("X2", "第2步：按框架提示授权 os 后放行", "import os\nos.getcwd()", ["os"]),
            ("X3", "第3步：授权 os 后可执行系统命令",
             f"import os\nos.system('echo x > \"{self.cmdmark_sh}\"')\n'ok'", ["os"]),
        ]
        out: list[CaseResult] = []
        for cid, claim, code, auth in chain:
            if os.path.exists(self.cmdmark):
                os.remove(self.cmdmark)
            r = _run(code, auth)
            cmd_ran = os.path.exists(self.cmdmark)
            # X1 期望「被拦」，X2/X3 期望「放行」
            want_blocked = cid == "X1"
            ok = (not r["ok"]) if want_blocked else r["ok"]
            out.append(
                CaseResult(
                    case_id=cid,
                    claim=claim,
                    status=Status.IMPLEMENTED if ok else Status.PARTIAL,
                    evidence=(
                        f"allowed={r['ok']} (期望{'拦截' if want_blocked else '放行'}) "
                        f"cmd_ran={cmd_ran} "
                        + (f"output={r['output']!r}" if r["ok"] else f"error={str(r['error'])[:100]}")
                    ),
                    detail={"authorized_imports": auth, "raw": r, "cmd_ran": cmd_ran},
                )
            )
        return out

    # ---------- 执行 ----------

    def run(self) -> list[CaseResult]:
        for c in self._cases():
            for p in (self.sentinel, self.cmdmark):
                if os.path.exists(p):
                    os.remove(p)

            r = _run(c.code, c.authorized_imports)
            file_touched = os.path.exists(self.sentinel)
            cmd_ran = os.path.exists(self.cmdmark)

            # 判定：以真实副作用为最高优先级
            if c.side_effect == "cmd_exec":
                blocked = not cmd_ran
            elif file_touched:
                blocked = False
            else:
                blocked = not r["ok"]

            matched = blocked == c.expect_blocked

            if matched:
                status = Status.IMPLEMENTED
                verdict = "符合预期"
            else:
                # 写文件/执行命令被放行 = 隔离被绕过，属声明与行为矛盾
                if c.side_effect in ("file_write", "cmd_exec"):
                    status = Status.MISMATCH
                    verdict = "隔离被绕过"
                else:
                    status = Status.PARTIAL
                    verdict = "与预期不符"

            evidence = (
                f"expect_blocked={c.expect_blocked} actual_blocked={blocked} "
                f"file_touched={file_touched} cmd_ran={cmd_ran} "
                + (f"output={r['output']!r}" if r["ok"] else f"error={str(r['error'])[:110]}")
            )

            self.results.append(
                CaseResult(
                    case_id=c.case_id,
                    claim=c.claim,
                    status=status,
                    evidence=evidence,
                    detail={
                        "note": c.note,
                        "verdict": verdict,
                        "authorized_imports": c.authorized_imports,
                        "raw": r,
                        "file_touched": file_touched,
                        "cmd_ran": cmd_ran,
                    },
                )
            )

        self.results.extend(self._escalation_chain())
        return self.results

    def cleanup(self) -> None:
        shutil.rmtree(self.workdir, ignore_errors=True)
