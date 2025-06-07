#constants.py# app/utils/constants.py

# Symbol mapping from display symbol to Yahoo Finance symbol
YF_SYMBOL_MAP = {
    "BTCUSD": "BTC-USD",
    "EURUSD": "EURUSD=X",
    "USOIL": "CL=F",
    "XAUUSD": "GC=F",
    "NAS100": "^NDX"
}

# Default pip precision by symbol
PIP_PRECISION_MAP = {
    "BTCUSD": 1.0,
    "EURUSD": 0.0001,
    "USOIL": 0.01,
    "XAUUSD": 0.1,
    "NAS100": 1.0
}

# Default account settings
DEFAULT_SETTINGS = {
    "account_size": 10000.0,
    "lot_size": 0.10,
    "risk_percent": 1.0,
    "entry_price": 1.1400,
    "rr_choice": "1:2",
    "selected_symbol": "BTCUSD"
}