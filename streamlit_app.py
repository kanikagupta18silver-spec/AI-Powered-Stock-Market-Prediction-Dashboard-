from xgboost import XGBRegressor
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import mplfinance as mpf
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression

# ---------------- PAGE CONFIG ---------------- #

st.set_page_config(
    page_title="Stock Prediction Dashboard",
    page_icon="📈",
    layout="wide"
)

# ---------------- CUSTOM CSS ---------------- #

st.markdown("""
<style>

.stApp {
    background-color: #0E1117;
    color: white;
}

h1, h2, h3 {
    color: white;
}

</style>
""", unsafe_allow_html=True)

# ---------------- TITLE ---------------- #

st.title("📈 Stock Price Prediction App")

st.markdown("""
### Real-Time Stock Market Prediction Dashboard  
Built using Machine Learning, Streamlit, and Financial Data Analysis
""")

# ---------------- AUTO REFRESH ---------------- #

st_autorefresh(
    interval=60000,
    key="stock_refresh"
)

# ---------------- SIDEBAR ---------------- #

st.sidebar.title("📊 Dashboard Settings")

stock_name = st.sidebar.selectbox(
    "Select Stock",
    ["AAPL", "MSFT", "GOOGL", "TSLA", "AMZN"]
)

stock_name = stock_name.upper()

# ---------------- DOWNLOAD STOCK DATA ---------------- #

stock = yf.download(
    stock_name,
    start="2020-01-01"
)

# ---------------- FIX MULTI-INDEX COLUMNS ---------------- #

if isinstance(stock.columns, pd.MultiIndex):
    stock.columns = stock.columns.get_level_values(0)

# ---------------- STOCK NEWS ---------------- #

st.divider()

st.subheader(f"📰 Latest {stock_name} News")

try:

    ticker = yf.Ticker(stock_name)

    news = ticker.news

    if news:

        for item in news[:5]:
            title = item.get("title")
            
            if not title:
                continue

            publisher = item.get(
                "publisher",
                "Unknown Publisher"
            )

            link = item.get("link", "")

            st.markdown(f"### {title}")

            st.write(publisher)

            st.write(link)

            st.divider()

    else:

        st.write("No news available.")

except Exception:

    st.warning("Unable to load news at the moment.")

# ---------------- LATEST PRICE ---------------- #

latest_close = stock['Close'].to_numpy().flatten()[-1]

previous_close = stock['Close'].to_numpy().flatten()[-2]

change = latest_close - previous_close

change_percent = (change / previous_close) * 100

col1, col2 = st.columns(2)

with col1:

    st.metric(
        label=f"{stock_name} Latest Price",
        value=f"${latest_close:.2f}"
    )

with col2:

    st.metric(
        label="Daily Change",
        value=f"{change:.2f} USD",
        delta=f"{change_percent:.2f}%"
    )

# ---------------- MOVING AVERAGES ---------------- #

stock['MA20'] = stock['Close'].rolling(20).mean()

stock['MA50'] = stock['Close'].rolling(50).mean()

# Buy/Sell signals
# ---------------- RSI ---------------- #

delta = stock['Close'].diff()

gain = delta.where(
    delta > 0,
    0
)

loss = -delta.where(
    delta < 0,
    0
)

avg_gain = gain.rolling(
    window=14
).mean()

avg_loss = loss.rolling(
    window=14
).mean()

rs = avg_gain / avg_loss

stock['RSI'] = 100 - (
    100 / (1 + rs)
)

# ---------------- MACD ---------------- #

ema12 = stock['Close'].ewm(
    span=12,
    adjust=False
).mean()

ema26 = stock['Close'].ewm(
    span=26,
    adjust=False
).mean()

stock['MACD'] = ema12 - ema26

stock['Signal'] = 0

stock.loc[
    stock['MA20'] > stock['MA50'],
    'Signal'
] = 1

stock.loc[
    stock['MA20'] < stock['MA50'],
    'Signal'
] = -1

# ---------------- CANDLESTICK CHART ---------------- #

st.divider()

st.subheader("Candlestick Chart")

candlestick_data = stock[
    ['Open', 'High', 'Low', 'Close', 'Volume']
].copy()

# Convert columns to numeric

for column in candlestick_data.columns:

    candlestick_data[column] = pd.to_numeric(
        candlestick_data[column],
        errors='coerce'
    )

candlestick_data = candlestick_data.dropna()

fig2, axlist = mpf.plot(
    candlestick_data,
    type='candle',
    mav=(20, 50),
    volume=True,
    style='yahoo',
    figsize=(12, 6),
    warn_too_much_data=10000,
    returnfig=True
)

