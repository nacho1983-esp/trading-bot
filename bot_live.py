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
            writer.writerow(["fecha", "simbolo", "direccion", "precio_entrada", "stop", "tp"])

def save_trade(fecha, simbolo, direccion, precio_entrada, stop, tp):
    with open("trades.csv", "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([fecha, simbolo, direccion, precio_entrada, stop, tp])

# --- TELEGRAM ---
def send(msg):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg}, timeout=10)
    except Exception as e:
        logging.error(f"Telegram error: {e}")

# --- DATA ---
def get_data(symbol):
    try:
        klines = client.get_klines(symbol=symbol, interval=interval, limit=1000)
    except Exception as e:
        logging.error(f"{symbol} error Binance: {e}")
        return None

    df = pd.DataFrame(klines, columns=[
        'time','open','high','low','close','volume',
        'ct','qav','n','tbbav','tbqav','ignore'
    ])

    df['time'] = pd.to_datetime(df['time'], unit='ms')
    df['open'] = df['open'].astype(float)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    df['close'] = df['close'].astype(float)

    # --- 🔥 FIX REAL: MA200 EN 4H (NO DIARIA) ---
    df['ma200'] = df['close'].rolling(200).mean()

    # --- indicadores ---
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

# --- MAIN ---
init_csv()
send("🤖 BOT INICIADO")

while True:

    try:
        logging.info("🔍 Buscando señal...")

        for symbol in symbols:

            df = get_data(symbol)
            if df is None or len(df) < 210:
                continue

            # 🔥 vela cerrada
            row = df.iloc[-2]
            prev = df.iloc[-3]

            # 🔍 DEBUG CLARO
            logging.info(
                f"{symbol} | close={row['close']:.2f} ema20={row['ema20']:.2f} ma200={row['ma200']:.2f}"
            )

            # evitar NaN
            if np.isnan(row['ma200']):
                logging.info(f"{symbol} ❌ ma200 nan")
                continue

            # --- FILTROS ---
            if row['atr'] > row['atr_mean'] * 2:
                continue

            if row['dist_ma'] < 0.01:
                continue

            # --- DIRECCIÓN ---
            if row['close'] > row['ma200']:
                direction = "long"
            elif row['close'] < row['ma200']:
                direction = "short"
            else:
                continue

            # --- CRUCE EMA20 ---
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
            stop_mult = 0.8

            if direction == "long":
                stop = price - atr * stop_mult
                tp = price + (price - stop) * 3
            else:
                stop = price + atr * stop_mult
                tp = price - (stop - price) * 3

            # --- GUARDAR ---
            fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_trade(fecha, symbol, direction, price, stop, tp)

            msg = f"""
🚀 TRADE DETECTADO
{symbol}

Tipo: {direction}
Entrada: {round(price,2)}
Stop: {round(stop,2)}
TP: {round(tp,2)}
"""

            send(msg)
            logging.info(msg)

        time.sleep(300)

    except Exception as e:
        logging.error(e)
        send(f"⚠️ ERROR {e}")
        time.sleep(60)