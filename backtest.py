import pandas as pd
import numpy as np
import matplotlib.pyplot as plt


def load_data(file):
    df = pd.read_excel(file)
    df = df.sort_values("timeOpen")
    df['date'] = pd.to_datetime(df['timeOpen'], unit='ms')

    df.rename(columns={
        "priceOpen": "open",
        "priceHigh": "high",
        "priceLow": "low",
        "priceClose": "close"
    }, inplace=True)

    return df


def prepare(df):
    df_1d = df.resample('1D', on='date').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last'
    }).dropna()

    df_1d['ma200'] = df_1d['close'].rolling(200).mean()
    df['ma200'] = df_1d['ma200'].reindex(df['date'], method='ffill').values

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


# --- CARGA ---
btc = prepare(load_data("bitcoin.xlsx"))
eth = prepare(load_data("ethereum.xlsx"))

assets = [btc, eth]

balance = 1000
risk_per_trade = 0.01

fee = 0.0004
slippage = 0.0002

equity = []
drawdowns = []

peak_balance = balance

trade_count = 0
wins = 0
losses = 0

total_R = 0

# --- NUEVO ---
last_trade_index = -50
cooldown = 3


for i in range(200, len(btc)-1):

    for df in assets:

        row = df.iloc[i]
        prev = df.iloc[i-1]

        # --- COOLDOWN ---
        if i - last_trade_index < cooldown:
            continue

        # --- FILTROS BASE ---

        if row['atr'] > row['atr_mean'] * 2:
            continue

        if row['dist_ma'] < 0.01:
            continue

        # --- NUEVO: FILTRO SUAVE DE MOMENTUM ---
        momentum = abs(row['close'] - prev['close']) / prev['close']
        if momentum < 0.002:
            continue

        if row['close'] > row['ma200']:
            direction = "long"
        elif row['close'] < row['ma200']:
            direction = "short"
        else:
            continue

        # EMA cross limpio
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

        if direction == "long":
            stop = price - atr * stop_mult
            one_r = price + (price - stop)
            tp = price + (price - stop) * 2
        else:
            stop = price + atr * stop_mult
            one_r = price - (stop - price)
            tp = price - (stop - price) * 2

        risk = balance * risk_per_trade

        future = df.iloc[i+1:]
        trade_open = True
        half_closed = False

        for _, f in future.iterrows():

            if direction == "long":

                # parcial
                if not half_closed and f['high'] >= one_r:
                    balance += risk * 0.5 * (1 - fee - slippage)
                    total_R += 0.5
                    half_closed = True
                    stop = price

                # stop
                if f['low'] <= stop:
                    if not half_closed:
                        balance -= risk * (1 + fee + slippage)
                        total_R -= 1
                        losses += 1
                    else:
                        wins += 1
                    trade_count += 1
                    trade_open = False
                    break

                # tp
                if f['high'] >= tp:
                    balance += risk * 1.5 * (1 - fee - slippage)
                    total_R += 1.5
                    wins += 1
                    trade_count += 1
                    trade_open = False
                    break

            else:

                if not half_closed and f['low'] <= one_r:
                    balance += risk * 0.5 * (1 - fee - slippage)
                    total_R += 0.5
                    half_closed = True
                    stop = price

                if f['high'] >= stop:
                    if not half_closed:
                        balance -= risk * (1 + fee + slippage)
                        total_R -= 1
                        losses += 1
                    else:
                        wins += 1
                    trade_count += 1
                    trade_open = False
                    break

                if f['low'] <= tp:
                    balance += risk * 1.5 * (1 - fee - slippage)
                    total_R += 1.5
                    wins += 1
                    trade_count += 1
                    trade_open = False
                    break

        if not trade_open:
            last_trade_index = i
            break

    peak_balance = max(peak_balance, balance)
    dd = (peak_balance - balance) / peak_balance

    equity.append(balance)
    drawdowns.append(dd)


# --- RESULTADOS ---
max_dd = max(drawdowns) if drawdowns else 0
winrate = wins / trade_count if trade_count > 0 else 0
expectancy = total_R / trade_count if trade_count > 0 else 0

print("Balance final:", round(balance, 2))
print("Max Drawdown:", round(max_dd * 100, 2), "%")
print("Trades:", trade_count)
print("Winrate:", round(winrate, 2))
print("Expectancy (R):", round(expectancy, 2))

plt.plot(equity)
plt.title("Equity Curve (FINAL VERSION)")
plt.show()