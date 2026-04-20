import logging
import time
from datetime import datetime

import numpy as np
import pandas as pd
import requests
from binance.client import Client

API_KEY = ""
API_SECRET = ""

TOKEN = "8620461652:AAH-49pOR11qqhwehF6cf6jKvsEVQxYQMl0"
CHAT_ID = "5629864767"

symbols = ["BTCUSDT", "ETHUSDT"]
interval = Client.KLINE_INTERVAL_4HOUR

balance = 1000
risk_per_trade = 0.01
open_trade = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

client = Client(API_KEY, API_SECRET)


def send(msg: str) -> bool:
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg}

    try:
        r = requests.post(url, data=payload, timeout=15)
        logging.info("Telegram status=%s body=%s", r.status_code, r.text)

        if r.status_code != 200:
            logging.error("Telegram HTTP error: %s", r.status_code)
            return False

        data = r.json()
        if not data.get("ok", False):
            logging.error("Telegram API error: %s", data)
            return False

        return True
    except Exception:
        logging.exception("Fallo enviando mensaje a Telegram")
        return False


def check_telegram() -> bool:
    try:
        r = requests.get(f"https://api.telegram.org/bot{TOKEN}/getMe", timeout=15)
        logging.info("Telegram getMe status=%s body=%s", r.status_code, r.text)
        if r.status_code != 200:
            return False
        data = r.json()
        return data.get("ok", False)
    except Exception:
        logging.exception("Error validando TOKEN de Telegram")
        return False


def get_data(symbol: str) -> pd.DataFrame:
    klines = client.get_klines(symbol=symbol, interval=interval, limit=100)

    df = pd.DataFrame(
        klines,
        columns=[
            "time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "ct",
            "qav",
            "n",
            "tbbav",
            "tbqav",
            "ignore",
        ],
    )

    df["time"] = pd.to_datetime(df["time"], unit="ms")
    df["open"] = df["open"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["close"] = df["close"].astype(float)

    df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()

    df["tr"] = np.maximum(
        df["high"] - df["low"],
        np.maximum(
            abs(df["high"] - df["close"].shift()),
            abs(df["low"] - df["close"].shift()),
        ),
    )
    df["atr"] = df["tr"].rolling(14).mean()
    df["atr_ma20"] = df["atr"].rolling(20).mean()

    return df


def main() -> None:
    if not check_telegram():
        logging.error(
            "Telegram no responde correctamente. Verifica TOKEN (si da 404, el token es inválido)."
        )

    send("🤖 BOT INICIADO")

    while True:
        try:
            logging.info("🔍 Buscando señal...")

            for symbol in symbols:
                logging.info("--- %s ---", symbol)

                df = get_data(symbol)
                row = df.iloc[-1]
                prev = df.iloc[-2]

                price = row["close"]
                logging.info("Precio %s: %s", symbol, price)

                signal = None

                if prev["close"] < prev["ema20"] and price > row["ema20"]:
                    signal = "long"
                elif prev["close"] > prev["ema20"] and price < row["ema20"]:
                    signal = "short"

                if signal:
                    logging.info("🚀 SEÑAL %s detectada, aplicando filtros...", signal.upper())

                    atr = row["atr"]
                    atr_ma20 = row["atr_ma20"]

                    if np.isnan(atr) or np.isnan(atr_ma20):
                        logging.warning("%s filtrada: ATR/ATR_MA20 inválido (NaN).", symbol)
                        continue

                    if signal == "long" and not (row["ema20"] > row["ema50"]):
                        logging.info(
                            "%s filtrada: tendencia no válida para LONG (EMA20 <= EMA50).",
                            symbol,
                        )
                        continue

                    if signal == "short" and not (row["ema20"] < row["ema50"]):
                        logging.info(
                            "%s filtrada: tendencia no válida para SHORT (EMA20 >= EMA50).",
                            symbol,
                        )
                        continue

                    if not (atr > atr_ma20):
                        logging.info(
                            "%s filtrada: volatilidad baja (ATR %.4f <= ATR_MA20 %.4f).",
                            symbol,
                            atr,
                            atr_ma20,
                        )
                        continue

                    candle_body = abs(row["close"] - row["open"])
                    min_body = atr * 0.5
                    if candle_body < min_body:
                        logging.info(
                            "%s filtrada: vela débil (cuerpo %.4f < 50%% ATR %.4f).",
                            symbol,
                            candle_body,
                            min_body,
                        )
                        continue

                    stop_dist = atr * 0.8
                    stop = price - stop_dist if signal == "long" else price + stop_dist
                    tp = price + stop_dist * 3 if signal == "long" else price - stop_dist * 3

                    msg = (
                        f"🚀 TRADE DETECTADO\n"
                        f"{symbol}\n\n"
                        f"Tipo: {signal}\n"
                        f"Entrada: {round(price, 2)}\n"
                        f"Stop: {round(stop, 2)}\n"
                        f"TP: {round(tp, 2)}\n"
                        f"Hora: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
                    )
                    send(msg)
                else:
                    logging.info("❌ No hay señal en %s", symbol)

            time.sleep(60)

        except Exception as e:
            logging.exception("Error en loop principal")
            send(f"⚠️ ERROR: {e}")
            time.sleep(60)


if __name__ == "__main__":
    main()