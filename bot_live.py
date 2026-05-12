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

# --- CONTROL ---
last_signal = None

# --- CSV ---
def init_csv():
    if not os.path.exists("trades.csv"):
        with open("trades.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "fecha",
                "simbolo",
                "direccion",
                "precio_entrada",
                "stop",
                "tp"
            ])

def save_trade(fecha, simbolo, direccion, precio_entrada, stop, tp):
    with open("trades.csv", "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            fecha,
            simbolo,
            direccion,
            precio_entrada,
            stop,
            tp
        ])

# --- TELEGRAM ---
def send(msg):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

        requests.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "text": msg
            },
            timeout=10
        )

    except Exception as e:
        logging.error(f"Telegram error: {e}")

# --- DATA ---
def get_data(symbol):

    max_retries = 3

    for attempt in range(max_retries):

        try:

            klines = client.get_klines(
                symbol=symbol,
                interval=interval,
                limit=1000
            )

            df = pd.DataFrame(klines, columns=[
                'time',
                'open',
                'high',
                'low',
                'close',
                'volume',
                'ct',
                'qav',
                'n',
                'tbbav',
                'tbqav',
                'ignore'
            ])

            df['time'] = pd.to_datetime(df['time'], unit='ms')

            numeric_cols = ['open', 'high', 'low', 'close']

            for col in numeric_cols:
                df[col] = df[col].astype(float)

            # --- MA200 ---
            df['ma200'] = df['close'].rolling(200).mean()

            # --- EMA20 ---
            df['ema20'] = df['close'].ewm(
                span=20,
                adjust=False
            ).mean()

            # --- DISTANCIA MA ---
            df['dist_ma'] = (
                abs(df['close'] - df['ma200']) / df['ma200']
            )

            # --- ATR ---
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

        except Exception as e:

            logging.error(
                f"{symbol} error Binance intento {attempt + 1}: {e}"
            )

            time.sleep(2)

    return None

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

            # --- USAR VELA CERRADA ---
            row = df.iloc[-2]
            prev = df.iloc[-3]

            logging.info(
                f"{symbol} | "
                f"close={row['close']:.2f} "
                f"ema20={row['ema20']:.2f} "
                f"ma200={row['ma200']:.2f}"
            )

            # --- VALIDACIONES ---
            if np.isnan(row['ma200']):
                continue

            if np.isnan(row['atr']):
                continue

            if np.isnan(row['atr_mean']):
                continue

            # --- FILTRO VOLATILIDAD ---
            if row['atr'] > row['atr_mean'] * 2:
                logging.info(f"{symbol} ❌ ATR alto")
                continue

            # --- FILTRO DISTANCIA ---
            if row['dist_ma'] < 0.01:
                logging.info(f"{symbol} ❌ dist_ma")
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
                    logging.info(f"{symbol} ❌ EMA20 long")
                    continue

                if row['close'] <= row['ema20']:
                    continue

            else:

                if prev['close'] < prev['ema20']:
                    logging.info(f"{symbol} ❌ EMA20 short")
                    continue

                if row['close'] >= row['ema20']:
                    continue

            # --- PRECIOS ---
            price = row['close']

            signal_id = f"{symbol}_{direction}_{round(price, 2)}"

            # --- EVITAR DUPLICADOS ---
            if last_signal == signal_id:
                logging.info(f"{symbol} ⏳ señal ya ejecutada")
                continue

            atr = row['atr']
            stop_mult = 0.8

            if direction == "long":

                stop = price - atr * stop_mult

                tp = price + (
                    (price - stop) * 3
                )

            else:

                stop = price + atr * stop_mult

                tp = price - (
                    (stop - price) * 3
                )

            # --- GUARDAR ÚLTIMA SEÑAL ---
            last_signal = signal_id

            # --- GUARDAR CSV ---
            fecha = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            save_trade(
                fecha,
                symbol,
                direction,
                round(price, 2),
                round(stop, 2),
                round(tp, 2)
            )

            # --- TELEGRAM ---
            msg = f"""
🚀 TRADE DETECTADO

{symbol}

Tipo: {direction}

Entrada: {round(price, 2)}

Stop: {round(stop, 2)}

TP: {round(tp, 2)}
"""

            send(msg)

            logging.info(msg)

        # --- ESPERA ---
        time.sleep(300)

    except Exception as e:

        logging.error(f"ERROR LOOP: {e}")

        send(f"⚠️ ERROR: {e}")

        time.sleep(60)