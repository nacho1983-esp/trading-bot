import streamlit as st
import pandas as pd
import numpy as np
from binance.client import Client
import plotly.graph_objects as go
from datetime import datetime
import os

API_KEY = ""
API_SECRET = ""

client = Client(API_KEY, API_SECRET)

symbols = ["BTCUSDT", "ETHUSDT"]
interval = Client.KLINE_INTERVAL_4HOUR

st.set_page_config(layout="wide")
st.title("📊 Trading Dashboard PRO + Logs")

LOG_FILE = "trades_log.csv"

# --- INIT ---
if "balance" not in st.session_state:
    st.session_state.balance = 1000
    st.session_state.peak = 1000
    st.session_state.trade = None
    st.session_state.entries = []
    st.session_state.exits = []

# --- LOG FUNCTION ---
def log_trade(data):
    df = pd.DataFrame([data])

    if not os.path.exists(LOG_FILE):
        df.to_csv(LOG_FILE, index=False)
    else:
        df.to_csv(LOG_FILE, mode='a', header=False, index=False)

# --- DATA ---
def get_data(symbol):
    klines = client.get_klines(symbol=symbol, interval=interval, limit=200)

    df = pd.DataFrame(klines, columns=[
        'time','open','high','low','close','volume',
        'ct','qav','n','tbbav','tbqav','ignore'
    ])

    df['time'] = pd.to_datetime(df['time'], unit='ms')
    df['open'] = df['open'].astype(float)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    df['close'] = df['close'].astype(float)

    df['ema20'] = df['close'].ewm(span=20).mean()

    df['tr'] = np.maximum(
        df['high'] - df['low'],
        np.maximum(
            abs(df['high'] - df['close'].shift()),
            abs(df['low'] - df['close'].shift())
        )
    )
    df['atr'] = df['tr'].rolling(14).mean()

    return df

# --- SELECT ---
symbol = st.selectbox("Activo", symbols)

df = get_data(symbol)

row = df.iloc[-1]
prev = df.iloc[-2]

price = row['close']

# --- SIGNAL ---
signal = None
if prev['close'] < prev['ema20'] and price > row['ema20']:
    signal = "long"
elif prev['close'] > prev['ema20'] and price < row['ema20']:
    signal = "short"

# --- ENTRY ---
if st.session_state.trade is None and signal:

    atr = row['atr']
    if not np.isnan(atr):

        risk = st.session_state.balance * 0.01
        stop_dist = atr * 0.8

        st.session_state.trade = {
            "entry": price,
            "direction": signal,
            "stop": price - stop_dist if signal == "long" else price + stop_dist,
            "tp": price + stop_dist*3 if signal == "long" else price - stop_dist*3,
            "half": False,
            "risk": risk,
            "entry_time": row['time'],
            "symbol": symbol
        }

        st.session_state.entries.append((row['time'], price))

# --- TRADE MANAGEMENT ---
if st.session_state.trade:

    t = st.session_state.trade
    high = row['high']
    low = row['low']

    one_r = t['entry'] + (t['entry'] - t['stop']) if t['direction']=="long" else t['entry'] - (t['stop'] - t['entry'])

    exit_reason = None
    pnl = 0

    if t['direction'] == "long":

        if not t['half'] and high >= one_r:
            st.session_state.balance += t['risk']
            t['half'] = True
            t['stop'] = t['entry']

        if low <= t['stop']:
            if not t['half']:
                st.session_state.balance -= t['risk']
                pnl = -t['risk']
            else:
                pnl = 0
            exit_reason = "STOP"

        elif high >= t['tp']:
            st.session_state.balance += t['risk'] * 2
            pnl = t['risk'] * 2
            exit_reason = "TP"

    # --- EXIT ---
    if exit_reason:

        log_trade({
            "symbol": t['symbol'],
            "entry_time": t['entry_time'],
            "exit_time": row['time'],
            "direction": t['direction'],
            "entry_price": t['entry'],
            "exit_price": price,
            "pnl": pnl,
            "balance": st.session_state.balance,
            "reason": exit_reason
        })

        st.session_state.exits.append((row['time'], price))
        st.session_state.trade = None

# --- DD ---
peak = max(st.session_state.peak, st.session_state.balance)
st.session_state.peak = peak
dd = (peak - st.session_state.balance) / peak

# --- METRICS ---
col1, col2, col3 = st.columns(3)
col1.metric("Balance", round(st.session_state.balance,2))
col2.metric("Drawdown", f"{round(dd*100,2)} %")
col3.metric("Trade activo", "Sí" if st.session_state.trade else "No")

# --- CHART ---
fig = go.Figure()

fig.add_trace(go.Candlestick(
    x=df['time'],
    open=df['open'],
    high=df['high'],
    low=df['low'],
    close=df['close']
))

fig.add_trace(go.Scatter(
    x=df['time'],
    y=df['ema20'],
    line=dict(color='blue'),
    name="EMA20"
))

for t, p in st.session_state.entries:
    fig.add_trace(go.Scatter(x=[t], y=[p], mode='markers', marker=dict(color='green', size=10)))

for t, p in st.session_state.exits:
    fig.add_trace(go.Scatter(x=[t], y=[p], mode='markers', marker=dict(color='red', size=10)))

fig.update_layout(height=700, xaxis_rangeslider_visible=False)

st.plotly_chart(fig, use_container_width=True)

# --- SHOW LOG ---
if os.path.exists(LOG_FILE):
    st.subheader("📋 Historial de Trades")
    log_df = pd.read_csv(LOG_FILE)
    st.dataframe(log_df.tail(20))

# --- METRICS ---
if os.path.exists(LOG_FILE):

    st.subheader("📊 Métricas del Sistema")

    log_df = pd.read_csv(LOG_FILE)

    if len(log_df) > 0:

        trades = len(log_df)
        wins = log_df[log_df["pnl"] > 0]
        losses = log_df[log_df["pnl"] < 0]

        winrate = len(wins) / trades if trades > 0 else 0

        total_win = wins["pnl"].sum()
        total_loss = abs(losses["pnl"].sum())

        profit_factor = total_win / total_loss if total_loss != 0 else 0

        avg_win = wins["pnl"].mean() if len(wins) > 0 else 0
        avg_loss = losses["pnl"].mean() if len(losses) > 0 else 0

        expectancy = (winrate * avg_win) + ((1 - winrate) * avg_loss)

        # equity curve
        log_df["equity"] = log_df["balance"]

        # drawdown real
        peak = log_df["equity"].cummax()
        dd = (peak - log_df["equity"]) / peak
        max_dd_real = dd.max()

        col1, col2, col3 = st.columns(3)
        col1.metric("Trades", trades)
        col2.metric("Winrate", f"{round(winrate*100,2)} %")
        col3.metric("Profit Factor", round(profit_factor,2))

        col4, col5, col6 = st.columns(3)
        col4.metric("Avg Win", round(avg_win,2))
        col5.metric("Avg Loss", round(avg_loss,2))
        col6.metric("Expectancy", round(expectancy,2))

        st.metric("Max DD Real", f"{round(max_dd_real*100,2)} %")

        # --- EQUITY CURVE ---
        st.subheader("📈 Equity Curve")

        st.line_chart(log_df["equity"])