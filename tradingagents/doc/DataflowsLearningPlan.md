# Dataflows 学习计划（tradingagents/dataflows）

本文面向想快速读懂并能改动 `tradingagents/dataflows` 的开发者，目标是：读完后能定位数据获取链路、理解缓存/降级策略、能新增或替换数据源（provider），并能写出可验证的小改动。

## 0. 先建立一张“心智地图”（15–30 分钟）

把 Dataflows 当作“数据能力层”：

- **对外统一入口**：`tradingagents/dataflows/__init__.py` 重新导出 `interface.py` 的主要函数，供上层 Agent、服务、API 使用
- **统一编排/降级**：`data_source_manager.py`（A股 + 美股），负责选择数据源、降级顺序、部分缓存读取
- **偏业务的高层封装**：`optimized_china_data.py`，把缓存、MongoDB 同步数据、速率限制、兜底数据拼成更稳定的 A 股工具
- **数据提供器（providers）**：`providers/*`，面向具体 SDK/API（tushare/akshare/baostock/yfinance/finnhub…），做数据获取与标准化
- **缓存层（cache）**：`cache/*`，提供文件缓存、数据库缓存、以及自适应/集成缓存入口
- **新闻（news）/技术指标（technical）**：独立子域能力，`interface.py` 会再封装成字符串输出
- **辅助**：数据完整性检查、实时估值指标、向后兼容导出

建议把“调用链”画出来（后面每周练习都会用到）：

1) **A股历史行情（推荐链路）**
- `optimized_china_data.OptimizedChinaDataProvider.get_stock_data`
- → MongoDB 同步数据（可选）→ 文件缓存（可选）→ `data_source_manager.get_china_stock_data_unified`
- → `DataSourceManager.get_stock_data`（内部按优先级尝试数据源）→ 结果写回缓存

2) **A股历史行情（轻量链路）**
- `data_source_manager.get_china_stock_data_unified` → `DataSourceManager.get_stock_data`

3) **新闻**
- `interface.get_google_news` → `news.google_news.getNewsData`（抓取 + 重试）
- 或 `news.realtime_news`（多源聚合，偏实时）

4) **技术指标**
- `interface.get_stockstats_indicator` / `get_stock_stats_indicators_window`
- → `technical.stockstats.StockstatsUtils.get_stock_stats`

## 1. 学习前置与环境准备（30–60 分钟）

### 1.1 关键依赖（建议先确认本仓库 requirements）

Dataflows 涉及的依赖比较多，但你不需要一次性把所有能力跑通。建议优先确保以下包可用：

- 数据分析：`pandas`
- A股数据源：`tushare`、`akshare`、`baostock`
- 美股数据源：`yfinance`、`finnhub-python`
- 技术指标：`stockstats`
- 新闻抓取：`requests`、`beautifulsoup4`、`tenacity`
- 反爬绕过（可选）：`curl-cffi`
- 数据库（可选）：`pymongo`、`redis`

### 1.2 你需要认识的环境变量（只列 Dataflows 里直接用到的）

- `TA_CACHE_STRATEGY`: 缓存策略选择（见 `cache/__init__.py`），默认 `integrated`
- `TA_USE_APP_CACHE`: 是否优先用 app 层 MongoDB 同步数据（见 `cache/mongodb_cache_adapter.py` 与 `optimized_china_data.py`）
- `DEFAULT_CHINA_DATA_SOURCE`: A股默认数据源（见 `data_source_manager.py`）
- `DEFAULT_US_DATA_SOURCE`: 美股默认数据源（见 `data_source_manager.py`）
- `TA_GOOGLE_NEWS_SLEEP_MIN_SECONDS` / `TA_GOOGLE_NEWS_SLEEP_MAX_SECONDS`: Google News 抓取随机等待
- `TA_CHINA_MIN_API_INTERVAL_SECONDS`: A股 API 调用最小间隔（速率限制）
- 实时新闻/部分美股数据源（可选）：`FINNHUB_API_KEY`、`ALPHA_VANTAGE_API_KEY`、`NEWSAPI_KEY`

## 2. 两周学习路径（建议 10 个工作日）

每一天都遵循同一个学习节奏：

1) 阅读 1–2 个核心文件（从导出入口到具体 provider）  
2) 追一次调用链（从“外部函数”追到“数据源/缓存”）  
3) 做一个“小实验”（写一段最小调用脚本/REPL 调用，观察返回格式与日志）

