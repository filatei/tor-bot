import os
import time
import csv
import requests
import yfinance as yf
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime, time as dtime, timezone
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Load environment variables
load_dotenv()

# Telegram config
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Google Sheets config
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "Liquidity_Trades")
GOOGLE_CRED_FILE = os.getenv("GOOGLE_CRED_FILE", "google-credentials.json")

# Account settings
ACCOUNT_BALANCE = float(os.getenv("ACCOUNT_BALANCE", 10000))
LEVERAGE = float(os.getenv("LEVERAGE", 30))
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", 0.01))
MAX_EXPOSURE = ACCOUNT_BALANCE * LEVERAGE
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", 300))  # seconds
ATR_PERIOD = int(os.getenv("ATR_PERIOD", 14))

# Crypto donation message
DONATION_TEXT = (
    "\n\n💰 *Support the bot:*\n"
    "BTC: `1H8rsoZiWn8eCH5N5nbALdLMimrgSMrxE4`\n"
    "ETH: `0xF1047695dc36F50CB32348a4b4Eb3a3c6bcEfE8a`\n"
    "USDT (TRC20): `TKKcyEys1wryUueCpnR5bUdt9pRB9VJAbv`"
)

# Trading sessions (UTC)
SESSIONS = {
    "Sydney": (dtime(21, 0), dtime(6, 0)),
    "Tokyo": (dtime(0, 0), dtime(8, 0)),
    "London": (dtime(8, 0), dtime(16, 0)),
    "New York": (dtime(13, 0), dtime(21, 0))
}

last_alerted_session = None

# Symbol-specific config
SYMBOLS = {
    "BTC/USD": {
        "ticker": "BTC-USD",
        "pip_value": 1,
        "threshold": 50,
        "sl_pips": 100,
        "tp_pips": 200,
        "margin_per_lot": 5000
    },
    "EUR/USD": {
        "ticker": "EURUSD=X",
        "pip_value": 100000,
        "threshold": 0.0010,
        "sl_pips": 0.0010,
        "tp_pips": 0.0020,
        "margin_per_lot": 3333.33
    }
}

def is_within_trading_hours():
    now_utc = datetime.now(timezone.utc).time()
    for session, (start, end) in SESSIONS.items():
        if start < end and start <= now_utc <= end:
            return session
        elif start > end and (now_utc >= start or now_utc <= end):
            return session
    return None

def send_telegram_message(message):
    # print(message)
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    response = requests.post(url, data=payload)
    if response.status_code != 200:
        raise Exception(f"Telegram API error: {response.status_code} - {response.text}")
    result = response.json()
    if not result.get("ok"):
        raise Exception(f"Telegram response error: {result}")

def fetch_price_and_atr(ticker):
    df = yf.download(ticker, interval="1h", period="2d", progress=False, auto_adjust=False)
    if df.empty or len(df) < ATR_PERIOD:
        raise ValueError(f"Not enough data for ATR for {ticker}")

    high = df['High']
    low = df['Low']
    close = df['Close']

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.rolling(window=ATR_PERIOD).mean().iloc[-1]
    current_price = close.iloc[-1]
    return float(current_price.item()), float(atr.item())

def generate_liquidity_grab_setup(symbol, price, pip_value, threshold, sl_pips, tp_pips, margin_per_lot):
    offset = threshold * 0.5
    risk_amount = ACCOUNT_BALANCE * RISK_PER_TRADE
    sl_in_dollars = sl_pips * pip_value
    lot_size = risk_amount / sl_in_dollars if sl_in_dollars else 0.01
    max_lots_by_margin = MAX_EXPOSURE / margin_per_lot
    lot_size = min(lot_size, max_lots_by_margin)
    lot_size = round(lot_size, 2)

    fake_high = price + threshold
    fake_low = price - threshold

    sell = {
        "type": "SELL LIMIT",
        "entry": round(fake_high + offset, 5),
        "sl": round(fake_high + sl_pips, 5),
        "tp": round(price - tp_pips, 5),
        "lot_size": lot_size
    }
    buy = {
        "type": "BUY LIMIT",
        "entry": round(fake_low - offset, 5),
        "sl": round(fake_low - sl_pips, 5),
        "tp": round(price + tp_pips, 5),
        "lot_size": lot_size
    }

    return {"symbol": symbol, "sell": sell, "buy": buy}

def main():
    global last_alerted_session
    print("📊 Liquidity Grab Bot using yfinance started.")
    while True:
        current_session = is_within_trading_hours()
        if not current_session:
            print("🕒 Outside trading hours (Tokyo/London/NY/Sydney). Retrying after delay...")
            time.sleep(POLL_INTERVAL)
            continue

        if current_session != last_alerted_session:
            send_telegram_message(f"📢 *{current_session} session started.* Monitoring for setups...{DONATION_TEXT}")
            last_alerted_session = current_session

        try:
            for name, config in SYMBOLS.items():
                price, atr = fetch_price_and_atr(config["ticker"])
                print(f"{datetime.now().strftime('%H:%M:%S')} {name} | Price: {price:.5f} | ATR: {atr:.5f}")

                if atr > config["threshold"]:
                    setup = generate_liquidity_grab_setup(
                        name, price, config["pip_value"], config["threshold"],
                        config["sl_pips"], config["tp_pips"], config["margin_per_lot"]
                    )

                    message = (
                        f"📉 *Liquidity Grab Setup - {name}*\n"
                        f"📈 Price: `{price}` | ATR: `{atr}`\n\n"
                        f"🔻 *{setup['sell']['type']}* at `{setup['sell']['entry']}`\n"
                        f"• SL: `{setup['sell']['sl']}` | TP: `{setup['sell']['tp']}` | Lot: `{setup['sell']['lot_size']}`\n\n"
                        f"🔺 *{setup['buy']['type']}* at `{setup['buy']['entry']}`\n"
                        f"• SL: `{setup['buy']['sl']}` | TP: `{setup['buy']['tp']}` | Lot: `{setup['buy']['lot_size']}`\n"
                        f"🕒 Time: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`{DONATION_TEXT}"
                    )
                    send_telegram_message(message)
                    print(message, end='\n' * 2)
                    print(f"✅ Alert sent for {name}")
                else:
                    print(f"⚠️ Skipping {name}: ATR {atr:.5f} below threshold {config['threshold']}")
        except Exception as e:
            print(f"❌ Error: {e}")

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
