import json
import yfinance as yf

def load_symbols():
    try:
        with open("data/symbols_config.json", "r") as f:
            return json.load(f)
    except:
        return []

def map_yf_symbol(mt5_symbol):
    overrides = {
        "XAUUSD": "GC=F", "BTCUSD": "BTC-USD", "USDJPY": "USDJPY=X",
        "EURUSD": "EURUSD=X", "USOIL": "CL=F", "NZDCAD": "NZDCAD=X"
    }
    return overrides.get(mt5_symbol, mt5_symbol + "=X")

def fetch_price(symbol):
    try:
        data = yf.Ticker(symbol)
        hist = data.history(period="1d")
        if not hist.empty:
            return round(float(hist["Close"].iloc[-1]), 5)
    except:
        return None