### 第 1 周：建立架构与稳定性理解

#### Day 1：入口与公共 API 形状

- 阅读：
  - `tradingagents/dataflows/__init__.py`
  - `tradingagents/dataflows/interface.py`（先看顶部导入与数据源配置读取函数）
- 关键问题：
  - Dataflows 对外暴露了哪些函数？返回值是 DataFrame 还是字符串？为什么？
  - 为什么 `interface.py` 里有大量“兼容导入/占位函数”？
- 小实验：
  - 在 Python 中 `from tradingagents.dataflows import get_google_news, get_china_stock_data_unified`，打印 `callable(...)` 与 docstring，感受 API 表面形态。

#### Day 2：A股统一编排（data_source_manager 的核心）

- 阅读：
  - `tradingagents/dataflows/data_source_manager.py`（重点：`DataSourceManager.__init__`、默认数据源、优先级读取、缓存读取）
- 关键问题：
  - “默认数据源”与“降级优先级”分别在哪里决定？如何从数据库读取配置？
  - `use_app_cache_enabled()` 的作用是什么？它如何把 MongoDB 变成最高优先级？
- 小实验：
  - 在不配置数据库的情况下，观察默认降级顺序如何回退到本地逻辑。

#### Day 3：缓存系统（cache 子模块）

- 阅读：
  - `tradingagents/dataflows/cache/__init__.py`
  - `tradingagents/dataflows/cache/integrated.py`
  - `tradingagents/dataflows/cache/adaptive.py`
  - （选读）`tradingagents/dataflows/cache/file_cache.py`
- 关键问题：
  - `get_cache()` 返回的到底是什么对象？它提供哪些统一方法（save/load/find）？
  - “集成缓存”和“自适应缓存”的差别是什么？如何降级到文件缓存？
- 小实验：
  - 切换 `TA_CACHE_STRATEGY=file` vs `integrated`，观察初始化日志与缓存命中行为（哪怕没有数据库）。

#### Day 4：MongoDB 同步数据优先（app-cache 适配层）

- 阅读：
  - `tradingagents/dataflows/cache/mongodb_cache_adapter.py`
- 关键问题：
  - `TA_USE_APP_CACHE` 打开时，查询是如何按数据源优先级在 MongoDB 中挑数据的？
  - “MongoDB 缓存”与“文件缓存”的职责边界如何划分？
- 小实验：
  - 没有 MongoDB 时，确认适配器如何安全回退到传统模式（不应导致异常中断）。

#### Day 5：A股高层工具（optimized_china_data）

- 阅读：
  - `tradingagents/dataflows/optimized_china_data.py`（重点：`OptimizedChinaDataProvider.get_stock_data`、`get_fundamentals_data`）
  - （选读）`tradingagents/dataflows/realtime_metrics.py`
- 关键问题：
  - 这个文件为什么存在（已经有 data_source_manager 了）？它增加了哪些“工程化稳定性”？
  - 它如何在“API失败/缓存过期/缺字段”时做兜底？
- 小实验：
  - 强制刷新与不强制刷新对命中路径的影响（MongoDB/文件缓存/API）。

### 第 2 周：深入 providers / 新闻 / 技术指标，并做一项改动

#### Day 6：Provider 统一接口与数据标准化

- 阅读：
  - `tradingagents/dataflows/providers/base_provider.py`
  - `tradingagents/dataflows/providers/examples/example_sdk.py`（作为“如何新增 provider”的模板）
- 关键问题：
  - `BaseStockDataProvider` 的抽象方法是什么？标准化字段有哪些约定？
  - 为什么 provider 层强调“不做数据库写入/不做业务逻辑”？
- 小实验：
  - 阅读 `standardize_basic_info` / `standardize_quotes` 的字段映射，挑一个 raw_data 自己喂进去，看输出结构。

#### Day 7：A股 providers（以 AKShare 为例）

- 阅读：
  - `tradingagents/dataflows/providers/china/akshare.py`
  - （选读）`tradingagents/dataflows/providers/china/tushare.py`、`baostock.py`
- 关键问题：
  - provider 内部如何处理第三方库不稳定（反爬、TLS 指纹、重试、超时）？
  - 为什么 AKShare provider 会 monkey patch `requests.get`？它会带来哪些副作用与风险？
- 小实验：
  - 找一个最小调用路径：`AKShareProvider().get_stock_basic_info(...)` 或 `get_historical_data(...)`，观察异常处理与日志。

