import yfinance as yf
import pandas as pd
import mplfinance as mpf
import numpy as np

# Fetch data
symbol = "BTC-USD"
data = yf.download(symbol, period="60d", interval="1h")

# Calculate support/resistance with proper rolling windows
def get_key_levels(df, window=20):
    df = df.copy()
    df['high_roll'] = df['High'].rolling(window=window, min_periods=1).max()
    df['low_roll'] = df['Low'].rolling(window=window, min_periods=1).min()
    return df

data = get_key_levels(data)

# Simplified signal detection without alignment issues
def detect_signals(df):
    df = df.copy()
    
    # Liquidity grabs
    df['liquidity_grab_bull'] = np.where(
        (df['Low'] < df['low_roll'].shift(1)) & 
        (df['Close'] > df['low_roll'].shift(1)), 
        df['Low'], 
        np.nan
    )
    
    df['liquidity_grab_bear'] = np.where(
        (df['High'] > df['high_roll'].shift(1)) & 
        (df['Close'] < df['high_roll'].shift(1)), 
        df['High'], 
        np.nan
    )
    
    # Breakouts with volume filter
    vol_mean = df['Volume'].rolling(20, min_periods=1).mean()
    df['breakout_bull'] = np.where(
        (df['Close'] > df['high_roll'].shift(1)) & 
        (df['Volume'] > 1.5 * vol_mean),
        df['Close'],
        np.nan
    )
    
    df['breakout_bear'] = np.where(
        (df['Close'] < df['low_roll'].shift(1)) & 
        (df['Volume'] > 1.5 * vol_mean),
        df['Close'],
        np.nan
    )
    
    return df

data = detect_signals(data)

# Plotting function
def plot_signals(df):
    apds = []
    
    # Add support/resistance lines
    apds.append(mpf.make_addplot(df['high_roll'], color='blue', alpha=0.5))
    apds.append(mpf.make_addplot(df['low_roll'], color='blue', alpha=0.5))
    
    # Add signals if they exist
    if not df['liquidity_grab_bull'].isna().all():
        apds.append(mpf.make_addplot(df['liquidity_grab_bull'], scatter=True, markersize=100, marker='^', color='green'))
    if not df['liquidity_grab_bear'].isna().all():
        apds.append(mpf.make_addplot(df['liquidity_grab_bear'], scatter=True, markersize=100, marker='v', color='red'))
    if not df['breakout_bull'].isna().all():
        apds.append(mpf.make_addplot(df['breakout_bull'], scatter=True, markersize=100, marker='*', color='lime'))
    if not df['breakout_bear'].isna().all():
        apds.append(mpf.make_addplot(df['breakout_bear'], scatter=True, markersize=100, marker='*', color='orangered'))
    
    # Plot
    mpf.plot(
        df[-200:], 
        type='candle', 
        style='charles', 
        addplot=apds,
        title=f"{symbol} Hybrid Strategy",
        volume=True,
        figratio=(12, 8),
        figscale=1.2
    )

plot_signals(data)