import os
import time
import csv
import requests
import yfinance as yf
import pandas as pd
from datetime import datetime, timezone
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials

load_dotenv()

# ----------------------
# Configuration / Env
# ----------------------
TELEGRAM_TOKEN      = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID    = os.getenv("TELEGRAM_CHAT_ID")
GOOGLE_SHEET_NAME   = os.getenv("GOOGLE_SHEET_NAME", "TradeSignals")
GOOGLE_CRED_FILE    = os.getenv("GOOGLE_CRED_FILE", "google-credentials.json")
ACCOUNT_BALANCE     = float(os.getenv("ACCOUNT_BALANCE", 10000))  # e.g. 10000 for FTMO
RISK_PERCENT        = float(os.getenv("RISK_PERCENT", 1.0))      # 1% risk by default
INTERVAL            = "1h"
PERIOD              = "7d"
POLL_INTERVAL       = 900  # 15 minutes

# ----------------------
# Instruments & Pip Info
# ----------------------
# pip_increment: smallest price move for 1 pip
# pip_value: USD value of 1 pip for a 1-lot (100,000 units) position
SYMBOLS = {
    "EUR/USD":   {"ticker": "EURUSD=X", "pip_increment": 0.0001,  "pip_value": 10},
    "BTC/USD":   {"ticker": "BTC-USD",  "pip_increment": 0.01,    "pip_value": 1},   # Crypto CFDs vary; adjust pip_value as needed
    "XAU/USD":   {"ticker": "GC=F",      "pip_increment": 0.1,     "pip_value": 10},  # Gold futures: 0.1 price = 1 pip
    "USD/JPY":   {"ticker": "JPY=X",     "pip_increment": 0.01,    "pip_value": 9.13}  # ~ $9.13 per pip for USD/JPY
}

# ----------------------
# Helpers: Telegram + CSV + Google Sheet
# ----------------------
def send_telegram_message(message: str):
    """Send a Markdown‐formatted message via Telegram."""
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
        print(f"❌ Failed to send Telegram message: {e}")


def append_to_csv(label, signal_type, entry_price, sl, tp, lot,
                  curr_price, profit_target, loss_target, timestamp):
    """
    Append one row of signal data to a local CSV. Create header if file doesn't exist.
    """
    file_name = "trade_signals.csv"
    file_exists = os.path.isfile(file_name)

    with open(file_name, mode="a", newline="") as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow([
                "Time", "Symbol", "Signal Type", "Entry Price", "SL", "TP",
                "Current Price", "Lot Size", "Profit Target", "Loss Target"
            ])
        writer.writerow([
            timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            label,
            signal_type,
            f"{entry_price:.5f}",
            f"{sl:.5f}",
            f"{tp:.5f}",
            f"{curr_price:.5f}",
            f"{lot:.2f}",
            f"{profit_target:.5f}",
            f"{loss_target:.5f}"
        ])
    print(f"✅ Appended to CSV: {label} | {signal_type} | Entry {entry_price:.5f}")


def append_to_google_sheet(label, signal_type, entry_price, sl, tp, lot,
                           curr_price, profit_target, loss_target, timestamp):
    """
    Append one row of signal data to Google Sheet (worksheet "Signals").
    """
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CRED_FILE, scope)
        client = gspread.authorize(creds)
        sheet = client.open(GOOGLE_SHEET_NAME).worksheet("Signals")
        sheet.append_row([
            timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            label,
            signal_type,
            f"{entry_price:.5f}",
            f"{sl:.5f}",
            f"{tp:.5f}",
            f"{curr_price:.5f}",
            f"{lot:.2f}",
            f"{profit_target:.5f}",
            f"{loss_target:.5f}"
        ])
        print(f"✅ Sent to Google Sheet: {label} | {signal_type} | Entry {entry_price:.5f}")
    except Exception as e:
        print(f"❌ Failed to write to sheet: {e}")


