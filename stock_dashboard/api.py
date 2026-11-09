"""FastAPI service for market data and persisted forecast results."""

from __future__ import annotations

import logging
import os
import secrets
import sqlite3
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from typing import Any

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator

from stock_dashboard.analytics import evaluate_and_forecast
from stock_dashboard.auth import (
    create_access_token,
    decode_access_token,
    hash_password,
    normalize_email,
    verify_password,
)
from stock_dashboard.database import (
    DatabaseIntegrityError,
    DatabaseUnavailableError,
    ForecastStore,
)
from stock_dashboard.market_data import (
    SUPPORTED_SYMBOLS,
    TICKERS,
    RequestException,
    YFException,
    load_stock_history,
)

logger = logging.getLogger(__name__)


class ForecastRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=24)
    horizon: int = Field(default=30, ge=1, le=60)
    start: date | None = None


class RegistrationRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=256)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)


class WatchlistRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=24)


class UserResponse(BaseModel):
    id: int
    email: str
    created_at: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class ForecastRunResponse(BaseModel):
    id: int
    symbol: str
    horizon: int
    selected_method: str
    future_price: float
    mae: float
    rmse: float
    baseline_mae: float
    model_comparison: dict[str, dict[str, float]]
    walk_forward: dict[str, Any]
    created_at: datetime


class ForecastResponse(BaseModel):
    id: int
    symbol: str
    horizon: int
    method: str
    future_price: float
    mae: float
    rmse: float
    model_mae: float
    baseline_mae: float
    model_comparison: dict[str, dict[str, float]]
    walk_forward: dict[str, Any]
    created_at: datetime
    r2: float
    directional_accuracy: float
    actual: list[float]
    predicted: list[float]
    target_dates: list[str]
    train_samples: int
    test_samples: int


