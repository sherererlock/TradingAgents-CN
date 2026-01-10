import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path


def _add_project_root_to_sys_path() -> Path:
    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))
    return project_root


def _load_dotenv_if_present(project_root: Path) -> None:
    env_path = project_root / ".env"
    if not env_path.exists():
        return

    try:
        from dotenv import load_dotenv

        load_dotenv(env_path)
        return
    except Exception:
        pass

    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :].strip()
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except Exception:
        return


def _compute_date_range(trade_date: str | None) -> tuple[str, str, str]:
    if trade_date:
        end_date_dt = datetime.strptime(trade_date, "%Y-%m-%d")
        curr_date = trade_date
    else:
        end_date_dt = datetime.now()
        curr_date = end_date_dt.strftime("%Y-%m-%d")
    start_date = (end_date_dt - timedelta(days=10)).strftime("%Y-%m-%d")
    return start_date, curr_date, curr_date


def _get_company_name(ticker: str, market_info: dict) -> str:
    try:
        if market_info.get("is_china"):
            try:
                from tradingagents.dataflows.interface import get_china_stock_info_unified

                stock_info = get_china_stock_info_unified(ticker)
                if stock_info and "股票名称:" in stock_info:
                    return stock_info.split("股票名称:")[1].split("\n")[0].strip()
            except Exception:
                pass

            try:
                from tradingagents.dataflows.data_source_manager import (
                    get_china_stock_info_unified as get_info_dict,
                )

                info_dict = get_info_dict(ticker)
                if info_dict and info_dict.get("name"):
                    return str(info_dict["name"]).strip()
            except Exception:
                pass

            return f"股票代码{ticker}"

        if market_info.get("is_hk"):
            try:
                from tradingagents.dataflows.providers.hk.improved_hk import (
                    get_hk_company_name_improved,
                )

                name = get_hk_company_name_improved(ticker)
                if name:
                    return str(name).strip()
            except Exception:
                pass

            clean_ticker = ticker.replace(".HK", "").replace(".hk", "")
            return f"港股{clean_ticker}"

        if market_info.get("is_us"):
            us_stock_names = {
                "AAPL": "苹果公司",
                "TSLA": "特斯拉",
                "NVDA": "英伟达",
                "MSFT": "微软",
                "GOOGL": "谷歌",
                "AMZN": "亚马逊",
                "META": "Meta",
                "NFLX": "奈飞",
            }
            return us_stock_names.get(ticker.upper(), f"美股{ticker}")

        return f"股票{ticker}"
    except Exception:
        return f"股票{ticker}"


def _parse_markdown_kv_metadata(text: str) -> dict:
    meta: dict[str, str] = {}
    for line in text.splitlines():
        s = line.strip()
        m = re.match(r"^\*\*(.+?)\*\*:\s*(.+?)\s*$", s)
        if m:
            meta[m.group(1)] = m.group(2)
    return meta


def _split_markdown_sections(text: str) -> list[dict]:
    sections: list[dict] = []
    current_title: str | None = None
    current_lines: list[str] = []

    def _flush():
        nonlocal current_title, current_lines
        if current_title is None:
            return
        content = "\n".join(current_lines).strip()
        sections.append({"title": current_title, "content": content})
        current_title = None
        current_lines = []

    for line in text.splitlines():
        if line.startswith("## "):
            _flush()
            current_title = line[len("## ") :].strip()
            current_lines = []
            continue
        if current_title is not None:
            current_lines.append(line)
    _flush()
    return sections