st.pyplot(fig2)

# ---------------- TRADING SIGNALS ---------------- #

st.divider()

st.subheader("📈 Buy/Sell Trading Signals")

latest_signal = stock['Signal'].iloc[-1]

if latest_signal == 1:

    st.success("BUY Signal Detected")

elif latest_signal == -1:

    st.error("SELL Signal Detected")

else:

    st.warning("No Clear Signal")

# ---------------- STOCK DATA TABLE ---------------- #

st.divider()

st.subheader("Stock Data")

st.write(stock.head())

# ---------------- INTERACTIVE STOCK GRAPH ---------------- #

st.divider()

st.subheader("📊 Interactive Stock Analysis")

fig = go.Figure()

# Close Price

fig.add_trace(
    go.Scatter(
        x=stock.index,
        y=stock['Close'],
        mode='lines',
        name='Close Price'
    )
)

# MA20

fig.add_trace(
    go.Scatter(
        x=stock.index,
        y=stock['MA20'],
        mode='lines',
        name='MA20'
    )
)

# MA50

fig.add_trace(
    go.Scatter(
        x=stock.index,
        y=stock['MA50'],
        mode='lines',
        name='MA50'
    )
)

# BUY signals

buy_signals = stock[
    stock['Signal'] == 1
]

fig.add_trace(
    go.Scatter(
        x=buy_signals.index,
        y=buy_signals['Close'],
        mode='markers',
        name='BUY',
        marker=dict(
            size=10,
            symbol='triangle-up'
        )
    )
)

# SELL signals

sell_signals = stock[
    stock['Signal'] == -1
]

fig.add_trace(
    go.Scatter(
        x=sell_signals.index,
        y=sell_signals['Close'],
        mode='markers',
        name='SELL',
        marker=dict(
            size=10,
            symbol='triangle-down'
        )
    )
)

fig.update_layout(
    template='plotly_dark',
    height=600,
    xaxis_title='Date',
    yaxis_title='Price',
    title=f'{stock_name} Interactive Trading Dashboard'
)

st.plotly_chart(
    fig,
    use_container_width=True
)

# ---------------- RSI GRAPH ---------------- #

st.divider()

st.subheader("RSI Indicator")

fig_rsi = plt.figure(figsize=(12, 4))

plt.plot(
    stock['RSI'],
    label='RSI'
)

plt.axhline(
    70,
    linestyle='--'
)

plt.axhline(
    30,
    linestyle='--'
)

plt.xlabel("Date")

plt.ylabel("RSI")

plt.legend()

st.pyplot(fig_rsi)

# ---------------- MACD GRAPH ---------------- #

st.divider()

st.subheader("MACD Indicator")

fig_macd = plt.figure(figsize=(12, 4))

plt.plot(
    stock['MACD'],
    label='MACD'
)

plt.axhline(
    0,
    linestyle='--'
)

plt.xlabel("Date")

plt.ylabel("MACD")

plt.legend()

st.pyplot(fig_macd)

# ---------------- MACHINE LEARNING ---------------- #

future_days = 30

stock['Prediction'] = stock['Close'].shift(-future_days)

stock = stock.dropna()

X = np.array(stock[['Close']])

y = np.array(stock['Prediction'])

# ---------------- TRAIN TEST SPLIT ---------------- #

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42
)

# ---------------- XGBOOST MODEL ---------------- #

model = XGBRegressor(
    n_estimators=100,
    learning_rate=0.1,
    max_depth=5,
    random_state=42
)

model.fit(
    X_train,
    y_train
)

# ---------------- PREDICTIONS ---------------- #

predictions = model.predict(X_test)

# ---------------- ACCURACY ---------------- #

accuracy = model.score(X_test, y_test)

st.divider()

st.subheader("Model Accuracy")

st.metric(
    "Model Accuracy Score",
    f"{accuracy:.2f}"
)

# ---------------- ACTUAL VS PREDICTED ---------------- #

st.divider()

st.subheader("Actual vs Predicted Prices")

fig3 = plt.figure(figsize=(12, 6))

plt.plot(
    y_test[:100],
    label='Actual'
)

plt.plot(
    predictions[:100],
    label='Predicted'
)

plt.xlabel("Data Points")

plt.ylabel("Price")

plt.legend()

st.pyplot(fig3)

# ---------------- FUTURE PREDICTION ---------------- #

st.divider()

st.subheader("Future Stock Price Prediction")

latest_price = stock['Close'].to_numpy().flatten()[-1]

future_price = model.predict(
    [[latest_price]]
)

st.write(
    f"Predicted Price After {future_days} Days:",
    round(float(future_price[0]), 2)
)