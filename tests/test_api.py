import pandas as pd
from fastapi.testclient import TestClient

from stock_dashboard.api import create_app


def test_stock_history_endpoint_returns_normalized_rows(tmp_path):
    history = pd.DataFrame(
        {"Close": [101.0, 102.0]},
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )
    app = create_app(
        database_path=str(tmp_path / "history.sqlite"),
        history_loader=lambda _: history,
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/stocks/AAPL/history")

    assert response.status_code == 200
    assert response.json()["data"] == [
        {"date": "2024-01-02T00:00:00", "close": 101.0},
        {"date": "2024-01-03T00:00:00", "close": 102.0},
    ]


def test_forecast_endpoint_persists_results_and_model_comparison(tmp_path):
    history = pd.DataFrame({"Close": [100.0, 101.0]})

    def evaluate_forecast(_, future_days):
        assert future_days == 10
        return {
            "method": "Random Forest",
            "future_price": 105.0,
            "mae": 1.5,
            "rmse": 1.8,
            "model_mae": 1.5,
            "baseline_mae": 2.0,
            "model_comparison": {"Random Forest": {"mae": 1.5, "rmse": 1.8, "r2": 0.9}},
            "walk_forward": {
                "folds": 2,
                "mae_by_model": {"Random Forest": 1.6},
                "baseline_mae": 2.1,
            },
            "r2": 0.9,
            "directional_accuracy": 0.8,
            "actual": [104.0, 105.0],
            "predicted": [103.5, 105.2],
            "target_dates": pd.to_datetime(["2024-01-05", "2024-01-08"]),
            "train_samples": 80,
            "test_samples": 20,
        }

    app = create_app(
        database_path=str(tmp_path / "forecasts.sqlite"),
        history_loader=lambda _: history,
        forecast_evaluator=evaluate_forecast,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/forecasts", json={"symbol": "AAPL", "horizon": 10}
        )
        recent = client.get("/api/v1/forecasts?symbol=AAPL")

    assert response.status_code == 200
    assert response.json()["future_price"] == 105.0
    assert response.json()["method"] == "Random Forest"
    assert response.json()["model_comparison"]["Random Forest"]["mae"] == 1.5
    assert response.json()["walk_forward"]["folds"] == 2
    assert response.json()["target_dates"][0].startswith("2024-01-05")
    assert len(recent.json()) == 1
    assert recent.json()[0]["selected_method"] == "Random Forest"


def test_api_rejects_unsupported_symbol(tmp_path):
    app = create_app(database_path=str(tmp_path / "unsupported.sqlite"))

    with TestClient(app) as client:
        response = client.get("/api/v1/stocks/UNKNOWN/history")

    assert response.status_code == 404


def test_registration_login_and_watchlist_are_user_scoped(tmp_path):
    app = create_app(
        database_path=str(tmp_path / "accounts.sqlite"),
        token_secret="test-secret",
    )

    with TestClient(app) as client:
        registered = client.post(
            "/api/v1/auth/register",
            json={"email": "  Kanika@example.com ", "password": "a-very-long-password"},
        )
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "kanika@example.com", "password": "a-very-long-password"},
        )
        assert registered.status_code == 201
        assert registered.json()["email"] == "kanika@example.com"
        assert "password" not in registered.json()
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        assert client.get("/api/v1/auth/me", headers=headers).json()["email"] == (
            "kanika@example.com"
        )
        added = client.post(
            "/api/v1/portfolio/watchlist",
            json={"symbol": "AAPL"},
            headers=headers,
        )
        duplicate = client.post(
            "/api/v1/portfolio/watchlist",
            json={"symbol": "AAPL"},
            headers=headers,
        )
        watchlist = client.get("/api/v1/portfolio/watchlist", headers=headers)
        unauthenticated = client.get("/api/v1/portfolio/watchlist")
        removed = client.delete("/api/v1/portfolio/watchlist/AAPL", headers=headers)
        empty_watchlist = client.get("/api/v1/portfolio/watchlist", headers=headers)

    assert added.status_code == 201
    assert duplicate.status_code == 409
    assert watchlist.json()[0]["symbol"] == "AAPL"
    assert unauthenticated.status_code == 401
    assert removed.status_code == 204
    assert empty_watchlist.json() == []


def test_login_rejects_wrong_password_and_duplicate_registration(tmp_path):
    app = create_app(
        database_path=str(tmp_path / "account-errors.sqlite"),
        token_secret="test-secret",
    )

    with TestClient(app) as client:
        payload = {"email": "user@example.com", "password": "correct-password-123"}
        registered = client.post("/api/v1/auth/register", json=payload)
        duplicate = client.post("/api/v1/auth/register", json=payload)
        wrong_password = client.post(
            "/api/v1/auth/login",
            json={"email": payload["email"], "password": "wrong-password"},
        )

    assert registered.status_code == 201
    assert duplicate.status_code == 409
    assert wrong_password.status_code == 401


def test_forecast_history_is_scoped_to_authenticated_user(tmp_path):
    history = pd.DataFrame({"Close": [100.0, 101.0]})

    def evaluate_forecast(_, future_days):
        return {
            "method": "Baseline",
            "future_price": 102.0,
            "mae": 1.0,
            "rmse": 1.0,
            "model_mae": 1.0,
            "baseline_mae": 1.0,
            "model_comparison": {},
            "walk_forward": {"folds": 2, "mae_by_model": {}, "baseline_mae": 1.0},
            "r2": 0.0,
            "directional_accuracy": 0.5,
            "actual": [102.0],
            "predicted": [102.0],
            "target_dates": pd.to_datetime(["2024-01-05"]),
            "train_samples": 10,
            "test_samples": 1,
        }

    app = create_app(
        database_path=str(tmp_path / "user-forecasts.sqlite"),
        history_loader=lambda _: history,
        forecast_evaluator=evaluate_forecast,
        token_secret="test-secret",
    )

    with TestClient(app) as client:
        accounts = []
        for email in ("first@example.com", "second@example.com"):
            client.post(
                "/api/v1/auth/register",
                json={"email": email, "password": "a-very-long-password"},
            )
            response = client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": "a-very-long-password"},
            )
            accounts.append(response.json()["access_token"])
        client.post(
            "/api/v1/forecasts",
            json={"symbol": "AAPL", "horizon": 1},
            headers={"Authorization": f"Bearer {accounts[0]}"},
        )
        first_user_history = client.get(
            "/api/v1/forecasts",
            headers={"Authorization": f"Bearer {accounts[0]}"},
        )
        second_user_history = client.get(
            "/api/v1/forecasts",
            headers={"Authorization": f"Bearer {accounts[1]}"},
        )
        public_history = client.get("/api/v1/forecasts")

    assert len(first_user_history.json()) == 1
    assert second_user_history.json() == []
    assert public_history.json() == []
