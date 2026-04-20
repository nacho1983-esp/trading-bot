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
peak_balance = 1000
base_risk = 0.01

fee = 0.0004
slippage = 0.0002

equity = []
drawdowns = []

trade_count = 0
wins = 0
losses = 0

open_trade = False
loss_streak = 0

MAX_DD = 0.15
MAX_LOSS_STREAK = 8

system_active = True


for i in range(50, len(btc)-20):

    drawdown = (peak_balance - balance) / peak_balance
    drawdowns.append(drawdown)

    if drawdown > MAX_DD:
        system_active = False

    if not system_active:
        equity.append(balance)
        continue

    if loss_streak >= MAX_LOSS_STREAK:
        equity.append(balance)
        continue

    if drawdown > 0.1:
        risk_per_trade = base_risk * 0.5
    elif drawdown > 0.05:
        risk_per_trade = base_risk * 0.75
    else:
        risk_per_trade = base_risk

    if open_trade:
        equity.append(balance)
        continue

    for df in assets:

        row = df.iloc[i]
        prev = df.iloc[i-1]

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
            one_r = price + (price - stop)
        else:
            stop = price + atr * stop_mult
            tp = price - (stop - price) * 3
            one_r = price - (stop - price)

        risk = balance * risk_per_trade
        half_closed = False

        future = df.iloc[i+1:i+20]
        open_trade = True

        for j, f in enumerate(future.iterrows()):
            f = f[1]

            if j > 10 and not half_closed:
                balance -= risk * 0.5
                losses += 1
                loss_streak += 1
                trade_count += 1
                open_trade = False
                break

            if direction == "long":

                if not half_closed and f['high'] >= one_r:
                    balance += risk * (1 - fee - slippage)
                    half_closed = True
                    stop = price

                if f['low'] <= stop:
                    if not half_closed:
                        balance -= risk * (1 + fee + slippage)
                        losses += 1
                        loss_streak += 1
                    else:
                        loss_streak = 0

                    trade_count += 1
                    open_trade = False
                    break

                if f['high'] >= tp:
                    balance += risk * 2 * (1 - fee - slippage)
                    wins += 1
                    loss_streak = 0
                    trade_count += 1
                    open_trade = False
                    break

            else:

                if not half_closed and f['low'] <= one_r:
                    balance += risk * (1 - fee - slippage)
                    half_closed = True
                    stop = price

                if f['high'] >= stop:
                    if not half_closed:
                        balance -= risk * (1 + fee + slippage)
                        losses += 1
                        loss_streak += 1
                    else:
                        loss_streak = 0

                    trade_count += 1
                    open_trade = False
                    break

                if f['low'] <= tp:
                    balance += risk * 2 * (1 - fee - slippage)
                    wins += 1
                    loss_streak = 0
                    trade_count += 1
                    open_trade = False
                    break

        break

    peak_balance = max(peak_balance, balance)
    equity.append(balance)


max_dd = max(drawdowns) if drawdowns else 0

print("Balance final:", round(balance,2))
print("Max Drawdown:", round(max_dd*100,2), "%")
print("Trades:", trade_count)
print("Winrate:", round(wins/trade_count,2) if trade_count > 0 else 0)

plt.plot(equity)
plt.title("Equity Curve (SAFE SYSTEM)")
plt.show()