def _extract_metrics(text: str) -> dict:
    patterns: dict[str, list[str]] = {
        "latest_price": [
            r"最新价格[:：]\s*[¥$]*\s*([0-9]+(?:\.[0-9]+)?)",
            r"最新价格[:：]\s*HK\$\s*([0-9]+(?:\.[0-9]+)?)",
        ],
        "pe": [
            r"\bPE\b\s*[:：]\s*([0-9]+(?:\.[0-9]+)?)",
            r"市盈率.*?[:：]\s*([0-9]+(?:\.[0-9]+)?)",
        ],
        "pb": [
            r"\bPB\b\s*[:：]\s*([0-9]+(?:\.[0-9]+)?)",
            r"市净率.*?[:：]\s*([0-9]+(?:\.[0-9]+)?)",
        ],
        "peg": [r"\bPEG\b.*?[:：]\s*([0-9]+(?:\.[0-9]+)?)"],
        "roe": [
            r"\bROE\b.*?[:：]\s*([0-9]+(?:\.[0-9]+)?)\s*%?",
            r"净资产收益率.*?[:：]\s*([0-9]+(?:\.[0-9]+)?)\s*%?",
        ],
    }

    extracted: dict[str, str] = {}
    for key, key_patterns in patterns.items():
        for pat in key_patterns:
            m = re.search(pat, text, flags=re.IGNORECASE)
            if m:
                extracted[key] = m.group(1)
                break
    return extracted


def _parse_unified_fundamentals_output(raw: str) -> dict:
    meta = _parse_markdown_kv_metadata(raw)
    sections = _split_markdown_sections(raw)
    metrics = _extract_metrics(raw)
    return {
        "meta": meta,
        "sections": sections,
        "metrics": metrics,
        "raw_preview": raw[:2000],
        "raw_length": len(raw),
    }


def _analysis_modules_from_research_depth(research_depth: str) -> str:
    normalized = str(research_depth).strip()
    if normalized.isdigit():
        numeric_to_chinese = {
            "1": "快速",
            "2": "基础",
            "3": "标准",
            "4": "深度",
            "5": "全面",
        }
        normalized = numeric_to_chinese.get(normalized, "标准")

    if normalized == "快速":
        return "basic"
    if normalized in {"基础", "标准"}:
        return "standard"
    if normalized == "深度":
        return "full"
    if normalized == "全面":
        return "comprehensive"
    return "standard"


