# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**TradingAgents-CN** is a Chinese-enhanced multi-agent stock analysis platform using AI/LLMs for educational and research purposes. Based on [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents), this version adds comprehensive Chinese localization, A-share market support, and modern web architecture.

### Important Notes
- **Educational/Research Only**: Not for live trading - analysis platform for learning
- **Mixed Licensing**: Core is Apache 2.0, but `app/` (FastAPI backend) and `frontend/` (Vue frontend) are proprietary
- **Data Required**: Stock data must be synchronized before analysis (use Tushare/AkShare/BaoStock)

## Common Commands

### Backend Development
```bash
# Install Python dependencies
pip install -e .

# Run backend development server (FastAPI)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run tests (unit only, skips integration tests by default)
pytest

# Run integration tests
pytest -m integration

# Run specific test file
pytest tests/test_analysis.py
```

### Frontend Development
```bash
cd frontend

# Install dependencies
npm install

# Run development server
npm run dev

# Build for production
npm run build

# Type checking
npm run type-check

# Lint
npm run lint
```

### Docker Deployment
```bash
# Full stack with MongoDB and Redis
docker-compose up -d

# With management interfaces (Mongo Express, Redis Commander)
docker-compose --profile management up -d

# Rebuild images
docker-compose build --no-cache

# View logs
docker-compose logs -f backend
```

### Core Analysis Usage
```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# Basic usage
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "google"  # or deepseek, openai, dashscope, qwen
config["online_tools"] = True

ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("600000", "2024-12-20")  # Use Chinese stock code format
```

## Architecture

### High-Level Structure

```
TradingAgents-CN/
├── tradingagents/          # Core analysis engine (Apache 2.0)
│   ├── agents/            # Multi-agent system
│   │   ├── analysts/      # Market, fundamentals, news, social media analysts
│   │   ├── researchers/   # Bull/bear researchers
│   │   ├── risk_mgmt/     # Conservative/aggressive debators
│   │   └── managers/      # Research and risk managers
│   ├── dataflows/         # Data layer
│   │   ├── providers/     # Data source adapters (Tushare, AkShare, etc.)
│   │   ├── cache/         # Multi-level caching (MongoDB/Redis/file)
│   │   └── news/          # News aggregation and analysis
│   ├── graph/             # LangGraph-based orchestration
│   ├── llm_adapters/      # LLM provider adapters (OpenAI-compatible)
│   └── config/            # Configuration management
├── app/                   # FastAPI backend (Proprietary - closed source)
├── frontend/              # Vue 3 SPA (Proprietary - closed source)
└── tests/                 # Test suites
```

### Multi-Agent System

The core uses **LangGraph** to orchestrate multiple specialized agents:

1. **Analysts** (Parallel):
   - `MarketAnalyst`: Technical indicators, price action, momentum
   - `FundamentalsAnalyst`: PE, PB, ROE, financial health
   - `NewsAnalyst`: News sentiment, quality assessment
   - `SocialMediaAnalyst`: Reddit/social sentiment
   - `ChinaMarketAnalyst`: A-share specific analysis

2. **Researchers** (Debate Phase):
   - `BullResearcher`: Bullish thesis construction
   - `BearResearcher`: Bearish thesis construction

3. **Risk Management** (Debate Phase):
   - `ConservativeDebator`: Risk-focused arguments
   - `AggressiveDebator`: Opportunity-focused arguments
   - `NeutralDebator`: Balanced perspective

4. **Trader**: Final decision synthesis (BUY/SELL/HOLD with confidence)

### Data Flow Architecture

```
User Request
    → TradingGraph.propagate(ticker, date)
    → Research Manager (orchestrates analysts)
        → Analysts fetch data via unified_news_tool, get_stock_data, etc.
        → DataProviders interface (TushareProvider, AkShareProvider, etc.)
        → Cache layer (Redis → MongoDB → File cache fallback)
    → Researchers synthesize views
    → Risk Management debates
    → Trader makes final decision
    → Returns AnalysisResult
```

### Key Architectural Patterns

1. **Provider Pattern**: `BaseProvider` abstract class with concrete implementations
   - `tradingagents/dataflows/providers/base_provider.py`
   - Chinese markets: `TushareProvider`, `AkShareProvider`, `BaoStockProvider`
   - HK market: `HKStockProvider`
   - US markets: `AlphaVantageProvider`, `FinnhubProvider`, `YFinanceProvider`

2. **Factory Pattern**: `create_llm_by_provider()` in `trading_graph.py` dynamically instantiates LLMs based on provider name

3. **LangGraph State Machine**: Agent states defined in `agent_states.py`:
   - `AgentState`: Main analysis state
   - `InvestDebateState`: Investment debate phase
   - `RiskDebateState`: Risk debate phase

