#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

DEFAULT_SYMBOLS = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
    "SBIN", "LT", "AXISBANK", "KOTAKBANK", "HINDUNILVR",
    "ITC", "BHARTIARTL", "BAJFINANCE", "ASIANPAINT", "MARUTI",
    "SUNPHARMA", "TATASTEEL", "ULTRACEMCO", "WIPRO", "NESTLEIND",
]
DEFAULT_INTERVALS = ["1d", "1h", "15m", "5m"]

def normalize_symbol(symbol: str) -> str:
    clean = symbol.strip().upper()
    if not clean:
        raise ValueError("Empty symbol is not allowed.")
    if clean.endswith(".NS") or "." in clean:
        return clean
    return f"{clean}.NS"

def clean_filename_symbol(symbol: str) -> str:
    return symbol.replace(".NS", "")

def load_symbols_from_csv(path: str | Path) -> list[str]:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Universe file not found: {file_path}")
    df = pd.read_csv(file_path)
    if df.empty:
        raise ValueError(f"Universe file is empty: {file_path}")
    columns_map = {str(c).strip().lower(): c for c in df.columns}
    for candidate in ["symbol", "ticker", "tradingsymbol", "instrument", "security"]:
        if candidate in columns_map:
            col = columns_map[candidate]
            return [normalize_symbol(v) for v in df[col].dropna().astype(str).tolist() if str(v).strip()]
    raise ValueError("Universe CSV must contain one of: symbol, ticker, tradingsymbol, instrument, security")

def interval_to_suffix(interval: str) -> str:
    mapping = {
        "1d": "1D", "5d": "5D", "1wk": "1W", "1mo": "1MO", "3mo": "3MO",
        "1h": "1H", "60m": "1H", "90m": "90M", "30m": "30M",
        "15m": "15M", "5m": "5M", "2m": "2M", "1m": "1M",
    }
    return mapping.get(interval, interval.upper())

def is_intraday(interval: str) -> bool:
    return interval in {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h"}

def download_one(symbol: str, interval: str, output_dir: Path, start: str | None, end: str | None, intraday_period: str, auto_adjust: bool) -> Path | None:
    ticker = normalize_symbol(symbol)
    suffix = interval_to_suffix(interval)
    output_path = output_dir / f"{clean_filename_symbol(ticker)}_{suffix}.csv"

    kwargs = {"interval": interval, "progress": False, "auto_adjust": auto_adjust, "threads": False}
    if is_intraday(interval):
        kwargs["period"] = intraday_period
    else:
        if start:
            kwargs["start"] = start
        if end:
            kwargs["end"] = end

    df = yf.download(ticker, **kwargs)
    if df is None or df.empty:
        print(f"WARNING: No data returned for {ticker} [{interval}]")
        return None

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]

    df = df.reset_index()
    rename_map = {}
    for col in df.columns:
        low = str(col).strip().lower()
        if low in {"date", "datetime"}:
            rename_map[col] = "timestamp"
        elif low in {"open", "high", "low", "close", "volume"}:
            rename_map[col] = low
    df = df.rename(columns=rename_map)

    required = ["timestamp", "open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Downloaded data missing columns for {ticker} [{interval}]: {missing}")

    df = df[required].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").drop_duplicates(subset=["timestamp"]).reset_index(drop=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Saved {ticker} [{interval}] -> {output_path} ({len(df)} rows)")
    return output_path

def parse_args():
    parser = argparse.ArgumentParser(description="Download Yahoo Finance NSE data into backtesting CSV format.")
    parser.add_argument("--symbols", nargs="*", default=None, help="Raw symbols like RELIANCE TCS INFY")
    parser.add_argument("--universe-file", type=str, default=None, help="CSV with symbol/ticker column")
    parser.add_argument("--intervals", nargs="*", default=DEFAULT_INTERVALS, help="Examples: 1d 1h 15m 5m")
    parser.add_argument("--output-dir", type=str, default="data", help="Where to save CSV files")
    parser.add_argument("--start", type=str, default="2018-01-01", help="Start date for non-intraday downloads")
    parser.add_argument("--end", type=str, default=None, help="End date for non-intraday downloads")
    parser.add_argument("--intraday-period", type=str, default="60d", help="Yahoo period for intraday data, e.g. 30d, 60d")
    parser.add_argument("--daily-only", action="store_true", help="Shortcut: only download 1d")
    parser.add_argument("--auto-adjust", action="store_true", help="Use adjusted OHLC values from Yahoo")
    return parser.parse_args()

def main() -> int:
    args = parse_args()
    if args.universe_file:
        symbols = load_symbols_from_csv(args.universe_file)
    elif args.symbols:
        symbols = [normalize_symbol(s) for s in args.symbols]
    else:
        symbols = [normalize_symbol(s) for s in DEFAULT_SYMBOLS]

    intervals = ["1d"] if args.daily_only else args.intervals
    output_dir = Path(args.output_dir)
    manifest_rows = []

    for symbol in symbols:
        for interval in intervals:
            try:
                saved = download_one(symbol, interval, output_dir, args.start, args.end, args.intraday_period, args.auto_adjust)
                if saved is not None:
                    manifest_rows.append({"symbol": symbol, "interval": interval, "file_path": str(saved)})
            except Exception as exc:
                print(f"ERROR: {symbol} [{interval}] -> {exc}", file=sys.stderr)

    if manifest_rows:
        manifest_path = output_dir / "download_manifest.csv"
        pd.DataFrame(manifest_rows).to_csv(manifest_path, index=False)
        print(f"Manifest saved to: {manifest_path}")
        return 0

    print("No files were downloaded successfully.", file=sys.stderr)
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
