"""Supported market symbols and Yahoo Finance data access."""

import pandas as pd
import yfinance as yf
from curl_cffi.requests.exceptions import RequestException
from yfinance.exceptions import YFException

from stock_dashboard.analytics import normalize_price_history

TICKERS = {
    "Apple (AAPL)": "AAPL",
    "Microsoft (MSFT)": "MSFT",
    "Alphabet (GOOGL)": "GOOGL",
    "Amazon (AMZN)": "AMZN",
    "Tesla (TSLA)": "TSLA",
    "Reliance Industries (RELIANCE.NS)": "RELIANCE.NS",
    "Tata Consultancy Services (TCS.NS)": "TCS.NS",
    "Infosys (INFY.NS)": "INFY.NS",
    "HDFC Bank (HDFCBANK.NS)": "HDFCBANK.NS",
    "ICICI Bank (ICICIBANK.NS)": "ICICIBANK.NS",
}

SUPPORTED_SYMBOLS = frozenset(TICKERS.values())


def load_stock_history(
    symbol: str, period: str = "5y", start: str | None = None
) -> pd.DataFrame:
    """Fetch and normalize daily adjusted prices for a supported ticker."""
    if symbol not in SUPPORTED_SYMBOLS:
        raise ValueError(f"Unsupported stock symbol: {symbol}")

    request = {
        "auto_adjust": True,
        "progress": False,
        "timeout": 15,
    }
    if start is not None:
        request["start"] = start
    else:
        request["period"] = period
    downloaded = yf.download(symbol, **request)
    return normalize_price_history(downloaded, symbol)


__all__ = ["TICKERS", "RequestException", "YFException", "load_stock_history"]
