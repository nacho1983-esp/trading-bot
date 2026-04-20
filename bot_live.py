import pandas as pd
import numpy as np
from binance.client import Client
import time
import requests
from datetime import datetime
import logging

API_KEY = ""
API_SECRET = ""

TOKEN = "8620461652:AAH-49pOR11qqhwehF6cf6jKvsEVQxYQMl0"
CHAT_ID = "5629864767"

symbols = ["BTCUSDT", "ETHUSDT", "XRPUSDT"]
interval = Client.KLINE_INTERVAL_1HOUR

balance = 1000
peak = 1000
risk_per_trade = 0.01

trade = None

logging.basicConfig(level=logging.INFO)

client = Client(API_KEY, API_SECRET)

def send(msg):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg})

def get_data(symbol):
    klines = client.get_klines(symbol=symbol, interval=interval, limit=100)

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

send("🚀 BOT PRO INICIADO")

while True:
    try:
        print("\n🔍 Buscando...")

        for symbol in symbols:

            df = get_data(symbol)

            row = df.iloc[-1]
            prev = df.iloc[-2]

            price = row['close']

            # ---- GESTIÓN TRADE ----
            if trade and trade['symbol'] == symbol:

                high = row['high']
                low = row['low']

                if trade['direction'] == "long":

                    if low <= trade['stop']:
                        balance -= trade['risk']
                        send(f"❌ STOP {symbol} | Balance: {round(balance,2)}")
                        trade = None

                    elif high >= trade['tp']:
                        balance += trade['risk'] * 3
                        send(f"✅ TP {symbol} | Balance: {round(balance,2)}")
                        trade = None

                else:

                    if high >= trade['stop']:
                        balance -= trade['risk']
                        send(f"❌ STOP {symbol} | Balance: {round(balance,2)}")
                        trade = None

                    elif low <= trade['tp']:
                        balance += trade['risk'] * 3
                        send(f"✅ TP {symbol} | Balance: {round(balance,2)}")
                        trade = None

            # ---- NUEVAS ENTRADAS ----
            if trade is None:

                signal = None

                if prev['close'] < prev['ema20'] and price > row['ema20']:
                    signal = "long"

                elif prev['close'] > prev['ema20'] and price < row['ema20']:
                    signal = "short"

                if signal:

                    atr = row['atr']
                    if np.isnan(atr):
                        continue

                    risk = balance * risk_per_trade

                    if signal == "long":
                        stop = price - atr
                        tp = price + (price - stop) * 3
                    else:
                        stop = price + atr
                        tp = price - (stop - price) * 3

                    trade = {
                        "symbol": symbol,
                        "direction": signal,
                        "entry": price,
                        "stop": stop,
                        "tp": tp,
                        "risk": risk
                    }

                    send(f"""
🚀 TRADE
{symbol}
{signal.upper()}

Entry: {round(price,2)}
Stop: {round(stop,2)}
TP: {round(tp,2)}
""")

        # ---- DRAWDOWN ----
        peak = max(peak, balance)
        dd = (peak - balance) / peak

        print(f"Balance: {round(balance,2)} | DD: {round(dd*100,2)}%")

        # ---- PROTECCIÓN ----
        if dd > 0.10:
            send(f"🛑 BOT STOPPED - DD {round(dd*100,2)}%")
            break

        time.sleep(60)

    except Exception as e:
        send(f"⚠️ ERROR {e}")
        time.sleep(60)