import os

import pytest
from pymongo import MongoClient

from app.core.config import settings
from tradingagents.dataflows.realtime_metrics import (
    calculate_realtime_pe_pb,
    get_pe_pb_with_fallback,
    validate_pe_pb,
)


def _live_enabled() -> bool:
    return os.getenv("TRADINGAGENTS_LIVE_MONGO_TESTS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _mongo_client() -> MongoClient:
    return MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=5000)


def _pick_symbol(db) -> str | None:
    preferred = os.getenv("TRADINGAGENTS_LIVE_SYMBOL", "").strip()
    if preferred:
        return str(preferred).zfill(6)

    quote = db.market_quotes.find_one(
        {"close": {"$gt": 0}, "pre_close": {"$gt": 0}},
        {"code": 1, "_id": 0},
    )
    if quote and quote.get("code"):
        return str(quote["code"]).zfill(6)

    basic = db.stock_basic_info.find_one(
        {
            "source": "tushare",
            "pe_ttm": {"$gt": 0},
            "$or": [{"total_share": {"$gt": 0}}, {"total_mv": {"$gt": 0}}],
        },
        {"code": 1, "_id": 0},
    )
    if basic and basic.get("code"):
        code = str(basic["code"]).zfill(6)
        quote2 = db.market_quotes.find_one({"code": code, "close": {"$gt": 0}}, {"code": 1, "_id": 0})
        if quote2:
            return code

    return None


@pytest.mark.integration
def test_calculate_realtime_pe_pb_live():
    if not _live_enabled():
        pytest.skip("set TRADINGAGENTS_LIVE_MONGO_TESTS=1 to enable")

    client = _mongo_client()
    db = client["tradingagents"]
    symbol = _pick_symbol(db)
    if not symbol:
        pytest.skip("no suitable market_quotes/stock_basic_info data found in MongoDB")

    result = calculate_realtime_pe_pb(symbol, client)
    assert isinstance(result, dict)
    assert result.get("price") is not None
    assert result["price"] > 0
    assert validate_pe_pb(result.get("pe"), result.get("pb"))


@pytest.mark.integration
def test_get_pe_pb_with_fallback_live():
    if not _live_enabled():
        pytest.skip("set TRADINGAGENTS_LIVE_MONGO_TESTS=1 to enable")

    client = _mongo_client()
    db = client["tradingagents"]
    symbol = _pick_symbol(db)
    if not symbol:
        pytest.skip("no suitable market_quotes/stock_basic_info data found in MongoDB")

    result = get_pe_pb_with_fallback(symbol, client)
    assert isinstance(result, dict)
    assert result
    assert "source" in result
    assert "is_realtime" in result
    assert validate_pe_pb(result.get("pe"), result.get("pb"))

