# smolagents 能力核验报告

- 对象：`smolagents` **v1.26.0**
- 环境：Python 3.13.14 / Windows-11-10.0.26300-SP0 / docker=False deno=False
- 整体结论：**FAIL**
- 统计：PARTIAL 3 · IMPLEMENTED 18 · UNVERIFIABLE 1 · MISMATCH 7

| ID | 声明 / 能力 | 状态 | 证据 |
|---|---|---|---|
| C1 | 「agents.py 逻辑约 1,000 行」 | **PARTIAL** | 有效代码 1255 行，超出「约1000行」255 行（+25%） |
| C2 | 支持 Blaxel / E2B / Modal / Docker 四种沙箱 | **IMPLEMENTED** | 四个类均存在于 remote_executors：['BlaxelExecutor', 'DockerExecutor', 'E2BExecutor', 'ModalExecutor', 'PythonExecutor', 'RemotePythonExecutor'] |
| C3 | 每种沙箱都有对应安装 extras | **IMPLEMENTED** | extras 覆盖情况：{'BlaxelExecutor': True, 'E2BExecutor': True, 'ModalExecutor': True, 'DockerExecutor': True} |
| C4 | 沙箱隔离可实机验证 | **UNVERIFIABLE** | 本机 docker=False deno=False；E2B/Modal/Blaxel 需云端凭证，未配置。仅做静态核查 |
| C5 | Docker 沙箱默认做容器加固 | **PARTIAL** | 默认加固项 0/6：{'network_disabled': False, 'mem_limit': False, 'read_only': False, 'cap_drop': False, 'no_new_privileges': False, 'user': False}。均未设置时容器以默认权限运行，隔离依赖容器本身而非参数 |
| C6 | 支持与 Hub 共享/拉取 tool 与 agent | **IMPLEMENTED** | 方法存在性：{'Tool.from_hub': True, 'Tool.push_to_hub': True, 'Tool.from_space': True, 'Agent.from_hub': True, 'Agent.push_to_hub': True} |
| C7 | 支持任意 LLM（本地 transformers / ollama / 各云厂商） | **IMPLEMENTED** | models.py 中定义 14 个 Model 类：['AmazonBedrockModel', 'AmazonBedrockServerModel', 'ApiModel', 'AzureOpenAIModel', 'AzureOpenAIServerModel', 'InferenceClientModel', 'LiteLLMModel', 'LiteLLMRouterModel', 'MLXModel', 'Model', 'OpenAIModel', 'OpenAIServerModel', 'TransformersModel', 'VLLMModel'] |
| C8 | 支持 text / vision / video / audio 输入 | **MISMATCH** | text=True, image=True, audio=True, 但整个包源码中 'video' 出现 0 次 —— 宣传的 video 输入无任何实现 |
| C9 | 可用任意 MCP / LangChain / Hub Space 作为工具 | **IMPLEMENTED** | 入口存在性：{'MCP (ToolCollection.from_mcp)': True, 'LangChain (Tool.from_langchain)': True, 'Hub Space (Tool.from_space)': True} |
| C10 | 提供 smolagent / webagent 两个 CLI | **IMPLEMENTED** | console_scripts=['smolagent', 'webagent']；本机 PATH 可执行={'smolagent': False, 'webagent': False} |
| C11 | 危险函数黑名单覆盖系统命令执行入口 | **MISMATCH** | 黑名单 9 条，但下列危险函数的实际限定名不在其中：['os.system', 'subprocess.run', 'subprocess.Popen', 'subprocess.check_output']。拦截逻辑用 `__module__` 精确匹配，模块归属随平台变化（本机 os.system.__module__='nt'） |
| A1 | 未授权 import os 应被拒绝 | **IMPLEMENTED** | expect_blocked=True actual_blocked=True file_touched=False cmd_ran=False error=InterpreterError: Code execution failed at line 'import os' due to: InterpreterError: Import of os is not allo |
| A2 | 未授权 open() 应被拒绝 | **IMPLEMENTED** | expect_blocked=True actual_blocked=True file_touched=False cmd_ran=False error=InterpreterError: Code execution failed at line 'open(r'E:\\WorkBuddy - AI - C\\Temp\\smolaudit_hxlxa6gg\\sent |
| A3 | dunder 属性访问应被拒绝 | **IMPLEMENTED** | expect_blocked=True actual_blocked=True file_touched=False cmd_ran=False error=InterpreterError: Code execution failed at line '().__class__.__base__' due to: InterpreterError: Forbidden ac |
| A4 | getattr 访问 dunder 应被拒绝 | **IMPLEMENTED** | expect_blocked=True actual_blocked=True file_touched=False cmd_ran=False error=InterpreterError: Code execution failed at line 'getattr((), '__class__')' due to: InterpreterError: Forbidden |
| A5 | subclasses 遍历应被拒绝 | **IMPLEMENTED** | expect_blocked=True actual_blocked=True file_touched=False cmd_ran=False error=InterpreterError: Code execution failed at line '().__class__.__base__.__subclasses__()' due to: InterpreterEr |
| A6 | __builtins__ 直取应被拒绝 | **IMPLEMENTED** | expect_blocked=True actual_blocked=True file_touched=False cmd_ran=False error=InterpreterError: Code execution failed at line '__builtins__['eval']' due to: InterpreterError: The variable  |
| A7 | while 死循环应被迭代上限截断 | **IMPLEMENTED** | expect_blocked=True actual_blocked=True file_touched=False cmd_ran=False error=InterpreterError: Code execution failed at line 'while i < 10**7: i+=1' due to: InterpreterError: Maximum numb |
| B1 | 授权 pandas 后不应能写任意路径 | **MISMATCH** | expect_blocked=True actual_blocked=False file_touched=True cmd_ran=False output='ok' |
| B2 | 授权 numpy 后不应能写任意路径 | **MISMATCH** | expect_blocked=True actual_blocked=False file_touched=True cmd_ran=False output='ok' |
| B3 | 授权 pandas 后不应能读任意文件 | **MISMATCH** | expect_blocked=True actual_blocked=False file_touched=False cmd_ran=False output='(1, 3)' |
| B4 | 授权 pandas 后访问 pandas.io 子模块应被拒绝 | **IMPLEMENTED** | expect_blocked=True actual_blocked=True file_touched=False cmd_ran=False error=InterpreterError: Code execution failed at line 'pd.io.common' due to: InterpreterError: Forbidden access to m |
| E1 | 授权 os 后不应能执行系统命令 | **MISMATCH** | expect_blocked=True actual_blocked=False file_touched=False cmd_ran=True output='called' |
| E2 | 授权 subprocess 后不应能执行系统命令 | **MISMATCH** | expect_blocked=True actual_blocked=False file_touched=False cmd_ran=True output='done' |
| D1 | 1GB 内存分配应被限制 | **PARTIAL** | expect_blocked=True actual_blocked=False file_touched=False cmd_ran=False output='1000000000' |
| D2 | print 输出应被截断到 50000 字符 | **IMPLEMENTED** | expect_blocked=False actual_blocked=False file_touched=False cmd_ran=False output='None' |
| X1 | 第1步：未授权 import os 被拦截 | **IMPLEMENTED** | allowed=False (期望拦截) cmd_ran=False error=InterpreterError: Code execution failed at line 'import os' due to: InterpreterError: Import of os i |
| X2 | 第2步：按框架提示授权 os 后放行 | **IMPLEMENTED** | allowed=True (期望放行) cmd_ran=False output='E:\\WorkBuddy-Work\\Workbuddy-Github-1\\smolagents-audit' |
| X3 | 第3步：授权 os 后可执行系统命令 | **IMPLEMENTED** | allowed=True (期望放行) cmd_ran=True output='ok' |