#### Day 8：港股/美股 providers（选择你最关心的一条）

- 港股阅读建议：
  - `tradingagents/dataflows/providers/hk/hk_stock.py`
  - `tradingagents/dataflows/providers/hk/improved_hk.py`
- 美股阅读建议：
  - `tradingagents/dataflows/providers/us/optimized.py`
  - `tradingagents/dataflows/providers/us/alpha_vantage_common.py`
  - `tradingagents/dataflows/providers/us/alpha_vantage_fundamentals.py`
  - `tradingagents/dataflows/providers/us/alpha_vantage_news.py`
  - `tradingagents/dataflows/providers/us/finnhub.py`
  - `tradingagents/dataflows/providers/us/yfinance.py`
- 关键问题：
  - 同一市场为什么会有多个 provider？降级顺序由哪里控制（环境变量/数据库配置）？
  - 美股侧 `data_source_manager.py` 里是如何做“启用数据源检查”和“数据库读取优先级”的？

#### Day 9：新闻与实时新闻（news 子域）

- 阅读：
  - `tradingagents/dataflows/news/__init__.py`
  - `tradingagents/dataflows/news/google_news.py`
  - `tradingagents/dataflows/news/realtime_news.py`
  - `tradingagents/dataflows/realtime_news_utils.py`（兼容层）
- 关键问题：
  - Google News 抓取如何处理 429/连接错误？重试策略是什么？
  - 实时新闻聚合器用了哪些源（RSS/API），以及如何做相关性/紧急度评估？
- 小实验：
  - 用同一关键词分别调用 Google News 与 realtime news，比较“覆盖度 vs 时效性”。

#### Day 10：技术指标 + 数据质量 + 做一次小改动

- 阅读：
  - `tradingagents/dataflows/technical/stockstats.py`
  - `tradingagents/dataflows/data_completeness_checker.py`
- 练习建议（选 1 项即可）：
  1) **增强数据完整性检查接入点**：在你自己的调用链里先跑一次完整性检查，不完整则强制刷新  
  2) **新增一个简单 provider**：基于 `providers/examples/example_sdk.py` 写一个“假数据源”用于测试链路  
  3) **给某个 provider 增加更稳的超时/重试**：只改动一个函数，保证失败能安全回退

完成标准：

- 你能解释“这个改动在调用链上处于哪一层”，以及“失败时如何被降级或缓存兜住”
- 你能给出一个可复现的最小调用示例（脚本/交互式调用）

## 3. 推荐的“阅读顺序清单”（按价值密度排序）

1) `tradingagents/dataflows/__init__.py`（对外 API 汇总）
2) `tradingagents/dataflows/interface.py`（公共接口层，很多上层直接用）
3) `tradingagents/dataflows/data_source_manager.py`（统一编排与降级）
4) `tradingagents/dataflows/cache/__init__.py` + `cache/integrated.py`（缓存入口与策略）
5) `tradingagents/dataflows/optimized_china_data.py`（工程化稳态封装）
6) `tradingagents/dataflows/providers/base_provider.py`（provider 统一接口）
7) 你关心市场的 provider（china/hk/us）
8) `tradingagents/dataflows/news/*`（新闻与实时新闻）
9) `tradingagents/dataflows/technical/*`（技术指标）
10) `tradingagents/dataflows/data_completeness_checker.py`、`realtime_metrics.py`（辅助增强）

## 4. 读代码时的“关注点模板”（每个文件都用同一套问题）

- **输入输出**：输入参数是什么？返回值类型是什么？是否稳定（DataFrame vs str vs Dict）？
- **边界条件**：没有依赖库/没有 API Key/没有数据库/被限流时，会发生什么？
- **降级链**：失败后去哪一层？有没有重复降级（同一个逻辑在多个地方实现）？
- **缓存策略**：缓存 key 如何构建？TTL/失效策略在哪？跨市场是否一致？
- **日志与可观测性**：关键路径是否有足够日志定位问题？是否存在过度日志（例如追踪日志）？

## 5. 一个现实提醒：README 与实际代码可能不完全一致

`tradingagents/dataflows/README.md` 描述了整体架构，但其中提到的个别文件在当前目录可能不存在或已迁移（例如某些“统一 DataFrame”工具、配置文件）。学习时以实际目录结构与 import 路径为准：  

- 以 `__init__.py` 与实际 import 为“对外 API 真相源”
- 以 `data_source_manager.py`/`cache/__init__.py` 为“核心链路真相源”

