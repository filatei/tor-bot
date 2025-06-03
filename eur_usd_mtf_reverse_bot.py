# eur_usd_mtf_reverse_bot.py
# Detects MTF reversals on EUR/USD using RSI + ATR. Sends Telegram alerts and logs to Google Sheets.

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
SHEET_NAME = "EURUSD_Signals"

# === Bot Configuration ===
SYMBOL = "EURUSD=X"
SUPPORT_ZONE = 1.1415
RESISTANCE_ZONE = 1.1430
RSI_PERIOD = 14
ATR_PERIOD = 14
CHECK_INTERVAL = 60  # seconds
INTERVAL = "15m"
TRADING_HOURS_UTC = list(range(8, 12)) + list(range(13, 17))  # London + NY sessions

# === Convert to scalar safely ===
def to_scalar(x):
    if isinstance(x, (float, int)):
        return x
    if isinstance(x, pd.Series):
        if x.shape[0] >= 1:
            return x.iloc[-1]
        else:
            raise ValueError("Series is empty")
    if isinstance(x, pd.DataFrame):
        if x.shape[1] == 1:
            return x.iloc[-1, 0]
        else:
            raise ValueError("DataFrame has more than one column")
    if hasattr(x, "item"):
        return x.item()
    raise ValueError(f"Cannot convert to scalar: {x} ({type(x)})")

# === Google Sheets Setup ===
def setup_google_sheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CRED_FILE, scope)
    client = gspread.authorize(creds)
    spreadsheet = client.open(SHEET_NAME)

    # Create or get "Signals" sheet
    try:
        sheet1 = spreadsheet.worksheet("Signals")
    except:
        sheet1 = spreadsheet.add_worksheet(title="Signals", rows="1000", cols="10")
        sheet1.append_row(["timestamp", "signal_type", "price", "rsi", "atr"])

    # Create or get "Stats" sheet
    try:
        stats_sheet = spreadsheet.worksheet("Stats")
    except:
        stats_sheet = spreadsheet.add_worksheet(title="Stats", rows="10", cols="2")
        stats_sheet.update("A1", "Metric")
        stats_sheet.update("B1", "Value")
        stats_sheet.update("A2:A5", [
            ["Total Signals"],
            ["Total BUY"],
            ["Total SELL"],
            ["Last Signal Time"]
        ])
        stats_sheet.update("B2", '=COUNTA(Signals!A2:A)')
        stats_sheet.update("B3", '=COUNTIF(Signals!B2:B, "BUY")')
        stats_sheet.update("B4", '=COUNTIF(Signals!B2:B, "SELL")')
        stats_sheet.update("B5", '=INDEX(Signals!A2:A, COUNTA(Signals!A2:A))')

    return sheet1

# === Log to Google Sheet ===
def log_to_google_sheet(sheet, signal_type, price, rsi, atr):
    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    row = [timestamp, signal_type, f"{price:.5f}", f"{rsi:.2f}", f"{atr:.5f}"]
    sheet.append_row(row, value_input_option="USER_ENTERED")

# === Telegram Notification ===
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, data=data)
    except Exception as e:
        print("Telegram error:", e)

# === Check Trading Window ===
def is_trading_hour():
    return datetime.now(timezone.utc).hour in TRADING_HOURS_UTC

# === RSI Calculation ===
def get_rsi(data, period=14):
    delta = data['Close'].diff()
    gain = delta.clip(lower=0).rolling(window=period).mean()
    loss = -delta.clip(upper=0).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi  # Return Series

# === ATR Calculation ===
def get_atr(data, period=14):
    high_low = data['High'] - data['Low']
    high_close = (data['High'] - data['Close'].shift()).abs()
    low_close = (data['Low'] - data['Close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    return atr  # Return Series

# === Bot Execution Loop ===
def main():
    last_signal = None
    sheet = setup_google_sheet()

    while True:
        try:
            if not is_trading_hour():
                print("⏳ Outside trading hours...")
                time.sleep(CHECK_INTERVAL)
                continue

            data = yf.download(SYMBOL, interval=INTERVAL, period="2d", progress=False, auto_adjust=True)

            if data.empty:
                print("⚠️ Data fetch failed")
                time.sleep(CHECK_INTERVAL)
                continue

            close = to_scalar(data['Close'])
            open_price = to_scalar(data['Open'])
            rsi = to_scalar(get_rsi(data))
            atr = to_scalar(get_atr(data))

            # === Trade Signal Logic ===
            signal = None
            signal_type = None

            print(f"[DEBUG] close={close:.5f}, open={open_price:.5f}, rsi={rsi:.2f}, atr={atr:.5f}")

            buy_condition = (33 < rsi < 45) and (close > open_price) and (close <= SUPPORT_ZONE)
            sell_condition = (40 < rsi < 50) and (close < open_price) and (close >= RESISTANCE_ZONE)

            if buy_condition:
                signal_type = "BUY"
                signal = f"🟢 BUY EUR/USD @ {close:.5f}\nRSI: {rsi:.2f} | ATR: {atr:.5f}"

            elif sell_condition:
                signal_type = "SELL"
                signal = f"🔴 SELL EUR/USD @ {close:.5f}\nRSI: {rsi:.2f} | ATR: {atr:.5f}"

            # === Execute Signal ===
            if signal and signal != last_signal:
                send_telegram_message(signal)
                log_to_google_sheet(sheet, signal_type, close, rsi, atr)
                print("✅ Signal sent and logged.")
                last_signal = signal
            else:
                print(f"No new signal | Price: {close:.5f} | RSI: {rsi:.2f}")

        except Exception as e:
            send_telegram_message(f"⚠️ Bot Error: {str(e)}")
            print("Exception:", e)

        time.sleep(CHECK_INTERVAL)

# === Start Bot ===
if __name__ == "__main__":
    main()
