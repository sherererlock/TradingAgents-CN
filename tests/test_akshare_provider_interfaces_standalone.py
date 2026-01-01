import argparse
import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)


@dataclass
class CheckResult:
    name: str
    status: str
    details: str


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _date_ymd(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def _safe_bool(x: Any) -> bool:
    return bool(x) if x is not None else False


def _require_keys(d: Dict[str, Any], keys: List[str]) -> List[str]:
    missing = []
    for k in keys:
        if k not in d:
            missing.append(k)
    return missing


def _fail(name: str, details: str) -> CheckResult:
    return CheckResult(name=name, status="FAIL", details=details)


def _warn(name: str, details: str) -> CheckResult:
    return CheckResult(name=name, status="WARN", details=details)


def _pass(name: str, details: str) -> CheckResult:
    return CheckResult(name=name, status="PASS", details=details)


def _validate_historical_df(df: pd.DataFrame, symbol: str, start_date: str, end_date: str) -> Tuple[bool, str]:
    if df is None or df.empty:
        return False, "DataFrame 为空"

    required_cols = ["date", "open", "close", "high", "low", "volume", "amount", "code", "full_symbol"]
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        return False, f"缺少列: {missing_cols}，实际列: {list(df.columns)}"

    if str(df["code"].iloc[0]) != str(symbol):
        return False, f"code 列不匹配: 期望 {symbol}，实际 {df['code'].iloc[0]}"

    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    dmin = pd.to_datetime(df["date"]).min()
    dmax = pd.to_datetime(df["date"]).max()
    if dmin < start - pd.Timedelta(days=3) or dmax > end + pd.Timedelta(days=3):
        return False, f"日期范围异常: [{dmin.date()}, {dmax.date()}] 不在 [{start.date()}, {end.date()}] 附近"

    numeric_cols = ["open", "close", "high", "low", "volume", "amount"]
    for col in numeric_cols:
        if (df[col] < 0).any():
            return False, f"{col} 存在负值"

    if (df["high"] < df[["open", "close", "low"]].max(axis=1)).any():
        return False, "high 小于当日 open/close/low 的最大值"

    if (df["low"] > df[["open", "close", "high"]].min(axis=1)).any():
        return False, "low 大于当日 open/close/high 的最小值"

    return True, f"行数={len(df)} 日期范围=[{dmin.date()}, {dmax.date()}] 列={list(df.columns)}"


async def _run_checks(
    symbols: List[str],
    start_date: str,
    end_date: str,
    period: str,
    news_limit: int,
    sample_stock_list: int,
) -> List[CheckResult]:
    from tradingagents.dataflows.providers.china.akshare import get_akshare_provider

    results: List[CheckResult] = []
    provider = get_akshare_provider()

    results.append(
        _pass(
            "ProviderInit",
            f"provider={provider!r} connected={provider.connected} available={provider.is_available()}",
        )
        if provider.is_available()
        else _fail("ProviderInit", f"provider={provider!r} connected={provider.connected} available={provider.is_available()}")
    )

    if not provider.is_available():
        return results

    try:
        stock_list = await provider.get_stock_list()
        if not stock_list:
            results.append(_fail("GetStockList", "返回空列表"))
        else:
            sample = stock_list[:sample_stock_list]
            bad = [x for x in sample if not x.get("code") or not x.get("name")]
            if bad:
                results.append(_warn("GetStockList", f"样本中存在缺少 code/name 的记录数={len(bad)}，样本前3={bad[:3]}"))
            else:
                results.append(_pass("GetStockList", f"总数={len(stock_list)} 样本={sample}"))
    except Exception as e:
        msg = f"异常: {type(e).__name__}: {e}"
        if "specify an engine manually" in str(e) or "Excel file format cannot be determined" in str(e):
            msg = f"{msg}；可能缺少 openpyxl（pip install openpyxl）"
        results.append(_fail("GetStockList", msg))

    for symbol in symbols:
        try:
            basic = await provider.get_stock_basic_info(symbol)
            if not basic:
                results.append(_fail(f"GetStockBasicInfo[{symbol}]", "返回 None/空"))
            else:
                missing = _require_keys(
                    basic,
                    ["code", "name", "market", "full_symbol", "market_info", "data_source", "last_sync", "sync_status"],
                )
                if missing:
                    results.append(_fail(f"GetStockBasicInfo[{symbol}]", f"缺少字段: {missing} 实际keys={list(basic.keys())}"))
                else:
                    results.append(_pass(f"GetStockBasicInfo[{symbol}]", json.dumps(basic, ensure_ascii=False, default=str)))
        except Exception as e:
            results.append(_fail(f"GetStockBasicInfo[{symbol}]", f"异常: {type(e).__name__}: {e}"))

        try:
            hist = await provider.get_historical_data(symbol, start_date, end_date, period)
            ok, detail = _validate_historical_df(hist, symbol, start_date, end_date)
            results.append(_pass(f"GetHistoricalData[{symbol}]", detail) if ok else _fail(f"GetHistoricalData[{symbol}]", detail))
        except Exception as e:
            results.append(_fail(f"GetHistoricalData[{symbol}]", f"异常: {type(e).__name__}: {e}"))

        try:
            quote = await provider.get_stock_quotes(symbol)
            if not quote:
                results.append(_fail(f"GetStockQuotes[{symbol}]", "返回 None/空"))
            else:
                missing = _require_keys(
                    quote,
                    ["code", "symbol", "price", "open", "high", "low", "volume", "amount", "trade_date", "updated_at", "data_source"],
                )
                if missing:
                    results.append(_fail(f"GetStockQuotes[{symbol}]", f"缺少字段: {missing} 实际keys={list(quote.keys())}"))
                else:
                    price = quote.get("price", 0)
                    volume = quote.get("volume", 0)
                    if price in (0, 0.0) or volume in (0, 0.0):
                        results.append(_warn(f"GetStockQuotes[{symbol}]", f"price/volume 可能为0（非交易时段或接口异常）: {json.dumps(quote, ensure_ascii=False, default=str)}"))
                    else:
                        results.append(_pass(f"GetStockQuotes[{symbol}]", json.dumps(quote, ensure_ascii=False, default=str)))
        except Exception as e:
            results.append(_fail(f"GetStockQuotes[{symbol}]", f"异常: {type(e).__name__}: {e}"))

        try:
            financial = await provider.get_financial_data(symbol)
            if not financial:
                results.append(_warn(f"GetFinancialData[{symbol}]", "返回空字典（常见原因：接口限流/字段变更/个股不支持）"))
            else:
                non_empty_sets = [k for k, v in financial.items() if isinstance(v, list) and len(v) > 0]
                if not non_empty_sets:
                    results.append(_warn(f"GetFinancialData[{symbol}]", f"数据集 keys={list(financial.keys())} 但记录为空"))
                else:
                    brief = {k: len(financial.get(k, [])) for k in financial.keys()}
                    results.append(_pass(f"GetFinancialData[{symbol}]", json.dumps(brief, ensure_ascii=False, default=str)))
        except Exception as e:
            results.append(_fail(f"GetFinancialData[{symbol}]", f"异常: {type(e).__name__}: {e}"))

        try:
            news = await provider.get_stock_news(symbol, limit=news_limit)
            if news is None:
                results.append(_fail(f"GetStockNews[{symbol}]", "返回 None"))
            elif not news:
                results.append(_warn(f"GetStockNews[{symbol}]", "返回空列表（常见原因：反爬虫/接口变更/网络问题）"))
            else:
                required = ["symbol", "title", "publish_time", "source", "data_source"]
                bad = [x for x in news if isinstance(x, dict) and _require_keys(x, required)]
                if bad:
                    results.append(_warn(f"GetStockNews[{symbol}]", f"存在结构不完整的新闻条数={len(bad)} 示例keys={list(bad[0].keys()) if isinstance(bad[0], dict) else type(bad[0]).__name__}"))
                else:
                    results.append(_pass(f"GetStockNews[{symbol}]", json.dumps(news[: min(3, len(news))], ensure_ascii=False, default=str)))
        except Exception as e:
            results.append(_fail(f"GetStockNews[{symbol}]", f"异常: {type(e).__name__}: {e}"))

    try:
        batch = await provider.get_batch_stock_quotes(symbols)
        if not batch:
            results.append(_warn("GetBatchStockQuotes", "返回空字典（可能因快照接口失败/反爬虫）"))
        else:
            sample_k = list(batch.keys())[: min(3, len(batch))]
            sample = {k: batch[k] for k in sample_k}
            results.append(_pass("GetBatchStockQuotes", f"命中={len(batch)}/{len(symbols)} 样本={json.dumps(sample, ensure_ascii=False, default=str)}"))
    except Exception as e:
        results.append(_fail("GetBatchStockQuotes", f"异常: {type(e).__name__}: {e}"))

    try:
        status = await provider.get_market_status()
        if not status:
            results.append(_fail("GetMarketStatus", "返回空"))
        else:
            missing = _require_keys(status, ["market_status", "current_time", "data_source"])
            if missing:
                results.append(_fail("GetMarketStatus", f"缺少字段: {missing}"))
            else:
                results.append(_pass("GetMarketStatus", json.dumps(status, ensure_ascii=False, default=str)))
    except Exception as e:
        results.append(_fail("GetMarketStatus", f"异常: {type(e).__name__}: {e}"))

    try:
        market_news = await provider.get_stock_news(None, limit=news_limit)
        if market_news is None:
            results.append(_fail("GetMarketNews", "返回 None"))
        elif not market_news:
            results.append(_warn("GetMarketNews", "返回空列表"))
        else:
            results.append(_pass("GetMarketNews", json.dumps(market_news[: min(3, len(market_news))], ensure_ascii=False, default=str)))
    except Exception as e:
        results.append(_fail("GetMarketNews", f"异常: {type(e).__name__}: {e}"))

    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=["000001", "600000"], help="股票代码列表，如 000001 600000")
    parser.add_argument("--period", default="daily", choices=["daily", "weekly", "monthly"], help="历史数据周期")
    parser.add_argument("--days", type=int, default=30, help="历史数据回看天数")
    parser.add_argument("--end-date", default=None, help="结束日期 YYYY-MM-DD，默认今天")
    parser.add_argument("--start-date", default=None, help="开始日期 YYYY-MM-DD，默认 end-date - days")
    parser.add_argument("--news-limit", type=int, default=5, help="新闻条数")
    parser.add_argument("--sample-stock-list", type=int, default=5, help="股票列表抽样条数")
    parser.add_argument("--verbose", action="store_true", help="输出更多日志")
    args = parser.parse_args()

    end_dt = datetime.strptime(args.end_date, "%Y-%m-%d") if args.end_date else datetime.now()
    start_dt = datetime.strptime(args.start_date, "%Y-%m-%d") if args.start_date else (end_dt - timedelta(days=args.days))
    start_date = _date_ymd(start_dt)
    end_date = _date_ymd(end_dt)

    base_level = logging.INFO if args.verbose else logging.WARNING
    logging.basicConfig(level=base_level, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    for ln in [
        "agents",
        "tradingagents",
        "tradingagents.dataflows.providers.china.akshare",
        "tradingagents.dataflows.data_source_manager",
    ]:
        logging.getLogger(ln).setLevel(base_level)

    print(f"[{_now_str()}] AKShareProvider 接口检查开始 symbols={args.symbols} period={args.period} range={start_date}~{end_date}")

    try:
        results = asyncio.run(
            _run_checks(
                symbols=args.symbols,
                start_date=start_date,
                end_date=end_date,
                period=args.period,
                news_limit=args.news_limit,
                sample_stock_list=args.sample_stock_list,
            )
        )
    except Exception as e:
        print(f"[{_now_str()}] 运行异常: {type(e).__name__}: {e}")
        return 2

    fail_count = 0
    warn_count = 0
    for r in results:
        if r.status == "FAIL":
            fail_count += 1
        elif r.status == "WARN":
            warn_count += 1

    width = max(len(r.name) for r in results) if results else 20
    print("")
    print(f"汇总: PASS={len(results) - fail_count - warn_count} WARN={warn_count} FAIL={fail_count} 总计={len(results)}")
    print("-" * 120)
    for r in results:
        name = r.name.ljust(width)
        print(f"{r.status:4} | {name} | {r.details}")
    print("-" * 120)

    return 1 if fail_count > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
