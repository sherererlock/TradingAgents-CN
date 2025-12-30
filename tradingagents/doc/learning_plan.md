以下是为你规划的最佳学习路径：

### 第一阶段：理解骨架与流程 (Architecture & Flow)
首先弄清楚系统是如何运转的，数据如何在各个 Agent 之间传递。

1.  **[agent_states.py](file:///e:\workspace\GitRepository\TradingAgents-CN\tradingagents\agents\utils\agent_states.py)** (关键数据结构)
    *   **核心点**: 查看 `AgentState` 类。这是整个系统的“共享内存”。
    *   **关注**: 它定义了所有 Agent 共享的数据字段，如 `company_of_interest` (目标公司), `market_report` (市场报告), `investment_plan` (投资计划) 等。理解了这个，你就知道 Agent 之间在交换什么信息。

2.  **[trading_graph.py](file:///e:\workspace\GitRepository\TradingAgents-CN\tradingagents\graph\trading_graph.py)** (入口与编排)
    *   **核心点**: 这是系统的总指挥部。
    *   **关注**: `TradingAgentsGraph` 类如何初始化。它定义了整个工作流的节点（Nodes）和边（Edges）。

3.  **[setup.py](file:///e:\workspace\GitRepository\TradingAgents-CN\tradingagents\graph\setup.py)** (图的构建)
    *   **核心点**: 这里的 `setup_graph` 方法实际构建了 `LangGraph` 状态图。
    *   **关注**: 它是如何将 `Analyst` -> `Researcher` -> `Manager` -> `Trader` 这些节点串联起来的。注意 `add_node` 和 `add_edge` 的逻辑。

---

### 第二阶段：理解大脑与决策 (Agents & Logic)
了解具体的 Agent 是如何工作的，它们如何思考和决策。

4.  **[market_analyst.py](file:///e:\workspace\GitRepository\TradingAgents-CN\tradingagents\agents\analysts\market_analyst.py)** (代表性的分析师)
    *   **核心点**: 这是一个典型的“工具使用者” Agent。
    *   **关注**: `create_market_analyst` 函数。看它如何接收 `state`，如何定义 Prompt，以及如何调用工具 (`toolkit.get_stock_market_data_unified`) 来获取数据。

5.  **[research_manager.py](file:///e:\workspace\GitRepository\TradingAgents-CN\tradingagents\agents\managers\research_manager.py)** (管理者/裁判)
    *   **核心点**: 这是一个“综合决策” Agent。
    *   **关注**: 它如何读取之前分析师生成的报告 (`market_report`, `news_report` 等)，并根据 Prompt 综合生成 `investment_plan`。它是连接分析与交易的关键桥梁。

6.  **[trader.py](file:///e:\workspace\GitRepository\TradingAgents-CN\tradingagents\agents\trader\trader.py)** (最终执行者)
    *   **核心点**: 系统的输出端。
    *   **关注**: 它如何根据投资计划生成最终的 `买入/卖出/持有` 建议和目标价格。

---

### 第三阶段：理解血液与养分 (Data & Tools)
最后了解系统是如何获取外部数据来支撑决策的。

7.  **[stock_data_service.py](file:///e:\workspace\GitRepository\TradingAgents-CN\tradingagents\dataflows\stock_data_service.py)** (数据服务)
    *   **核心点**: 数据的获取源头。
    *   **关注**: 它的降级机制（MongoDB -> 增强获取器 -> 兜底方案）。这展示了如何在生产环境中保证数据的高可用性。

8.  **[interface.py](file:///e:\workspace\GitRepository\TradingAgents-CN\tradingagents\dataflows\interface.py)** (数据接口)
    *   **核心点**: Agent 调用的统一接口。
    *   **关注**: `get_stock_market_data_unified` 等函数，它们封装了底层的数据复杂性，为 Agent 提供干净的接口。

### 总结建议
建议你按照 **`State` (数据) -> `Graph` (流程) -> `Agent` (个体) -> `Data` (底层)** 的顺序阅读。

你可以从 [agent_states.py](file:///e:\workspace\GitRepository\TradingAgents-CN\tradingagents\agents\utils\agent_states.py) 开始，先看懂数据结构，然后去 [setup.py](file:///e:\workspace\GitRepository\TradingAgents-CN\tradingagents\graph\setup.py) 看流程图是如何画出来的。