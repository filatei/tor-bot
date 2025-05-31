import os
import time
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Constants
ACCOUNT_BALANCE = 10000
RISK_PER_TRADE = 0.01   # 1%
STOP_LOSS_PIPS = 10
TP_PIPS = 20
PIP_VALUE_PER_LOT = 10  # $10 per pip for 1 lot of EUR/USD

# API + Telegram
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SYMBOL = "EUR/USD"
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))

def fetch_price():
    url = f"https://api.twelvedata.com/price?symbol={SYMBOL}&apikey={TWELVEDATA_API_KEY}"
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()
    return float(data["price"])

def send_telegram_message(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    requests.post(url, data=payload)

def calculate_trade_setup(current_price):
    stop_loss = current_price - 0.0010  # 10 pips
    take_profit = current_price + 0.0020  # 20 pips
    risk_amount = ACCOUNT_BALANCE * RISK_PER_TRADE
    lot_size = round(risk_amount / (STOP_LOSS_PIPS * PIP_VALUE_PER_LOT), 2)
    return {
        "entry": round(current_price, 5),
        "sl": round(stop_loss, 5),
        "tp": round(take_profit, 5),
        "lot_size": lot_size
    }

def main():
    print(f"🔁 FTMO Dynamic EUR/USD Bot running...")

    active_trade = False
    entry_price = None
    sl = None
    tp = None
    lot_size = None

    while True:
        try:
            current_price = fetch_price()
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Price: {current_price:.5f}")

            if not active_trade:
                setup = calculate_trade_setup(current_price)
                entry_price, sl, tp, lot_size = setup['entry'], setup['sl'], setup['tp'], setup['lot_size']
                active_trade = True

                message = (
                    f"📈 *New Trade Idea - FTMO 10K*\n\n"
                    f"🟢 *Entry:* `{entry_price}`\n"
                    f"🛑 *Stop-Loss:* `{sl}`\n"
                    f"🎯 *Take-Profit:* `{tp}`\n"
                    f"📦 *Lot Size:* `{lot_size}`\n"
                    f"💸 *Risk:* `${ACCOUNT_BALANCE * RISK_PER_TRADE}`\n"
                    f"⏰ *Time:* `{time.strftime('%Y-%m-%d %H:%M:%S')}`"
                )
                print(message)
                send_telegram_message(message)
                print("✅ Trade setup sent.")

            else:
                if current_price >= tp:
                    send_telegram_message(f"✅ *TP Hit!* EUR/USD reached {tp}. Booking profit.")
                    print("✅ Take profit hit. Resetting.")
                    active_trade = False

                elif current_price <= sl:
                    send_telegram_message(f"🛑 *SL Hit!* EUR/USD dropped to {sl}. Stopping trade.")
                    print("🛑 Stop loss hit. Resetting.")
                    active_trade = False

        except Exception as e:
            print(f"❌ Error: {e}")

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
