import streamlit as st
import pandas as pd
import numpy as np
from binance.client import Client
import plotly.graph_objects as go

API_KEY = ""
API_SECRET = ""

client = Client(API_KEY, API_SECRET)

symbols = ["BTCUSDT", "ETHUSDT"]
interval = Client.KLINE_INTERVAL_4HOUR

st.set_page_config(layout="wide")
st.title("📊 Trading Dashboard PRO")

# --- ESTADO ---
if "balance" not in st.session_state:
    st.session_state.balance = 1000
    st.session_state.peak = 1000
    st.session_state.trade = None
    st.session_state.entries = []
    st.session_state.exits = []

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

# --- SELECCIÓN ACTIVO ---
symbol = st.selectbox("Activo", symbols)

df = get_data(symbol)

row = df.iloc[-1]
prev = df.iloc[-2]

price = row['close']

# --- SEÑAL ---
signal = None
if prev['close'] < prev['ema20'] and price > row['ema20']:
    signal = "long"
elif prev['close'] > prev['ema20'] and price < row['ema20']:
    signal = "short"

# --- LÓGICA TRADING ---
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
            "risk": risk
        }

        st.session_state.entries.append((row['time'], price))

# --- GESTIÓN TRADE ---
if st.session_state.trade:

    t = st.session_state.trade
    high = row['high']
    low = row['low']

    one_r = t['entry'] + (t['entry'] - t['stop']) if t['direction']=="long" else t['entry'] - (t['stop'] - t['entry'])

    if t['direction'] == "long":

        if not t['half'] and high >= one_r:
            st.session_state.balance += t['risk']
            t['half'] = True
            t['stop'] = t['entry']

        if low <= t['stop']:
            if not t['half']:
                st.session_state.balance -= t['risk']
            st.session_state.exits.append((row['time'], price))
            st.session_state.trade = None

        elif high >= t['tp']:
            st.session_state.balance += t['risk'] * 2
            st.session_state.exits.append((row['time'], price))
            st.session_state.trade = None

# --- DRAWDOWN ---
peak = max(st.session_state.peak, st.session_state.balance)
st.session_state.peak = peak
dd = (peak - st.session_state.balance) / peak

# --- MÉTRICAS ---
col1, col2, col3 = st.columns(3)
col1.metric("Balance", round(st.session_state.balance,2))
col2.metric("Drawdown", f"{round(dd*100,2)} %")
col3.metric("Trade activo", "Sí" if st.session_state.trade else "No")

# --- GRÁFICO ---
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

# entradas
for t, p in st.session_state.entries:
    fig.add_trace(go.Scatter(x=[t], y=[p], mode='markers', marker=dict(color='green', size=10)))

# salidas
for t, p in st.session_state.exits:
    fig.add_trace(go.Scatter(x=[t], y=[p], mode='markers', marker=dict(color='red', size=10)))

fig.update_layout(height=700, xaxis_rangeslider_visible=False)

st.plotly_chart(fig, use_container_width=True)