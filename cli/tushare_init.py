#!/usr/bin/env python3
"""
Tushare数据初始化CLI工具
用于首次部署时的数据初始化操作
"""
import asyncio
import argparse
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.database import init_database
from app.worker.tushare_init_service import get_tushare_init_service


def print_banner():
    """打印横幅"""
    print("=" * 60)
    print("🚀 Tushare数据初始化工具")
    print("=" * 60)
    print()


def print_help():
    """打印帮助信息"""
    print("📋 使用说明:")
    print("  python cli/tushare_init.py [选项]")
    print()
    print("🔧 选项:")
    print("  --full              运行完整初始化（推荐首次使用）")
    print("  --basic-only        仅初始化基础信息")
    print("  --historical-days   历史数据天数（默认365天）")
    print("  --multi-period      同步多周期数据（日线、周线、月线）")
    print("  --sync-items        指定要同步的数据类型（逗号分隔）")
    print("                      可选值: basic_info,historical,weekly,monthly,financial,quotes,news")
    print("  --force             强制初始化（覆盖已有数据）")
    print("  --batch-size        批处理大小（默认100）")
    print("  --check-only        仅检查数据库状态")
    print("  --help              显示此帮助信息")
    print()
    print("📝 示例:")
    print("  # 首次完整初始化（推荐，默认1年历史数据）")
    print("  python cli/tushare_init.py --full")
    print()
    print("  # 初始化最近6个月的历史数据")
    print("  python cli/tushare_init.py --full --historical-days 180")
    print()
    print("  # 初始化全历史数据（从1990年至今，需要>=3650天）")
    print("  python cli/tushare_init.py --full --historical-days 10000")
    print()
    print("  # 初始化并同步多周期数据（日线、周线、月线）")
    print("  python cli/tushare_init.py --full --multi-period")
    print()
    print("  # 全历史多周期初始化（推荐用于生产环境）")
    print("  python cli/tushare_init.py --full --multi-period --historical-days 10000")
    print()
    print("  # 仅同步历史数据（日线）")
    print("  python cli/tushare_init.py --full --sync-items historical")
    print()
    print("  # 仅同步财务数据和行情数据")
    print("  python cli/tushare_init.py --full --sync-items financial,quotes")
    print()
    print("  # 仅同步新闻数据")
    print("  python cli/tushare_init.py --full --sync-items news")
    print()
    print("  # 仅更新周线和月线数据")
    print("  python cli/tushare_init.py --full --sync-items weekly,monthly")
    print()
    print("  # 强制重新初始化所有数据")
    print("  python cli/tushare_init.py --full --force")
    print()
    print("  # 仅检查当前数据状态")
    print("  python cli/tushare_init.py --check-only")
    print()


async def check_database_status():
    """检查数据库状态"""
    print("📊 检查数据库状态...")
    
    try:
        from app.core.database import get_mongo_db
        db = get_mongo_db()
        
        # 检查各集合状态
        basic_count = await db.stock_basic_info.count_documents({})
        quotes_count = await db.market_quotes.count_documents({})
        
        # 检查扩展字段覆盖率
        extended_count = await db.stock_basic_info.count_documents({
            "full_symbol": {"$exists": True},
            "market_info": {"$exists": True}
        })
        
        # 检查最新更新时间
        latest_basic = await db.stock_basic_info.find_one(
            {}, sort=[("updated_at", -1)]
        )
        latest_quotes = await db.market_quotes.find_one(
            {}, sort=[("updated_at", -1)]
        )
        
        print(f"  📋 股票基础信息: {basic_count:,}条")
        if basic_count > 0:
            coverage = extended_count / basic_count * 100
            print(f"     扩展字段覆盖: {extended_count:,}条 ({coverage:.1f}%)")
            if latest_basic and latest_basic.get("updated_at"):
                print(f"     最新更新: {latest_basic['updated_at']}")
        
        print(f"  📈 行情数据: {quotes_count:,}条")
        if quotes_count > 0 and latest_quotes and latest_quotes.get("updated_at"):
            print(f"     最新更新: {latest_quotes['updated_at']}")
        
        # 判断是否需要初始化
        if basic_count == 0:
            print("  ⚠️  数据库为空，建议运行完整初始化")
            return False
        elif extended_count / basic_count < 0.5:
            print("  ⚠️  扩展字段覆盖率较低，建议重新初始化")
            return False
        else:
            print("  ✅ 数据库状态良好")
            return True
            
    except Exception as e:
        print(f"  ❌ 检查数据库状态失败: {e}")
        return False


def _mask_token(token: str) -> str:
    if not token:
        return ""
    token = str(token)
    if len(token) <= 8:
        return "*" * len(token)
    return f"{token[:3]}***{token[-3:]}"


