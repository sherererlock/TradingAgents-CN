# tests/ 目录说明（测试与诊断）

本项目的 [tests](file:///e:/workspace/GitRepository/TradingAgents-CN/tests) 目录用于验证核心功能、后端 API 行为、数据链路稳定性，以及第三方模型/数据源的连通性。这里不仅包含标准的 pytest 测试，也包含一些可直接运行的“诊断/验证脚本”（通常带有 `main()`，用于快速定位环境或集成问题）。

## 目录里有什么

在当前仓库中，tests 目录大致分两类内容：

- **pytest 测试**：以 `test_*.py` 为主，适合在 CI/本地批量运行，断言清晰、失败可复现。
- **诊断/演示脚本**：以 `debug_*.py`、`quick_*.py`、`*_check*.py`、`demo_*.py` 为主，通常带打印输出，用于人工排查问题或快速回归验证。

整体目录结构（以“关注点”归类）：

- [tests/README.md](file:///e:/workspace/GitRepository/TradingAgents-CN/tests/README.md)：测试入口说明与常用命令索引
- [tests/pytest.ini](file:///e:/workspace/GitRepository/TradingAgents-CN/tests/pytest.ini)：pytest 收集与默认过滤策略
- [tests/conftest.py](file:///e:/workspace/GitRepository/TradingAgents-CN/tests/conftest.py)：将项目根目录加入 `sys.path`，保证 `import tradingagents` 可用
- [tests/config](file:///e:/workspace/GitRepository/TradingAgents-CN/tests/config)：配置加载/覆盖与日志配置相关测试
- [tests/services](file:///e:/workspace/GitRepository/TradingAgents-CN/tests/services)：服务层（任务调度、行情入库、回填等）测试
- [tests/system](file:///e:/workspace/GitRepository/TradingAgents-CN/tests/system)：系统级 API/安全策略（鉴权、脱敏等）测试
- [tests/middleware](file:///e:/workspace/GitRepository/TradingAgents-CN/tests/middleware)：中间件行为测试（如 trace/request id）
- [tests/dataflows](file:///e:/workspace/GitRepository/TradingAgents-CN/tests/dataflows)：数据流处理与指标统计相关测试
- [tests/integration](file:///e:/workspace/GitRepository/TradingAgents-CN/tests/integration)：依赖外部服务的集成验证（LLM、第三方 API）
- [tests/0.1.14](file:///e:/workspace/GitRepository/TradingAgents-CN/tests/0.1.14)：偏“版本回归/历史验证”的脚本集合，用于复现或回归特定版本问题

## 如何运行

### 1) 运行 pytest（推荐）

在项目根目录执行：

```bash
python -m pytest tests/
```

pytest 的默认行为由 [tests/pytest.ini](file:///e:/workspace/GitRepository/TradingAgents-CN/tests/pytest.ini) 控制：

- `testpaths = tests`：只收集 `tests/` 下的测试，避免误扫根目录
- `addopts = -m "not integration" -k "not (test_server_config or test_stock_codes)"`：默认不跑标记为 `integration` 的测试，并通过 `-k` 排除部分用例

如果你需要运行被标记为 `integration` 的用例：

```bash
python -m pytest tests/ -m integration
```

### 2) 直接运行诊断脚本（用于排查）

这类脚本通常带较多打印输出，适合快速确认“环境变量/网络/依赖”是否正确：

```bash
python tests/integration/test_dashscope_integration.py
python tests/quick_redis_test.py
python tests/debug_imports.py
```

## 关键配置文件解读

### pytest.ini：收集范围与默认过滤

见 [pytest.ini](file:///e:/workspace/GitRepository/TradingAgents-CN/tests/pytest.ini#L1-L10)：

- 将测试收集范围限定在 `tests/`
- 预定义 `integration` marker，用于区分“需要外部服务/网络”的测试
- 默认用 `-m "not integration"` 跳过集成类测试（前提是测试被正确打上 marker）

### conftest.py：导入路径兜底

见 [conftest.py](file:///e:/workspace/GitRepository/TradingAgents-CN/tests/conftest.py#L1-L7)：

- 将项目根目录加入 `sys.path`
- 让测试文件无需安装包也能 `import tradingagents`/`import app`

## 代表性测试用例（读懂它们就能读懂整体风格）

### 1) LLM/第三方服务连通性：DashScope（阿里百炼）

文件：[test_dashscope_integration.py](file:///e:/workspace/GitRepository/TradingAgents-CN/tests/integration/test_dashscope_integration.py)

这个文件更像“集成验证脚本”，核心关注点：

- **导入链路**：能否导入 `ChatDashScope` 与 `TradingAgentsGraph`
- **环境变量**：`DASHSCOPE_API_KEY`、`FINNHUB_API_KEY` 是否存在
- **直接 SDK 调用**：用 `dashscope.Generation.call(...)` 做一次最小连通性验证
- **LangChain 适配器**：用 `llm.invoke(...)` 验证适配层可用
- **图配置可初始化**：构造 `TradingAgentsGraph`，验证 provider 与模型名组合不报错

适用场景：外部模型接入异常、网络/密钥问题、适配层升级回归。

### 2) 服务启动与任务调度：行情定时任务

文件：[test_scheduler_quotes_job.py](file:///e:/workspace/GitRepository/TradingAgents-CN/tests/services/test_scheduler_quotes_job.py)

这个测试关注后端启动时“是否按预期注册定时任务”，关键做法：

- 用 `monkeypatch` 替换 `AsyncIOScheduler`、`QuotesIngestionService` 等依赖，避免真实启动外部服务
- 通过驱动 `app.main.lifespan(...)` 执行启动逻辑，捕获 `add_job(...)` 是否被调用
- 验证注册的 trigger 类型为 `IntervalTrigger`，并模拟一次 tick，确保会触发 `asyncio.create_task(...)`

适用场景：排查定时任务没有运行、启动流程改动导致 job 丢失等问题。

### 3) 配置加载与拼接：Settings / URL 生成

文件：[test_settings.py](file:///e:/workspace/GitRepository/TradingAgents-CN/tests/config/test_settings.py)

这个测试覆盖两类常见坑：

- 环境变量覆盖是否生效（如 `PORT`、`DEBUG`）
- Mongo/Redis 连接串是否按约定拼装（含用户名密码场景）

适用场景：配置项调整、部署环境变量差异导致服务连不上 Mongo/Redis。

### 4) 安全与脱敏：系统配置摘要接口

文件：[test_config_summary.py](file:///e:/workspace/GitRepository/TradingAgents-CN/tests/system/test_config_summary.py)

这个测试验证两件事：

- `/api/system/config/summary` 必须鉴权（未鉴权 401）
- 返回的配置摘要中，敏感字段必须被统一脱敏为 `***`，包括派生的 `MONGO_URI` / `REDIS_URL` 中的凭据部分

适用场景：安全回归（脱敏逻辑被改坏）、接口权限控制变更。

## 新增/维护测试的建议（面向新手）

- 优先写“可离线跑”的单元测试：不要依赖真实外部 API；用 `monkeypatch`/fake service 隔离。
- 需要外部依赖时，用 `pytest.mark.integration` 标记，并确保默认测试不会误跑。
- 尽量避免在测试输出中打印完整密钥；必要时只显示前几位。
- 测试用例的目标要单一：一次只验证一个行为（例如“是否注册 job”、“是否脱敏”等）。

## 与其他文档的关系

- [tests/README.md](file:///e:/workspace/GitRepository/TradingAgents-CN/tests/README.md) 更像“命令索引 + 文件清单”。
- 本文更像“读代码指南”：告诉你 tests 的组织方式、关键入口与典型模式，方便你快速定位该看哪里、该怎么加新测试。

