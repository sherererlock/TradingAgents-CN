# CacheManager（缓存系统说明）

本文档基于 `tradingagents/dataflows/cache/` 目录内源码整理，描述 TradingAgents-CN 的缓存体系结构、策略开关、Key/TTL 规则、后端与降级逻辑，以及它与数据源管理器（DataSourceManager）的关系。

## 1. 缓存系统在项目里的位置

这个目录里实际存在两类“缓存/存储”能力：

1) **分析链路的请求结果缓存（Result Cache）**
- 用途：缓存从 provider 拉取的行情/新闻/基本面等结果，减少外部 API 调用，提高多 Agent 并发分析速度。
- 典型调用方：`tradingagents/dataflows/data_source_manager.py`（通过 `get_cache()` 初始化 `cache_manager`，并在拉取前后读写）。

2) **应用侧同步数据读取（App MongoDB Adapter / App Cache）**
- 用途：当 `TA_USE_APP_CACHE`（由 `runtime_settings.use_app_cache_enabled` 读取）启用时，优先从 app 的 MongoDB 同步库读取“已落库的权威数据”（基础信息/历史行情/财务/新闻/社媒/快照）。
- 典型调用方：`DataSourceManager` 把它当作“最高优先级数据源”（不是 result cache 的一部分）。

这两条链路都在 `cache/` 目录下，因此阅读时建议先分清：
- `get_cache()` 返回的是 **Result Cache** 的统一入口；
- `MongoDBCacheAdapter` / `app_adapter.py` 提供的是 **App 同步库读取适配层**。

## 2. 统一入口与策略选择（get_cache）