async def check_tushare_status(test_ts_code: str = "000001.SZ") -> bool:
    print("🔌 检查 Tushare Token 与接口连通性...")

    env_token = os.getenv("TUSHARE_TOKEN", "")
    if env_token:
        placeholder = env_token.startswith("your_")
        env_status = "占位符" if placeholder else "已设置"
        print(f"  • 环境变量 TUSHARE_TOKEN: {env_status} (长度: {len(env_token)}, 预览: {_mask_token(env_token)})")
    else:
        print("  • 环境变量 TUSHARE_TOKEN: 未设置")

    try:
        from tradingagents.dataflows.providers.china.tushare import TushareProvider
    except Exception as e:
        print(f"  ❌ 无法导入 TushareProvider: {e}")
        return False

    provider = TushareProvider()

    db_token = None
    try:
        db_token = await asyncio.to_thread(provider._get_token_from_database)
    except Exception:
        db_token = None

    if db_token:
        placeholder = str(db_token).startswith("your_")
        db_status = "占位符" if placeholder else "已设置"
        print(f"  • 数据库 Token: {db_status} (长度: {len(str(db_token))}, 预览: {_mask_token(str(db_token))})")
    else:
        print("  • 数据库 Token: 未找到或不可用")

    try:
        ok = await provider.connect()
    except Exception as e:
        print(f"  ❌ Tushare 连接异常: {e}")
        return False

    if not ok or not getattr(provider, "api", None):
        print("  ❌ Tushare 连接失败")
        return False

    print("  ✅ Tushare 连接成功")

    try:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)).strftime("%Y%m%d")
        df = await asyncio.to_thread(
            provider.api.trade_cal,
            exchange="SSE",
            start_date=start_date,
            end_date=end_date
        )
        if df is not None and len(df) > 0:
            print(f"  • trade_cal 返回: {len(df)} 行")
    except Exception as e:
        print(f"  ⚠️ trade_cal 调用失败: {e}")

    try:
        df = await asyncio.to_thread(
            provider.api.stock_basic,
            list_status="L",
            ts_code=test_ts_code,
            limit=1
        )
        if df is not None and not df.empty:
            name = df.iloc[0].get("name")
            print(f"  • stock_basic: {test_ts_code} {name or ''}".rstrip())
        else:
            print(f"  ⚠️ stock_basic: 返回空数据 (ts_code={test_ts_code})")
    except Exception as e:
        print(f"  ⚠️ stock_basic 调用失败: {e}")

    try:
        trade_cal = await asyncio.to_thread(
            provider.api.trade_cal,
            exchange="SSE",
            start_date=(datetime.now() - timedelta(days=30)).strftime("%Y%m%d"),
            end_date=datetime.now().strftime("%Y%m%d"),
            is_open=1
        )
        trade_date = None
        if trade_cal is not None and len(trade_cal) > 0:
            trade_date = str(trade_cal.iloc[-1].get("cal_date"))

        if trade_date:
            df = await asyncio.to_thread(
                provider.api.daily_basic,
                ts_code=test_ts_code,
                trade_date=trade_date,
                fields="ts_code,trade_date,pe,pb,dv_ratio,total_mv"
            )
            if df is not None and not df.empty:
                row = df.iloc[0].to_dict()
                pe = row.get("pe")
                pb = row.get("pb")
                dv = row.get("dv_ratio")
                print(f"  • daily_basic({trade_date}): PE={pe} PB={pb} 股息率={dv}")
            else:
                print(f"  ⚠️ daily_basic: 返回空数据 (ts_code={test_ts_code}, trade_date={trade_date})")
    except Exception as e:
        print(f"  ⚠️ daily_basic 调用失败: {e}")

    return True


async def run_basic_initialization():
    """运行基础信息初始化"""
    print("📋 开始基础信息初始化...")
    
    try:
        service = await get_tushare_init_service()
        
        # 仅同步基础信息
        result = await service.sync_service.sync_stock_basic_info(force_update=True)
        
        if result:
            success_count = result.get("success_count", 0)
            print(f"✅ 基础信息初始化完成: {success_count:,}只股票")
            return True
        else:
            print("❌ 基础信息初始化失败")
            return False
            
    except Exception as e:
        print(f"❌ 基础信息初始化失败: {e}")
        return False


