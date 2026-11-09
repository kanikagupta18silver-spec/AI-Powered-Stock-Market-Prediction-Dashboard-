"""Testable price-history, indicator, and forecasting logic."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor

PRICE_FIELDS = ("Open", "High", "Low", "Close", "Volume")


class _LinearRegression:
    def fit(self, features: pd.DataFrame, target: pd.Series) -> _LinearRegression:
        matrix = np.column_stack((np.ones(len(features)), features.to_numpy()))
        self.coefficients = np.linalg.lstsq(matrix, target.to_numpy(), rcond=None)[0]
        return self

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        matrix = np.column_stack((np.ones(len(features)), features.to_numpy()))
        return matrix @ self.coefficients


def normalize_price_history(data: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Normalize yfinance's single-ticker output across MultiIndex layouts."""
    if data.empty:
        raise ValueError(f"No price history was returned for {symbol}.")

    normalized = data.copy()
    if isinstance(normalized.columns, pd.MultiIndex):
        matching_level = next(
            (
                level
                for level in range(normalized.columns.nlevels)
                if symbol in normalized.columns.get_level_values(level)
            ),
            None,
        )
        if matching_level is not None:
            normalized = normalized.xs(
                symbol, axis=1, level=matching_level, drop_level=True
            )

        if isinstance(normalized.columns, pd.MultiIndex):
            flattened = {}
            for field in PRICE_FIELDS:
                matching_columns = [
                    column
                    for column in normalized.columns
                    if field in tuple(str(part) for part in column)
                ]
                if matching_columns:
                    flattened[field] = normalized[matching_columns[0]]
            normalized = pd.DataFrame(flattened, index=normalized.index)

    normalized.columns = [str(column) for column in normalized.columns]
    if "Close" not in normalized.columns:
        raise ValueError(f"Downloaded data did not contain {symbol} closing prices.")

    normalized = normalized.sort_index()
    normalized["Close"] = pd.to_numeric(normalized["Close"], errors="coerce")
    normalized = normalized.dropna(subset=["Close"])
    if len(normalized) < 2:
        raise ValueError(f"Not enough valid price history was returned for {symbol}.")

    return normalized


def add_technical_indicators(data: pd.DataFrame) -> pd.DataFrame:
    """Return price history enriched with trend and momentum indicators."""
    if "Close" not in data.columns:
        raise ValueError("Price history must contain a Close column.")

    result = data.copy()
    close = pd.to_numeric(result["Close"], errors="coerce")
    result["MA20"] = close.rolling(20, min_periods=20).mean()
    result["MA50"] = close.rolling(50, min_periods=50).mean()

    daily_change = close.diff()
    average_gain = daily_change.clip(lower=0).rolling(14, min_periods=14).mean()
    average_loss = -daily_change.clip(upper=0).rolling(14, min_periods=14).mean()
    relative_strength = average_gain.div(average_loss.replace(0, np.nan))
    result["RSI"] = 100 - (100 / (1 + relative_strength))
    result.loc[(average_loss == 0) & (average_gain > 0), "RSI"] = 100
    result.loc[(average_gain == 0) & (average_loss > 0), "RSI"] = 0
    result.loc[(average_gain == 0) & (average_loss == 0), "RSI"] = 50

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    result["MACD"] = ema12 - ema26
    result["MACD_Signal"] = result["MACD"].ewm(span=9, adjust=False).mean()
    result["MACD_Histogram"] = result["MACD"] - result["MACD_Signal"]

    bullish_cross = (result["MA20"] > result["MA50"]) & (
        result["MA20"].shift(1) <= result["MA50"].shift(1)
    )
    bearish_cross = (result["MA20"] < result["MA50"]) & (
        result["MA20"].shift(1) >= result["MA50"].shift(1)
    )
    result["Crossover"] = 0
    result.loc[bullish_cross, "Crossover"] = 1
    result.loc[bearish_cross, "Crossover"] = -1

    return result


