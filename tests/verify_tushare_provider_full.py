#!/usr/bin/env python3
"""
全面验证 TushareProvider 接口的数据完整性和准确性
"""
import asyncio
import sys
import os
from datetime import datetime, timedelta
import pandas as pd
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradingagents.dataflows.providers.china.tushare import TushareProvider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger("TushareVerifier")


async def verify_tushare_provider():
    print("🔍 开始验证 TushareProvider 数据完整性和准确性")
    print("=" * 60)

    provider = TushareProvider()

    print("\n1️⃣ 验证连接状态...")
    connected = await provider.connect()
    if connected:
        print("✅ 连接成功")
    else:
        print("❌ 连接失败")
        return

    print("\n2️⃣ 验证 get_stock_list()...")
    stock_list = await provider.get_stock_list()
    if stock_list and len(stock_list) > 0:
        print(f"✅ 获取成功: 共 {len(stock_list)} 只股票")
        first_stock = stock_list[0]
        required_fields = ["code", "name", "data_source"]
        missing_fields = [f for f in required_fields if f not in first_stock]
        if not missing_fields:
            print(f"✅ 数据结构完整: {first_stock}")
        else:
            print(f"❌ 数据结构缺失字段: {missing_fields}")
    else:
        print("❌ 获取股票列表失败或为空")

    test_code = "000001"
    print(f"\n3️⃣ 验证 get_stock_basic_info('{test_code}')...")
    basic_info = await provider.get_stock_basic_info(test_code)
    if basic_info:
        print("✅ 获取成功")
        expected_fields = [
            "code",
            "name",
            "area",
            "industry",
            "market",
            "list_date",
            "full_symbol",
            "market_info",
            "data_source",
        ]
        missing = [f for f in expected_fields if f not in basic_info]
        if not missing:
            print("✅ 关键字段完整")
            print(f"   行业: {basic_info.get('industry')}")
            print(f"   地区: {basic_info.get('area')}")
            print(f"   上市日期: {basic_info.get('list_date')}")
            if basic_info.get("industry") in (None, "", "未知") or basic_info.get("area") in (
                None,
                "",
                "未知",
            ):
                print("⚠️ 警告: 行业或地区信息为'未知/空'，可能数据源缺失")
            else:
                print("✅ 数据内容有效")
        else:
            print(f"❌ 缺失字段: {missing}")
    else:
        print("❌ 获取基础信息失败")

    print(f"\n4️⃣ 验证 get_stock_quotes('{test_code}')...")
    try:
        quote = await provider.get_stock_quotes(test_code)
    except Exception as e:
        quote = None
        print(f"❌ 获取实时行情异常: {e}")

    if quote:
        print("✅ 获取成功")
        price_fields = ["current_price", "open", "high", "low", "pre_close", "close"]
        missing_price_fields = [f for f in price_fields if f not in quote]
        if missing_price_fields:
            print(f"❌ 缺失价格字段: {missing_price_fields}")
        else:
            current_price = quote.get("current_price")
            pre_close = quote.get("pre_close")
            if isinstance(current_price, (int, float)) and current_price > 0:
                print(f"✅ 价格数据有效: 现价={current_price}, 昨收={pre_close}")
            else:
                print(f"⚠️ 价格数据可能为空或异常: { {k: quote.get(k) for k in price_fields} }")

        fin_fields = ["pe", "pb", "total_mv", "circ_mv", "turnover_rate"]
        missing_fin_fields = [f for f in fin_fields if f not in quote]
        if missing_fin_fields:
            print(f"❌ 缺失财务指标字段: {missing_fin_fields}")
        else:
            print("✅ 财务指标字段存在（可能为None，取决于接口返回）")
            print(f"   市盈率(PE): {quote.get('pe')}")
            print(f"   市净率(PB): {quote.get('pb')}")
            print(f"   总市值: {quote.get('total_mv')}")
    else:
        print("⚠️ 未获取到实时行情数据（可能停牌/节假日/配额限制）")

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    print(f"\n5️⃣ 验证 get_historical_data('{test_code}', {start_date}, {end_date})...")

    hist_df = await provider.get_historical_data(test_code, start_date, end_date)
    if hist_df is not None and not hist_df.empty:
        print(f"✅ 获取成功: {len(hist_df)} 条记录")
        required_cols = ["date", "open", "close", "high", "low", "volume", "amount"]
        missing_cols = [c for c in required_cols if c not in hist_df.columns]
        if not missing_cols:
            print("✅ 列名完整")
            if pd.api.types.is_datetime64_any_dtype(hist_df["date"]):
                print("✅ 日期列格式正确")
            else:
                print(f"❌ 日期列格式错误: {hist_df['date'].dtype}")

            if (hist_df["close"] > 0).all():
                print("✅ 收盘价数据有效 (>0)")
            else:
                print("❌ 存在无效收盘价 (<=0)")
        else:
            print(f"❌ 缺失列: {missing_cols}")
    else:
        print("❌ 获取历史数据失败或为空")

    print(f"\n6️⃣ 验证 get_financial_data('{test_code}')...")
    financial_data = await provider.get_financial_data(test_code)
    if financial_data:
        print("✅ 获取成功")
        if isinstance(financial_data.get("raw_data"), dict):
            raw = financial_data["raw_data"]
            tables = [
                ("income_statement", raw.get("income_statement")),
                ("balance_sheet", raw.get("balance_sheet")),
                ("cashflow_statement", raw.get("cashflow_statement")),
                ("financial_indicators", raw.get("financial_indicators")),
                ("main_business", raw.get("main_business")),
            ]
            for name, rows in tables:
                if rows:
                    print(f"   ✅ raw_data.{name}: {len(rows)} 条记录")
                else:
                    print(f"   ⚠️ raw_data.{name}: 无数据")
        else:
            print("⚠️ 返回结构不包含 raw_data，跳过明细表校验")

        key_metrics = ["revenue", "net_income", "net_profit", "total_assets", "roe", "gross_margin"]
        present_metrics = {k: financial_data.get(k) for k in key_metrics if k in financial_data}
        if present_metrics:
            print(f"   指标示例: {present_metrics}")
    else:
        print("❌ 获取财务数据失败")

    print(f"\n7️⃣ 验证 get_stock_news('{test_code}')...")
    news_list = await provider.get_stock_news(test_code, limit=5)
    if news_list and len(news_list) > 0:
        print(f"✅ 获取成功: {len(news_list)} 条新闻")
        first_news = news_list[0]
        print(f"   示例标题: {first_news.get('title')}")
        print(f"   发布时间: {first_news.get('publish_time')}")
        if first_news.get("content"):
            print("✅ 新闻内容存在")
        else:
            print("⚠️ 新闻内容为空")
    else:
        print("⚠️ 未获取到新闻数据 (可能无新闻/接口限制/积分不足)")

    print("\n" + "=" * 60)
    print("🏁 验证结束")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(verify_tushare_provider())
