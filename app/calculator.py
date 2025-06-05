# profit_calc.py
import streamlit as st
import yfinance as yf

def normalize_symbol(symbol: str) -> str:
    symbol = symbol.upper().strip()
    if symbol in ["BTCUSD", "BTC-USD"]: return "BTC-USD"
    if symbol in ["ETHUSD", "ETH-USD"]: return "ETH-USD"
    if symbol in ["BNBUSD"]: return "BNB-USD"
    if symbol in ["XRPUSD"]: return "XRP-USD"
    if symbol in ["SOLUSD"]: return "SOL-USD"
    if symbol in ["ADAUSD"]: return "ADA-USD"
    if symbol in ["DOGEUSD"]: return "DOGE-USD"
    if symbol in ["DOTUSD"]: return "DOT-USD"
    if symbol in ["AVAXUSD"]: return "AVAX-USD"
    if symbol.endswith("USD") and "-" not in symbol: return symbol + "=X"
    return symbol

def profit_calculator_tab():
    st.title("📊 Profit Calculator")

    default_symbols = [
        "EURUSD=X", "GBPUSD=X", "USDJPY=X", "USDCHF=X", "USDCAD=X", "AUDUSD=X", "NZDUSD=X",
        "EURJPY=X", "EURCHF=X", "EURGBP=X", "GBPJPY=X", "AUDJPY=X", "USDZAR=X",
        "XAUUSD=X", "XAGUSD=X", "CL=F", "NG=F", "BZ=F", "HG=F",
        "BTC-USD", "ETH-USD", "BNB-USD", "XRP-USD", "SOL-USD", "ADA-USD", "DOGE-USD", "DOT-USD", "AVAX-USD"
    ]

    symbol_labels = {s: s.replace("=X", "").replace("-USD", "/USD").replace("CL=F", "Crude Oil").replace("XAUUSD", "Gold") for s in default_symbols}

    col1, col2 = st.columns([1.5, 1])

    with col1:
        # Inputs
        symbol = st.selectbox("🔍 Select Symbol", options=default_symbols,
                              format_func=lambda x: f"{symbol_labels.get(x, x)} ({x})")
        normalized_symbol = normalize_symbol(symbol)

        try:
            data = yf.Ticker(normalized_symbol)
            hist = data.history(period="1d", interval="1m")
            latest_price = float(hist["Close"].iloc[-1]) if not hist.empty else 0.0
            st.info(f"📈 Current Price for {symbol_labels.get(normalized_symbol, normalized_symbol)}: {latest_price:.5f}")
        except Exception as e:
            st.error(f"❌ Error fetching price for {normalized_symbol}: {e}")
            return

        if "open_price" not in st.session_state or st.session_state.get("last_price_symbol") != normalized_symbol:
            st.session_state.open_price = latest_price
            st.session_state.close_price = latest_price
            st.session_state.last_price_symbol = normalized_symbol

        account_balance = st.number_input("💼 Account Balance", min_value=1.0, value=10000.0, step=100.0)
        lot_size = st.number_input("📦 Trade Size (Lots)", value=0.01, min_value=0.001, step=0.001)
        open_price = st.number_input("📥 Open Price", value=st.session_state.open_price, key="open_price_input")
        close_price = st.number_input("📤 Close Price", value=st.session_state.close_price, key="close_price_input")
        direction = st.radio("🧭 Trade Direction", ["Buy", "Sell"], horizontal=True)

    with col2:
        # Leverage & Calculate
        leverage = st.number_input("⚖️ Leverage (e.g., 100 = 1:100)", value=100, min_value=1)
        calculate_margin = st.checkbox("🔓 Show Margin Requirement", value=True)

        if st.button("💰 Calculate"):
            units = lot_size * 100000 if "USD" in normalized_symbol and "BTC" not in normalized_symbol else lot_size
            price_diff = close_price - open_price if direction == "Buy" else open_price - close_price
            result = round(units * price_diff, 2)
            pct = round((result / account_balance) * 100, 2) if account_balance else 0
            st.session_state["last_result"] = result
            st.session_state["last_pct"] = pct

            if calculate_margin:
                notional = open_price * lot_size * 100000
                margin = round(notional / leverage, 2)
                st.session_state["last_margin"] = margin
            else:
                st.session_state.pop("last_margin", None)

        # Result Display
        result = st.session_state.get("last_result")
        pct = st.session_state.get("last_pct")
        margin = st.session_state.get("last_margin")

        st.markdown("### 📈 Result")
        if result is not None:
            if result > 0:
                st.markdown(f"**💵 Profit:** :green[${result} (+{pct:.2f}%)]")
            elif result < 0:
                st.markdown(f"**💸 Loss:** :red[${result} ({pct:.2f}%)]")
            else:
                st.markdown(f"**⚖️ No P/L:** ${result:.2f}")

        if margin is not None:
            st.info(f"📌 Required Margin: ${margin}")