async def run_full_initialization(historical_days: int, force: bool, multi_period: bool = False, sync_items: list = None):
    """运行完整初始化"""
    if sync_items:
        print(f"🚀 开始数据初始化（历史数据: {historical_days}天）...")
        print(f"📋 同步项目: {', '.join(sync_items)}")
    else:
        period_info = "日线、周线、月线" if multi_period else "日线"
        print(f"🚀 开始完整数据初始化（历史数据: {historical_days}天，周期: {period_info}）...")

    try:
        service = await get_tushare_init_service()

        result = await service.run_full_initialization(
            historical_days=historical_days,
            skip_if_exists=not force,
            enable_multi_period=multi_period,
            sync_items=sync_items
        )
        
        # 显示结果
        if result["success"]:
            print("🎉 完整初始化成功完成！")
        else:
            print("⚠️ 初始化部分完成，存在一些问题")
        
        print(f"  ⏱️  耗时: {result['duration']:.2f}秒")
        print(f"  📊 进度: {result['progress']}")

        data_summary = result["data_summary"]
        print(f"  📋 基础信息: {data_summary['basic_info_count']:,}条")
        print(f"  📊 历史数据: {data_summary['historical_records']:,}条")
        if multi_period:
            print(f"     - 日线数据: {data_summary.get('daily_records', 0):,}条")
            print(f"     - 周线数据: {data_summary.get('weekly_records', 0):,}条")
            print(f"     - 月线数据: {data_summary.get('monthly_records', 0):,}条")
        print(f"  💰 财务数据: {data_summary['financial_records']:,}条")
        print(f"  📈 行情数据: {data_summary['quotes_count']:,}条")
        print(f"  📰 新闻数据: {data_summary.get('news_count', 0):,}条")
        
        if result["errors"]:
            print(f"  ⚠️  错误数量: {len(result['errors'])}")
            for error in result["errors"][:3]:  # 只显示前3个错误
                print(f"     - {error['step']}: {error['error']}")
        
        return result["success"]
        
    except Exception as e:
        print(f"❌ 完整初始化失败: {e}")
        return False


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="Tushare数据初始化工具",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument("--full", action="store_true", help="运行完整初始化")
    parser.add_argument("--basic-only", action="store_true", help="仅初始化基础信息")
    parser.add_argument("--historical-days", type=int, default=365, help="历史数据天数")
    parser.add_argument("--multi-period", action="store_true", help="同步多周期数据（日线、周线、月线）")
    parser.add_argument("--sync-items", type=str, help="指定要同步的数据类型（逗号分隔），可选: basic_info,historical,weekly,monthly,financial,quotes,news")
    parser.add_argument("--force", action="store_true", help="强制初始化")
    parser.add_argument("--batch-size", type=int, default=100, help="批处理大小")
    parser.add_argument("--check-only", action="store_true", help="仅检查数据库状态")
    parser.add_argument("--check-tushare", action="store_true", help="检查 Tushare Token 与接口连通性")
    parser.add_argument("--test-ts-code", type=str, default="000001.SZ", help="Tushare 测试股票代码（默认000001.SZ）")
    parser.add_argument("--help-detail", action="store_true", help="显示详细帮助")
    
    args = parser.parse_args()
    
    # 显示详细帮助
    if args.help_detail:
        print_help()
        return
    
    print_banner()
    
    try:
        if args.check_tushare and not (args.full or args.basic_only or args.check_only):
            tushare_ok = await check_tushare_status(test_ts_code=args.test_ts_code)
            if not tushare_ok:
                sys.exit(1)
            return

        # 初始化数据库连接
        print("🔄 初始化数据库连接...")
        await init_database()
        print("✅ 数据库连接成功")
        print()
        
        # 检查数据库状态
        db_ok = await check_database_status()
        print()

        tushare_ok = True
        if args.check_tushare:
            tushare_ok = await check_tushare_status(test_ts_code=args.test_ts_code)
            print()
        
        # 根据参数执行相应操作
        if args.check_only:
            print("📋 数据库状态检查完成")
            if args.check_tushare and not tushare_ok:
                sys.exit(1)
            return
        
        elif args.basic_only:
            if args.check_tushare and not tushare_ok:
                sys.exit(1)
            success = await run_basic_initialization()
            
        elif args.full:
            if args.check_tushare and not tushare_ok:
                sys.exit(1)
            if not args.force and db_ok:
                print("⚠️ 数据库已有数据，使用 --force 强制重新初始化")
                return

            # 解析sync_items参数
            sync_items = None
            if args.sync_items:
                sync_items = [item.strip() for item in args.sync_items.split(',')]
                # 验证sync_items
                valid_items = ['basic_info', 'historical', 'weekly', 'monthly', 'financial', 'quotes', 'news']
                invalid_items = [item for item in sync_items if item not in valid_items]
                if invalid_items:
                    print(f"❌ 无效的同步项目: {', '.join(invalid_items)}")
                    print(f"   有效选项: {', '.join(valid_items)}")
                    return

            success = await run_full_initialization(args.historical_days, args.force, args.multi_period, sync_items)
            
        else:
            if args.check_tushare:
                if not tushare_ok:
                    sys.exit(1)
                return
            print("❓ 请指定操作类型，使用 --help-detail 查看详细帮助")
            return
        
        if success:
            print("\n🎉 初始化操作成功完成！")
        else:
            print("\n❌ 初始化操作失败")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断操作")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 初始化失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
