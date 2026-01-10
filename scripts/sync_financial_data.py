#!/usr/bin/env python3
"""
同步股票财务数据

功能：
1. 从 AKShare 获取股票财务指标
2. 更新 stock_basic_info 集合的财务字段
3. 创建/更新 stock_financial_data 集合

使用方法：
    python scripts/sync_financial_data.py 600036  # 同步单只股票
    python scripts/sync_financial_data.py --all   # 同步所有股票
    python scripts/sync_financial_data.py --batch 100  # 批量同步前100只
"""

import asyncio
import os
import sys
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
from tradingagents.dataflows.providers.china.akshare import AKShareProvider
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def _build_debt_wide_from_long_df(df_long: pd.DataFrame) -> pd.DataFrame:
    if df_long is None or getattr(df_long, "empty", True):
        return pd.DataFrame()

    if not {"report_date", "metric_name", "value"}.issubset(set(df_long.columns)):
        return pd.DataFrame()

    required_metrics = [
        "assets_total",
        "parent_holder_equity_total",
        "total_debt",
        "total_current_assets",
        "current_total_debt",
    ]

    debt_filtered = df_long[df_long["metric_name"].isin(required_metrics)].copy()
    if debt_filtered.empty:
        return pd.DataFrame()

    debt_filtered["value_num"] = debt_filtered["value"].apply(_parse_financial_value)
    debt_wide = (
        debt_filtered.pivot_table(
            index="report_date",
            columns="metric_name",
            values="value_num",
            aggfunc="first",
        )
        .reset_index()
    )

    for metric_col in required_metrics:
        if metric_col in debt_wide.columns:
            debt_wide[metric_col] = pd.to_numeric(debt_wide[metric_col], errors="coerce")

    debt_wide["报告期"] = pd.to_datetime(debt_wide["report_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    debt_wide = debt_wide.drop(columns=["report_date"])

    if "assets_total" in debt_wide.columns and "资产合计" not in debt_wide.columns:
        debt_wide["资产合计"] = debt_wide["assets_total"]
    if "parent_holder_equity_total" in debt_wide.columns and "归属于母公司所有者权益合计" not in debt_wide.columns:
        debt_wide["归属于母公司所有者权益合计"] = debt_wide["parent_holder_equity_total"]

    if "assets_total" in debt_wide.columns and "total_debt" in debt_wide.columns and "资产负债率" not in debt_wide.columns:
        debt_wide["资产负债率"] = debt_wide["total_debt"] / debt_wide["assets_total"].replace({0: pd.NA}) * 100
    if (
        "total_current_assets" in debt_wide.columns
        and "current_total_debt" in debt_wide.columns
        and "流动比率" not in debt_wide.columns
    ):
        debt_wide["流动比率"] = debt_wide["total_current_assets"] / debt_wide["current_total_debt"].replace({0: pd.NA})

    keep_cols = ["报告期", "资产合计", "归属于母公司所有者权益合计", "资产负债率", "流动比率"]
    keep_cols = [c for c in keep_cols if c in debt_wide.columns]
    return debt_wide[keep_cols].copy()


async def sync_single_stock_financial_data(
    code: str,
    provider: AKShareProvider,
    db
) -> bool:
    """
    同步单只股票的财务数据
    
    Returns:
        bool: 是否成功
    """
    code6 = str(code).zfill(6)
    

    try:
        logger.info(f"🔄 同步 {code6} 的财务数据...")
        
        # 1. 获取财务指标数据
        import akshare as ak

        def fetch_financial_indicator():
            df1 = ak.stock_financial_debt_ths(symbol=code6)
            df2 = ak.stock_financial_abstract_ths(symbol=code6)

            if (
                isinstance(df1, pd.DataFrame)
                and isinstance(df2, pd.DataFrame)
                and ('报告期' in df1.columns)
                and ('报告期' in df2.columns)
            ):
                df = pd.merge(df1, df2, on='报告期', how='inner')
                return df.sort_values('报告期', ascending=True).reset_index(drop=True)

            indicator_raw = ak.stock_financial_abstract(symbol=code6)
            if indicator_raw is None or getattr(indicator_raw, "empty", True):
                raise RuntimeError("stock_financial_abstract 返回空数据")

            if "指标" not in indicator_raw.columns:
                raise RuntimeError(f"stock_financial_abstract 缺少“指标”列: {list(indicator_raw.columns)}")

            meta_cols = [c for c in ["选项", "指标"] if c in indicator_raw.columns]
            date_cols = [c for c in indicator_raw.columns if c not in meta_cols]
            indicator_table = indicator_raw[["指标"] + date_cols].copy()
            indicator_table["指标"] = indicator_table["指标"].astype(str).str.strip()
            indicator_table = indicator_table.groupby("指标", as_index=False).first()
            indicator_wide = indicator_table.set_index("指标").T
            indicator_wide.index.name = "报告期_raw"
            indicator_wide = indicator_wide.reset_index()
            indicator_wide["报告期"] = (
                pd.to_datetime(indicator_wide["报告期_raw"], format="%Y%m%d", errors="coerce")
                .dt.strftime("%Y-%m-%d")
            )
            indicator_wide = indicator_wide.drop(columns=["报告期_raw"])
            indicator_wide = indicator_wide[indicator_wide["报告期"].notna()].reset_index(drop=True)

            if "归母净利润" in indicator_wide.columns and "净利润" not in indicator_wide.columns:
                indicator_wide["净利润"] = indicator_wide["归母净利润"]
            if "毛利率" in indicator_wide.columns and "销售毛利率" not in indicator_wide.columns:
                indicator_wide["销售毛利率"] = indicator_wide["毛利率"]
            if "净资产收益率(ROE)" in indicator_wide.columns and "净资产收益率" not in indicator_wide.columns:
                indicator_wide["净资产收益率"] = indicator_wide["净资产收益率(ROE)"]

            merged = indicator_wide
            if (
                isinstance(df1, pd.DataFrame)
                and {"report_date", "metric_name", "value"}.issubset(set(df1.columns))
            ):
                debt_wide = _build_debt_wide_from_long_df(df1)
                if not debt_wide.empty:
                    merged = pd.merge(merged, debt_wide, on="报告期", how="left", suffixes=("", "_debt"))
                    for col in ["资产负债率", "流动比率"]:
                        debt_col = f"{col}_debt"
                        if debt_col in merged.columns:
                            if col in merged.columns:
                                merged[col] = merged[col].combine_first(merged[debt_col])
                                merged = merged.drop(columns=[debt_col])
                            else:
                                merged = merged.rename(columns={debt_col: col})

            merged["_report_dt"] = pd.to_datetime(merged["报告期"], errors="coerce")
            merged = merged[merged["_report_dt"].notna()].sort_values("_report_dt", ascending=True)
            merged = merged.drop(columns=["_report_dt"]).reset_index(drop=True)
            return merged
        try:
            df = await asyncio.to_thread(fetch_financial_indicator)

            if df is None or df.empty:
                logger.warning(f"⚠️  {code6} 未获取到财务指标数据")
                return False

            # 获取最新一期数据
            latest = df.iloc[-1].to_dict()

            logger.info(f"   获取到 {len(df)} 期财务数据，最新期: {latest.get('报告期', 'N/A')}")

            # 计算 TTM（最近12个月）营业收入和净利润
            ttm_revenue = _calculate_ttm_metric(df, '营业总收入')
            ttm_net_profit = _calculate_ttm_metric(df, '净利润')

            if ttm_revenue:
                logger.info(f"   TTM营业总收入: {ttm_revenue:.2f} 万元")
            if ttm_net_profit:
                logger.info(f"   TTM净利润: {ttm_net_profit:.2f} 万元")

        except Exception as e:
            logger.error(f"❌ {code6} 获取财务指标失败: {e}")
            return False

        net_profit_raw = _parse_financial_value(latest.get('净利润'))
        net_profit = net_profit_raw / 10000 if net_profit_raw is not None else None
        total_assets_raw = _parse_financial_value(latest.get('资产合计'))
        total_assets = total_assets_raw / 10000 if total_assets_raw is not None else None
        revenue_raw = _parse_financial_value(latest.get('营业总收入'))
        revenue = revenue_raw / 10000 if revenue_raw is not None else None
        total_hldr_eqy_raw = _parse_financial_value(latest.get('归属于母公司所有者权益合计'))
        total_hldr_eqy_exc_min_int = total_hldr_eqy_raw / 10000 if total_hldr_eqy_raw is not None else None
        # 2. 解析财务数据
        financial_data = {
            "code": code6,
            "symbol": code6,
            "report_period": latest.get('报告期', ''),
            "data_source": "akshare",
            "updated_at": datetime.utcnow(),

            # 盈利能力指标
            "roe": _parse_financial_value(latest.get('净资产收益率')),  # ROE
            "roa": 100 * net_profit / total_assets if all([net_profit, total_assets]) else None, # ROA
            "gross_margin": _parse_financial_value(latest.get('销售毛利率')),  # 毛利率
            "netprofit_margin": _parse_financial_value(latest.get('销售净利率')),  # 净利率

            # 财务数据（万元）
            "revenue": revenue,
            "revenue_ttm": ttm_revenue,  # TTM营业总收入（最近12个月）
            "net_profit": net_profit,
            "net_profit_ttm": ttm_net_profit,  # TTM净利润（最近12个月）
            "total_assets": total_assets,
            "total_hldr_eqy_exc_min_int": total_hldr_eqy_exc_min_int,

            # 每股指标
            "basic_eps": _parse_financial_value(latest.get('基本每股收益')),  # 每股收益
            "bps": _parse_financial_value(latest.get('每股净资产')),  # 每股净资产

            # 偿债能力指标
            "debt_to_assets": _parse_financial_value(latest.get('资产负债率')),  # 资产负债率
            "current_ratio": _parse_financial_value(latest.get('流动比率')),  # 流动比率

            # 运营能力指标
            "total_asset_turnover": revenue / total_assets if all([revenue, total_assets]) else None,  # 总资产周转率(次)
        }

        # 3. 获取股本数据
        try:
            def fetch_stock_info():
                return ak.stock_individual_info_em(symbol=code6)
            
            stock_info_df = await asyncio.to_thread(fetch_stock_info)
            
            if stock_info_df is not None and not stock_info_df.empty:
                # 提取总股本
                total_share_row = stock_info_df[stock_info_df['item'] == '总股本']
                if not total_share_row.empty:
                    total_share_str = str(total_share_row['value'].iloc[0])
                    # 解析总股本（可能是 "193.78亿" 这种格式）
                    total_share = _parse_share_value(total_share_str)
                    financial_data['total_share'] = total_share
                    logger.info(f"   总股本: {total_share} 万股")
                
                # 提取流通股本
                float_share_row = stock_info_df[stock_info_df['item'] == '流通股']
                if not float_share_row.empty:
                    float_share_str = str(float_share_row['value'].iloc[0])
                    float_share = _parse_share_value(float_share_str)
                    financial_data['float_share'] = float_share
        
        except Exception as e:
            logger.warning(f"⚠️  {code6} 获取股本数据失败: {e}")
        logger.info(f"   解析财务数据: {financial_data}")
        # 4. 计算市值和估值指标（如果有实时价格）
        quote = await db.market_quotes.find_one(
            {"$or": [{"code": code6}, {"symbol": code6}]}
        )
        
        if quote and financial_data.get('total_share'):
            price = quote.get('close')
            if price:
                # 计算市值（万元）
                market_cap = price * financial_data['total_share']
                financial_data['money_cap'] = market_cap

                # 计算 PE（优先使用 TTM 净利润）
                net_profit_for_pe = financial_data.get('net_profit_ttm') or financial_data.get('net_profit')
                pe_type = "TTM" if financial_data.get('net_profit_ttm') else "单期"

                if net_profit_for_pe and net_profit_for_pe > 0:
                    pe = market_cap / net_profit_for_pe
                    financial_data['pe'] = round(pe, 2)
                    logger.info(f"   PE({pe_type}): {pe:.2f}")

                # 计算 PB
                if financial_data.get('total_hldr_eqy_exc_min_int') and financial_data['total_hldr_eqy_exc_min_int'] > 0:
                    pb = market_cap / financial_data['total_hldr_eqy_exc_min_int']
                    financial_data['pb'] = round(pb, 2)
                    logger.info(f"   PB: {pb:.2f}")

                # 计算 PS（优先使用 TTM 营业收入）
                revenue_for_ps = financial_data.get('revenue_ttm') or financial_data.get('revenue')
                ps_type = "TTM" if financial_data.get('revenue_ttm') else "单期"

                if revenue_for_ps and revenue_for_ps > 0:
                    ps = market_cap / revenue_for_ps
                    financial_data['ps'] = round(ps, 2)
                    logger.info(f"   PS({ps_type}): {ps:.2f}")
        
        # 5. 更新 stock_basic_info 集合
        await db.stock_basic_info.update_one(
            {"code": code6},
            {"$set": {
                "total_share": financial_data.get('total_share'),
                "float_share": financial_data.get('float_share'),
                "net_profit": financial_data.get('net_profit'),
                "net_profit_ttm": financial_data.get('net_profit_ttm'),
                "revenue_ttm": financial_data.get('revenue_ttm'),
                "total_hldr_eqy_exc_min_int": financial_data.get('total_hldr_eqy_exc_min_int'),
                "money_cap": financial_data.get('money_cap'),
                "pe": financial_data.get('pe'),
                "pb": financial_data.get('pb'),
                "ps": financial_data.get('ps'),
                "roe": financial_data.get('roe'),
                "updated_at": datetime.utcnow()
            }},
            upsert=False  # 不创建新文档，只更新已存在的
        )
        
        # 6. 更新 stock_financial_data 集合
        await db.stock_financial_data.update_one(
            {"code": code6, "report_period": financial_data['report_period']},
            {"$set": financial_data},
            upsert=True
        )
        
        print(financial_data)

        logger.info(f"✅ {code6} 财务数据同步成功")
        return True
        
    except Exception as e:
        logger.error(f"❌ {code6} 财务数据同步失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def _calculate_ttm_metric(df, metric_name: str) -> Optional[float]:
    """
    计算 TTM（最近12个月）指标值（营业收入、净利润等）

    策略：
    1. 如果最新期是年报（12月31日），直接使用年报数据
    2. 如果最新期是中报/季报，计算 TTM = 最新年报 + (本期累计 - 去年同期累计)
    3. 如果数据不足，返回 None（不使用简单年化，因为对季节性行业不准确）

    Args:
        df: AKShare 返回的财务指标 DataFrame，包含 '报告期' 和指标列
        metric_name: 指标名称（如 '营业收入'、'净利润'）

    Returns:
        TTM 指标值（万元），如果无法计算则返回 None
    """
    logger.info(f"数据：----------------- ")
    logger.info(f"{df}")

    try:
        if df is None or df.empty or len(df) < 1:
            return None

        # 确保有必要的列
        if '报告期' not in df.columns or metric_name not in df.columns:
            return None

        def _normalize_report_period(value) -> Optional[str]:
            if value is None:
                return None
            s = str(value).strip()
            if not s or s.lower() in {"nan", "none", "null", "--"}:
                return None
            if "-" in s:
                s = s.replace("-", "")
            if len(s) != 8 or not s.isdigit():
                return None
            return s

        df_local = df.copy()
        df_local["_period_norm"] = df_local["报告期"].apply(_normalize_report_period)
        df_local = df_local[df_local["_period_norm"].notna()]
        if df_local.empty:
            return None
        df_local = df_local.sort_values("_period_norm")

        latest = df_local.iloc[-1]
        latest_period = str(latest["_period_norm"])
        latest_value = _parse_financial_value(latest[metric_name])

        if latest_value is None:
            return None

        if latest_period.endswith("1231"):
            latest_value /= 10000 # 万元
            logger.debug(f"   使用年报{metric_name}作为TTM: {latest_value:.2f} 万元")
            return latest_value

        # 非年报，需要计算 TTM
        # 提取年份和月份
        try:
            year = int(latest_period[:4])
            month_day = latest_period[4:8]
        except:
            return None

        # 查找最近的年报（上一年的12-31）
        last_year = year - 1
        last_annual_period = f"{last_year}1231"

        # 查找去年同期
        last_same_period = f"{last_year}{month_day}"

        # 在 DataFrame 中查找
        last_annual_row = df_local[df_local["_period_norm"] == last_annual_period]
        last_same_row = df_local[df_local["_period_norm"] == last_same_period]

        if not last_annual_row.empty and not last_same_row.empty:
            last_annual_value = _parse_financial_value(last_annual_row.iloc[0][metric_name])
            last_same_value = _parse_financial_value(last_same_row.iloc[0][metric_name])

            if last_annual_value is not None and last_same_value is not None:
                # TTM = 最近年报 + (本期累计 - 去年同期累计)
                ttm_value = (last_annual_value + (latest_value - last_same_value)) / 10000
                logger.debug(f"   ✅ 计算{metric_name}TTM: {last_annual_value:.2f} + ({latest_value:.2f} - {last_same_value:.2f}) = {ttm_value:.2f} 万元")
                return ttm_value if ttm_value > 0 else None

        # 如果无法计算 TTM，返回 None（不使用简单年化，因为对季节性行业不准确）
        if not last_annual_row.empty:
            logger.warning(f"   ⚠️ {metric_name}TTM计算失败: 缺少去年同期数据（需要: {last_same_period}）")
        else:
            logger.warning(f"   ⚠️ {metric_name}TTM计算失败: 缺少基准年报（需要: {last_annual_period}）")

        return None

    except Exception as e:
        logger.warning(f"   计算{metric_name}TTM失败: {e}")
        return None


# 保留旧函数名以保持向后兼容
def _calculate_ttm_revenue(df) -> Optional[float]:
    """
    计算 TTM（最近12个月）营业收入

    已弃用：请使用 _calculate_ttm_metric(df, '营业收入')
    """
    return _calculate_ttm_metric(df, '营业收入')


def _parse_share_value(value_str: str) -> Optional[float]:
    """解析股本数值（支持 "193.78亿" 这种格式）"""
    try:
        value_str = str(value_str).strip()
        
        # 移除单位并转换
        if '亿' in value_str:
            num = float(value_str.replace('亿', ''))
            return num * 10000  # 亿 -> 万
        elif '万' in value_str:
            return float(value_str.replace('万', ''))
        else:
            # 假设是股数，转换为万股
            return float(value_str) / 10000
    except:
        return None


def _parse_financial_value(value_str) -> Optional[float]:
    """解析财务数值（支持带单位和百分比的格式）"""
    if value_str is None:
        return None
    
    try:
        value_str = str(value_str).strip()
        
        # 处理空值和特殊标记
        if value_str in ['--', '', 'nan', 'None', 'False']:
            return None
        
        # 处理百分比
        if '%' in value_str:
            # 移除百分号并转换为小数
            return float(value_str.replace('%', ''))
        
        # 处理带单位的数值（亿、万）
        if '万亿' in value_str:
            num = float(value_str.replace('万亿', ''))
            return num * 10000 * 10000 * 10000  # 万亿 -> 元
        elif '亿' in value_str:
            num = float(value_str.replace('亿', ''))
            return num * 100000000  # 亿 -> 元
        elif '万' in value_str:
            num = float(value_str.replace('万', ''))
            return num * 10000  # 万 -> 元
        
        # 直接转换为浮点数
        return float(value_str)
    except (ValueError, TypeError):
        return None


async def main(code: Optional[str] = None, sync_all: bool = False, batch: Optional[int] = None):
    """主函数"""
    logger.info("=" * 80)
    logger.info("🚀 同步股票财务数据")
    logger.info("=" * 80)
    
    # 连接数据库
    mongo_uri = os.getenv("MONGODB_CONNECTION_STRING") or settings.MONGO_URI
    db_name = os.getenv("MONGODB_DATABASE_NAME") or settings.MONGO_DB
    client = AsyncIOMotorClient(mongo_uri)
    db = client[db_name]
    
    # 初始化 Provider
    provider = AKShareProvider()
    await provider.connect()

    if code is None:
        code = "600089"
    
    try:
        if code:
            # 同步单只股票
            await sync_single_stock_financial_data(code, provider, db)
        
        elif sync_all or batch:
            # 批量同步
            cursor = db.stock_basic_info.find({}, {"code": 1, "name": 1})
            stocks = await cursor.to_list(length=batch if batch else None)
            
            total = len(stocks)
            logger.info(f"📊 准备同步 {total} 只股票的财务数据")
            
            success_count = 0
            failed_count = 0
            
            for i, stock in enumerate(stocks, 1):
                stock_code = stock.get('code')
                stock_name = stock.get('name', 'N/A')
                
                logger.info(f"\n[{i}/{total}] {stock_code} ({stock_name})")
                
                success = await sync_single_stock_financial_data(stock_code, provider, db)
                
                if success:
                    success_count += 1
                else:
                    failed_count += 1
                
                # 延迟，避免API限流
                if i < total:
                    await asyncio.sleep(0.5)
            
            logger.info(f"\n" + "=" * 80)
            logger.info(f"📊 同步完成统计")
            logger.info(f"=" * 80)
            logger.info(f"   总计: {total} 只")
            logger.info(f"   成功: {success_count} 只")
            logger.info(f"   失败: {failed_count} 只")
            logger.info(f"=" * 80)
        
        else:
            logger.error("❌ 请指定股票代码、--all 或 --batch 参数")
    
    finally:
        client.close()
    
    logger.info("")
    logger.info("✅ 同步完成！")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="同步股票财务数据",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "code",
        nargs="?",
        type=str,
        help="股票代码（6位）"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="同步所有股票"
    )
    parser.add_argument(
        "--batch",
        type=int,
        help="批量同步前N只股票"
    )
    
    args = parser.parse_args()
    
    asyncio.run(main(
        code=args.code,
        sync_all=args.all,
        batch=args.batch
    ))

