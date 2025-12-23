
import akshare as ak
import pandas as pd
import logging
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_akshare_600089():
    symbol = "600089"
    print(f"Testing AKShare for symbol: {symbol}")
    
    # 1. Test stock_individual_info_em (Get Stock Info)
    try:
        print("\n1. Testing stock_individual_info_em...")
        start_time = time.time()
        info = ak.stock_individual_info_em(symbol=symbol)
        duration = time.time() - start_time
        print(f"Duration: {duration:.2f}s")
        if info is not None and not info.empty:
            print("SUCCESS: Retrieved stock info")
            print(info)
        else:
            print("FAILURE: Returned empty or None")
    except Exception as e:
        print(f"ERROR in stock_individual_info_em: {e}")

    # 2. Test stock_zh_a_hist (Get Historical Data)
    try:
        print("\n2. Testing stock_zh_a_hist...")
        start_date = "20230101"
        end_date = "20231231"
        start_time = time.time()
        hist = ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust="qfq"
        )
        duration = time.time() - start_time
        print(f"Duration: {duration:.2f}s")
        if hist is not None and not hist.empty:
            print(f"SUCCESS: Retrieved {len(hist)} records")
            print(hist.head(1))
        else:
            print("FAILURE: Returned empty or None")
    except Exception as e:
        print(f"ERROR in stock_zh_a_hist: {e}")

    # 3. Test stock_zh_a_spot_em (Alternative for Info)
    try:
        print("\n3. Testing stock_zh_a_spot_em (Alternative)...")
        start_time = time.time()
        spot = ak.stock_zh_a_spot_em()
        duration = time.time() - start_time
        print(f"Duration: {duration:.2f}s")
        if spot is not None and not spot.empty:
            target = spot[spot['代码'] == symbol]
            if not target.empty:
                print(f"SUCCESS: Found {symbol} in spot data")
                print(target)
            else:
                print(f"FAILURE: {symbol} not found in spot data")
        else:
            print("FAILURE: Spot data empty")
    except Exception as e:
        print(f"ERROR in stock_zh_a_spot_em: {e}")

if __name__ == "__main__":
    test_akshare_600089()
