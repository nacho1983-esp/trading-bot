import csv
import logging
import os
import time
from datetime import datetime

import numpy as np
import pandas as pd
import requests
from binance.client import Client

# --- CONFIG ---
API_KEY = ""
API_SECRET = ""

TOKEN = "TU_TOKEN"
CHAT_ID = "TU_CHAT_ID"

symbols = ["BTCUSDT", "ETHUSDT"]
interval = Client.KLINE_INTERVAL_4HOUR

client = Client(API_KEY, API_SECRET, requests_params={"timeout": 10})

logging.basicConfig(level=logging.INFO)


# --- CSV ---
def init_csv():
    if not os.path.exists("trades.csv"):
        with open("trades.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "fecha", "simbolo", "direccion",
                "entrada", "stop", "one_r", "tp"
            ])


def save_trade(fecha, simbolo, direccion, entrada, stop, one_r, tp):
    with open("trades.csv", "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([fecha, simbolo, direccion, entrada, stop, one_r, tp])


# --- TELEGRAM ---
def send(msg):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg}, timeout=10)


# --- DATA ---
def get_data(symbol):
    klines = client.get_klines(symbol=symbol, interval=interval, limit=1000)

    df = pd.DataFrame(klines, columns=[
        'time', 'open', 'high', 'low', 'close', 'volume',
        'ct', 'qav', 'n', 'tbbav', 'tbqav', 'ignore'
    ])

    df['time'] = pd.to_datetime(df['time'], unit='ms')
    df[['open', 'high', 'low', 'close']] = df[['open', 'high', 'low', 'close']].astype(float)

    df = df.sort_values('time')

    # --- INDICADORES (IGUAL QUE BACKTEST) ---
    df_1d = df.resample('1D', on='time').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last'
    }).dropna()

    df_1d['ma200'] = df_1d['close'].rolling(200).mean()
    df['ma200'] = df_1d['ma200'].reindex(df['time'], method='ffill').values

    df['ema20'] = df['close'].ewm(span=20).mean()
    df['dist_ma'] = abs(df['close'] - df['ma200']) / df['ma200']

    df['tr'] = np.maximum(
        df['high'] - df['low'],
        np.maximum(
            abs(df['high'] - df['close'].shift()),
            abs(df['low'] - df['close'].shift())
        )
    )

    df['atr'] = df['tr'].rolling(14).mean()
    df['atr_mean'] = df['atr'].rolling(50).mean()

    return df


# --- INIT ---
init_csv()
send("🤖 BOT LIVE V5 INICIADO")

last_signal_time = None


# --- MAIN LOOP ---
while True:

    try:
        logging.info("🔍 Buscando señal...")

        for symbol in symbols:

            df = get_data(symbol)
            if df is None or len(df) < 3:
                continue

            row = df.iloc[-2]
            prev = df.iloc[-3]

            # evitar duplicados
            candle_time = row['time']
            if last_signal_time == candle_time:
                continue

            # --- FILTROS (IGUAL QUE BACKTEST) ---
            if row['atr'] > row['atr_mean'] * 2:
                continue

            if row['dist_ma'] < 0.01:
                continue

            if row['close'] > row['ma200']:
                direction = "long"
            elif row['close'] < row['ma200']:
                direction = "short"
            else:
                continue

            # EMA CROSS
            if direction == "long":
                if prev['close'] > prev['ema20']:
                    continue
                if row['close'] <= row['ema20']:
                    continue
            else:
                if prev['close'] < prev['ema20']:
                    continue
                if row['close'] >= row['ema20']:
                    continue

            atr = row['atr']
            if np.isnan(atr):
                continue

            price = row['close']
            stop_mult = 1.2

            # --- EXACTO BACKTEST V5 ---
            if direction == "long":
                stop = price - atr * stop_mult
                one_r = price + (price - stop)
                tp = price + (price - stop) * 2
            else:
                stop = price + atr * stop_mult
                one_r = price - (stop - price)
                tp = price - (stop - price) * 2

            # --- SAVE ---
            fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_trade(fecha, symbol, direction, price, stop, one_r, tp)

            last_signal_time = candle_time

            # --- MENSAJE ---
            msg = f"""
🚀 TRADE DETECTADO (V5)

{symbol}
Tipo: {direction}

Entrada: {round(price,2)}
Stop: {round(stop,2)}

🎯 Parcial (1R): {round(one_r,2)}
🎯 TP final (2R): {round(tp,2)}

Gestión:
- 50% en 1R
- Stop a Break Even
- Resto hasta 2R
"""

            send(msg)
            logging.info(msg)

        time.sleep(300)

    except Exception as e:
        logging.error(e)
        send(f"⚠️ ERROR {e}")
        time.sleep(60)