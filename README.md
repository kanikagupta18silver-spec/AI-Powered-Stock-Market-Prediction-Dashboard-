# AI-powered stock market analytics platform

An interactive stock analytics web app and REST API for US and Indian equities.
It combines daily market history, technical indicators, multiple forecasting
models, a persistence baseline, and saved forecast runs. Historical prices and
model outputs are for education and demonstration only; they are not investment
advice.

## Demo

[Open the Streamlit demo](https://stock-price-prediction-ru9arvok6svory5yoo3dni.streamlit.app/)

The hosted demo may not include the latest local changes until this version is
deployed.

## Features

- Daily adjusted prices for selected US and Indian companies.
- Moving averages, RSI, MACD, and moving-average crossover markers.
- Linear Regression, Random Forest, and XGBoost compared with a last-close
  baseline.
- Expanding walk-forward model selection and a chronological holdout with
  forecast-horizon leakage prevention.
- R², MAE, RMSE, directional accuracy, and downloadable CSV data.
- FastAPI endpoints for stock history, forecasts, and forecast history.
- SQLite persistence for saved forecast runs, accounts, and private watchlists.
- Optional PostgreSQL persistence through `DATABASE_URL`.
- Next.js web client and an Expo Android/iOS client with account and watchlist flows.
- Automated analytics/API tests and GitHub Actions CI.

## Screenshots

![Stock dashboard overview](images/dashboard.png)

![Actual and predicted prices](images/actual_vs_predicted.png)

![Technical indicator chart](images/macd_indicator.png)

## Quick start

Python 3.11 or newer is recommended.

### Windows

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Terminal 1: start the API
.\.venv\Scripts\python.exe -m uvicorn stock_dashboard.api:app --reload

# Terminal 2: start the dashboard
$env:STOCK_API_URL = "http://127.0.0.1:8000"
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

The API is available at `http://127.0.0.1:8000`; interactive API documentation
is at `http://127.0.0.1:8000/docs`. The dashboard runs at
`http://localhost:8501`. `STOCK_API_URL` makes the dashboard load prices and
submit forecasts through the API. By default, data is written to
`stock_market.db`. Set a stable signing secret before running the API so
sessions remain valid across restarts:

```powershell
$env:JWT_SECRET = "replace-with-a-long-random-secret"
```

To use a different SQLite file, set `DATABASE_PATH`. PostgreSQL can be selected
with a PostgreSQL connection string in `DATABASE_URL`:

```powershell
$env:DATABASE_PATH = "data/stock_market.db"
# Or:
$env:DATABASE_URL = "postgresql://user:password@localhost:5432/stock_market"
```

For the Next.js client, in another terminal:

```powershell
cd web
npm install
$env:NEXT_PUBLIC_API_URL = "http://127.0.0.1:8000"
npm run dev
```

Open `http://localhost:3000`. To start the Expo app:

```powershell
cd mobile
npm install
# For a physical phone, use the computer's LAN IP instead of localhost.
$env:EXPO_PUBLIC_API_URL = "http://127.0.0.1:8000"
npm run start
```

Then press `w` for Expo web or open the Expo Go development link on a device.
Android emulators default to `10.0.2.2`; physical devices need the host
computer's reachable LAN address in `EXPO_PUBLIC_API_URL`.

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn stock_dashboard.api:app --reload
# In another terminal:
export STOCK_API_URL="http://127.0.0.1:8000"
python -m streamlit run streamlit_app.py
```

The dashboard fetches daily price history and news from Yahoo Finance, so an
internet connection is required. The provider may limit requests or change its
response format; the app reports data-loading errors and supports common
single-ticker column layouts.

## Run tests

```bash
python -m pip install -r requirements-dev.txt
python -m ruff check .
python -m ruff format --check .
python -m pytest -q
```

The analytics tests use generated price series and do not call the Yahoo
Finance API. GitHub Actions runs them on Python 3.11, 3.12, and 3.13.

## Project structure

```text
.
├── .github/workflows/tests.yml
├── .streamlit/config.toml
├── images/
├── mobile/
├── web/
├── stock_dashboard/
│   ├── api.py
│   ├── __init__.py
│   ├── analytics.py
│   ├── database.py
│   └── market_data.py
├── tests/
│   ├── test_analytics.py
│   └── test_api.py
├── app.py
├── streamlit_app.py
├── requirements.txt
├── requirements-dev.txt
└── INTERVIEW_GUIDE.md
```

`streamlit_app.py` is the dashboard entry point. `stock_dashboard.api:app` is
the REST API entry point, and `app.py` remains a compatibility launcher for the
dashboard.

## Roadmap status

The implemented local slice covers multi-market history, indicators, three
forecast candidates, expanding walk-forward selection, a leakage-aware final
holdout, a REST API, account authentication, private watchlists, SQLite, and an
optional PostgreSQL adapter. The web client runs with Next.js, and the Expo
client includes market, forecast, sign-in, and watchlist screens. PostgreSQL
connectivity and native device builds still require their respective local
services/toolchains. Production deployment, deep-learning candidates, model
registry, cloud observability, and automated retraining remain future work.

## Forecast methodology

The target is the adjusted closing price a selectable number of trading days
ahead. Features include past returns, moving-average gaps, rolling volatility,
and RSI. Expanding walk-forward folds select the model using earlier data; the
latest observations remain a separate chronological holdout. Training rows
whose target dates overlap each validation/test period are excluded.

The app compares Linear Regression, Random Forest, and XGBoost against a
persistence benchmark that predicts the future close will equal the current
close. It selects the model with the lowest mean walk-forward MAE only when it
improves on the baseline; otherwise it uses the baseline. This is a demonstration—not
evidence of a profitable trading strategy. The models do not account for
transaction costs, news, or portfolio risk, and one historical test period
cannot guarantee future performance.

## Interview preparation

See [INTERVIEW_GUIDE.md](./INTERVIEW_GUIDE.md) for a concise project pitch,
architecture, modeling rationale, limitations, and a resume-ready project
bullet.
