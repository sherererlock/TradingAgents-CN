这个文件实现了 **反思与记忆更新机制 (Reflection & Memory Update)**。它的核心作用是让智能体能够从过去的决策中学习，通过“复盘”来不断优化未来的表现。

### 主要功能

1.  **复盘分析 (Reasoning)**：
    它会分析每个关键角色（Bull Researcher, Bear Researcher, Trader, Investment Judge, Risk Judge）的决策，并结合实际的市场回报（Returns/Losses），判断决策是否正确。

2.  **提出改进 (Improvement)**：
    对于错误的决策，它会分析原因（如是否忽略了某个技术指标、新闻或基本面数据），并提出具体的改进建议。

3.  **总结经验 (Summary)**：
    将成功和失败的经验总结成简练的“教训”，并将其存入 **长短期记忆模块 (Memory)** 中。这些记忆会在未来的决策中被检索和使用，从而实现“吃一堑，长一智”。

### 核心类 `Reflector`

*   `_get_reflection_prompt()`: 定义了反思专家的 System Prompt，指导 LLM 如何进行复盘。
*   `_reflect_on_component(...)`: 通用的反思方法，调用 LLM 生成反思报告。
*   `reflect_bull_researcher` / `reflect_bear_researcher`: 复盘多空研究员的辩论过程。
*   `reflect_trader`: 复盘交易员的初始计划。
*   `reflect_invest_judge`: 复盘研究经理的最终判断。
*   `reflect_risk_manager`: 复盘风险裁判的最终决策。

简而言之，这就是 Trading Agents 的 **“事后诸葛亮”模块**，但它的目的是为了让这个“诸葛亮”在下一次事前就能发挥作用。