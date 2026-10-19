# 核验方法说明

## 判定状态定义

| 状态 | 含义 | 判定依据 |
|---|---|---|
| `IMPLEMENTED` | 源码有实现，行为符合声明，有测试保护 | 运行结果 + 源码定位 + 变异测试捕获 |
| `PARTIAL` | 有实现，但只在部分条件下成立 | 运行结果落在「部分满足」区间 |
| `INTERFACE_ONLY` | 只有 API 壳子，无实际实现 | 方法存在但调用即失败 / 无实现体 |
| `UNVERIFIABLE` | 本机无法验证，且无静态证据可替代 | 缺运行时 / 缺凭证，且无法用源码推断 |
| `MISMATCH` | 源码或行为与宣传直接矛盾 | 声明 vs 实测的硬冲突 |
| `GAP` | 实现有效，但缺测试保护 | 变异后行为改变，测试却全绿 |

## 三条判定纪律

### 1. 以真实副作用为准，不看「是否抛异常」

沙箱逃逸最常见的误判是：代码抛了异常，但副作用已经发生。

```python
# 错误判定
try:
    executor("open('/tmp/x','w').write('pwned')")
    blocked = False
except:
    blocked = True          # ← 错！文件可能已经写了
```

本套件的做法：**先删哨兵文件 → 执行 → 检查文件是否真的存在**。

```python
if os.path.exists(sentinel):   # 最高优先级证据
    blocked = False
```

`E1`/`E2` 用 `echo > file` 而非看 stdout，也是同一理由——`os.system` 的返回值可能是 `0`，但命令确实执行了。

### 2. 变异测试必须比较「失败用例集合」，不能比失败数量

第一版判定逻辑：

```python
detected = failed_count > 0     # ← 错
```

问题：基线本身有 1 个平台性失败（Windows 上 `os.system` 未被拦截），
导致 `failed_count > 0` 永远成立，M2/M3 被误判为「有覆盖」。

修正为集合差集：

```python
new_failures = failed_after - failed_baseline
detected = len(new_failures) > 0
```

### 3. 测试过滤范围会改变结论

用 `-k vulnerability` 过滤时，M3（while 迭代上限）被判为「无覆盖」；
跑全量后发现 `TestEvaluatePythonCode::test_while` 会红，实际是「有覆盖」。

**过滤范围直接决定结论，这类判定必须跑全量。**

## 为什么不用 LLM

核心能力是「代码执行隔离」，这完全可以在不调用任何模型的情况下测
`LocalPythonExecutor`。引入 LLM 会带来三个问题：

1. 结果不确定（模型每次生成的代码不同）
2. 需要 API key，提高复现门槛
3. 掩盖真正要验证的东西——隔离层的行为与 LLM 无关

## 为什么区分 6 档而不是通过/不通过

`PARTIAL`（部分条件成立）和 `MISMATCH`（直接矛盾）是两类完全不同的问题：

- `PARTIAL`：功能在，但没宣传的那么强（如「约1000行」实际 1255 行）
- `MISMATCH`：宣传的东西不存在（如 `video` 输入，源码零命中）

混在一起会掩盖真问题。`UNVERIFIABLE` 单独列出，是为了**不把「我没条件测」伪装成「它不行」**。

## 本套件不做什么

- **不评价云端沙箱的隔离质量**：E2B / Modal / Blaxel 需凭证，本机无法实测，标 `UNVERIFIABLE`
- **不做武器化**：只验证「边界在哪」，不构造完整逃逸链
- **不修改上游代码**：变异测试会临时改动 `local_python_executor.py`，
  跑完按**字节比对**校验恢复（`read(SRC) == ORIGINAL`）

## 交叉验证记录

三项独立证据，排除「测试方法造成的伪影」：

| 验证项 | 方法 | 结果 |
|---|---|---|
| pandas 读任意文件 | 写入已知 CSV，读回比对内容（非只看 shape） | 读到 `{'name': {'0': 'alice'...}, 'score': {...}}` |
| pandas 写任意路径 | 检查落盘文件的实际内容 | 内容 `'x\n7\n8\n9\n'`，由沙箱内 DataFrame 产生 |
| os.system 执行命令 | 执行前确认标记不存在，执行后读内容 | 文件内容 `SANDBOX_ESCAPE` |

## 版本敏感性

本报告基于 `smolagents==1.26.0`。

**过程中踩过的坑**：最初装的是 1.21.0（当时 PyPI 缓存里的版本），
在那个版本里 `BlaxelExecutor` / `ModalExecutor` 确实不存在，
一度得出「README 宣传两种不存在的沙箱」的结论。
升级到最新版 1.26.0 后四个沙箱全部存在——**结论完全反转**。

教训：**核验前必须先确认装的是最新版本**，否则会把「版本滞后」误判为「虚假宣传」。
