# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TradingAgents-CN is a Chinese-enhanced multi-agent stock analysis platform based on [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents). It uses LLM-powered agents to analyze stocks (A-shares, HK stocks, US stocks) through debates between analysts, researchers, and risk managers. **For research and education only — not investment advice.**

## Tech Stack

- **Python 3.10+** (see `.python-version`)
- **Backend**: FastAPI + Uvicorn (`app/` directory, proprietary license)
- **Frontend**: Vue 3 + Vite + Element Plus + TypeScript (`frontend/` directory, proprietary license)
- **Database**: MongoDB (via motor/pymongo) + Redis
- **AI/LLM**: LangChain + LangGraph, supports OpenAI, DeepSeek, DashScope (Alibaba), Google Gemini, Anthropic, and custom OpenAI-compatible endpoints
- **Data sources**: AKShare, Tushare, BaoStock, Finnhub, yfinance, EODHD

## Licensing

Mixed license model:
- **Apache 2.0**: Everything except `app/` and `frontend/`
- **Proprietary** (requires commercial license): `app/` (FastAPI backend) and `frontend/` (Vue frontend)

## Common Commands

### Backend (FastAPI)
```bash
# Install dependencies
pip install -e .
# or: uv pip install -e .

# Run backend server
python -m app
# Runs on http://0.0.0.0:8000 by default

# API docs (debug mode): http://localhost:8000/docs
```

### Frontend (Vue 3)
```bash
cd frontend
yarn install
yarn dev        # Dev server (Vite)
yarn build      # Production build (vue-tsc + vite build)
yarn lint       # ESLint fix
yarn format     # Prettier format
yarn type-check # TypeScript type checking
```

### Docker
```bash
docker-compose up -d
# Services: backend (8000), frontend (3000), mongodb (27017), redis (6379)
# Optional management: --profile management (redis-commander:8081, mongo-express:8082)
```

### Tests
```bash
# Run unit tests (default, skips integration tests)
pytest

# Run specific test
pytest tests/test_config_loading.py

# Run integration tests
pytest -m integration

# Test config: tests/pytest.ini — only collects from tests/ directory
```

## Architecture

### Core Multi-Agent System (`tradingagents/`)

The analysis pipeline is a LangGraph state graph with these agent roles:

- **Analysts** (`agents/analysts/`): Market analyst, fundamentals analyst, news analyst, social media analyst, China market analyst
- **Researchers** (`agents/researchers/`): Bull/bear researchers that debate investment theses
- **Risk Management** (`agents/risk_mgmt/`): Risk analysts that evaluate downside
- **Trader** (`agents/trader/`): Final trading decision
- **Managers** (`agents/managers/`): Portfolio management decisions

Key graph files:
- `graph/trading_graph.py` — Main `TradingAgentsGraph` class orchestrating the full pipeline
- `graph/setup.py` — LangGraph node/edge wiring
- `graph/propagation.py` — Forward propagation logic
- `graph/signal_processing.py` — Signal extraction from agent outputs

### LLM Client Layer (`tradingagents/llm_clients/`)

Abstraction over multiple LLM providers:
- `factory.py` — `create_llm_client()` factory function
- `openai_client.py`, `google_client.py`, `anthropic_client.py` — Provider implementations
- `provider_keys.py` — Environment variable mapping and provider key normalization
- `model_catalog.py` — Model metadata

### Data Layer (`tradingagents/dataflows/`)

- `interface.py` — Unified data access interface
- `data_source_manager.py` — Multi-source data management (AKShare, Tushare, BaoStock)
- `optimized_china_data.py` — China market optimized data fetching
- `providers/` — Data provider implementations
- `news/` — News data fetching and filtering
- `technical/` — Technical indicator calculations

### Backend API (`app/`)

FastAPI application structure:
- `main.py` — App factory, middleware, router registration, scheduler setup
- `core/config.py` — Pydantic `Settings` class loading from `.env`
- `core/database.py` — MongoDB/Redis connection lifecycle
- `routers/` — API route modules (analysis, stocks, config, auth, reports, SSE, etc.)
- `services/` — Business logic layer
- `worker/` — Background sync services (Tushare, AKShare, BaoStock)
- `middleware/` — Operation logging, auth middleware
- `schemas/` — Pydantic request/response models

### Frontend (`frontend/`)

Vue 3 SPA:
- `src/api/` — Axios API client modules
- `src/views/` — Page components
- `src/components/` — Reusable UI components
- `src/stores/` — Pinia state stores
- `src/router/` — Vue Router config

## Configuration

### Environment Variables (.env)

Copy `.env.example` to `.env`. Key settings:
- `MONGODB_*` — MongoDB connection (required)
- `REDIS_*` — Redis connection (required)
- `JWT_SECRET` — Auth token secret (required, change in production)
- `DEEPSEEK_API_KEY`, `DASHSCOPE_API_KEY`, `OPENAI_API_KEY`, etc. — LLM API keys (at least one required)
- `DEFAULT_CHINA_DATA_SOURCE` — Default data source: `akshare`, `tushare`, or `baostock`

### LLM Config (`tradingagents/default_config.py`)

`DEFAULT_CONFIG` dict controls:
- `llm_provider` — Provider name (openai, google, dashscope, deepseek, etc.)
- `deep_think_llm` / `quick_think_llm` — Model names for deep/quick analysis
- `backend_url` — API endpoint URL
- `max_debate_rounds` / `max_risk_discuss_rounds` — Agent debate iterations
- `online_tools` / `online_news` / `realtime_data` — Feature toggles

## Key Patterns

- **Provider normalization**: Provider keys are normalized via `normalize_provider_key()` in `llm_clients/provider_keys.py` to handle aliases (e.g., "siliconflow" → uses OpenAI client)
- **Data source fallback**: Multiple data sources with automatic fallback chains (e.g., AKShare → BaoStock → Tushare)
- **Database version isolation**: MongoDB database names include version/instance tags when `MONGODB_DATABASE_SCOPE=auto` (see `core/config.py`)
- **SSE + WebSocket**: Real-time progress updates via Server-Sent Events and WebSocket notifications
- **Background workers**: APScheduler-based sync services for periodic data ingestion

## Data Source Initialization

Before analyzing stocks, data must be synced. Init routes:
- `POST /api/tushare/init` — Tushare data initialization
- `POST /api/akshare/init` — AKShare data initialization
- `POST /api/baostock/init` — BaoStock data initialization
