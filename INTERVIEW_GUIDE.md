# Interview guide

## 60-second project introduction

> I built a Streamlit dashboard and FastAPI service for US and Indian stock
> analytics. The dashboard shows adjusted prices, moving-average crossovers,
> RSI, and MACD. Forecast selection compares linear regression, random forest,
> and XGBoost with a last-close persistence baseline using expanding walk-forward
> folds, then reports results on a separate chronological holdout. Training
> examples whose target dates overlap validation/test dates are removed. The API
> exposes market history and forecast endpoints and saves forecast runs in
> SQLite. I also added deterministic analytics/API tests and CI.

## Architecture

- `streamlit_app.py` owns page layout, user controls, chart rendering, and
  user-facing error messages.
- `stock_dashboard/api.py` exposes market history, forecast, and saved-run
  endpoints.
- `stock_dashboard/analytics.py` contains testable price normalization,
  technical indicators, feature engineering, model comparison, and validation.
- `stock_dashboard/database.py` persists forecast results in SQLite.
- `stock_dashboard/market_data.py` owns supported symbols and Yahoo Finance
  access.
- `tests/` exercises ticker-column formats, indicators, API responses, database
  persistence, validation boundaries, and baseline fallback.
- `.github/workflows/tests.yml` runs the automated test suite on each push and
  pull request.
- Yahoo Finance price/news requests and model results use bounded cache
  lifetimes; chart refreshes every five minutes.

## Forecasting decisions

1. The target is the adjusted close `h` trading days after each observation.
2. Features use information available on the observation date: daily, weekly,
   and monthly returns; 20/50-day moving-average gaps; 20-day volatility; and
   14-day RSI.
3. The dataset is split by time rather than randomly. Training rows are further
   filtered so their target dates occur before the first test observation.
4. Linear Regression, Random Forest, and XGBoost candidates are compared with
   the last-close persistence baseline using expanding walk-forward folds.
5. The selected candidate is evaluated once on a later chronological holdout;
   R², MAE, RMSE, and directional accuracy are not guarantees of future
   performance.

## Common interview questions

### Why is the split chronological?

Randomly shuffling time-series observations can let later observations
influence training. A chronological holdout better represents the real
workflow: fit on the past, then evaluate on later dates.

### Why remove training rows whose target crosses the test boundary?

Each label refers to a future price. A training example near the boundary could
use a target from the test period even if its feature date is earlier. Filtering
by target date prevents that horizon overlap from leaking test-period outcomes
into training.

### Why compare candidates with a last-close baseline?

Stock prices are persistent, so a complex model can appear plausible while
performing worse than simply carrying today's price forward. The baseline makes
that comparison explicit. If no candidate beats it on walk-forward MAE, the app
uses the baseline rather than implying a model adds value.

### What do the metrics mean?

- **MAE** is the average absolute price error, in USD.
- **RMSE** penalizes large misses more heavily than MAE.
- **R²** measures explained variance relative to predicting the test-set mean;
  it can be negative.
- **Directional accuracy** is the fraction of test observations where the
  predicted price movement has the same direction as the realized movement.

### What are the main limitations?

Each run uses one daily price series and technical features. The platform does
not yet include deep-learning models, user portfolios, authentication, news
sentiment in the model, transaction costs, or native mobile clients. A single
holdout result does not establish profitability; future work should evaluate
multiple market regimes and risk-adjusted strategy returns after realistic
costs.

## Resume bullet

> Built a multi-market stock analytics dashboard and FastAPI service with
> technical indicators, walk-forward model selection, a persistence baseline,
> SQLite forecast history, automated tests, and GitHub Actions CI.

Add a measured impact or deployment link only after you have independently
verified it; do not claim forecast accuracy or investment performance from one
historical test split.