# ----------------------
# Trade‐calculation helper
# ----------------------
def calculate_trade_details(entry, direction, pip_increment, pip_value):
    """
    Given:
      - entry (float)
      - direction: "SELL LIMIT" or "BUY LIMIT"
      - pip_increment: smallest price move corresponding to 1 pip
      - pip_value: USD value of 1 pip for a 1-lot position

    Return:
      sl (stop‐loss price),
      tp (take‐profit price),
      lot_size (rounded to 2 decimal places),
      profit_target (price‐difference),
      loss_target (price‐difference)
    """
    # Example buffers—10 pips for SL, 20 pips for TP
    sl_buffer = pip_increment * 10
    tp_buffer = pip_increment * 20

    if direction == "SELL LIMIT":
        sl = entry + sl_buffer
        tp = entry - tp_buffer
    else:  # BUY LIMIT
        sl = entry - sl_buffer
        tp = entry + tp_buffer

    # Risk amount in USD
    risk_amount = ACCOUNT_BALANCE * (RISK_PERCENT / 100)  # e.g. 0.01 * 10000 = $100

    # Distance to SL in price units (absolute)
    loss_price_diff = abs(entry - sl)

    # Convert price‐difference to pips:
    #   number_of_pips = price_diff / pip_increment
    loss_pips = (loss_price_diff / pip_increment) if pip_increment != 0 else 0

    # Lot size formula: (risk_amount) / (loss_pips * pip_value)
    lot_size = (risk_amount / (loss_pips * pip_value)) if (loss_pips * pip_value) != 0 else 0.01
    lot_size = round(lot_size, 2)

    # Profit target difference in price units:
    profit_price_diff = abs(tp - entry)

    return sl, tp, lot_size, profit_price_diff, loss_price_diff


# ----------------------
# Signal‐detection functions (using integer‐indexing only)
# ----------------------
def detect_fvg(df: pd.DataFrame):
    """
    Return a list of tuples: (timestamp, 'bearish'/'bullish', start_price, end_price)
    """
    fvg_signals = []

    # Precompute column indices
    col_high = df.columns.get_loc("High")
    col_low  = df.columns.get_loc("Low")
    col_open = df.columns.get_loc("Open")

    for i in range(2, len(df)):
        prev_high = df.iloc[i - 2, col_high].item()
        prev_low  = df.iloc[i - 2, col_low].item()
        curr_open = df.iloc[i, col_open].item()

        if pd.notna(prev_high) and pd.notna(prev_low) and pd.notna(curr_open):
            if curr_open > prev_high:
                fvg_signals.append((df.index[i], "bearish", prev_high, curr_open))
            elif curr_open < prev_low:
                fvg_signals.append((df.index[i], "bullish", curr_open, prev_low))

    return fvg_signals


def detect_liquidity(df: pd.DataFrame):
    """
    Return a list of tuples: (timestamp, 'Liquidity Grab (Bull)', price) or breakout signals.
    """
    liquidity_signals = []
    df2 = df.copy()

    # Rolling support/resistance & volume average
    df2["high_roll"] = df2["High"].rolling(window=20).max()
    df2["low_roll"]  = df2["Low"].rolling(window=20).min()
    df2["vol_mean"]  = df2["Volume"].rolling(window=20).mean()

    # Precompute column indices
    col_high    = df2.columns.get_loc("High")
    col_low     = df2.columns.get_loc("Low")
    col_close   = df2.columns.get_loc("Close")
    col_vol     = df2.columns.get_loc("Volume")
    col_highr   = df2.columns.get_loc("high_roll")
    col_lowr    = df2.columns.get_loc("low_roll")
    col_volmean = df2.columns.get_loc("vol_mean")

    for i in range(20, len(df2)):
        ts      = df2.index[i]
        high_roll = df2.iloc[i - 1, col_highr].item()
        low_roll  = df2.iloc[i - 1, col_lowr].item()
        close   = df2.iloc[i, col_close].item()
        high    = df2.iloc[i, col_high].item()
        low     = df2.iloc[i, col_low].item()
        volume  = df2.iloc[i, col_vol].item()
        vol_avg = df2.iloc[i, col_volmean].item()

        if pd.notna(high_roll) and pd.notna(low_roll):
            # Liquidity‐grab long
            if (low < low_roll) and (close > low_roll):
                liquidity_signals.append((ts, "Liquidity Grab (Bull)", low))
            # Liquidity‐grab short
            elif (high > high_roll) and (close < high_roll):
                liquidity_signals.append((ts, "Liquidity Grab (Bear)", high))

            # Breakout long
            if (close > high_roll) and (volume > 1.5 * vol_avg):
                liquidity_signals.append((ts, "Breakout (Bull)", close))
            # Breakout short
            elif (close < low_roll) and (volume > 1.5 * vol_avg):
                liquidity_signals.append((ts, "Breakout (Bear)", close))

    return liquidity_signals


