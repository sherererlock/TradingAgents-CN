#!/usr/bin/env python3
"""
全面验证 AKShareProvider 接口的数据完整性和准确性
"""
import asyncio
import sys
import os
from datetime import datetime, timedelta
import pandas as pd
import logging

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradingagents.dataflows.providers.china.akshare import AKShareProvider

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s'
)
logger = logging.getLogger("AKShareVerifier")

async def verify_akshare_provider():
    print("🔍 开始验证 AKShareProvider 数据完整性和准确性")
    print("=" * 60)
    
    provider = AKShareProvider()
    
    # 1. 验证连接
    print("\n1️⃣ 验证连接状态...")
    connected = await provider.connect()
    if connected:
        print("✅ 连接成功")
    else:
        print("❌ 连接失败")
        return

    # 2. 验证股票列表
    print("\n2️⃣ 验证 get_stock_list()...")
    stock_list = await provider.get_stock_list()
    if stock_list and len(stock_list) > 0:
        print(f"✅ 获取成功: 共 {len(stock_list)} 只股票")
        # 检查第一条数据的结构
        first_stock = stock_list[0]
        required_fields = ["code", "name", "source"]
        missing_fields = [f for f in required_fields if f not in first_stock]
        if not missing_fields:
            print(f"✅ 数据结构完整: {first_stock}")
        else:
            print(f"❌ 数据结构缺失字段: {missing_fields}")
    else:
        print("❌ 获取股票列表失败或为空")

    # 3. 验证股票基础信息
    test_code = "600089"
    print(f"\n3️⃣ 验证 get_stock_basic_info('{test_code}')...")
    basic_info = await provider.get_stock_basic_info(test_code)
    if basic_info:
        print("✅ 获取成功")
        # 检查关键字段
        expected_fields = [
            "code", "name", "area", "industry", "market", 
            "list_date", "full_symbol", "market_info"
        ]
        missing = [f for f in expected_fields if f not in basic_info]
        if not missing:
            print("✅ 关键字段完整")
            print(f"   行业: {basic_info.get('industry')}")
            print(f"   地区: {basic_info.get('area')}")
            print(f"   上市日期: {basic_info.get('list_date')}")
            
            # 准确性检查
            if basic_info['industry'] == '未知' or basic_info['area'] == '未知':
                print("⚠️ 警告: 行业或地区信息为'未知'，可能数据源缺失")
            else:
                print("✅ 数据内容有效")
        else:
            print(f"❌ 缺失字段: {missing}")
    else:
        print(f"❌ 获取基础信息失败")

    # 4. 验证批量实时行情
    test_codes = ["600089"]
    print(f"\n4️⃣ 验证 get_batch_stock_quotes({test_codes})...")
    quotes = await provider.get_batch_stock_quotes(test_codes)
    if quotes:
        print(f"✅ 获取成功: {len(quotes)}/{len(test_codes)} 只")
        
        # 检查平安银行(600089)的数据结构
        if "600089" in quotes:
            q = quotes["600089"]
            print("✅ 数据结构示例 (600089):")
            
            # 检查价格相关字段
            price_fields = ["price", "open_price", "high_price", "low_price", "pre_close"]
            valid_prices = all(isinstance(q.get(f), (int, float)) and q.get(f) > 0 for f in price_fields)
            
            if valid_prices:
                print(f"   价格数据有效: 现价={q['price']}, 昨收={q['pre_close']}")
            else:
                print(f"❌ 价格数据异常: { {k: q.get(k) for k in price_fields} }")
                
            # 检查财务指标字段
            fin_fields = ["pe", "pb", "total_mv", "circ_mv", "turnover_rate"]
            has_fin = all(f in q for f in fin_fields)
            if has_fin:
                print(f"✅ 财务指标字段完整")
                print(f"   市盈率(PE): {q.get('pe')}")
                print(f"   市净率(PB): {q.get('pb')}")
                print(f"   总市值: {q.get('total_mv')} 亿")
            else:
                print(f"❌ 缺失财务指标字段: {[f for f in fin_fields if f not in q]}")
        else:
            print("❌ 未找到 000001 的行情数据")
    else:
        print("❌ 批量获取行情失败")

    # 5. 验证历史行情
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    print(f"\n5️⃣ 验证 get_historical_data('{test_code}', {start_date}, {end_date})...")
    
    hist_df = await provider.get_historical_data(test_code, start_date, end_date)
    if hist_df is not None and not hist_df.empty:
        print(f"✅ 获取成功: {len(hist_df)} 条记录")
        
        # 检查列名
        required_cols = ["date", "open", "close", "high", "low", "volume", "amount"]
        missing_cols = [c for c in required_cols if c not in hist_df.columns]
        
        if not missing_cols:
            print("✅ 列名完整")
            # 检查数据类型
            if pd.api.types.is_datetime64_any_dtype(hist_df['date']):
                print("✅ 日期列格式正确")
            else:
                print(f"❌ 日期列格式错误: {hist_df['date'].dtype}")
                
            # 检查数值有效性
            if (hist_df['close'] > 0).all():
                print("✅ 收盘价数据有效 (>0)")
            else:
                print("❌ 存在无效收盘价 (<=0)")
        else:
            print(f"❌ 缺失列: {missing_cols}")
    else:
        print("❌ 获取历史数据失败或为空")

    # 6. 验证财务数据
    print(f"\n6️⃣ 验证 get_financial_data('{test_code}')...")
    financial_data = await provider.get_financial_data(test_code)
    if financial_data:
        print("✅ 获取成功")
        tables = ["main_indicators", "balance_sheet", "income_statement", "cash_flow"]
        for table in tables:
            if table in financial_data and financial_data[table]:
                print(f"   ✅ {table}: {len(financial_data[table])} 条记录")
            else:
                print(f"   ⚠️ {table}: 无数据")
    else:
        print("❌ 获取财务数据失败")

    # 7. 验证新闻数据
    print(f"\n7️⃣ 验证 get_stock_news('{test_code}')...")
    news_list = await provider.get_stock_news(test_code, limit=5)
    if news_list and len(news_list) > 0:
        print(f"✅ 获取成功: {len(news_list)} 条新闻")
        first_news = news_list[0]
        print(f"   示例标题: {first_news.get('title')}")
        print(f"   发布时间: {first_news.get('publish_time')}")
        
        if first_news.get('content'):
            print("✅ 新闻内容存在")
        else:
            print("⚠️ 新闻内容为空")
    else:
        print("⚠️ 未获取到新闻数据 (可能是最近无新闻或接口限制)")
        
    print("\n" + "=" * 60)
    print("🏁 验证结束")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(verify_akshare_provider())