def _forecast_features(close: pd.Series) -> pd.DataFrame:
    daily_returns = close.pct_change()
    average_gain = daily_returns.clip(lower=0).rolling(14).mean()
    average_loss = -daily_returns.clip(upper=0).rolling(14).mean()
    relative_strength = average_gain.div(average_loss.replace(0, np.nan))
    rsi = 100 - (100 / (1 + relative_strength))
    rsi.loc[(average_loss == 0) & (average_gain > 0)] = 100
    rsi.loc[(average_gain == 0) & (average_loss > 0)] = 0
    rsi.loc[(average_gain == 0) & (average_loss == 0)] = 50

    return pd.DataFrame(
        {
            "return_1d": daily_returns,
            "return_5d": close.pct_change(5),
            "return_20d": close.pct_change(20),
            "ma20_gap": close.div(close.rolling(20).mean()).sub(1),
            "ma50_gap": close.div(close.rolling(50).mean()).sub(1),
            "volatility_20d": daily_returns.rolling(20).std(),
            "rsi_14": rsi,
        },
        index=close.index,
    )


def evaluate_and_forecast(
    close_prices: pd.Series, future_days: int = 30
) -> dict[str, object]:
    """Compare several regressors with persistence on a chronological holdout."""
    if not isinstance(future_days, int) or future_days < 1:
        raise ValueError("Forecast horizon must be a positive number of trading days.")
    if not isinstance(close_prices, pd.Series):
        close_prices = pd.Series(close_prices)

    close = pd.to_numeric(close_prices, errors="coerce").dropna().sort_index()
    if close.index.has_duplicates:
        raise ValueError("Price history must not contain duplicate dates.")
    if not np.isfinite(close.to_numpy()).all():
        raise ValueError("Price history contains non-finite closing prices.")
    if (close <= 0).any():
        raise ValueError("Closing prices must be greater than zero.")

    features = _forecast_features(close)
    target = close.shift(-future_days).rename("Target")
    target_dates = pd.Series(close.index, index=close.index).shift(-future_days)
    samples = features.join(close.rename("Close")).join(target).dropna()
    samples = samples.replace([np.inf, -np.inf], np.nan).dropna()
    target_dates = target_dates.loc[samples.index]

    if len(samples) < 100:
        raise ValueError(
            "At least 100 usable observations are required for a reliable "
            "chronological forecast evaluation."
        )

    split_index = min(max(int(len(samples) * 0.8), 1), len(samples) - 1)
    test = samples.iloc[split_index:]
    first_test_date = test.index[0]
    train_mask = target_dates.loc[samples.index] < first_test_date
    train = samples.loc[train_mask]
    if len(train) < 30:
        raise ValueError(
            "Not enough pre-test history remains after separating forecast horizons."
        )

    feature_columns = list(features.columns)

    model_factories = {
        "Linear Regression": _LinearRegression,
        "Random Forest": lambda: XGBRegressor(
            n_estimators=1,
            num_parallel_tree=120,
            max_depth=3,
            subsample=0.8,
            colsample_bynode=0.8,
            objective="reg:squarederror",
            n_jobs=1,
            random_state=42,
        ),
        "XGBoost": lambda: XGBRegressor(
            n_estimators=160,
            learning_rate=0.04,
            max_depth=3,
            subsample=0.8,
            colsample_bytree=0.8,
            objective="reg:squarederror",
            eval_metric="rmse",
            n_jobs=1,
            random_state=42,
        ),
    }

    fold_size = max(int(len(train) * 0.15), 1)
    fold_ends = sorted(
        {max(int(len(train) * fraction), 1) for fraction in (0.6, 0.8, 1.0)}
    )
    fold_scores: dict[str, list[float]] = {
        model_name: [] for model_name in model_factories
    }
    baseline_fold_scores = []
    for fold_end in fold_ends:
        fold_start = max(fold_end - fold_size, 0)
        validation = train.iloc[fold_start:fold_end]
        if validation.empty:
            continue
        validation_start = validation.index[0]
        fold_train_mask = target_dates.loc[train.index] < validation_start
        fold_train = train.loc[fold_train_mask]
        if len(fold_train) < 30:
            continue

        validation_actual = validation["Target"].to_numpy()
        baseline_fold_scores.append(
            float(
                mean_absolute_error(validation_actual, validation["Close"].to_numpy())
            )
        )
        for model_name, model_factory in model_factories.items():
            fold_model = model_factory()
            fold_model.fit(fold_train[feature_columns], fold_train["Target"])
            fold_predictions = fold_model.predict(validation[feature_columns])
            fold_scores[model_name].append(
                float(mean_absolute_error(validation_actual, fold_predictions))
            )

    walk_forward_scores = {
        model_name: float(np.mean(scores))
        for model_name, scores in fold_scores.items()
        if scores
    }
    walk_forward_baseline_mae = (
        float(np.mean(baseline_fold_scores)) if baseline_fold_scores else None
    )

    actual_prices = test["Target"].to_numpy()
    baseline_predictions = test["Close"].to_numpy()
    baseline_mae = float(mean_absolute_error(actual_prices, baseline_predictions))

    model_comparison: dict[str, dict[str, float]] = {}
    model_predictions: dict[str, np.ndarray] = {}
    for model_name, model_factory in model_factories.items():
        model = model_factory()
        model.fit(train[feature_columns], train["Target"])
        predictions = model.predict(test[feature_columns])
        model_predictions[model_name] = predictions
        model_comparison[model_name] = {
            "mae": float(mean_absolute_error(actual_prices, predictions)),
            "rmse": float(np.sqrt(mean_squared_error(actual_prices, predictions))),
            "r2": float(r2_score(actual_prices, predictions)),
        }

    selection_scores = walk_forward_scores or {
        model_name: metrics["mae"] for model_name, metrics in model_comparison.items()
    }
    selected_model = min(selection_scores, key=selection_scores.get)
    selected_method = "Last-close baseline"
    selected_predictions = baseline_predictions
    future_price = float(close.iloc[-1])
    selection_baseline_mae = (
        walk_forward_baseline_mae
        if walk_forward_baseline_mae is not None
        else baseline_mae
    )
    if selection_scores[selected_model] < selection_baseline_mae:
        final_model = model_factories[selected_model]()
        final_model.fit(samples[feature_columns], samples["Target"])
        latest_features = features.loc[[close.index[-1]], feature_columns]
        future_price = float(final_model.predict(latest_features)[0])
        selected_method = selected_model
        selected_predictions = model_predictions[selected_model]

    return {
        "r2": float(r2_score(actual_prices, selected_predictions)),
        "mae": float(mean_absolute_error(actual_prices, selected_predictions)),
        "rmse": float(np.sqrt(mean_squared_error(actual_prices, selected_predictions))),
        "model_mae": model_comparison["XGBoost"]["mae"],
        "baseline_mae": baseline_mae,
        "model_comparison": model_comparison,
        "walk_forward": {
            "folds": len(baseline_fold_scores),
            "mae_by_model": walk_forward_scores,
            "baseline_mae": walk_forward_baseline_mae,
        },
        "directional_accuracy": float(
            np.mean(
                np.sign(selected_predictions - test["Close"].to_numpy())
                == np.sign(actual_prices - test["Close"].to_numpy())
            )
        ),
        "actual": actual_prices,
        "predicted": selected_predictions,
        "target_dates": target_dates.loc[test.index],
        "future_price": future_price,
        "method": selected_method,
        "train_samples": len(train),
        "test_samples": len(test),
        "train_target_end": target_dates.loc[train.index].max(),
        "test_start": test.index[0],
        "features": feature_columns,
    }