# ----------------------
# Main Loop
# ----------------------
def main():
    print("📈 Hybrid Strategy Bot Running")
    while True:
        try:
            for label, info in SYMBOLS.items():
                ticker        = info["ticker"]
                pip_increment = info["pip_increment"]
                pip_value     = info["pip_value"]

                # 1) Fetch 1h candles (last 7 days)
                df = yf.download(ticker, interval=INTERVAL, period=PERIOD, progress=False)
                if df.empty:
                    print(f"No data for {label}")
                    continue

                # 2) Detect signals
                fvg_signals       = detect_fvg(df)
                liquidity_signals = detect_liquidity(df)

                if not fvg_signals and not liquidity_signals:
                    print(f"No valid signals for {label}")
                    continue

                # 3) Current close price
                curr_price = df.iloc[-1, df.columns.get_loc("Close")].item()

                # 4) Build and send alerts
                message = f"\n📊 *Signals for {label}*\n"
                timestamp_now = datetime.now(timezone.utc)

                # ----- FVG (only most recent)
                if fvg_signals:
                    ts, direction, start, end = fvg_signals[-1]
                    entry = (start + end) / 2
                    signal_type = "SELL LIMIT" if direction == "bearish" else "BUY LIMIT"
                    sl, tp, lot, profit_target, loss_target = calculate_trade_details(
                        entry, signal_type, pip_increment, pip_value
                    )

                    message += (
                        f"\n🔸 *FVG Detected*\n"
                        f"Type: `{signal_type}`\n"
                        f"Entry: `{entry:.5f}`\n"
                        f"Current Price: `{curr_price:.5f}`\n"
                        f"SL: `{sl:.5f}` | TP: `{tp:.5f}`\n"
                        f"Lot Size: `{lot}`\n"
                        f"Profit Target (price diff): `{profit_target:.5f}`\n"
                        f"Loss Target (price diff): `{loss_target:.5f}`\n"
                        f"Time: `{ts.strftime('%Y-%m-%d %H:%M:%S')}`\n"
                    )

                    append_to_csv(
                        label, signal_type, entry, sl, tp, lot,
                        curr_price, profit_target, loss_target, ts
                    )
                    append_to_google_sheet(
                        label, signal_type, entry, sl, tp, lot,
                        curr_price, profit_target, loss_target, ts
                    )

                # ----- Liquidity / Breakout (up to last 3)
                for ts, sig_type, price in liquidity_signals[-3:]:
                    direction = "BUY LIMIT" if "Bull" in sig_type else "SELL LIMIT"
                    sl, tp, lot, profit_target, loss_target = calculate_trade_details(
                        price, direction, pip_increment, pip_value
                    )

                    message += (
                        f"\n🔹 *{sig_type}*\n"
                        f"Entry: `{price:.5f}`\n"
                        f"Current Price: `{curr_price:.5f}`\n"
                        f"SL: `{sl:.5f}` | TP: `{tp:.5f}`\n"
                        f"Lot Size: `{lot}`\n"
                        f"Profit Target (price diff): `{profit_target:.5f}`\n"
                        f"Loss Target (price diff): `{loss_target:.5f}`\n"
                        f"Time: `{ts.strftime('%Y-%m-%d %H:%M:%S')}`\n"
                    )

                    append_to_csv(
                        label, sig_type, price, sl, tp, lot,
                        curr_price, profit_target, loss_target, ts
                    )
                    append_to_google_sheet(
                        label, sig_type, price, sl, tp, lot,
                        curr_price, profit_target, loss_target, ts
                    )

                # Donation reminder
                message += (
                    "\n💰 *Support the bot:*\n"
                    "BTC: `your-btc-address`\n"
                    "ETH: `your-eth-address`"
                )

                send_telegram_message(message)
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
