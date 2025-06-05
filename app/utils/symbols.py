# app/utils/symbols.py

import json
import os
import yfinance as yf

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "symbols_config.json")

def load_symbols():
    """Load symbol metadata from symbols_config.json"""
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"Missing config file: {CONFIG_PATH}")
    
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def map_yf_symbol(mt5_symbol):
    """Map a MetaTrader symbol to its Yahoo Finance equivalent"""
    overrides = {
        "XAUUSD": "GC=F",
        "XAGUSD": "SI=F",
        "USOIL": "CL=F",
        "WTI": "CL=F",
        "BRENT": "BZ=F",
        "BTCUSD": "BTC-USD",
        "ETHUSD": "ETH-USD",
        "BNBUSD": "BNB-USD",
        "USDJPY": "USDJPY=X",
        "EURUSD": "EURUSD=X",
        "GBPUSD": "GBPUSD=X",
        "NZDCAD": "NZDCAD=X",
    }
    return overrides.get(mt5_symbol.upper(), f"{mt5_symbol.upper()}=X")

def fetch_price(yf_symbol):
    """Fetch latest close price for a given Yahoo Finance symbol"""
    try:
        data = yf.Ticker(yf_symbol)
        hist = data.history(period="1d")
        if not hist.empty:
            return round(float(hist["Close"].iloc[-1]), 5)
    except Exception as e:
        print(f"[Error] fetch_price({yf_symbol}): {e}")
    return None