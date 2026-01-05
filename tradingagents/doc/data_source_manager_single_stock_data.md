## DataSourceManager：单只股票可获取的数据（按类别整理）

本文总结 [data_source_manager.py](file:///e:/workspace/GitRepository/TradingAgents-CN/tradingagents/dataflows/data_source_manager.py) 中，围绕“单只股票”可以获取到的交易相关数据，并按用途进行分类，方便交易入门者理解与使用。

### 1) 行情/交易数据（历史K线）

对应入口：
- 文本报告接口：[get_stock_data](file:///e:/workspace/GitRepository/TradingAgents-CN/tradingagents/dataflows/data_source_manager.py#L1031-L1142)
- DataFrame接口：[get_stock_dataframe](file:///e:/workspace/GitRepository/TradingAgents-CN/tradingagents/dataflows/data_source_manager.py#L911-L986) + 标准化：[ _standardize_dataframe](file:///e:/workspace/GitRepository/TradingAgents-CN/tradingagents/dataflows/data_source_manager.py#L987-L1030)

主要覆盖的数据项（以日/周/月等周期为单位）：
- 价格：开盘(open)、最高(high)、最低(low)、收盘(close)
- 成交：成交量(vol/volume)、成交额(amount)（不同数据源字段名会被标准化）
- 日期：date/trade_date（会尽量转成日期并排序）
- 衍生列：pct_change（若缺失会用收盘价自动计算）

周期支持：
- 参数 period 支持 daily/weekly/monthly（实际可用性取决于具体数据源与缓存是否有对应周期数据）

### 2) 技术指标（由历史K线计算）

对应实现：
- 指标计算与报告生成：[ _format_stock_data_response](file:///e:/workspace/GitRepository/TradingAgents-CN/tradingagents/dataflows/data_source_manager.py#L682-L910)

会基于历史 close（以及 high/low/volume 等）计算并输出的指标/信号：
- 均线 MA：MA5、MA10、MA20、MA60
- RSI：
  - 同花顺风格：RSI6、RSI12、RSI24（使用 ewm 的“中国式SMA”近似）
  - 国际参考：RSI14（简单移动平均）
  - 常用信号：RSI 超买/超卖（阈值示例：>=80 / <=20），以及 RSI 多头/空头排列判断
- MACD：
  - DIF、DEA、MACD柱
  - 常用信号：金叉/死叉（DIF 上穿/下穿 DEA）
- 布林带 BOLL：
  - 中轨(boll_mid)、上轨(boll_upper)、下轨(boll_lower)
  - 常用信号：价格位置百分比（接近上轨/下轨的提示）
- 统计信息（展示最近若干交易日）：
  - 最高价、最低价、平均价、平均成交量（做了多列名兼容的安全读取）

注意：
- 这些技术指标不是“数据源直接给的”，而是“拿到历史行情后在本地计算出来的”。

### 3) 股票基础信息（公司/标的静态信息 + 可选快照行情）

对应入口：
- [get_stock_info](file:///e:/workspace/GitRepository/TradingAgents-CN/tradingagents/dataflows/data_source_manager.py#L1421-L1530)
- 兼容接口（单只股票/全量列表）：[get_stock_basic_info](file:///e:/workspace/GitRepository/TradingAgents-CN/tradingagents/dataflows/data_source_manager.py#L1531-L1570)

单只股票常见字段（不同数据源可能有差异）：
- symbol：股票代码
- name：股票简称/名称
- area：地区（可能为“未知”）
- industry：行业（代码里做了“行业/板块字段归一化”的处理，避免把“主板/创业板”等当行业）
- market：上市市场/板块（可能为“未知”）
- list_date：上市日期（可能为“未知”）
- source：数据来源标记（如 app_cache / tushare / akshare / baostock 等）

可选的“快照行情附加字段”（当启用 app Mongo 缓存且命中行情集合时）：
- current_price：当前/最新价格
- change_pct：涨跌幅
- volume：成交量
- quote_date：行情日期
- quote_source：行情来源标记

### 4) 基本面/财务与估值

对应入口：
- 统一入口：[get_fundamentals_data](file:///e:/workspace/GitRepository/TradingAgents-CN/tradingagents/dataflows/data_source_manager.py#L249-L315)
- MongoDB财务格式化：[ _format_financial_data](file:///e:/workspace/GitRepository/TradingAgents-CN/tradingagents/dataflows/data_source_manager.py#L1878-L1992)

这部分数据的现实情况（以当前文件实现为准）：
- MongoDB：可以读取财务数据并生成结构化报告（主要可用）
- Tushare：当前实现是“暂时不可用/未实现”（会提示不可用）
- AKShare：当前实现为“生成一份基本面分析文本”（不含详细财务表）

MongoDB 财务报告会尝试覆盖的指标（字段存在才会输出）：
- 报告期：report_period / end_date
- 财务指标：
  - 营业总收入：revenue / total_revenue
  - 净利润：net_profit / net_income
  - 总资产：total_assets
  - 总负债：total_liab
  - 股东权益：total_equity
- 估值指标（优先从 stock_basic_info 集合补充，缺失则尝试从财务数据本身取）：
  - 市盈率：pe、pe_ttm
  - 市净率：pb
  - 总市值：total_mv（亿元）
  - 流通市值：circ_mv（亿元）
  - 市销率：ps（如果只能从财务数据获得）
- 盈利能力：
  - ROE、ROA、毛利率(gross_margin)、净利率(netprofit_margin / net_margin)
- 现金流：
  - 经营活动现金流：n_cashflow_act
  - 投资活动现金流：n_cashflow_inv_act
  - 期末现金及等价物：c_cash_equ_end_period

### 5) 新闻数据（公司新闻/市场新闻）

对应入口：
- 统一入口：[get_news_data](file:///e:/workspace/GitRepository/TradingAgents-CN/tradingagents/dataflows/data_source_manager.py#L329-L401)
- MongoDB实现：[ _get_mongodb_news](file:///e:/workspace/GitRepository/TradingAgents-CN/tradingagents/dataflows/data_source_manager.py#L2049-L2068)

这部分数据的现实情况（以当前文件实现为准）：
- MongoDB：从 stock_news 集合读取新闻列表（主要可用）
- Tushare / AKShare：当前实现为“暂时不可用”（会返回空列表并触发降级）

MongoDB新闻的字段结构取决于入库数据，但代码层面至少会按以下条件查询/排序：
- symbol：股票代码（6位补零后）
- publish_time：发布时间（用于 hours_back 回溯过滤与倒序排序）
- 其它可能字段（常见但不保证）：title、content/summary、source、url、keywords 等

### 6) 数据源与降级逻辑（理解“为什么有时拿不到某类数据”）

核心点：
- 行情数据：支持 MongoDB / Tushare / AKShare / BaoStock 获取；失败会按数据库配置优先级尝试降级（默认回退顺序也内置了一份）
- 技术指标：只要拿到历史行情，就能计算
- 基本面与新闻：目前“只有 MongoDB 路径”真正实现了详细数据；其他数据源多为占位/生成文本

相关实现参考：
- 数据源优先级（按市场分类从数据库读取，失败则用默认顺序）：[ _get_data_source_priority_order](file:///e:/workspace/GitRepository/TradingAgents-CN/tradingagents/dataflows/data_source_manager.py#L91-L172)
- 行情数据降级：[ _try_fallback_sources](file:///e:/workspace/GitRepository/TradingAgents-CN/tradingagents/dataflows/data_source_manager.py#L1378-L1419)
- 基本面降级：[ _try_fallback_fundamentals](file:///e:/workspace/GitRepository/TradingAgents-CN/tradingagents/dataflows/data_source_manager.py#L2015-L2048)
- 新闻降级：[ _try_fallback_news](file:///e:/workspace/GitRepository/TradingAgents-CN/tradingagents/dataflows/data_source_manager.py#L2091-L2123)

