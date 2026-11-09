"""Streamlit entry point for the stock analytics dashboard."""

import os

import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
import yfinance as yf
from streamlit_autorefresh import st_autorefresh
from xgboost.core import XGBoostError

from stock_dashboard.analytics import (
    add_technical_indicators,
    evaluate_and_forecast,
)
from stock_dashboard.market_data import (
    TICKERS,
    RequestException,
    YFException,
    load_stock_history,
)

st.set_page_config(
    page_title="Stock Market Analytics",
    page_icon="📈",
    layout="wide",
)

WINDOWS = {"1 year": 1, "3 years": 3, "5 years": 5, "All history": None}


@st.cache_data(ttl=300, max_entries=10, show_spinner=False)
def load_stock_data(symbol: str, api_url: str | None) -> pd.DataFrame:
    if api_url:
        response = requests.get(
            f"{api_url.rstrip('/')}/api/v1/stocks/{symbol}/history",
            params={"start": "2019-01-01"},
            timeout=30,
        )
        response.raise_for_status()
        history = pd.DataFrame(response.json()["data"])
        history["date"] = pd.to_datetime(history["date"])
        return history.set_index("date").rename(columns=str.title)
    return load_stock_history(symbol, start="2019-01-01")


@st.cache_data(ttl=300, max_entries=10, show_spinner=False)
def load_stock_news(symbol: str) -> list:
    return yf.Ticker(symbol).news


@st.cache_data(ttl=3600, max_entries=20, show_spinner=False)
def get_forecast(
    symbol: str, close_prices: pd.Series, horizon: int, api_url: str | None
) -> dict[str, object]:
    if api_url:
        response = requests.post(
            f"{api_url.rstrip('/')}/api/v1/forecasts",
            json={
                "symbol": symbol,
                "horizon": horizon,
                "start": "2019-01-01",
            },
            timeout=120,
        )
        response.raise_for_status()
        return response.json()
    return evaluate_and_forecast(close_prices, future_days=horizon)


def build_price_chart(data: pd.DataFrame, symbol: str) -> go.Figure:
    chart = go.Figure()
    chart.add_trace(go.Scatter(x=data.index, y=data["Close"], name="Adjusted close"))
    for column, color in (("MA20", "#f5a623"), ("MA50", "#5b9bd5")):
        chart.add_trace(
            go.Scatter(
                x=data.index,
                y=data[column],
                name=column,
                line={"color": color},
            )
        )

    bullish = data[data["Crossover"] == 1]
    bearish = data[data["Crossover"] == -1]
    for points, name, color, symbol_style in (
        (bullish, "Bullish crossover", "#20c997", "triangle-up"),
        (bearish, "Bearish crossover", "#ff6b6b", "triangle-down"),
    ):
        chart.add_trace(
            go.Scatter(
                x=points.index,
                y=points["Close"],
                mode="markers",
                name=name,
                marker={"color": color, "size": 10, "symbol": symbol_style},
            )
        )

    chart.update_layout(
        template="plotly_dark",
        height=470,
        margin={"l": 10, "r": 10, "t": 35, "b": 10},
        title=f"{symbol} adjusted close and trend",
        xaxis_title="Date",
        yaxis_title="Price (USD)",
        legend={"orientation": "h", "y": 1.08},
    )
    return chart


def render_news(symbol: str) -> None:
    st.subheader("Latest company news")
    try:
        items = load_stock_news(symbol)
    except (YFException, RequestException, OSError, TimeoutError) as error:
        st.warning(f"News is temporarily unavailable: {error}")
        return

    articles = []
    for item in (items or [])[:5]:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, dict):
            content = item
        title = content.get("title")
        if not title:
            continue
        provider = content.get("provider") or {}
        click_url = content.get("clickThroughUrl") or {}
        canonical_url = content.get("canonicalUrl") or {}
        if not isinstance(provider, dict):
            provider = {}
        if not isinstance(click_url, dict):
            click_url = {}
        if not isinstance(canonical_url, dict):
            canonical_url = {}
        articles.append(
            {
                "title": title,
                "publisher": (
                    provider.get("displayName")
                    or item.get("publisher")
                    or "Unknown publisher"
                ),
                "url": (
                    click_url.get("url") or canonical_url.get("url") or item.get("link")
                ),
            }
        )

    if not articles:
        st.info("No recent articles are available.")
        return

    for index, article in enumerate(articles):
        st.write(article["title"])
        st.caption(article["publisher"])
        if article["url"]:
            st.link_button(
                "Read article",
                article["url"],
                key=f"news-{symbol}-{index}",
            )
        if index < len(articles) - 1:
            st.divider()