def create_app(
    database_path: str | None = None,
    history_loader: Callable[..., pd.DataFrame] = load_stock_history,
    forecast_evaluator: Callable[..., dict[str, Any]] = evaluate_and_forecast,
    token_secret: str | None = None,
) -> FastAPI:
    store = ForecastStore(database_path)
    configured_secret = token_secret or os.getenv("JWT_SECRET")
    if not configured_secret and os.getenv("APP_ENV") == "production":
        raise RuntimeError("JWT_SECRET must be set in production.")
    configured_secret = configured_secret or secrets.token_urlsafe(32)
    bearer_scheme = HTTPBearer(auto_error=False)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        store.initialize()
        yield

    app = FastAPI(
        title="Stock Market Prediction API",
        description="Market history, model evaluation, and persisted forecasts.",
        version="1.0.0",
        lifespan=lifespan,
    )
    cors_origins = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000,"
            "http://localhost:8081,http://127.0.0.1:8081",
        ).split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    def get_optional_current_user(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),  # noqa: B008
    ) -> dict[str, Any] | None:
        if credentials is None:
            return None
        if credentials.scheme.lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authorization scheme.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            payload = decode_access_token(credentials.credentials, configured_secret)
            user = store.get_user_by_id(int(payload["sub"]))
        except (ValueError, KeyError) as error:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired access token.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from error
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired access token.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user

    def get_current_user(
        user: dict[str, Any] | None = Depends(get_optional_current_user),  # noqa: B008
    ) -> dict[str, Any]:
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user

    @app.get("/health")
    def health() -> dict[str, str]:
        try:
            store.check_connection()
        except DatabaseUnavailableError as error:
            logger.exception("Database health check failed.")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database is unavailable.",
            ) from error
        return {"status": "ok", "database": "ok"}

    @app.post(
        "/api/v1/auth/register",
        response_model=UserResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def register_user(request: RegistrationRequest) -> dict[str, Any]:
        try:
            return store.create_user(request.email, hash_password(request.password))
        except (sqlite3.IntegrityError, DatabaseIntegrityError) as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists.",
            ) from error

    @app.post("/api/v1/auth/login", response_model=TokenResponse)
    def login_user(request: LoginRequest) -> dict[str, Any]:
        user = store.get_user_by_email(request.email)
        encoded_password = (
            user["password_hash"] if user else hash_password(secrets.token_urlsafe(24))
        )
        if not verify_password(request.password, encoded_password) or user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return {
            "access_token": create_access_token(user, configured_secret),
            "expires_in": 60 * 60 * 24,
        }

    @app.get("/api/v1/auth/me", response_model=UserResponse)
    def current_user(
        user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
    ) -> dict[str, Any]:
        return user

    @app.get("/api/v1/portfolio/watchlist")
    def get_watchlist(
        user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return store.list_watchlist(user["id"])

    @app.post("/api/v1/portfolio/watchlist", status_code=status.HTTP_201_CREATED)
    def add_watchlist_symbol(
        request: WatchlistRequest,
        user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
    ) -> dict[str, str]:
        if request.symbol not in SUPPORTED_SYMBOLS:
            raise HTTPException(status_code=404, detail="Unsupported stock symbol.")
        if not store.add_watchlist_symbol(
            user["id"], request.symbol, datetime.now(UTC).isoformat()
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This stock is already in your watchlist.",
            )
        return {"symbol": request.symbol}

    @app.delete("/api/v1/portfolio/watchlist/{symbol}", status_code=204)
    def remove_watchlist_symbol(
        symbol: str,
        user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
    ) -> None:
        if not store.remove_watchlist_symbol(user["id"], symbol):
            raise HTTPException(status_code=404, detail="Stock not in watchlist.")

    @app.get("/api/v1/stocks")
    def list_stocks() -> list[dict[str, str]]:
        return [{"name": name, "symbol": symbol} for name, symbol in TICKERS.items()]

    @app.get("/api/v1/stocks/{symbol}/history")
    def stock_history(symbol: str, start: date | None = None) -> dict[str, Any]:
        if symbol not in SUPPORTED_SYMBOLS:
            raise HTTPException(status_code=404, detail="Unsupported stock symbol.")
        try:
            history = (
                history_loader(symbol, start=start.isoformat())
                if start is not None
                else history_loader(symbol)
            )
        except (RequestException, YFException, OSError, TimeoutError) as error:
            logger.warning("Market data unavailable for %s: %s", symbol, error)
            raise HTTPException(
                status_code=502, detail="Market data provider is unavailable."
            ) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

        rows = []
        fields = ("Open", "High", "Low", "Close", "Volume")
        for historical_date, row in history.iterrows():
            record: dict[str, Any] = {"date": historical_date.isoformat()}
            for field in fields:
                if field in history:
                    value = row[field]
                    record[field.lower()] = None if pd.isna(value) else float(value)
            rows.append(record)
        return {"symbol": symbol, "data": rows}

    @app.post("/api/v1/forecasts", response_model=ForecastResponse)
    def create_forecast(
        request: ForecastRequest,
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),  # noqa: B008
    ) -> dict[str, Any]:
        if request.symbol not in SUPPORTED_SYMBOLS:
            raise HTTPException(status_code=404, detail="Unsupported stock symbol.")
        user_id = None
        if credentials is not None:
            if credentials.scheme.lower() != "bearer":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authorization scheme.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            try:
                payload = decode_access_token(
                    credentials.credentials, configured_secret
                )
                user = store.get_user_by_id(int(payload["sub"]))
            except (ValueError, KeyError) as error:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired access token.",
                    headers={"WWW-Authenticate": "Bearer"},
                ) from error
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired access token.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            user_id = user["id"]
        try:
            history = (
                history_loader(request.symbol, start=request.start.isoformat())
                if request.start is not None
                else history_loader(request.symbol)
            )
        except (RequestException, YFException, OSError, TimeoutError) as error:
            logger.warning("Market data unavailable for %s: %s", request.symbol, error)
            raise HTTPException(
                status_code=502, detail="Market data provider is unavailable."
            ) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

        try:
            result = forecast_evaluator(history["Close"], future_days=request.horizon)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

        record = store.save(
            {
                "symbol": request.symbol,
                "horizon": request.horizon,
                "user_id": user_id,
                "selected_method": result["method"],
                "future_price": float(result["future_price"]),
                "mae": float(result["mae"]),
                "rmse": float(result["rmse"]),
                "baseline_mae": float(result["baseline_mae"]),
                "model_comparison": result["model_comparison"],
                "walk_forward": result["walk_forward"],
                "created_at": datetime.now(UTC).isoformat(),
            }
        )
        record.update(
            {
                "method": result["method"],
                "model_mae": float(result["model_mae"]),
                "r2": float(result["r2"]),
                "directional_accuracy": float(result["directional_accuracy"]),
                "actual": [float(value) for value in result["actual"]],
                "predicted": [float(value) for value in result["predicted"]],
                "target_dates": [
                    pd.Timestamp(value).isoformat() for value in result["target_dates"]
                ],
                "train_samples": int(result["train_samples"]),
                "test_samples": int(result["test_samples"]),
            }
        )
        return record

    @app.get("/api/v1/forecasts", response_model=list[ForecastRunResponse])
    def list_forecasts(
        symbol: str | None = None,
        limit: int = Query(default=20, ge=1, le=100),
        user: dict[str, Any] | None = Depends(get_optional_current_user),  # noqa: B008
    ) -> list[dict[str, Any]]:
        if symbol is not None and symbol not in SUPPORTED_SYMBOLS:
            raise HTTPException(status_code=404, detail="Unsupported stock symbol.")
        return store.list_recent(symbol, limit, user["id"] if user else None)

    return app


app = create_app()
