# multi_instrument_reverse_bot.py
# Logs reversal signals for any instrument to a single worksheet in a Google Sheet
# Uses RSI, ATR, and dynamic support/resistance from recent price action

import os
import time
import requests
import yfinance as yf
from datetime import datetime, timezone
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd

# === Load .env Variables ===
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GOOGLE_CRED_FILE = os.getenv("GOOGLE_CRED_FILE", "google-credentials.json")

# === Config ===
SPREADSHEET_NAME = "trade_signals"
WORKSHEET_NAME = "Signals"
SYMBOLS = ["XAUUSD=X", "GBPUSD=X"]  # add more as needed
RSI_PERIOD = 14
ATR_PERIOD = 14
INTERVAL = "15m"
CHECK_INTERVAL = 60  # seconds
TRADING_HOURS_UTC = list(range(8, 12)) + list(range(13, 17))  # London + NY
ZONE_WINDOW = 48  # candles for support/resistance

# === Google Sheets Setup ===
def setup_google_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CRED_FILE, scope)
    client = gspread.authorize(creds)
    spreadsheet = client.open(SPREADSHEET_NAME)

    try:
        sheet = spreadsheet.worksheet(WORKSHEET_NAME)
    except gspread.exceptions.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title=WORKSHEET_NAME, rows="1000", cols="10")
        sheet.append_row(["timestamp", "symbol", "signal_type", "price", "rsi", "atr", "support", "resistance"])
    
    return sheet

# === Telegram Alert ===
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message})
    except Exception as e:
        print("Telegram error:", e)

# === Technical Indicators ===
def get_rsi(data, period=14):
    delta = data['Close'].diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def get_atr(data, period=14):
    high_low = data['High'] - data['Low']
    high_close = (data['High'] - data['Close'].shift()).abs()
    low_close = (data['Low'] - data['Close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    return atr

def get_dynamic_zones(data, window=48):
    recent = data.tail(window)
    return recent['Low'].min(), recent['High'].max()

def to_scalar(x):
    if isinstance(x, (float, int)):
        return x
    if isinstance(x, pd.Series) and not x.empty:
        return x.iloc[-1]
    if isinstance(x, pd.DataFrame) and x.shape[1] == 1:
        return x.iloc[-1, 0]
    if hasattr(x, "item"):
        return x.item()
    raise ValueError(f"Cannot convert to scalar: {x} ({type(x)})")

# === Signal Detection ===
def detect_signal(symbol, sheet):
    data = yf.download(symbol, interval=INTERVAL, period="3d", progress=False, auto_adjust=True)

    if data.empty or len(data) < ZONE_WINDOW:
        print(f"⚠️ Skipping {symbol} - insufficient data")
        return

    close = to_scalar(data['Close'])
    open_price = to_scalar(data['Open'])
    rsi = to_scalar(get_rsi(data, RSI_PERIOD))
    atr = to_scalar(get_atr(data, ATR_PERIOD))
    support, resistance = get_dynamic_zones(data, ZONE_WINDOW)

    print(f"[{symbol}] Price: {close:.2f}, RSI: {rsi:.2f}, Support: {support:.2f}, Resistance: {resistance:.2f}")

    buy_condition = (33 < rsi < 45) and (close > open_price) and (close <= support)
    sell_condition = (40 < rsi < 50) and (close < open_price) and (close >= resistance)

    signal_type = None
    message = None

    if buy_condition:
        signal_type = "BUY"
        message = f"🟢 BUY {symbol.replace('=X','')} @ {close:.2f}\nRSI: {rsi:.2f}, ATR: {atr:.2f}, Support: {support:.2f}"
    elif sell_condition:
        signal_type = "SELL"
        message = f"🔴 SELL {symbol.replace('=X','')} @ {close:.2f}\nRSI: {rsi:.2f}, ATR: {atr:.2f}, Resistance: {resistance:.2f}"

    if signal_type:
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        sheet.append_row([
            timestamp, symbol.replace("=X", ""), signal_type,
            f"{close:.2f}", f"{rsi:.2f}", f"{atr:.2f}",
            f"{support:.2f}", f"{resistance:.2f}"
        ], value_input_option="USER_ENTERED")
        send_telegram_message(message)
        print(f"✅ {symbol}: {signal_type} signal logged and sent.")
    else:
        print(f"⏸️ No signal for {symbol}")

# === Entry Point ===
def main():
    sheet = setup_google_sheet()
    while True:
        if datetime.now(timezone.utc).hour not in TRADING_HOURS_UTC:
            print("⏳ Outside trading hours...")
            time.sleep(CHECK_INTERVAL)
            continue
        for symbol in SYMBOLS:
            try:
                detect_signal(symbol, sheet)
            except Exception as e:
                print(f"❌ Error processing {symbol}: {e}")
                send_telegram_message(f"⚠️ Error on {symbol}: {str(e)}")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()