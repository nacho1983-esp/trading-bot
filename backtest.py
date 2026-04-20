import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# --- CARGA ---
def load(file):
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

    df['tr'] = np.maximum(
        df['high'] - df['low'],
        np.maximum(
            abs(df['high'] - df['close'].shift()),
            abs(df['low'] - df['close'].shift())
        )
    )
    df['atr'] = df['tr'].rolling(14).mean()

    return df

btc = prepare(load("bitcoin.xlsx"))
eth = prepare(load("ethereum.xlsx"))
xrp = prepare(load("ripple.xlsx"))

assets = [btc, eth, xrp]

balance = 1000
peak = 1000
risk_per_trade = 0.01

equity = []
drawdowns = []

open_trade = False

trades = 0
wins = 0
losses = 0

for i in range(50, len(btc)-20):

    dd = (peak - balance) / peak
    drawdowns.append(dd)

    if open_trade:
        equity.append(balance)
        continue

    for df in assets:

        row = df.iloc[i]
        prev = df.iloc[i-1]

        if row['close'] > row['ma200']:
            direction = "long"
        elif row['close'] < row['ma200']:
            direction = "short"
        else:
            continue

        if direction == "long":
            if not (prev['close'] < prev['ema20'] and row['close'] > row['ema20']):
                continue
        else:
            if not (prev['close'] > prev['ema20'] and row['close'] < row['ema20']):
                continue

        atr = row['atr']
        if np.isnan(atr):
            continue

        price = row['close']
        stop_dist = atr * 0.8

        if direction == "long":
            stop = price - stop_dist
            tp = price + stop_dist*3
        else:
            stop = price + stop_dist
            tp = price - stop_dist*3

        risk = balance * risk_per_trade

        future = df.iloc[i+1:i+20]

        open_trade = True

        for _, f in future.iterrows():

            if direction == "long":

                if f['low'] <= stop:
                    balance -= risk
                    losses += 1
                    trades += 1
                    open_trade = False
                    break

                if f['high'] >= tp:
                    balance += risk*3
                    wins += 1
                    trades += 1
                    open_trade = False
                    break

            else:

                if f['high'] >= stop:
                    balance -= risk
                    losses += 1
                    trades += 1
                    open_trade = False
                    break

                if f['low'] <= tp:
                    balance += risk*3
                    wins += 1
                    trades += 1
                    open_trade = False
                    break

        break

    peak = max(peak, balance)
    equity.append(balance)

max_dd = max(drawdowns) if drawdowns else 0

print("Balance final:", round(balance,2))
print("Max DD:", round(max_dd*100,2), "%")
print("Trades:", trades)
print("Winrate:", round(wins/trades,2) if trades > 0 else 0)

plt.plot(equity)
plt.title("Equity Curve MULTI-ACTIVO (BTC+ETH+XRP)")
plt.show()