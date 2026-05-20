import csv
import json
import logging
import os
import time
from datetime import datetime

import numpy as np
import pandas as pd
import requests
from binance.client import Client

# =========================
# CONFIG
# =========================

API_KEY = ""
API_SECRET = ""

TOKEN = "TU_TOKEN"
CHAT_ID = "TU_CHAT_ID"

symbols = ["BTCUSDT", "ETHUSDT"]

interval = Client.KLINE_INTERVAL_4HOUR

client = Client(
    API_KEY,
    API_SECRET,
    requests_params={"timeout": 10}
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

# =========================
# RISK
# =========================

balance = 1000
peak_balance = 1000

risk_per_trade = 0.01

# =========================
# FILES
# =========================

TRADES_FILE = "trades.csv"
ACTIVE_TRADE_FILE = "active_trade.json"

# =========================
# CSV
# =========================

def init_csv():

    if not os.path.exists(TRADES_FILE):

        with open(TRADES_FILE, "w", newline="", encoding="utf-8") as f:

            writer = csv.writer(f)

            writer.writerow([
                "fecha",
                "tipo",
                "simbolo",
                "direccion",
                "entrada",
                "stop",
                "tp",
                "resultado",
                "balance"
            ])

# =========================
# TELEGRAM
# =========================

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

# =========================
# ACTIVE TRADE
# =========================

def save_active_trade(trade):

    with open(ACTIVE_TRADE_FILE, "w") as f:
        json.dump(trade, f)

def load_active_trade():

    if not os.path.exists(ACTIVE_TRADE_FILE):
        return None

    with open(ACTIVE_TRADE_FILE, "r") as f:
        return json.load(f)

def clear_active_trade():

    if os.path.exists(ACTIVE_TRADE_FILE):
        os.remove(ACTIVE_TRADE_FILE)

# =========================
# SAVE CSV
# =========================

def save_trade(
    tipo,
    simbolo,
    direccion,
    entrada,
    stop,
    tp,
    resultado,
    balance_actual
):

    with open(TRADES_FILE, "a", newline="", encoding="utf-8") as f:

        writer = csv.writer(f)

        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            tipo,
            simbolo,
            direccion,
            round(entrada, 2),
            round(stop, 2),
            round(tp, 2),
            resultado,
            round(balance_actual, 2)
        ])

# =========================
# DATA
# =========================

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

            numeric_cols = [
                'open',
                'high',
                'low',
                'close'
            ]

            for col in numeric_cols:
                df[col] = df[col].astype(float)

            # =========================
            # INDICATORS
            # =========================

            df['ma200'] = df['close'].rolling(200).mean()

            df['ema20'] = df['close'].ewm(
                span=20,
                adjust=False
            ).mean()

            df['dist_ma'] = (
                abs(df['close'] - df['ma200']) / df['ma200']
            )

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
                f"{symbol} Binance error intento {attempt+1}: {e}"
            )

            time.sleep(2)

    return None

# =========================
# CHECK OPEN TRADE
# =========================

