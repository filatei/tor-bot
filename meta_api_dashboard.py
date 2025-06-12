import streamlit as st
import os
import pandas as pd
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from metaapi_cloud_sdk import MetaApi
import asyncio
import time
import logging
import io

# === Load .env ===
load_dotenv()
META_API_TOKEN = os.getenv("META_API_ACCESS_TOKEN")
ACCOUNT_ID = os.getenv("META_API_ACCOUNT_ID")

# === Logging for MetaApi ===
log_buffer = io.StringIO()
logging.basicConfig(stream=log_buffer, level=logging.INFO)
logger = logging.getLogger("metaapi")

# === Streamlit Layout ===
st.set_page_config(page_title="MetaApi RPC Dashboard", layout="wide")
st.title("📊 MetaApi RPC Trading Dashboard")

# === Fetch data async ===
async def fetch_rpc_data():
    metaapi = MetaApi(META_API_TOKEN, {'logger': logger})
    account = await metaapi.metatrader_account_api.get_account(ACCOUNT_ID)

    if account.state != 'DEPLOYED':
        return None, "⚠️ Account is not deployed."

    rpc = account.get_rpc_connection()
    await rpc.connect()
    await asyncio.sleep(1)  # Let it stabilize

    info = await rpc.get_account_information()
    positions = await rpc.get_positions()
    orders = await rpc.get_orders()
    symbols = await rpc.get_symbols()

    return {
        "rpc": rpc,
        "account_info": info,
        "positions": positions,
        "orders": orders,
        "symbols": symbols
    }, None

# === Sync wrapper ===
def run_rpc_fetch():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(fetch_rpc_data())

# === Fetch data ===
data, error = run_rpc_fetch()

# === Display or error ===
if error:
    st.error(error)
elif data:
    rpc = data["rpc"]
    acc = data["account_info"]
    symbols = data["symbols"]

    # --- Live Equity and Margin
    st.markdown("### 💰 Live Equity & Margin")
    cols = st.columns(4)
    cols[0].metric("Equity", f"${acc['equity']:.2f}")
    cols[1].metric("Balance", f"${acc['balance']:.2f}")
    cols[2].metric("Margin", f"${acc['margin']:.2f}")
    cols[3].metric("Free Margin", f"${acc['freeMargin']:.2f}")

    st.divider()

    # --- Open Positions
    st.subheader("📌 Open Positions")
    if data["positions"]:
        st.dataframe(pd.DataFrame(data["positions"]))
    else:
        st.info("No open positions.")

    # --- Pending Orders
    st.subheader("📑 Pending Orders")
    if data["orders"]:
        st.dataframe(pd.DataFrame(data["orders"]))
    else:
        st.info("No pending orders.")

    st.divider()

    # --- Submit Order
    st.subheader("📤 Submit Pending Order")

    # Build symbol list with BTC symbols first
    btc_symbols = [s for s in symbols if "BTC" in s.upper()]
    symbol_list = sorted(set(btc_symbols + symbols[:20]))

    with st.form("order_form"):
        col1, col2 = st.columns(2)
        with col1:
            symbol = st.selectbox("Symbol", symbol_list, index=0)
            order_type = st.selectbox("Type", ["SELL_LIMIT", "BUY_LIMIT"])
            volume = st.number_input("Lot Size", min_value=0.01, value=0.01)
            price = st.number_input("Price", value=108000.0)
        with col2:
            sl = st.number_input("Stop Loss", value=price + 500)
            tp = st.number_input("Take Profit", value=price - 500)
            comment = st.text_input("Comment", value="MetaApi RPC Order")
            magic = st.number_input("Magic Number", value=123456, step=1)
        submit = st.form_submit_button("📨 Place Order")

    if submit:
        st.info("🚀 Sending order to MetaApi via RPC...")
        async def place_rpc_order():
            order = {
                "symbol": symbol,
                "type": order_type,
                "volume": volume,
                "price": price,
                "stopLoss": sl,
                "takeProfit": tp,
                "magic": int(magic),
                "comment": comment
            }
            start = time.time()
            result = await rpc.create_order(order)
            elapsed = time.time() - start
            return result, elapsed

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result, elapsed = loop.run_until_complete(place_rpc_order())
            st.success(f"✅ Order placed in {elapsed:.2f} seconds. Code: {result.get('stringCode')}")
        except Exception as e:
            st.error(f"❌ Failed to place order: {e}")

    st.divider()
    with st.expander("🛠 MetaApi Debug Logs"):
        st.code(log_buffer.getvalue(), language="bash")