4. **Multi-Level Caching**: `IntegratedCache` in `cache/integrated.py`
   - L1: Redis (fast, optional)
   - L2: MongoDB (persistent, optional)
   - L3: File cache (fallback)
   - Configurable via `CACHE_TYPE` env variable

5. **Configuration Management**:
   - `config_manager.py`: YAML-based config
   - `mongodb_storage.py`: Database-backed settings (for web UI)
   - `runtime_settings.py`: In-memory runtime config

### LLM Integration

The system supports multiple LLM providers through adapter classes in `llm_adapters/`:

- **OpenAI**: `langchain_openai.ChatOpenAI` (native)
- **Google AI**: `ChatGoogleOpenAI` (custom adapter, supports gemini models)
- **DeepSeek**: `ChatDeepSeek` (custom adapter)
- **DashScope (Alibaba)**: `ChatDashScopeOpenAI` (custom adapter)
- **Qwen**: Via DashScope OpenAI-compatible API
- **Generic OpenAI-compatible**: `create_openai_compatible_llm()`

All adapters implement a common interface with `base_url`, `api_key`, `temperature`, `max_tokens`, `timeout` parameters.

### Data Synchronization

Before analysis, stock data must be synchronized. The project provides CLI commands:

```bash
# Sync specific stock (A-share format)
tradingagents sync 600000

# Sync US stock
tradingagents sync AAPL

# Sync HK stock
tradingagents sync 00700
```

Data providers require API keys:
- **Tushare**: Free token required, best for A-shares
- **AkShare**: Free, no key required but rate-limited
- **BaoStock**: Free, good for historical data
- **Finnhub/Alpha Vantage**: For US stocks

## Testing Strategy

- **Unit Tests**: `tests/` directory, run with `pytest` (excludes integration by default)
- **Integration Tests**: Marked with `@pytest.mark.integration`, run with `pytest -m integration`
- **Test Configuration**: `tests/pytest.ini` configures test discovery and markers
- **Scripts**: Many `test_*.py` files in `scripts/` are development/debugging scripts, not formal tests

## Environment Variables

Key environment variables (see `.env.example`):

```bash
# Database
TRADINGAGENTS_MONGODB_URL=mongodb://localhost:27017/tradingagents
TRADINGAGENTS_REDIS_URL=redis://localhost:6379
TRADINGAGENTS_CACHE_TYPE=redis  # or mongodb, file

# LLM Providers
GOOGLE_API_KEY=your_key_here
DEEPSEEK_API_KEY=your_key_here
DASHSCOPE_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here

# Data Sources
TUSHARE_TOKEN=your_token_here
AKSHARE_TOKEN=optional
BAOSTOCK_TOKEN=optional

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
CORS_ORIGINS=http://localhost:3000
```

## Development Guidelines

### Code Organization
- Keep core analysis logic in `tradingagents/` (Apache 2.0 licensed)
- Web-specific code goes in `app/` (proprietary)
- When adding new data providers, inherit from `BaseProvider`
- New LLM providers should follow adapter pattern in `llm_adapters/`

### Event Loop Considerations
The project has had issues with asyncio event loop conflicts. When working with async code:
- Use `asyncio.run()` for top-level async calls
- Avoid mixing sync and async contexts
- The `unified_news_tool` uses thread pools to avoid blocking

### Chinese Market Specifics
- Stock codes: 6-digit for A-shares (e.g., "600000"), 5-digit for HK (e.g., "00700")
- Market types: `stock_utils.MarketType.SHANGHAI`, `SHENZHEN`, `HONG_KONG`, `US`
- Tushare is preferred for A-shares (most comprehensive data)
- AkShare is good fallback but has rate limits

### Adding New Analysts
1. Create analyst class in `tradingagents/agents/analysts/`
2. Inherit from appropriate base class or follow existing patterns
3. Define system prompt and bind tools (e.g., `unified_news_tool`, `get_stock_data`)
4. Add to research manager in `research_manager.py`
5. Update graph setup in `graph/setup.py` if needed

## Important Files to Reference

- **Main entry point**: `main.py` (example usage)
- **Graph orchestration**: `tradingagents/graph/trading_graph.py`
- **Agent states**: `tradingagents/agents/utils/agent_states.py`
- **Default config**: `tradingagents/default_config.py`
- **Stock utilities**: `tradingagents/utils/stock_utils.py`
- **Data providers**: `tradingagents/dataflows/providers/`
- **Configuration**: `tradingagents/config/config_manager.py`

## License Notes

- Apache 2.0: Everything except `app/` and `frontend/`
- Commercial use of `app/` and `frontend/` requires separate licensing
- Core analysis engine can be used freely under Apache 2.0
