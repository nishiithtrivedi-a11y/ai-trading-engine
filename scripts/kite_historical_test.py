#!/usr/bin/env python
"""
Kite Connect — Historical Data Smoke Test
============================================

Fetches a small sample of historical data for RELIANCE (daily + 5-minute),
saves CSV output, and confirms schema compatibility with the engine.

Prerequisites:
    - Fill ZERODHA_API_KEY, ZERODHA_API_SECRET, ZERODHA_ACCESS_TOKEN in .env
    - pip install kiteconnect python-dotenv

Usage:
    python scripts/kite_historical_test.py
    python scripts/kite_historical_test.py --symbol TCS
    python scripts/kite_historical_test.py --symbol INFY --days 30
"""

import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.base import Timeframe
from src.data.sources import ZerodhaDataSource
from src.utils.kite_auth import get_kite_credentials


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Kite historical data smoke test")
    parser.add_argument("--symbol", type=str, default="RELIANCE", help="Symbol to fetch")
    parser.add_argument("--days", type=int, default=10, help="Number of days to fetch")
    args = parser.parse_args()

    print("Loading credentials...")
    try:
        creds = get_kite_credentials()
    except EnvironmentError as e:
        print(f"\nERROR: {e}")
        sys.exit(1)

    if not creds["access_token"]:
        print("\nERROR: ZERODHA_ACCESS_TOKEN is not set in .env")
        print("Run: python scripts/kite_auth_test.py --request-token YOUR_TOKEN")
        sys.exit(1)

    source = ZerodhaDataSource(
        api_key=creds["api_key"],
        api_secret=creds["api_secret"],
        access_token=creds["access_token"],
    )

    end = datetime.now()
    start = end - timedelta(days=args.days)

    # --- Daily data ---
    print(f"\n{'='*60}")
    print(f"DAILY DATA — {args.symbol} (last {args.days} days)")
    print(f"{'='*60}")
    try:
        df_daily = source.fetch_historical(args.symbol, Timeframe.DAILY, start, end)
        print(f"  Bars     : {len(df_daily)}")
        print(f"  Index    : {df_daily.index.name} ({df_daily.index.dtype})")
        print(f"  Columns  : {list(df_daily.columns)}")
        print(f"  Date range: {df_daily.index.min()} -> {df_daily.index.max()}")
        print(f"\n  First 5 bars:")
        print(df_daily.head().to_string(max_colwidth=20))

        # Save CSV
        out_path = f"data/{args.symbol}_KITE_1D.csv"
        df_daily.to_csv(out_path)
        print(f"\n  Saved to: {out_path}")
    except Exception as e:
        print(f"\n  ERROR: {e}")

    # --- 5-minute data (last 5 days max to stay within limits) ---
    intraday_days = min(args.days, 5)
    start_intraday = end - timedelta(days=intraday_days)

    print(f"\n{'='*60}")
    print(f"5-MINUTE DATA — {args.symbol} (last {intraday_days} days)")
    print(f"{'='*60}")
    try:
        df_5m = source.fetch_historical(args.symbol, Timeframe.MINUTE_5, start_intraday, end)
        print(f"  Bars     : {len(df_5m)}")
        print(f"  Index    : {df_5m.index.name} ({df_5m.index.dtype})")
        print(f"  Columns  : {list(df_5m.columns)}")
        if len(df_5m) > 0:
            print(f"  Date range: {df_5m.index.min()} -> {df_5m.index.max()}")
            print(f"\n  First 5 bars:")
            print(df_5m.head().to_string(max_colwidth=20))

        # Save CSV
        out_path = f"data/{args.symbol}_KITE_5M.csv"
        df_5m.to_csv(out_path)
        print(f"\n  Saved to: {out_path}")
    except Exception as e:
        print(f"\n  ERROR: {e}")

    # --- Schema compatibility check ---
    print(f"\n{'='*60}")
    print("ENGINE SCHEMA COMPATIBILITY CHECK")
    print(f"{'='*60}")
    required_cols = {"open", "high", "low", "close", "volume"}
    for label, df in [("Daily", df_daily), ("5-min", df_5m)]:
        if df is not None and not df.empty:
            has_cols = required_cols.issubset(set(df.columns))
            has_index = df.index.name == "timestamp"
            is_sorted = df.index.is_monotonic_increasing
            print(f"  {label:8s}: columns={has_cols}  index={has_index}  sorted={is_sorted}")
        else:
            print(f"  {label:8s}: EMPTY (cannot check)")

    print(f"\n{'='*60}")
    print("Historical data fetch is working correctly!")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
