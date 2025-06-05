
import json
import requests
import yfinance as yf

def load_symbols():
    try:
        response = requests.get("http://localhost:3600/api/trading/symbols", timeout=5)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    with open("symbols_config.json", "r") as f:
        return json.load(f)

def map_yf_symbol(mt5_symbol):
    overrides = {
        "XAUUSD": "GC=F",
        "BTCUSD": "BTC-USD",
        "USDJPY": "USDJPY=X",
        "EURUSD": "EURUSD=X",
        "USOIL": "CL=F",
        "NZDCAD": "NZDCAD=X"
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
