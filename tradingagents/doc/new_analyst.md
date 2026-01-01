# 新闻分析师 (News Analyst) 工作流程

本文档描述了 `NewsAnalyst` 节点的内部工作流程。该分析师负责根据股票代码获取相关新闻，分析市场情绪，并生成投资建议。

## 核心流程图

```mermaid
flowchart TD
    Start([开始 NewsAnalyst]) --> Init[初始化配置]
    Init --> GetInfo[获取市场信息与公司名称]
    GetInfo --> CreateTool[创建 UnifiedNewsTool]
    CreateTool --> BuildPrompt[构建 Prompt与系统提示词]
    
    BuildPrompt --> CheckPre{是 DashScope/DeepSeek/Zhipu 模型?}
    
    %% 预处理分支 (针对特定国产模型优化)
    CheckPre -- 是 --> PreFetch[预处理: 强制直接调用新闻工具]
    PreFetch --> CheckPreSuccess{预获取成功?}
    CheckPreSuccess -- 是 --> GenPreReport[基于预获取数据生成报告]
    GenPreReport --> ReturnPre[返回分析结果]
    CheckPreSuccess -- 否 --> LogWarn[记录警告]
    LogWarn --> CallLLM
    
    %% 标准流程
    CheckPre -- 否 --> CallLLM["调用 LLM (bind_tools)"]
    
    CallLLM --> CheckGoogle{是 Google 模型?}
    
    %% Google 模型分支
    CheckGoogle -- 是 --> GoogleHandler["GoogleToolCallHandler
    (处理工具调用循环与报告生成)"]
    GoogleHandler --> Finalize
    
    %% 非 Google 模型分支
    CheckGoogle -- 否 --> CheckTools{LLM 返回了 ToolCalls?}
    
    CheckTools -- 无 ToolCalls --> Remediation[启动补救机制]
    Remediation --> ForceTool[强制调用新闻工具]
    ForceTool --> CheckForceSuccess{强制获取成功?}
    CheckForceSuccess -- 是 --> GenForceReport[基于强制获取数据重新生成报告]
    CheckForceSuccess -- 否 --> UseOriginal["使用原始结果 (可能为空)"]
    GenForceReport --> Finalize
    UseOriginal --> Finalize
    
    CheckTools -- 有 ToolCalls --> UseContent["直接使用 result.content
    (注意: 此处逻辑可能假定内容已在content中)"]
    UseContent --> Finalize
    
    %% 结束
    Finalize[封装结果] --> CreateMsg[创建清洁 AIMessage]
    CreateMsg --> UpdateState["更新状态: 
    1. messages
    2. news_report
    3. tool_call_count"]
    UpdateState --> End([结束])

    style Start fill:#f9f,stroke:#333,stroke-width:2px
    style End fill:#f9f,stroke:#333,stroke-width:2px
    style GoogleHandler fill:#e1f5fe,stroke:#01579b
    style PreFetch fill:#e8f5e9,stroke:#2e7d32
    style Remediation fill:#fff3e0,stroke:#ef6c00
```

## 流程详解

1.  **初始化与信息获取**
    *   从状态中获取 `ticker` 和 `date`。
    *   识别市场类型（A股/港股/美股）。
    *   解析公司名称（如将代码转换为"贵州茅台"）。

2.  **模型特定预处理 (Optimization)**
    *   针对 DashScope (阿里)、DeepSeek、Zhipu (智谱) 等模型。
    *   **目的**：避免这些模型在工具调用上的不稳定性。
    *   **动作**：在调用 LLM 之前，直接在 Python 代码中执行 `UnifiedNewsTool`。
    *   如果获取到新闻，直接将新闻拼接到 Prompt 中让 LLM 分析，**跳过后续所有步骤**。

3.  **LLM 调用**
    *   如果预处理未命中或失败，执行标准的 LLM 调用 (`chain.invoke`)。
    *   模型绑定了 `get_stock_news_unified` 工具。

4.  **Google 模型特殊处理**
    *   如果检测到是 Google (Gemini) 模型，移交给 `GoogleToolCallHandler`。
    *   该处理器内部实现了 "执行工具 -> 获取结果 -> 生成最终报告" 的完整闭环。

5.  **标准模型处理与补救**
    *   **无工具调用 (Zero Tool Calls)**：
        *   如果 LLM 没有调用工具（直接返回了闲聊或拒绝），触发**补救机制**。
        *   系统强制调用新闻工具，将结果再次喂给 LLM 生成报告。
    *   **有工具调用**：
        *   当前代码逻辑中，如果非 Google 模型返回了工具调用，系统倾向于直接使用其 `content`（注意：这里可能存在逻辑分支的简化，通常 OpenAI 模型在调用工具时 content 为空，依赖 Graph 的下一跳来执行工具，但 NewsAnalyst 似乎试图在节点内闭环或返回清洁消息）。

6.  **结果封装**
    *   生成一个不包含工具调用信息的 `AIMessage` (清洁消息)。
    *   更新 `news_report` 状态。
    *   增加 `news_tool_call_count` 计数器以防止死循环。
