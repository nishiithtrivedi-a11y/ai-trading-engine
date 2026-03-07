from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

import pandas as pd


DEFAULT_NIFTY_50 = [
    "ADANIENT.NS",
    "ADANIPORTS.NS",
    "APOLLOHOSP.NS",
    "ASIANPAINT.NS",
    "AXISBANK.NS",
    "BAJAJ-AUTO.NS",
    "BAJAJFINSV.NS",
    "BAJFINANCE.NS",
    "BEL.NS",
    "BHARTIARTL.NS",
    "BPCL.NS",
    "BRITANNIA.NS",
    "CIPLA.NS",
    "COALINDIA.NS",
    "DRREDDY.NS",
    "EICHERMOT.NS",
    "ETERNAL.NS",
    "GRASIM.NS",
    "HCLTECH.NS",
    "HDFC.NS",
    "HDFCBANK.NS",
    "HDFCLIFE.NS",
    "HEROMOTOCO.NS",
    "HINDALCO.NS",
    "HINDUNILVR.NS",
    "ICICIBANK.NS",
    "INDUSINDBK.NS",
    "INFY.NS",
    "ITC.NS",
    "JIOFIN.NS",
    "JSWSTEEL.NS",
    "KOTAKBANK.NS",
    "LT.NS",
    "M&M.NS",
    "MARUTI.NS",
    "NESTLEIND.NS",
    "NTPC.NS",
    "ONGC.NS",
    "POWERGRID.NS",
    "RELIANCE.NS",
    "SBILIFE.NS",
    "SBIN.NS",
    "SHRIRAMFIN.NS",
    "SUNPHARMA.NS",
    "TATACONSUM.NS",
    "TATAMOTORS.NS",
    "TATASTEEL.NS",
    "TCS.NS",
    "TECHM.NS",
    "TITAN.NS",
    "TRENT.NS",
    "ULTRACEMCO.NS",
    "WIPRO.NS",
]

DEFAULT_NIFTY_BANK = [
    "AUBANK.NS",
    "AXISBANK.NS",
    "BANDHANBNK.NS",
    "BANKBARODA.NS",
    "FEDERALBNK.NS",
    "HDFCBANK.NS",
    "ICICIBANK.NS",
    "IDFCFIRSTB.NS",
    "INDUSINDBK.NS",
    "KOTAKBANK.NS",
    "PNB.NS",
    "SBIN.NS",
]

DEFAULT_NIFTY_NEXT_50 = [
    "ABB.NS",
    "ADANIENSOL.NS",
    "ADANIGREEN.NS",
    "AMBUJACEM.NS",
    "BAJAJHLDNG.NS",
    "BOSCHLTD.NS",
    "CANBK.NS",
    "CGPOWER.NS",
    "CHOLAFIN.NS",
    "DABUR.NS",
    "DIVISLAB.NS",
    "DLF.NS",
    "DMART.NS",
    "GAIL.NS",
    "GODREJCP.NS",
    "HAL.NS",
    "HAVELLS.NS",
    "ICICIGI.NS",
    "ICICIPRULI.NS",
    "INDIGO.NS",
    "INDUSTOWER.NS",
    "IRCTC.NS",
    "JINDALSTEL.NS",
    "LICI.NS",
    "LODHA.NS",
    "MCDOWELL-N.NS",
    "NAUKRI.NS",
    "NMDC.NS",
    "PAYTM.NS",
    "PIDILITIND.NS",
    "PFC.NS",
    "PIIND.NS",
    "PNBHOUSING.NS",
    "RECLTD.NS",
    "SBICARD.NS",
    "SIEMENS.NS",
    "SRF.NS",
    "TORNTPHARM.NS",
    "TVSMOTOR.NS",
    "UNITDSPR.NS",
    "VEDL.NS",
    "VBL.NS",
    "ZYDUSLIFE.NS",
]


@dataclass(frozen=True)
class UniverseConfig:
    exchange_suffix: str = ".NS"
    deduplicate: bool = True
    sort_symbols: bool = True
    uppercase: bool = True


class NSEUniverseError(Exception):
    """Raised when universe loading or validation fails."""