st.title("Stock market analytics")
st.markdown(
    "Explore historical prices, technical indicators, and transparent "
    "forecast benchmarks. Market data is provided by Yahoo Finance."
)
st.caption(
    "Educational demonstration only. Prices and model outputs are not "
    "investment advice."
)

st.sidebar.header("Dashboard settings")
selected_company = st.sidebar.selectbox("Company", list(TICKERS))
symbol = TICKERS[selected_company]
stock_api_url = os.getenv("STOCK_API_URL")
selected_window = st.sidebar.selectbox(
    "Chart history", list(WINDOWS), index=1, key="chart_window"
)
st_autorefresh(interval=300_000, key="market-data-refresh")
st.sidebar.caption("Data refreshes every 5 minutes.")

try:
    raw_stock = load_stock_data(symbol, stock_api_url)
except (
    requests.exceptions.RequestException,
    YFException,
    RequestException,
    OSError,
    TimeoutError,
    ValueError,
) as error:
    st.error(f"Could not load {symbol} price history: {error}")
    st.info("Check your connection or try again later.")
    st.stop()

stock = add_technical_indicators(raw_stock)
if WINDOWS[selected_window] is None:
    visible_stock = stock
else:
    cutoff = stock.index[-1] - pd.DateOffset(years=WINDOWS[selected_window])
    visible_stock = stock.loc[stock.index >= cutoff]

latest_close = float(stock["Close"].iloc[-1])
previous_close = float(stock["Close"].iloc[-2])
daily_change = latest_close - previous_close
daily_change_percent = daily_change / previous_close * 100 if previous_close else 0
if pd.isna(stock["MA20"].iloc[-1]) or pd.isna(stock["MA50"].iloc[-1]):
    latest_trend = "Unavailable"
else:
    latest_trend = (
        "Bullish" if stock["MA20"].iloc[-1] > stock["MA50"].iloc[-1] else "Bearish"
    )
year_ago = stock.loc[stock.index >= stock.index[-1] - pd.DateOffset(days=365)]
year_change = (
    (latest_close / float(year_ago["Close"].iloc[0]) - 1) * 100
    if not year_ago.empty
    else 0.0
)

metric_columns = st.columns(4)
metric_columns[0].metric(
    "Latest adjusted close",
    f"${latest_close:,.2f}",
    help=f"Latest available daily close: {stock.index[-1].date()}",
)
metric_columns[1].metric(
    "Daily change",
    f"${daily_change:,.2f}",
    f"{daily_change_percent:.2f}%",
)
metric_columns[2].metric("Trend (MA20 vs MA50)", latest_trend)
metric_columns[3].metric("1-year change", f"{year_change:+.2f}%")
st.caption(f"Selected: {selected_company} · Latest data: {stock.index[-1].date()}")

overview_tab, technical_tab, forecast_tab, data_tab = st.tabs(
    ["Overview", "Technical analysis", "Forecast & evaluation", "Data & news"]
)

with overview_tab:
    st.subheader("Price performance")
    st.plotly_chart(
        build_price_chart(visible_stock, symbol),
        width="stretch",
        alt=f"{symbol} adjusted closing price, moving averages, and crossovers",
        key="overview-price-chart",
    )
    recent_crossovers = stock.loc[stock["Crossover"] != 0, "Crossover"].tail(1)
    if recent_crossovers.empty:
        st.info("No moving-average crossover has been recorded in this history.")
    else:
        last_cross_date = recent_crossovers.index[-1].date()
        last_cross_name = "Bullish" if recent_crossovers.iloc[-1] == 1 else "Bearish"
        st.caption(f"Most recent crossover: {last_cross_name} · {last_cross_date}")

