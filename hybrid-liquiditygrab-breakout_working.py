import os
import time
import requests
import yfinance as yf
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "TradeSignals")
GOOGLE_CRED_FILE = os.getenv("GOOGLE_CRED_FILE", "google-credentials.json")
ACCOUNT_BALANCE = float(os.getenv("ACCOUNT_BALANCE", 1000))
RISK_PERCENT = float(os.getenv("RISK_PERCENT", 1.0))  # 1% default

SYMBOLS = {
    "EUR/USD": "EURUSD=X",
    "BTC/USD": "BTC-USD",
    "XAU/USD": "GC=F",
    "USD/JPY": "JPY=X"
}

INTERVAL = "1h"
PERIOD = "7d"
POLL_INTERVAL = 900  # 15 minutes


def send_telegram_message(message):
    print(message)
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")


def append_to_google_sheet(label, signal_type, entry_price, sl, tp, lot, timestamp):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CRED_FILE, scope)
        client = gspread.authorize(creds)
        sheet = client.open(GOOGLE_SHEET_NAME).worksheet("Signals")
        sheet.append_row([
            label, signal_type, f"{entry_price:.5f}", f"{sl:.5f}", f"{tp:.5f}", f"{lot:.2f}", timestamp.strftime('%Y-%m-%d %H:%M:%S')
        ])
        print(f"✅ Sent to Google Sheet: {label} | {signal_type} | {entry_price}")
    except Exception as e:
        print(f"❌ Failed to write to sheet: {e}")


def calculate_trade_details(entry, direction, sl_buffer=0.0010, tp_buffer=0.0020):
    if direction == "SELL LIMIT":
        sl = entry + sl_buffer
        tp = entry - tp_buffer
    else:
        sl = entry - sl_buffer
        tp = entry + tp_buffer

    risk_amount = ACCOUNT_BALANCE * (RISK_PERCENT / 100)
    pip_value = abs(entry - sl)
    lot_size = risk_amount / pip_value if pip_value != 0 else 0.01

    return sl, tp, round(min(lot_size, 10), 2)  # cap lot size for safety


def detect_fvg(df):
    fvg_signals = []
    for i in range(2, len(df)):
        prev_high = df.iloc[i - 2]['High'].item()
        prev_low = df.iloc[i - 2]['Low'].item()
        curr_open = df.iloc[i]['Open'].item()

        if pd.notna(prev_high) and pd.notna(prev_low) and pd.notna(curr_open):
            if curr_open > prev_high:
                fvg_signals.append((df.index[i], 'bearish', prev_high, curr_open))
            elif curr_open < prev_low:
                fvg_signals.append((df.index[i], 'bullish', curr_open, prev_low))
    return fvg_signals


def detect_liquidity(df):
    liquidity_signals = []
    df = df.copy()
    df['high_roll'] = df['High'].rolling(window=20).max()
    df['low_roll'] = df['Low'].rolling(window=20).min()
    df['vol_mean'] = df['Volume'].rolling(20).mean()

    for i in range(20, len(df)):
        ts = df.index[i]
        high_roll = df['high_roll'].iloc[i - 1].item()
        low_roll = df['low_roll'].iloc[i - 1].item()
        close = df['Close'].iloc[i].item()
        high = df['High'].iloc[i].item()
        low = df['Low'].iloc[i].item()
        volume = df['Volume'].iloc[i].item()
        vol_avg = df['vol_mean'].iloc[i].item()

        if pd.notna(high_roll) and pd.notna(low_roll):
            if (low < low_roll) and (close > low_roll):
                liquidity_signals.append((ts, 'Liquidity Grab (Bull)', low))
            elif (high > high_roll) and (close < high_roll):
                liquidity_signals.append((ts, 'Liquidity Grab (Bear)', high))

            if (close > high_roll) and (volume > 1.5 * vol_avg):
                liquidity_signals.append((ts, 'Breakout (Bull)', close))
            elif (close < low_roll) and (volume > 1.5 * vol_avg):
                liquidity_signals.append((ts, 'Breakout (Bear)', close))

    return liquidity_signals


def main():
    print("\U0001F4C8 Hybrid Strategy Bot Running")
    while True:
        try:
            for label, ticker in SYMBOLS.items():
                df = yf.download(ticker, interval=INTERVAL, period=PERIOD, progress=False)
                if df.empty:
                    print(f"No data for {label}")
                    continue

                fvg_signals = detect_fvg(df)
                liquidity_signals = detect_liquidity(df)

                if not fvg_signals and not liquidity_signals:
                    print(f"No valid signals for {label}")
                    continue

                message = f"\n\U0001F4CA *Signals for {label}*\n"

                if fvg_signals:
                    ts, direction, start, end = fvg_signals[-1]
                    entry = (start + end) / 2
                    signal_type = "SELL LIMIT" if direction == "bearish" else "BUY LIMIT"
                    sl, tp, lot = calculate_trade_details(entry, signal_type)
                    message += (
                        f"\n\U0001F538 *FVG Detected*\n"
                        f"Type: `{signal_type}`\n"
                        f"Entry: `{entry:.5f}`\n"
                        f"SL: `{sl:.5f}` | TP: `{tp:.5f}`\n"
                        f"Lot: `{lot}`\n"
                        f"Time: `{ts.strftime('%Y-%m-%d %H:%M:%S')}`\n"
                    )
                    append_to_google_sheet(label, signal_type, entry, sl, tp, lot, ts)

                for ts, sig_type, price in liquidity_signals[-3:]:
                    sl, tp, lot = calculate_trade_details(price, "BUY LIMIT" if "Bull" in sig_type else "SELL LIMIT")
                    message += (
                        f"\n\U0001F539 *{sig_type}*\n"
                        f"Price: `{price:.5f}`\n"
                        f"SL: `{sl:.5f}` | TP: `{tp:.5f}`\n"
                        f"Lot: `{lot}`\n"
                        f"Time: `{ts.strftime('%Y-%m-%d %H:%M:%S')}`\n"
                    )
                    append_to_google_sheet(label, sig_type, price, sl, tp, lot, ts)

                message += (
                    "\n\U0001F4B0 *Support the bot:*\n"
                    "BTC: `your-btc-address`\n"
                    "ETH: `your-eth-address`"
                )
                send_telegram_message(message)
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
