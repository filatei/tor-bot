"""
multi_symbol_bot.py

This bot scans broker-specific forex and crypto pairs via MetaApi to detect trade signals
based on multi-timeframe RSI confirmation, ATR volatility filter, and dynamic support/resistance.
If a signal is generated, it sends a Telegram alert and logs it to Google Sheets.

Supported: EUR/USD, BTC/USD, Gold, USD/CHF (symbols auto-mapped via broker's symbol list)
"""

import os
import time
import asyncio
import requests
import pandas as pd
from datetime import datetime, timezone
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from metaapi_cloud_sdk import MetaApi

# === Load environment variables ===
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GOOGLE_CRED_FILE = os.getenv("GOOGLE_CRED_FILE")
SHEET_NAME = "Market_Signals"
META_API_TOKEN = os.getenv("META_API_ACCESS_TOKEN")
ACCOUNT_ID = os.getenv("META_API_ACCOUNT_ID")

# === Strategy Settings ===
RSI_PERIOD = 14
ATR_PERIOD = 14
ZONE_WINDOW = 20
INTERVAL_FAST = "15m"
INTERVAL_SLOW = "1h"
TRADING_HOURS_UTC = list(range(7, 17))  # 7am–4pm UTC
CHECK_INTERVAL = 60  # seconds

TARGET_NAMES = {
    "EUR/USD": ["eurusd", "eur/usd"],
    "BTC/USD": ["btcusd", "btc/usd"],
    "Gold": ["xauusd", "gold"],
    "USD/CHF": ["usdchf", "usd/chf"]
}

def to_scalar(x):
    if isinstance(x, (float, int)):
        return x
    if isinstance(x, pd.Series) and not x.empty:
        return x.iloc[-1]
    if isinstance(x, pd.DataFrame) and x.shape[1] == 1:
        return x.iloc[-1, 0]
    raise ValueError(f"Cannot convert to scalar: {x} ({type(x)})")

def get_rsi(df, period=14):
    delta = df["Close"].diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def get_atr(df, period=14):
    hl = df["High"] - df["Low"]
    hc = (df["High"] - df["Close"].shift()).abs()
    lc = (df["Low"] - df["Close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def calculate_zones(df, window=20):
    support = df["Low"].rolling(window).min().iloc[-1]
    resistance = df["High"].rolling(window).max().iloc[-1]
    return support, resistance

def send_telegram(message):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": message}
        )
    except Exception as e:
        print("Telegram Error:", e)

def setup_google_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CRED_FILE, scope)
    client = gspread.authorize(creds)
    sheet = client.open(SHEET_NAME)
    try:
        ws = sheet.worksheet("Signals")
    except:
        ws = sheet.add_worksheet("Signals", rows="1000", cols="10")
        ws.append_row(["timestamp", "symbol", "signal", "price", "rsi_15m", "rsi_1h", "atr"])
    return ws

def is_trading_time():
    return datetime.now(timezone.utc).hour in TRADING_HOURS_UTC

async def fetch_candles(account, symbol, timeframe, count=100):
    try:
        candles = await account.get_candles(symbol, timeframe, count)
        if not candles:
            return pd.DataFrame()

        df = pd.DataFrame(candles)
        df.rename(columns={
            'time': 'Time',
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Close',
            'volume': 'Volume'
        }, inplace=True)
        df['Time'] = pd.to_datetime(df['Time'])
        return df
    except Exception as e:
        print(f"Error fetching candles for {symbol} ({timeframe}): {e}")
        return pd.DataFrame()

async def find_broker_symbols(account):
    symbols = await account.get_symbols()
    resolved = {}

    for target, aliases in TARGET_NAMES.items():
        for sym in symbols:
            broker_sym = sym['symbol'].lower()
            if any(alias in broker_sym for alias in aliases):
                resolved[target] = sym['symbol']
                break

    return resolved

async def main():
    metaapi = MetaApi(META_API_TOKEN)
    account = await metaapi.metatrader_account_api.get_account(ACCOUNT_ID)
    await account.wait_connected()

    connection = account.get_rpc_connection()
    await connection.connect()  # ✅ Add this to initialize connection

    sheet = setup_google_sheet()
    symbol_map = await find_broker_symbols(connection)

    if not symbol_map:
        print("❌ No symbols resolved.")
        return

    last_signals = {}

    while True:
        try:
            if not is_trading_time():
                print("⏳ Outside trading hours...")
                await asyncio.sleep(CHECK_INTERVAL)
                continue

            for label, broker_symbol in symbol_map.items():
                print(f"🔍 Checking {label} ({broker_symbol})...")

                df_15m = await fetch_candles(connection, broker_symbol, INTERVAL_FAST)
                df_1h = await fetch_candles(connection, broker_symbol, INTERVAL_SLOW)

                if df_15m.empty or df_1h.empty:
                    print(f"⚠️ No data for {label}")
                    continue

                try:
                    support, resistance = calculate_zones(df_15m)
                    rsi_15m = to_scalar(get_rsi(df_15m))
                    rsi_1h = to_scalar(get_rsi(df_1h))
                    atr = to_scalar(get_atr(df_15m))
                    close = to_scalar(df_15m["Close"])
                    open_price = to_scalar(df_15m["Open"])
                except Exception as e:
                    print(f"⚠️ Data error for {label}: {e}")
                    continue

                signal_type = None
                if (30 < rsi_15m < 45) and (close > open_price) and (close <= support) and (rsi_1h < 50):
                    signal_type = "BUY"
                elif (55 > rsi_15m > 40) and (close < open_price) and (close >= resistance) and (rsi_1h > 50):
                    signal_type = "SELL"

                if signal_type and last_signals.get(label) != signal_type:
                    msg = (
                        f"{'🟢' if signal_type == 'BUY' else '🔴'} {signal_type} {label} @ {close:.5f}\n"
                        f"RSI 15m: {rsi_15m:.1f} | RSI 1h: {rsi_1h:.1f} | ATR: {atr:.5f}"
                    )
                    print("✅", msg)
                    send_telegram(msg)
                    sheet.append_row([
                        datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                        label, signal_type, f"{close:.5f}",
                        f"{rsi_15m:.2f}", f"{rsi_1h:.2f}", f"{atr:.5f}"
                    ])
                    last_signals[label] = signal_type
                else:
                    print(f"📉 No signal | {label} | Close={close:.5f} RSI15m={rsi_15m:.1f} RSI1h={rsi_1h:.1f}")

        except Exception as e:
            print("🚨 Error:", e)
            send_telegram(f"⚠️ Bot error: {str(e)}")

        await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())