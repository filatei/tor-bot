# mt5_risk_dashboard_live_price.py
import streamlit as st
import requests
import json
import yfinance as yf
import pandas as pd
import plotly.graph_objs as go
from datetime import datetime
from profit_calc import profit_calculator_tab

tab1, tab2 = st.tabs(["📈 Trade Dashboard", "📊 Profit Calculator"])

with tab1:
    st.title("📈 Trade Dashboard")

    # === Session State Defaults ===
    def ensure_session_state_defaults():
        defaults = {
            "selected_symbol": "BTCUSD",
            "plan_exported": False,
            "account_size": 10000.0,
            "lot_size": 0.10,
            "risk_percent": 1.0,
            "entry_price": 1.1400,
            "rr_choice": "1:2"
        }
        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value

    ensure_session_state_defaults()

    # === Symbol Utilities ===
    def load_symbols():
        try:
            response = requests.get("http://localhost:3600/api/trading/symbols", timeout=5)
            if response.status_code == 200:
                return response.json()
        except Exception:
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
        except Exception:
            return None

    # === Load Symbols ===
    symbols = load_symbols()
    symbols.extend([
        {"symbol": "USOIL", "pip_precision": 0.1},
        {"symbol": "NZDCAD", "pip_precision": 0.0001}
    ])
    symbol_names = [s["symbol"] for s in symbols]
    selected_symbol = st.selectbox("🧭 Select Symbol", options=symbol_names, index=symbol_names.index(st.session_state.selected_symbol))
    st.session_state.selected_symbol = selected_symbol
    pip_precision = next((s["pip_precision"] for s in symbols if s["symbol"] == selected_symbol), 0.0001)
    yf_symbol = map_yf_symbol(selected_symbol)
    live_price = fetch_price(yf_symbol)

    # === Trade Settings ===
    st.markdown("### ⚙️ Trade Settings")
    st.session_state.account_size = st.number_input("💼 Account Balance ($)", min_value=100.0, value=st.session_state.account_size, step=100.0)
    st.session_state.lot_size = st.number_input("📦 Lot Size", min_value=0.01, value=st.session_state.lot_size, step=0.01)
    st.session_state.risk_percent = st.number_input("🎯 Risk per Trade (%)", min_value=0.1, max_value=10.0, value=st.session_state.risk_percent, step=0.1)
    st.session_state.entry_price = st.number_input("🎯 Entry Price", value=live_price or st.session_state.entry_price, format="%.5f")
    st.session_state.rr_choice = st.selectbox("📐 Risk:Reward", ["1:1", "1:2", "1:3"], index=["1:1", "1:2", "1:3"].index(st.session_state.rr_choice))

    account_size = st.session_state.account_size
    lot_size = st.session_state.lot_size
    risk_percent = st.session_state.risk_percent
    entry_price = st.session_state.entry_price
    rr_value = {"1:1": 1.0, "1:2": 2.0, "1:3": 3.0}[st.session_state.rr_choice]

    risk_dollar = account_size * (risk_percent / 100)
    sl_pips = risk_dollar / (lot_size * 10)
    tp_pips = sl_pips * rr_value
    sl_price = entry_price - (sl_pips * pip_precision)
    tp_price = entry_price + (tp_pips * pip_precision)

    stop_loss_price = st.number_input("🛑 Stop Loss Price", value=sl_price, format="%.5f")
    take_profit_price = st.number_input("🎯 Take Profit Price", value=tp_price, format="%.5f")

    sl_pips = abs(entry_price - stop_loss_price) / pip_precision
    tp_pips = abs(take_profit_price - entry_price) / pip_precision
    risk_amount = sl_pips * lot_size * 10
    reward_amount = tp_pips * lot_size * 10
    rr_ratio = reward_amount / risk_amount if risk_amount else 0
    suggested_lot_size = (account_size * risk_percent / 100) / (sl_pips * 10) if sl_pips else 0

    # === Trade Summary ===
    st.subheader("📊 Trade Summary")
    if live_price:
        st.info(f"💹 Current {selected_symbol} Price: {live_price}")
    else:
        st.warning("⚠️ Live price unavailable.")

    cols = st.columns(3)
    cols[0].metric("SL", f"{sl_pips:.1f} pips")
    cols[1].metric("TP", f"{tp_pips:.1f} pips")
    cols[2].metric("R:R", f"{rr_ratio:.2f}")
    cols2 = st.columns(2)
    cols2[0].metric("Risk ($)", f"${risk_amount:.2f}")
    cols2[1].metric("Reward ($)", f"${reward_amount:.2f}")
    st.caption(f"Suggested Lot Size: {suggested_lot_size:.2f}")

    # === Export ===
    custom_path = st.text_input("📁 Export Path", value="trade_risk_calc.json")
    if st.button("📤 Export Trade Plan"):
        trade_data = {
            "symbol": st.session_state.selected_symbol,
            "yf_symbol": map_yf_symbol(st.session_state.selected_symbol),
            "lot_size": lot_size,
            "account_size": account_size,
            "risk_percent": risk_percent,
            "entry_price": entry_price,
            "stop_loss": stop_loss_price,
            "take_profit": take_profit_price,
            "pip_precision": pip_precision,
            "stop_loss_pips": round(sl_pips, 1),
            "take_profit_pips": round(tp_pips, 1),
            "risk_usd": round(risk_amount, 2),
            "reward_usd": round(reward_amount, 2),
            "rr_ratio": round(rr_ratio, 2),
            "suggested_lot_size": round(suggested_lot_size, 2),
            "created_at": str(datetime.now())
        }
        with open(custom_path, "w") as f:
            json.dump(trade_data, f, indent=2)
        st.success(f"✅ Saved to {custom_path}")

    # === Chart + Backtest ===
    with st.expander("📈 Historical Price Chart + Backtest"):
        period = st.selectbox("🗓️ Period", ["5d", "7d", "1mo", "3mo", "6mo", "12mo"], index=5)
        interval = st.selectbox("⏱️ Interval", ["1h", "30m", "15m"])
        session_filter = st.selectbox("🕒 Session Filter", ["All", "London", "New York"], index=0)

        if st.button("📅 Fetch, Filter & Backtest"):
            df = yf.download(yf_symbol, period=period, interval=interval)

            if df.empty:
                st.warning("No data returned from Yahoo Finance.")
            else:
                df.index = df.index.tz_localize(None)
                df.reset_index(inplace=True)

                df["Hour"] = df["Datetime"].dt.hour
                if session_filter == "London":
                    df = df[df["Hour"].between(7, 16)]
                elif session_filter == "New York":
                    df = df[df["Hour"].between(13, 21)]

                csv = df.to_csv(index=False).encode("utf-8")
                filename = f"{selected_symbol}_{period}_{interval}_{session_filter}.csv"
                st.download_button("⬇️ Download Filtered CSV", data=csv, file_name=filename)

                df["MA21"] = df["Close"].rolling(21).mean()
                df.dropna(inplace=True)
                df.reset_index(drop=True, inplace=True)

                fig = go.Figure()
                fig.add_trace(go.Candlestick(x=df["Datetime"], open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"], name="Price"))
                fig.add_trace(go.Scatter(x=df["Datetime"], y=df["MA21"], line=dict(color='red'), name="MA21"))
                st.plotly_chart(fig, use_container_width=True)

                trades = []
                balance = 100000
                for i in range(1, len(df)):
                    try:
                        prev_close = df.iloc[i - 1]["Close"]
                        prev_ma21 = df.iloc[i - 1]["MA21"]
                        curr_close = df.iloc[i]["Close"]
                        curr_ma21 = df.iloc[i]["MA21"]

                        if prev_close < prev_ma21 and curr_close > curr_ma21:
                            entry = curr_close
                            sl = entry - 0.0020
                            tp = entry + 0.0030
                            high = df.iloc[i]["High"]
                            low = df.iloc[i]["Low"]

                            exit_price = tp if high >= tp else (sl if low <= sl else curr_close)
                            profit = 1500 if exit_price >= tp else (-1000 if exit_price <= sl else 0)
                            balance += profit

                            trades.append({
                                "Datetime": df.iloc[i]["Datetime"],
                                "Entry": entry,
                                "Exit": exit_price,
                                "Result ($)": profit,
                                "Balance": balance
                            })
                    except Exception as e:
                        st.warning(f"⚠️ Skipped row {i} due to: {e}")

                if trades:
                    results_df = pd.DataFrame(trades)
                    st.line_chart(results_df.set_index("Datetime")["Balance"])
                    st.dataframe(results_df)
                    st.success(f"✅ Total Trades: {len(results_df)}, Final Balance: ${balance:,.2f}")
                else:
                    st.info("No breakout trades triggered in this dataset.")

with tab2:
    profit_calculator_tab()

# === Footer ===
st.markdown("---")
st.caption("© 2025 Torama. All rights reserved.")