with technical_tab:
    st.subheader("Candlestick chart")
    required_fields = ["Open", "High", "Low", "Close", "Volume"]
    if set(required_fields).issubset(visible_stock.columns):
        candles = (
            visible_stock[required_fields]
            .apply(pd.to_numeric, errors="coerce")
            .dropna()
        )
        if len(candles) >= 50:
            figure, _ = mpf.plot(
                candles,
                type="candle",
                mav=(20, 50),
                volume=True,
                style="yahoo",
                figsize=(12, 7),
                returnfig=True,
            )
            st.pyplot(figure, alt=f"{symbol} candlestick chart with moving averages")
            plt.close(figure)
        else:
            st.info("Not enough complete OHLCV history for a candlestick chart.")
    else:
        st.info("The data provider did not return all OHLCV fields.")

    left, right = st.columns(2)
    with left:
        st.subheader("Relative strength index")
        rsi_chart = go.Figure()
        rsi_chart.add_trace(
            go.Scatter(x=visible_stock.index, y=visible_stock["RSI"], name="RSI")
        )
        rsi_chart.add_hline(y=70, line_dash="dash")
        rsi_chart.add_hline(y=30, line_dash="dash")
        rsi_chart.update_layout(
            template="plotly_dark",
            height=330,
            yaxis={"range": [0, 100], "title": "RSI"},
            margin={"l": 10, "r": 10, "t": 25, "b": 10},
        )
        st.plotly_chart(
            rsi_chart,
            width="stretch",
            alt=f"{symbol} 14-day relative strength index",
            key="rsi-chart",
        )
    with right:
        st.subheader("MACD")
        macd_chart = go.Figure()
        macd_chart.add_trace(
            go.Scatter(x=visible_stock.index, y=visible_stock["MACD"], name="MACD")
        )
        macd_chart.add_trace(
            go.Scatter(
                x=visible_stock.index,
                y=visible_stock["MACD_Signal"],
                name="Signal line",
            )
        )
        macd_chart.add_hline(y=0, line_dash="dash")
        macd_chart.update_layout(
            template="plotly_dark",
            height=330,
            yaxis_title="MACD",
            margin={"l": 10, "r": 10, "t": 25, "b": 10},
        )
        st.plotly_chart(
            macd_chart,
            width="stretch",
            alt=f"{symbol} MACD and signal line",
            key="macd-chart",
        )
    st.caption(
        "RSI guide levels (30/70) and MACD are technical indicators, "
        "not standalone trading instructions."
    )

