# 股票数据获取流程图（工程实现）

本文用 Mermaid 流程图把工程内“获取股票数据”的关键路径串起来，覆盖：

- 在线查询链路（tradingagents 调用数据源管理器，带缓存与降级）
- 后端 API 查询链路（FastAPI 从 MongoDB 读取）
- 后端数据同步链路（worker 从 Provider 拉取并写入 MongoDB）
- AKShareProvider 内部调用细节（反爬、重试、各接口调用）

## 在线查询链路（tradingagents：统一接口 → DataSourceManager → Provider）

```mermaid
flowchart TD
U["调用方\nAgents / CLI / API封装"] --> I["tradingagents/dataflows/interface.py\nget_china_stock_data_unified()"];
I --> D["tradingagents/dataflows/data_source_manager.py\nDataSourceManager.get_stock_data()"];
D --> M{current_source == MongoDB?};
M -->|是| M1["_get_mongodb_data()"];
M1 --> M2{MongoDB命中?};
M2 -->|命中| F["_format_stock_data_response()\n技术指标计算"];
M2 -->|未命中/异常| FB["_try_fallback_sources()"];
M -->|否| S{current_source};
S -->|Tushare| T["_get_tushare_data()"];
S -->|AKShare| A["_get_akshare_data()"];
S -->|BaoStock| B["_get_baostock_data()"];
T --> Q{结果有效?};
A --> Q;
B --> Q;
Q -->|是| F;
Q -->|否| FB;
FB --> O{按优先级尝试备用源};
O --> T;
O --> A;
O --> B;
F --> R["返回格式化文本/结构化结果"];
```

关键实现位置：
- 统一入口： [interface.py:get_china_stock_data_unified](file:///e:/workspace/GitRepository/TradingAgents-CN/tradingagents/dataflows/interface.py#L1514-L1627)
- 调度与降级： [data_source_manager.py:get_stock_data](file:///e:/workspace/GitRepository/TradingAgents-CN/tradingagents/dataflows/data_source_manager.py#L1031-L1142)
- MongoDB 优先与降级： [data_source_manager.py:_get_mongodb_data](file:///e:/workspace/GitRepository/TradingAgents-CN/tradingagents/dataflows/data_source_manager.py#L1143-L1182)
- AKShare 历史数据拉取： [data_source_manager.py:_get_akshare_data](file:///e:/workspace/GitRepository/TradingAgents-CN/tradingagents/dataflows/data_source_manager.py#L1283-L1324)

## 后端 API 查询链路（FastAPI：MongoDB 读 → 返回）

这一条链路是“读库返回”，不直接调用外部数据源；外部数据源拉取通常由 worker 同步写入 MongoDB 后被查询到。

```mermaid
flowchart TD
FE["前端/调用方"] --> API["app/routers/stocks.py\nREST API"];
API --> DB[(MongoDB)];
DB --> C1["stock_basic_info\n按 source 优先级查找"];
DB --> C2["stock_financial_data\n最新财务指标"];
DB --> C3["market_quotes\n最新行情"];
DB --> C4["stock_daily_data / historical\n历史行情"];
C1 --> RESP["组装响应并返回"];
C2 --> RESP;
C3 --> RESP;
C4 --> RESP;
```

关键实现位置：
- A 股基础信息按 source 优先级读取： [stocks.py](file:///e:/workspace/GitRepository/TradingAgents-CN/app/routers/stocks.py#L251-L289)

## 后端数据同步链路（worker：Provider 拉取 → 标准化 → 写 MongoDB）

```mermaid
flowchart TD
JOB["定时任务/手动触发"] --> SVC["app/worker/akshare_sync_service.py\nAKShareSyncService.initialize()"];
SVC --> P["get_akshare_provider()\n全局单例"];
SVC --> DB[(MongoDB)];
SVC --> L["provider.get_stock_list()"];
L --> BATCH{批次处理};
BATCH --> BI["provider.get_stock_basic_info(code)"];
BATCH --> Q["provider.get_batch_stock_quotes(codes)"];
BATCH --> H["provider.get_historical_data(code, range)"];
BATCH --> FD["provider.get_financial_data(code)"];
BATCH --> N["provider.get_stock_news(code)"];
BI --> W1["写 stock_basic_info"];
Q --> W2["写 market_quotes"];
H --> W3["写 stock_daily_data / historical"];
FD --> W4["写 stock_financial_data"];
N --> W5["写 news / stock_news"];
W1 --> DB;
W2 --> DB;
W3 --> DB;
W4 --> DB;
W5 --> DB;
```

关键实现位置：
- 同步服务初始化与获取列表： [akshare_sync_service.py](file:///e:/workspace/GitRepository/TradingAgents-CN/app/worker/akshare_sync_service.py#L37-L114)

## AKShareProvider 内部数据获取细节（反爬/重试/标准化）

```mermaid
flowchart TD
INIT["AKShareProvider.__init__()"] --> PATCH["_initialize_akshare()"];
PATCH --> C1{curl_cffi 可用?};
C1 -->|是| TLS["curl_cffi impersonate=chrome120\n用于 eastmoney.com"];
C1 -->|否| REQ["使用 requests"];
PATCH --> MONKEY["monkey patch requests.get\nheaders + 0.5s限速 + 重试"];
PATCH --> OK["connected=True\nsocket超时=60s"];
OK --> LIST["get_stock_list()\nak.stock_info_a_code_name"];
OK --> BASIC["get_stock_basic_info(code)\nak.stock_individual_info_em\n失败→缓存列表兜底"];
OK --> HIST["get_historical_data(code, range, period)\nak.stock_zh_a_hist adjust=qfq\n列名标准化"];
OK --> QUOTE1["get_stock_quotes(code)\nak.stock_bid_ask_em\n手→股, open/high/low 对齐"];
OK --> QUOTE2["get_batch_stock_quotes(codes)\n优先 ak.stock_zh_a_spot(Sina)\n失败→ak.stock_zh_a_spot_em"];
OK --> FIN["get_financial_data(code)\nabstract/balance/profit/cashflow"];
OK --> NEWS["get_stock_news(code)"];
NEWS --> DOCKER{Docker?};
DOCKER -->|是| DIRECT["直连东方财富 JSONP Search API\ncurl_cffi"];
DOCKER -->|否| AKNEWS["ak.stock_news_em"];
DIRECT -->|失败| AKNEWS;
AKNEWS --> STRUCT["新闻结构化\n分类/情绪/关键词/重要性"];
```

关键实现位置：
- 初始化、反爬补丁： [akshare.py:_initialize_akshare](file:///e:/workspace/GitRepository/TradingAgents-CN/tradingagents/dataflows/providers/china/akshare.py#L36-L167)
- 历史数据与列名标准化： [akshare.py:get_historical_data](file:///e:/workspace/GitRepository/TradingAgents-CN/tradingagents/dataflows/providers/china/akshare.py#L896-L998)
- 单只实时行情字段对齐： [akshare.py:get_stock_quotes](file:///e:/workspace/GitRepository/TradingAgents-CN/tradingagents/dataflows/providers/china/akshare.py#L702-L797)
- 批量实时行情快照： [akshare.py:get_batch_stock_quotes](file:///e:/workspace/GitRepository/TradingAgents-CN/tradingagents/dataflows/providers/china/akshare.py#L555-L701)
- 新闻（Docker 直连 + 回退 + 结构化）： [akshare.py:get_stock_news](file:///e:/workspace/GitRepository/TradingAgents-CN/tradingagents/dataflows/providers/china/akshare.py#L1183-L1362)
