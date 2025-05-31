import os
import time
import requests
import yfinance as yf
import pandas as pd
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Symbols to monitor
SYMBOLS = {
    "EUR/USD": "EURUSD=X",
    "BTC/USD": "BTC-USD",
    "XAU/USD": "GC=F",  # Gold futures
    "USD/JPY": "JPY=X"
}

INTERVAL = "1h"
PERIOD = "7d"
POLL_INTERVAL = 900  # Every 15 minutes

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

def detect_fair_value_gaps(df):
    gaps = []
    for i in range(2, len(df)):
        prev_high = df.iloc[i - 2]['High']
        prev_low = df.iloc[i - 2]['Low']
        curr_open = df.iloc[i]['Open']
        curr_close = df.iloc[i]['Close']

        if curr_open > prev_high:
            gaps.append((df.index[i], 'bearish', prev_high, curr_open))
        elif curr_open < prev_low:
            gaps.append((df.index[i], 'bullish', curr_open, prev_low))

    return gaps

def main():
    print("📈 Fair Value Gap Bot Started")
    while True:
        try:
            for label, ticker in SYMBOLS.items():
                df = yf.download(ticker, interval=INTERVAL, period=PERIOD, progress=False)
                if df.empty:
                    print(f"No data for {label}")
                    continue

                gaps = detect_fair_value_gaps(df)
                if not gaps:
                    print(f"No FVG for {label}")
                    continue

                last_gap = gaps[-1]
                direction = "SELL LIMIT" if last_gap[1] == "bearish" else "BUY LIMIT"
                entry = (last_gap[2] + last_gap[3]) / 2

                message = (
                    f"\n\ud83d\udd39 *FVG Signal - {label}*\n"
                    f"\ud83d\udcca Type: `{direction}`\n"
                    f"\ud83d\udd22 Gap: `{last_gap[2]:.5f}` - `{last_gap[3]:.5f}`\n"
                    f"\u26a1 Entry Idea: `{entry:.5f}`\n"
                    f"\ud83d\udd52 Time: `{last_gap[0].strftime('%Y-%m-%d %H:%M:%S')}`\n"
                    f"\n\ud83d\udcb0 *Support:*\nBTC: `your-btc-address`\nETH: `your-eth-address`"
                )
                send_telegram_message(message)
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