with forecast_tab:
    st.subheader("Out-of-sample forecast")
    if "forecast_horizon" not in st.session_state:
        st.session_state["forecast_horizon"] = 30
    horizon = st.selectbox(
        "Forecast horizon (trading days)",
        [5, 10, 20, 30, 60],
        key="forecast_horizon",
    )
    with st.spinner("Evaluating forecast against a simple baseline..."):
        try:
            result = get_forecast(symbol, stock["Close"], horizon, stock_api_url)
        except requests.exceptions.RequestException as error:
            st.error(f"Forecast API request failed: {error}")
        except ValueError as error:
            st.warning(f"Forecast unavailable: {error}")
        except XGBoostError as error:
            st.error(f"Forecast evaluation failed: {error}")
        else:
            metrics = st.columns(4)
            metrics[0].metric("Test R²", f"{result['r2']:.3f}")
            metrics[1].metric("Selected MAE", f"${result['mae']:.2f}")
            metrics[2].metric("Selected RMSE", f"${result['rmse']:.2f}")
            metrics[3].metric(
                "Direction accuracy",
                f"{result['directional_accuracy']:.1%}",
            )
            st.info(
                f"Selected method: **{result['method']}** · "
                f"XGBoost MAE: ${result['model_mae']:.2f} · "
                f"last-close baseline MAE: ${result['baseline_mae']:.2f}"
            )
            st.dataframe(
                pd.DataFrame.from_dict(
                    result["model_comparison"], orient="index"
                ).rename_axis("Model"),
                width="stretch",
                alt="Holdout performance comparison for candidate forecasting models",
                column_config={
                    "mae": st.column_config.NumberColumn("MAE", format="$%.2f"),
                    "rmse": st.column_config.NumberColumn("RMSE", format="$%.2f"),
                    "r2": st.column_config.NumberColumn("R²", format="%.3f"),
                },
            )
            walk_forward = result["walk_forward"]
            if walk_forward["folds"]:
                walk_forward_scores = dict(walk_forward["mae_by_model"])
                walk_forward_scores["Last-close baseline"] = walk_forward[
                    "baseline_mae"
                ]
                st.caption(
                    f"Model selection uses {walk_forward['folds']} expanding "
                    "walk-forward validation folds."
                )
                st.dataframe(
                    pd.DataFrame.from_dict(
                        walk_forward_scores, orient="index", columns=["MAE"]
                    ).rename_axis("Validation model"),
                    width="stretch",
                    alt="Mean absolute error across expanding walk-forward validation folds",
                    column_config={
                        "MAE": st.column_config.NumberColumn(
                            "Walk-forward MAE", format="$%.2f"
                        )
                    },
                )

            comparison = go.Figure()
            comparison.add_trace(
                go.Scatter(
                    x=result["target_dates"],
                    y=result["actual"],
                    name="Actual",
                )
            )
            comparison.add_trace(
                go.Scatter(
                    x=result["target_dates"],
                    y=result["predicted"],
                    name=f"Selected prediction ({result['method']})",
                )
            )
            comparison.update_layout(
                template="plotly_dark",
                height=430,
                xaxis_title="Target date",
                yaxis_title="Adjusted close (USD)",
                margin={"l": 10, "r": 10, "t": 25, "b": 10},
            )
            st.plotly_chart(
                comparison,
                width="stretch",
                alt=f"{symbol} actual and out-of-sample predicted prices",
                key="forecast-comparison",
            )
            st.metric(
                f"Estimate for {horizon} trading days",
                f"${result['future_price']:,.2f}",
            )
            st.caption(
                f"Last close: ${latest_close:,.2f} on {stock.index[-1].date()}. "
                "Future values are estimates, not guarantees."
            )
            with st.expander("How this evaluation works"):
                st.markdown(
                    f"""
                    - **Target:** adjusted closing price {horizon} trading days ahead.
                    - **Features:** historical returns, moving-average gaps,
                      recent volatility, and RSI.
                    - **Validation:** expanding walk-forward folds select the
                      model; the chronological holdout measures final performance.
                      Overlapping target horizons are removed from training.
                    - **Benchmark:** predict that the future close equals the
                      current close; a model is selected only when its average
                      walk-forward MAE is lower than the baseline.
                    - **Training samples:** {result["train_samples"]:,}; test
                      samples: {result["test_samples"]:,}.
                    - **Limitations:** one ticker, daily prices, no transaction
                      costs, corporate-event/news features, or guarantee of
                      future performance.
                    """
                )

with data_tab:
    st.subheader("Recent price data")
    st.dataframe(
        visible_stock.tail(100),
        width="stretch",
        alt=f"Recent {symbol} daily prices and technical indicators",
        column_config={
            "Close": st.column_config.NumberColumn("Adjusted close", format="$%.2f"),
            "MA20": st.column_config.NumberColumn("20-day average", format="$%.2f"),
            "MA50": st.column_config.NumberColumn("50-day average", format="$%.2f"),
            "RSI": st.column_config.NumberColumn("RSI", format="%.1f"),
        },
    )
    st.download_button(
        "Download displayed data (CSV)",
        data=visible_stock.to_csv(index_label="Date").encode("utf-8"),
        file_name=f"{symbol.lower()}_daily_prices.csv",
        mime="text/csv",
    )
    st.divider()
    render_news(symbol)
