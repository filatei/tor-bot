import streamlit as st
import yfinance as yf

# === Symbol Formatter ===
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

# === Profit Calculator Tab ===
def profit_calculator_tab():
    st.header("📊 Profit Calculator")

    default_symbols = [
        "EURUSD=X", "GBPUSD=X", "USDJPY=X", "USDCHF=X", "USDCAD=X", "AUDUSD=X", "NZDUSD=X",
        "EURJPY=X", "EURCHF=X", "EURGBP=X", "GBPJPY=X", "AUDJPY=X", "USDZAR=X",
        "XAUUSD=X", "XAGUSD=X", "CL=F", "NG=F", "BZ=F", "HG=F",
        "BTC-USD", "ETH-USD", "BNB-USD", "XRP-USD", "SOL-USD", "ADA-USD", "DOGE-USD", "DOT-USD", "AVAX-USD"
    ]

    symbol_labels = {
        "EURUSD=X": "EUR/USD", "GBPUSD=X": "GBP/USD", "USDJPY=X": "USD/JPY", "USDCHF=X": "USD/CHF",
        "USDCAD=X": "USD/CAD", "AUDUSD=X": "AUD/USD", "NZDUSD=X": "NZD/USD",
        "EURJPY=X": "EUR/JPY", "EURCHF=X": "EUR/CHF", "EURGBP=X": "EUR/GBP", "GBPJPY=X": "GBP/JPY", "AUDJPY=X": "AUD/JPY",
        "USDZAR=X": "USD/ZAR", "XAUUSD=X": "Gold", "XAGUSD=X": "Silver", "CL=F": "Crude Oil WTI", "BZ=F": "Brent Oil",
        "NG=F": "Natural Gas", "HG=F": "Copper", "BTC-USD": "Bitcoin", "ETH-USD": "Ethereum", "BNB-USD": "BNB",
        "XRP-USD": "XRP", "SOL-USD": "Solana", "ADA-USD": "Cardano", "DOGE-USD": "Dogecoin",
        "DOT-USD": "Polkadot", "AVAX-USD": "Avalanche"
    }

    symbol = st.selectbox("🔍 Search or Select Symbol", options=default_symbols,
                          format_func=lambda x: f"{symbol_labels.get(x, x)} ({x})")
    normalized_symbol = normalize_symbol(symbol)
    st.session_state["last_symbol"] = normalized_symbol

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

    # === Trade Inputs ===
    account_balance = st.number_input("💼 Account Balance", min_value=1.0, value=10000.0, step=100.0)
    lot_size = st.number_input("📦 Trade Size (Lots)", value=0.01, min_value=0.001, step=0.001)
    open_price = st.number_input("📥 Open Price", value=st.session_state.open_price, key="open_price_input")
    close_price = st.number_input("📤 Close Price", value=st.session_state.close_price, key="close_price_input")

    col_dir, _ = st.columns([1, 1])
    with col_dir:
        direction = st.radio("🧭 Trade Direction", ["Buy", "Sell"], horizontal=True)

    leverage = st.number_input("⚖️ Leverage (e.g., 100 for 1:100)", value=100, min_value=1)
    calculate_margin = st.checkbox("🔓 Show Margin Requirement", value=True)

    def calculate_profit(symbol, direction, open_price, close_price, lot_size):
        units = lot_size * 100000 if "USD" in symbol and "BTC" not in symbol else lot_size
        price_diff = close_price - open_price if direction == "Buy" else open_price - close_price
        return round(units * price_diff, 2)

    def calculate_required_margin(open_price, lot_size, leverage):
        notional_value = open_price * lot_size * 100000
        return round(notional_value / leverage, 2)

    if st.button("💰 Calculate"):
        result = calculate_profit(normalized_symbol, direction, open_price, close_price, lot_size)
        pct = (result / account_balance) * 100 if account_balance else 0
        st.session_state["last_result"] = result
        st.session_state["last_pct"] = pct

        if calculate_margin:
            margin_required = calculate_required_margin(open_price, lot_size, leverage)
            st.session_state["last_margin"] = margin_required
        else:
            st.session_state.pop("last_margin", None)

    # === Display Results After Button Press ===
    result = st.session_state.get("last_result")
    pct = st.session_state.get("last_pct")
    if result is not None:
        col1, col2 = st.columns([1, 1])
        with col2:
            if result > 0:
                st.markdown(f"### 💵 Profit: :green[${result} (+{pct:.2f}%)]")
            elif result < 0:
                st.markdown(f"### 💸 Loss: :red[${result} ({pct:.2f}%)]")
            else:
                st.markdown(f"### ⚖️ No P/L: ${result}")

    if "last_margin" in st.session_state:
        margin = st.session_state["last_margin"]
        st.info(f"📌 Required Margin: ${margin} at 1:{leverage} leverage")