def manage_trade():

    global balance
    global peak_balance

    trade = load_active_trade()

    if trade is None:
        return

    symbol = trade['symbol']

    df = get_data(symbol)

    if df is None:
        return

    row = df.iloc[-1]

    high = row['high']
    low = row['low']

    direction = trade['direction']

    entry = trade['entry']
    stop = trade['stop']
    tp = trade['tp']

    risk_amount = balance * risk_per_trade

    # =========================
    # LONG
    # =========================

    if direction == "long":

        # STOP
        if low <= stop:

            balance -= risk_amount

            peak_balance = max(
                peak_balance,
                balance
            )

            msg = f"""
❌ STOP HIT

{symbol}

LONG

Entrada: {entry}
Stop: {stop}

Balance: {round(balance,2)}
"""

            send(msg)

            logging.info(msg)

            save_trade(
                "STOP",
                symbol,
                direction,
                entry,
                stop,
                tp,
                -risk_amount,
                balance
            )

            clear_active_trade()

            return

        # TAKE PROFIT
        if high >= tp:

            reward = risk_amount * 3

            balance += reward

            peak_balance = max(
                peak_balance,
                balance
            )

            msg = f"""
✅ TAKE PROFIT

{symbol}

LONG

Entrada: {entry}
TP: {tp}

Balance: {round(balance,2)}
"""

            send(msg)

            logging.info(msg)

            save_trade(
                "TP",
                symbol,
                direction,
                entry,
                stop,
                tp,
                reward,
                balance
            )

            clear_active_trade()

            return

    # =========================
    # SHORT
    # =========================

    else:

        # STOP
        if high >= stop:

            balance -= risk_amount

            peak_balance = max(
                peak_balance,
                balance
            )

            msg = f"""
❌ STOP HIT

{symbol}

SHORT

Entrada: {entry}
Stop: {stop}

Balance: {round(balance,2)}
"""

            send(msg)

            logging.info(msg)

            save_trade(
                "STOP",
                symbol,
                direction,
                entry,
                stop,
                tp,
                -risk_amount,
                balance
            )

            clear_active_trade()

            return

        # TP
        if low <= tp:

            reward = risk_amount * 3

            balance += reward

            peak_balance = max(
                peak_balance,
                balance
            )

            msg = f"""
✅ TAKE PROFIT

{symbol}

SHORT

Entrada: {entry}
TP: {tp}

Balance: {round(balance,2)}
"""

            send(msg)

            logging.info(msg)

            save_trade(
                "TP",
                symbol,
                direction,
                entry,
                stop,
                tp,
                reward,
                balance
            )

            clear_active_trade()

            return

# =========================
# FIND SIGNALS
# =========================

def find_signals():

    trade = load_active_trade()

    if trade is not None:

        logging.info("⏳ Trade activo")

        return

    for symbol in symbols:

        df = get_data(symbol)

        if df is None or len(df) < 210:
            continue

        row = df.iloc[-2]
        prev = df.iloc[-3]

        logging.info(
            f"{symbol} | "
            f"close={row['close']:.2f} "
            f"ema20={row['ema20']:.2f} "
            f"ma200={row['ma200']:.2f}"
        )

        # =========================
        # VALIDATIONS
        # =========================

        if np.isnan(row['ma200']):
            continue

        if np.isnan(row['atr']):
            continue

        if np.isnan(row['atr_mean']):
            continue

        # =========================
        # FILTERS
        # =========================

        if row['atr'] > row['atr_mean'] * 2:

            logging.info(f"{symbol} ❌ ATR")

            continue

        if row['dist_ma'] < 0.01:

            logging.info(f"{symbol} ❌ DIST")

            continue

        # =========================
        # DIRECTION
        # =========================

        if row['close'] > row['ma200']:

            direction = "long"

        elif row['close'] < row['ma200']:

            direction = "short"

        else:
            continue

        # =========================
        # EMA CROSS
        # =========================

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

        # =========================
        # TRADE
        # =========================

        price = row['close']

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

        trade_data = {
            "symbol": symbol,
            "direction": direction,
            "entry": float(price),
            "stop": float(stop),
            "tp": float(tp)
        }

        save_active_trade(trade_data)

        msg = f"""
🚀 NUEVA OPERACIÓN

{symbol}

Tipo: {direction}

Entrada: {round(price,2)}

Stop: {round(stop,2)}

TP: {round(tp,2)}

Balance: {round(balance,2)}
"""

        send(msg)

        logging.info(msg)

        save_trade(
            "ENTRY",
            symbol,
            direction,
            price,
            stop,
            tp,
            0,
            balance
        )

        return

# =========================
# MAIN
# =========================

init_csv()

send("🤖 BOT LIVE INICIADO")

while True:

    try:

        logging.info("🔍 LOOP")

        manage_trade()

        find_signals()

        dd = (
            (peak_balance - balance)
            / peak_balance
        ) * 100

        logging.info(
            f"Balance={round(balance,2)} "
            f"DD={round(dd,2)}%"
        )

        time.sleep(300)

    except Exception as e:

        logging.error(f"ERROR LOOP: {e}")

        send(f"⚠️ ERROR: {e}")

        time.sleep(60)