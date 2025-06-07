# main.py

import streamlit as st
from app.dashboard import dashboard_tab
from app.calculator import profit_calculator_tab

tab1, tab2 = st.tabs([" Profit Calculator", "📈 Trade Dashboard"])
with tab1:
    profit_calculator_tab()
with tab2:    
    dashboard_tab()

st.markdown("---")
st.caption("© 2025 Torama. All rights reserved.")