class NSEUniverseLoader:
    """
    Offline-first universe loader for Indian equities.

    Supports:
    - built-in placeholder universes
    - loading custom universes from CSV
    - normalizing symbols into Yahoo/NSE style, e.g. RELIANCE.NS

    Future extensions:
    - NSE scraping
    - Zerodha instrument dump mapping
    - Upstox instrument mapping
    """

    def __init__(self, config: UniverseConfig | None = None) -> None:
        self.config = config or UniverseConfig()

    def get_nifty50(self) -> List[str]:
        return self._finalize(DEFAULT_NIFTY_50)

    def get_banknifty_constituents(self) -> List[str]:
        return self._finalize(DEFAULT_NIFTY_BANK)

    def get_nifty_next_50(self) -> List[str]:
        return self._finalize(DEFAULT_NIFTY_NEXT_50)

    def get_custom_universe(self, file_path: str | Path) -> List[str]:
        path = Path(file_path)
        if not path.exists():
            raise NSEUniverseError(f"Universe file not found: {path}")

        try:
            df = pd.read_csv(path)
        except Exception as exc:
            raise NSEUniverseError(f"Failed to read universe file {path}: {exc}") from exc

        if df.empty:
            raise NSEUniverseError(f"Universe file is empty: {path}")

        symbol_col = self._detect_symbol_column(df.columns)
        if symbol_col is None:
            raise NSEUniverseError(
                "Universe CSV must contain one of these columns: "
                "symbol, ticker, tradingsymbol, instrument, security"
            )

        raw_symbols = df[symbol_col].dropna().astype(str).tolist()
        if not raw_symbols:
            raise NSEUniverseError(f"No valid symbols found in file: {path}")

        return self._finalize(raw_symbols)

    def get_universe(self, universe_name: str, file_path: str | Path | None = None) -> List[str]:
        name = universe_name.strip().lower()

        if name in {"nifty50", "nifty_50"}:
            return self.get_nifty50()
        if name in {"banknifty", "nifty_bank", "niftybank"}:
            return self.get_banknifty_constituents()
        if name in {"niftynext50", "nifty_next_50", "next50"}:
            return self.get_nifty_next_50()
        if name in {"custom", "csv"}:
            if file_path is None:
                raise NSEUniverseError("file_path is required for custom/csv universe loading.")
            return self.get_custom_universe(file_path)

        raise NSEUniverseError(f"Unknown universe name: {universe_name}")

    def normalize_symbol(self, symbol: str) -> str:
        if symbol is None:
            raise NSEUniverseError("Symbol cannot be None.")

        clean = symbol.strip()
        if not clean:
            raise NSEUniverseError("Empty symbol is not allowed.")

        if self.config.uppercase:
            clean = clean.upper()

        if clean.endswith(self.config.exchange_suffix.upper()):
            return clean

        if "." in clean:
            return clean

        return f"{clean}{self.config.exchange_suffix}"

    def normalize_symbols(self, symbols: Sequence[str]) -> List[str]:
        return self._finalize(symbols)

    def _finalize(self, symbols: Iterable[str]) -> List[str]:
        normalized = [self.normalize_symbol(sym) for sym in symbols if str(sym).strip()]

        if self.config.deduplicate:
            seen = set()
            deduped: List[str] = []
            for symbol in normalized:
                if symbol not in seen:
                    seen.add(symbol)
                    deduped.append(symbol)
            normalized = deduped

        if self.config.sort_symbols:
            normalized = sorted(normalized)

        return normalized

    @staticmethod
    def _detect_symbol_column(columns: Sequence[str]) -> str | None:
        normalized_map = {str(col).strip().lower(): col for col in columns}
        candidates = ["symbol", "ticker", "tradingsymbol", "instrument", "security"]
        for candidate in candidates:
            if candidate in normalized_map:
                return normalized_map[candidate]
        return None


class ZerodhaUniverseSource:
    """
    Placeholder for future Zerodha instrument/universe integration.
    """

    def fetch_universe(self, universe_name: str) -> List[str]:
        raise NotImplementedError(
            "ZerodhaUniverseSource is a placeholder. API integration will be added later."
        )


class UpstoxUniverseSource:
    """
    Placeholder for future Upstox instrument/universe integration.
    """

    def fetch_universe(self, universe_name: str) -> List[str]:
        raise NotImplementedError(
            "UpstoxUniverseSource is a placeholder. API integration will be added later."
        )