def _get_stock_fundamentals_unified_no_toolkit(
    ticker: str,
    start_date: str,
    end_date: str,
    curr_date: str,
    market_info: dict,
    research_depth: str,
) -> str:
    if market_info.get("is_china"):
        from tradingagents.dataflows.interface import get_china_stock_data_unified
        from tradingagents.dataflows.optimized_china_data import OptimizedChinaDataProvider

        recent_end_date = curr_date
        recent_start_date = (
            datetime.strptime(curr_date, "%Y-%m-%d") - timedelta(days=2)
        ).strftime("%Y-%m-%d")

        current_price_data = get_china_stock_data_unified(ticker, recent_start_date, recent_end_date)

        analysis_modules = _analysis_modules_from_research_depth(research_depth)
        analyzer = OptimizedChinaDataProvider()
        fundamentals_data = analyzer._generate_fundamentals_report(
            ticker,
            current_price_data,
            analysis_modules,
        )

        result_data = [
            f"## A股当前价格信息\n{current_price_data}",
            f"## A股基本面财务数据\n{fundamentals_data}",
        ]

        combined_result = f"""# {ticker} 基本面分析数据

**股票类型**: {market_info.get('market_name', '中国A股')}
**货币**: {market_info.get('currency_name', '人民币')} ({market_info.get('currency_symbol', '¥')})
**分析日期**: {curr_date}
**数据深度级别**: {analysis_modules}

{chr(10).join(result_data)}

---
*数据来源: 根据股票类型自动选择最适合的数据源*
"""
        return combined_result

    if market_info.get("is_hk"):
        from tradingagents.dataflows.interface import get_hk_stock_data_unified, get_hk_stock_info_unified

        hk_data_success = False
        result_data: list[str] = []

        try:
            hk_data = get_hk_stock_data_unified(ticker, start_date, end_date)
            if hk_data and len(hk_data) > 100 and "❌" not in hk_data:
                result_data.append(f"## 港股数据\n{hk_data}")
                hk_data_success = True
        except Exception:
            hk_data_success = False

        if not hk_data_success:
            try:
                hk_info = get_hk_stock_info_unified(ticker)
                stock_name = hk_info.get("name", f"港股{ticker}") if isinstance(hk_info, dict) else f"港股{ticker}"
                source = hk_info.get("source", "基础信息") if isinstance(hk_info, dict) else "基础信息"
                basic_info = f"""## 港股基础信息

**股票代码**: {ticker}
**股票名称**: {stock_name}
**交易货币**: 港币 (HK$)
**交易所**: 香港交易所 (HKG)
**数据源**: {source}

⚠️ 注意：详细的价格和财务数据暂时无法获取，建议稍后重试或使用其他数据源。
"""
                result_data.append(basic_info)
            except Exception as e:
                fallback_info = f"""## 港股信息（备用）

**股票代码**: {ticker}
**股票类型**: 港股
**交易货币**: 港币 (HK$)
**交易所**: 香港交易所 (HKG)

❌ 数据获取遇到问题: {str(e)}
"""
                result_data.append(fallback_info)

        combined_result = f"""# {ticker} 基本面分析数据

**股票类型**: {market_info.get('market_name', '港股')}
**货币**: {market_info.get('currency_name', '港币')} ({market_info.get('currency_symbol', 'HK$')})
**分析日期**: {curr_date}
**数据深度级别**: {_analysis_modules_from_research_depth(research_depth)}

{chr(10).join(result_data)}

---
*数据来源: 根据股票类型自动选择最适合的数据源*
"""
        return combined_result

    from tradingagents.dataflows.interface import get_fundamentals_openai

    try:
        us_data = get_fundamentals_openai(ticker, curr_date)
    except Exception as e:
        us_data = f"获取失败: {e}"

    combined_result = f"""# {ticker} 基本面分析数据

**股票类型**: {market_info.get('market_name', '美股')}
**货币**: {market_info.get('currency_name', '美元')} ({market_info.get('currency_symbol', '$')})
**分析日期**: {curr_date}
**数据深度级别**: {_analysis_modules_from_research_depth(research_depth)}

## 美股基本面数据
{us_data}

---
*数据来源: 根据股票类型自动选择最适合的数据源*
"""
    return combined_result


def main() -> int:
    project_root = _add_project_root_to_sys_path()
    _load_dotenv_if_present(project_root)

    # parser = argparse.ArgumentParser()
    # parser.add_argument("--ticker", required=True)
    # parser.add_argument("--trade-date", default=None)
    # parser.add_argument("--research-depth", default="标准")
    # parser.add_argument("--online-tools", action=argparse.BooleanOptionalAction, default=True)
    # parser.add_argument("--pretty", action=argparse.BooleanOptionalAction, default=True)
    # args = parser.parse_args()

    from tradingagents.utils.stock_utils import StockUtils

    # ticker = str(args.ticker).strip()
    # start_date, end_date, curr_date = _compute_date_range(args.trade_date)

    ticker = "600160"
    start_date = "2025-07-18"
    end_date = "2026-01-09"
    curr_date = "2026-01-09"

    market_info = StockUtils.get_market_info(ticker)
    company_name = _get_company_name(ticker, market_info)

    raw = _get_stock_fundamentals_unified_no_toolkit(
        ticker=ticker,
        start_date=start_date,
        end_date=end_date,
        curr_date=curr_date,
        market_info=market_info,
        research_depth="标准",
    )

    if not isinstance(raw, str):
        raw = json.dumps(raw, ensure_ascii=False, default=str)

    parsed = _parse_unified_fundamentals_output(raw)

    output = {
        "ticker": ticker,
        "company_name": company_name,
        "date_range": {"start_date": start_date, "end_date": end_date, "curr_date": curr_date},
        "market_info": market_info,
        "fundamentals": parsed,
    }


    print(json.dumps(output, ensure_ascii=False, indent=2))


    return 0


if __name__ == "__main__":
    raise SystemExit(main())
