import numpy as np
import pandas as pd
import pytest

from stock_dashboard.analytics import (
    add_technical_indicators,
    evaluate_and_forecast,
    normalize_price_history,
)


def make_prices(count=500, flat=False):
    dates = pd.bdate_range("2020-01-01", periods=count)
    if flat:
        values = np.full(count, 100.0)
    else:
        steps = np.arange(count)
        values = 100 + steps * 0.04 + 2 * np.sin(steps / 15)
    return pd.Series(values, index=dates, name="Close")


@pytest.mark.parametrize(
    "columns",
    [
        pd.MultiIndex.from_product([["Close", "Volume"], ["AAPL"]]),
        pd.MultiIndex.from_product([["AAPL"], ["Close", "Volume"]]),
    ],
)
def test_normalize_price_history_handles_yfinance_multiindex(columns):
    raw = pd.DataFrame(
        [[100.0, 1000], [101.0, 1200]],
        index=pd.bdate_range("2024-01-01", periods=2),
        columns=columns,
    )

    normalized = normalize_price_history(raw, "AAPL")

    assert list(normalized.columns) == ["Close", "Volume"]
    assert normalized["Close"].tolist() == [100.0, 101.0]


def test_normalize_price_history_rejects_empty_data():
    with pytest.raises(ValueError, match="No price history"):
        normalize_price_history(pd.DataFrame(), "AAPL")


def test_indicators_keep_rsi_bounded_and_only_mark_crossovers():
    prices = make_prices()
    history = pd.DataFrame({"Close": prices})

    result = add_technical_indicators(history)

    valid_rsi = result["RSI"].dropna()
    assert valid_rsi.between(0, 100).all()
    assert set(result["Crossover"].unique()).issubset({-1, 0, 1})
    assert (result["Crossover"] != 0).sum() < len(result)
    assert {"MACD", "MACD_Signal", "MACD_Histogram"}.issubset(result.columns)


def test_forecast_splits_chronologically_without_target_leakage():
    prices = make_prices()

    result = evaluate_and_forecast(prices, future_days=20)

    assert result["train_target_end"] < result["test_start"]
    assert result["target_dates"].is_monotonic_increasing
    assert len(result["actual"]) == len(result["predicted"])
    assert result["test_samples"] == len(result["actual"])
    assert result["method"] in {
        "Linear Regression",
        "Random Forest",
        "XGBoost",
        "Last-close baseline",
    }
    assert result["walk_forward"]["folds"] == 3
    expected_method = min(
        result["walk_forward"]["mae_by_model"],
        key=result["walk_forward"]["mae_by_model"].get,
    )
    if (
        result["walk_forward"]["mae_by_model"][expected_method]
        >= result["walk_forward"]["baseline_mae"]
    ):
        expected_method = "Last-close baseline"
    assert result["method"] == expected_method
    assert set(result["model_comparison"]) == {
        "Linear Regression",
        "Random Forest",
        "XGBoost",
    }
    assert np.isfinite(
        [
            result["r2"],
            result["mae"],
            result["rmse"],
            result["future_price"],
            result["directional_accuracy"],
        ]
    ).all()


def test_forecast_uses_baseline_when_model_does_not_improve_it():
    prices = make_prices(flat=True)

    result = evaluate_and_forecast(prices, future_days=10)

    assert result["method"] == "Last-close baseline"
    assert result["future_price"] == prices.iloc[-1]
    assert result["mae"] == result["baseline_mae"] == 0


@pytest.mark.parametrize("horizon", [0, -1, 1.5])
def test_forecast_rejects_invalid_horizon(horizon):
    with pytest.raises(ValueError, match="positive number"):
        evaluate_and_forecast(make_prices(), future_days=horizon)


def test_forecast_rejects_short_history():
    with pytest.raises(ValueError, match="100 usable observations"):
        evaluate_and_forecast(make_prices(count=90), future_days=30)
