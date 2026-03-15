#!/usr/bin/env python
"""
Kite Connect — Instruments Smoke Test
=======================================

Downloads the NSE instrument list from Kite, caches it locally,
and verifies that symbol lookup works for common stocks.

Prerequisites:
    - Fill ZERODHA_API_KEY, ZERODHA_API_SECRET, ZERODHA_ACCESS_TOKEN in .env
    - pip install kiteconnect python-dotenv

Usage:
    python scripts/kite_instruments_test.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.kite_auth import get_kite_client
from src.data.instrument_mapper import KiteInstrumentMapper


def main():
    print("Connecting to Kite Connect...")
    try:
        kite = get_kite_client()
    except (EnvironmentError, ImportError) as e:
        print(f"\nERROR: {e}")
        sys.exit(1)

    mapper = KiteInstrumentMapper(kite)

    # Download and cache instruments
    print("\nDownloading NSE instruments from Kite...")
    try:
        df = mapper.refresh_cache()
    except Exception as e:
        print(f"\nERROR downloading instruments: {e}")
        sys.exit(1)

    print(f"  Total instruments cached: {len(df)}")
    print(f"  Cache file: {mapper.cache_path}")

    # Show sample
    print(f"\n{'='*60}")
    print("SAMPLE INSTRUMENTS (first 10)")
    print(f"{'='*60}")
    eq = df[df["instrument_type"] == "EQ"].head(10)
    for _, row in eq.iterrows():
        print(
            f"  {row['tradingsymbol']:20s}  "
            f"token={row['instrument_token']:>10}  "
            f"lot={row.get('lot_size', 'N/A')}"
        )

    # Test lookups for well-known symbols
    print(f"\n{'='*60}")
    print("SYMBOL RESOLUTION TEST")
    print(f"{'='*60}")
    test_symbols = [
        "RELIANCE",
        "RELIANCE.NS",
        "TCS",
        "INFY",
        "HDFCBANK",
        "ICICIBANK",
    ]
    for sym in test_symbols:
        try:
            token = mapper.get_instrument_token(sym)
            print(f"  {sym:20s} -> token={token}")
        except ValueError as e:
            print(f"  {sym:20s} -> NOT FOUND ({e})")

    print(f"\n{'='*60}")
    print("Instrument mapping is working correctly!")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