### 2.1 入口文件
- 统一入口：[`cache/__init__.py`](file:///e:/workspace/GitRepository/TradingAgents-CN/tradingagents/dataflows/cache/__init__.py)

### 2.2 策略开关
通过环境变量 `TA_CACHE_STRATEGY` 决定 `get_cache()` 返回哪套实现：
- `integrated` 或 `adaptive`：优先返回 `IntegratedCacheManager`（内部再决定启用自适应后端还是文件缓存）
- 其他值（例如 `file`）：返回 `StockDataCache`（纯文件缓存）

默认值是：`integrated`（即默认尝试启用集成/自适应缓存，失败则降级到文件缓存）。

## 3. 对外接口层（调用方应该依赖什么）

无论实际后端是什么，调用方应尽量只使用这些“统一接口”方法（来自 `StockDataCache` 或 `IntegratedCacheManager` 的同名方法）：

- 股票行情：
  - `save_stock_data(symbol, data, start_date, end_date, data_source="...") -> cache_key`
  - `find_cached_stock_data(symbol, start_date, end_date, data_source=None, max_age_hours=None) -> cache_key|None`
  - `load_stock_data(cache_key) -> DataFrame|str|None`
- 新闻：
  - `save_news_data(...) / load_news_data(...)`（部分实现只提供保存）
- 基本面：
  - `save_fundamentals_data(...) / load_fundamentals_data(...)`
  - `find_cached_fundamentals_data(...)`（集成缓存里即使启用 adaptive，也会降级走文件缓存查找）

## 4. 集成缓存（IntegratedCacheManager）：策略编排层

### 4.1 文件位置
- [`cache/integrated.py`](file:///e:/workspace/GitRepository/TradingAgents-CN/tradingagents/dataflows/cache/integrated.py)

### 4.2 核心职责
`IntegratedCacheManager` 把“对外统一接口”与“后端实现细节”隔离开：
- `legacy_cache`：始终存在的文件缓存（`StockDataCache`），作为稳定兜底。
- `adaptive_cache`：可选的自适应缓存（`AdaptiveCacheSystem`）。如果初始化成功，则 `use_adaptive=True`。

### 4.3 路由与降级
- `use_adaptive=True` 时：
  - 股票/新闻/基本面保存与加载主要走 `AdaptiveCacheSystem`。
  - 基本面 **查找**（`find_cached_fundamentals_data`）仍然固定降级到文件缓存查找，以保持旧逻辑兼容。
- `use_adaptive=False` 时：全部走文件缓存（`StockDataCache`）。

### 4.4 清理与统计
- `get_cache_stats()`：统一返回标准统计结构，并附带 `backend_info`。
- `clear_expired_cache()`：
  - 如果启用 adaptive，会先清理 adaptive 的过期文件缓存；
  - 然后总会清理 legacy 文件缓存。
- `clear_old_cache(max_age_days)`：
  - 对 Redis：仅能 `flushdb`（当 `max_age_days==0`），否则依赖 TTL 自动过期；
  - 对 MongoDB：按 `created_at` 清理 `stock_data/news_data/fundamentals_data` 这三个集合；
  - 对文件缓存：调用 legacy 的 `clear_old_cache()`。

注意：自适应缓存的 MongoDB 写入集合与上述清理/统计所用集合在当前实现中存在不一致，详见第 8 节“已知实现差异”。

## 5. 自适应缓存（AdaptiveCacheSystem）：多后端实现层

### 5.1 文件位置
- [`cache/adaptive.py`](file:///e:/workspace/GitRepository/TradingAgents-CN/tradingagents/dataflows/cache/adaptive.py)

### 5.2 后端选择与配置来源
`AdaptiveCacheSystem` 从 `DatabaseManager.get_config()` 读取 `config["cache"]`：
- `primary_backend`：`redis` / `mongodb` / `file`
- `fallback_enabled`：主要后端失败是否降级到文件
- `ttl_settings`：按市场与数据类型配置 TTL 秒数

### 5.3 Key 规则
- Key = `md5(f"{symbol}_{start_date}_{end_date}_{data_source}_{data_type}")`
  - `data_type` 在集成缓存里常用：`stock_data`、`news_data`、`fundamentals_data`

### 5.4 TTL 规则
- 市场识别：
  - `symbol` 为 6 位纯数字 → `china`
  - 否则 → `us`
- TTL key：`f"{market}_{data_type}"`，例如：
  - `china_stock_data`
  - `us_news_data`
  - `china_fundamentals_data`
- 若配置缺失，默认 TTL = 7200 秒。

### 5.5 序列化与存储格式
- 文件后端：`{cache_key}.pkl`，pickle 保存结构 `{data, metadata, timestamp, backend}`。
- Redis：对上述结构 pickle 后 `setex(cache_key, ttl_seconds, bytes)`。
- MongoDB：写入 `tradingagents.cache` 集合（字段包含 `expires_at`）。
  - DataFrame：保存为 `data.to_json()`（`data_type='dataframe'`）
  - 其他：pickle 后转 hex 字符串（`data_type='pickle'`）

### 5.6 读取与有效性
- 按 `primary_backend` 读取，失败且 `fallback_enabled=True` 时尝试文件后端。
- 文件后端在读取后会二次校验 `timestamp + ttl` 是否过期；
- Redis/MongoDB 的过期依赖各自机制：
  - Redis：TTL 自动删除键
  - MongoDB：实现中通过 `expires_at` 在读取时检查并删除（不是 TTL index 自动清理）

## 6. 文件缓存（StockDataCache）：纯文件实现层

### 6.1 文件位置
- [`cache/file_cache.py`](file:///e:/workspace/GitRepository/TradingAgents-CN/tradingagents/dataflows/cache/file_cache.py)

### 6.2 目录结构
默认根目录：`tradingagents/dataflows/cache/data_cache/`（相对 `file_cache.py` 所在目录）
- `china_stocks/`、`us_stocks/`
- `china_news/`、`us_news/`
- `china_fundamentals/`、`us_fundamentals/`
- `metadata/`：`{cache_key}_meta.json`

### 6.3 Key 规则
- `cache_key = f"{symbol}_{data_type}_{md5[:12]}"`
- md5 输入包含 `data_type + symbol + kwargs(sorted)`，kwargs 常见包括：
  - `start_date/end_date`
  - `source`（数据源）
  - `market`（china/us）
  - fundamentals 里还会包含 `date`（按天生成 key）

### 6.4 TTL 与有效性
- 元数据文件会写入 `cached_at`。
- `is_cache_valid(cache_key, max_age_hours=None, symbol=None, data_type=None)`：
  - 若 `max_age_hours=None`，会根据 `market_type + data_type` 从 `cache_config` 取默认 TTL。
  - 默认 TTL（实现内置）：
    - A 股历史数据：1 小时
    - 美股历史数据：2 小时
    - A 股新闻：4 小时，美股新闻：6 小时
    - A 股基本面：12 小时，美股基本面：24 小时

### 6.5 查找策略（find_cached_stock_data）
- 先生成“精确匹配 key”并校验 TTL；
- 若精确未命中，会遍历 `metadata/*.json` 找“部分匹配”（同 symbol、同 market、同 data_type，且 data_source 匹配或未指定），再校验 TTL。

### 6.6 内容过长与“跳过缓存”
文件缓存支持可选的长度检查：
- `ENABLE_CACHE_LENGTH_CHECK=true` 时启用
- `MAX_CACHE_CONTENT_LENGTH` 默认 50000 字符
- 如果内容过长且没有“长文本提供商”可用，会选择跳过缓存
  - “长文本提供商可用性”通过环境变量是否存在来判断：`DASHSCOPE_API_KEY/OPENAI_API_KEY/GOOGLE_API_KEY/ANTHROPIC_API_KEY`

注意：在 `save_*` 的“跳过缓存”分支里会返回一个“虚拟 key”，但不会落盘数据/元数据；调用方不应期待后续 `load_*` 可以通过该 key 读回数据。

## 7. DatabaseCacheManager（db_cache.py）：独立的 MongoDB+Redis 缓存实现

### 7.1 文件位置
- [`cache/db_cache.py`](file:///e:/workspace/GitRepository/TradingAgents-CN/tradingagents/dataflows/cache/db_cache.py)

### 7.2 定位
这是另一套“直接使用 pymongo + redis”的数据库缓存实现，提供：
- MongoDB（持久化）+ Redis（短 TTL 加速）
- 对股票/新闻/基本面分别落到三个集合：`stock_data/news_data/fundamentals_data`

它在 `cache/__init__.py` 中被导入，但 `get_cache()` 当前默认走 `IntegratedCacheManager`（即 adaptive+file 或纯 file），因此 `DatabaseCacheManager` 更偏“可选/旧实现/独立使用”。

### 7.3 配置与连接
- 默认端口与密码从环境变量读：
  - `MONGODB_PORT`（默认 27018）、`REDIS_PORT`（默认 6380）
  - `MONGODB_PASSWORD`、`REDIS_PASSWORD`（默认 `tradingagents123`）
  - 或直接提供 `MONGODB_URL/REDIS_URL`
- MongoDB 超时：
  - `MONGO_CONNECT_TIMEOUT_MS`、`MONGO_SOCKET_TIMEOUT_MS`、`MONGO_SERVER_SELECTION_TIMEOUT_MS`

### 7.4 Key 与 TTL
- key 形如：`"{data_type}:{symbol}:{md5[:16]}"`
- Redis TTL：
  - 股票数据：6 小时
  - 新闻/基本面：24 小时
- MongoDB 不自动过期（由 `find_cached_*` 的 `max_age_hours` 查询窗口控制）。

## 8. App 同步库读取：MongoDBCacheAdapter 与 app_adapter

### 8.1 MongoDBCacheAdapter
- 文件：[`cache/mongodb_cache_adapter.py`](file:///e:/workspace/GitRepository/TradingAgents-CN/tradingagents/dataflows/cache/mongodb_cache_adapter.py)
- 开关：`runtime_settings.use_app_cache_enabled()`（通常由 `TA_USE_APP_CACHE` 控制）
- 读取对象：app 的 MongoDB 同步数据（例如 `stock_daily_quotes/stock_financial_data/stock_news/market_quotes` 等）
- 关键能力：
  - `_get_data_source_priority(symbol)` 会从 `system_configs.data_source_configs` 读取启用的数据源并按 priority 排序，且按市场分类过滤。
  - `get_historical_data` 按优先级逐个 data_source 查询，命中则返回 DataFrame。

### 8.2 app_adapter.py
- 文件：[`cache/app_adapter.py`](file:///e:/workspace/GitRepository/TradingAgents-CN/tradingagents/dataflows/cache/app_adapter.py)
- 提供两个“模块级函数”用于轻量读取：
  - `get_basics_from_cache(stock_code)`：读 `stock_basic_info`
  - `get_market_quote_dataframe(symbol)`：读 `market_quotes` 并映射为单行 DataFrame

## 9. 与 DataSourceManager 的衔接（缓存如何被触发）

`DataSourceManager` 在初始化时会尝试启用统一缓存管理器：
- 如果 `get_cache()` 成功：`self.cache_manager` 生效，`self.cache_enabled=True`
- 拉取行情（例如 `_get_tushare_data`）时常见流程是：
  1) `find_cached_stock_data(...) -> cache_key`（命中）
  2) `load_stock_data(cache_key) -> DataFrame`
  3) 未命中则调用 provider 拉取
  4) 拉取成功后 `save_stock_data(...)` 回写

另外，当 app 同步库读取开关启用时，`DataSourceManager` 还会把 `MongoDBCacheAdapter` 视作最高优先级数据源（属于“数据源优先级/降级”体系，而不是 result cache）。

## 10. 已知实现差异（按当前代码如实记录）

1) **AdaptiveCacheSystem 的 MongoDB 写入集合与统计/清理集合不一致**
- `AdaptiveCacheSystem._save_to_mongodb` 写入的是 `tradingagents.cache` 集合（单集合）。
- 但 `AdaptiveCacheSystem.get_cache_stats` 统计的是 `stock_data/news_data/fundamentals_data` 三个集合。
- `IntegratedCacheManager.clear_old_cache` 清理的也是 `stock_data/news_data/fundamentals_data` 三个集合。

因此：当 primary_backend=mongodb 且走 adaptive 写入时，统计/清理可能看不到或清不到 `db.cache` 中的数据。

2) **文件缓存的“跳过缓存”返回虚拟 key**
- `StockDataCache.save_*` 在判定内容过长要跳过缓存时，仅返回 key，不落盘不写元数据。
- 这更像一种“告知上层本次未缓存”的日志辅助，而不是可回读的缓存条目。

3) **基本面查找在 integrated+adaptive 下仍走 legacy 文件缓存**
- `IntegratedCacheManager.find_cached_fundamentals_data` 在 `use_adaptive=True` 时仍固定降级到文件缓存查找。

## 11. 快速使用示例

```python
from tradingagents.dataflows.cache import get_cache

cache = get_cache()

# 写入行情（DataFrame）
cache_key = cache.save_stock_data(
    symbol="600000",
    data=df,
    start_date="2024-01-01",
    end_date="2024-12-31",
    data_source="tushare",
)

# 查找 + 读取
hit_key = cache.find_cached_stock_data(
    symbol="600000",
    start_date="2024-01-01",
    end_date="2024-12-31",
    data_source="tushare",
)

if hit_key:
    df2 = cache.load_stock_data(hit_key)
```
