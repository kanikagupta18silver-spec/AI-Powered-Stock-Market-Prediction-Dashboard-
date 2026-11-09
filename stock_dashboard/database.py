"""SQLite persistence for forecast runs."""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class DatabaseUnavailableError(RuntimeError):
    """Raised when the configured database cannot be reached."""


class DatabaseIntegrityError(RuntimeError):
    """Raised when a configured database constraint rejects a write."""


class ForecastStore:
    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or os.getenv(
            "DATABASE_URL", os.getenv("DATABASE_PATH", "stock_market.db")
        )
        self.use_postgres = self.database_url.startswith(
            ("postgres://", "postgresql://", "postgresql+psycopg://")
        )
        if self.database_url.startswith("postgresql+psycopg://"):
            self.database_url = self.database_url.replace(
                "postgresql+psycopg://", "postgresql://", 1
            )

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        if self.use_postgres:
            try:
                import psycopg
                from psycopg.rows import dict_row
            except (ImportError, OSError) as error:
                raise DatabaseUnavailableError(
                    "Install psycopg to use PostgreSQL: pip install 'psycopg[binary]'"
                ) from error
            try:
                connection = psycopg.connect(
                    self.database_url, row_factory=dict_row, connect_timeout=10
                )
            except psycopg.Error as error:
                raise DatabaseUnavailableError(
                    "Could not connect to the configured PostgreSQL database."
                ) from error
        else:
            Path(self.database_url).parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.database_url, timeout=10)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        except BaseException:
            connection.rollback()
            raise
        else:
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connect() as connection:
            integer_id = (
                "BIGSERIAL PRIMARY KEY"
                if self.use_postgres
                else ("INTEGER PRIMARY KEY AUTOINCREMENT")
            )
            user_id_type = "BIGINT" if self.use_postgres else "INTEGER"
            self._execute(
                connection,
                f"""
                CREATE TABLE IF NOT EXISTS users (
                    id {integer_id},
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """,
            )
            self._execute(
                connection,
                f"""
                CREATE TABLE IF NOT EXISTS forecast_runs (
                    id {integer_id},
                    user_id {user_id_type} REFERENCES users(id) ON DELETE SET NULL,
                    symbol TEXT NOT NULL,
                    horizon INTEGER NOT NULL,
                    selected_method TEXT NOT NULL,
                    future_price DOUBLE PRECISION NOT NULL,
                    mae DOUBLE PRECISION NOT NULL,
                    rmse DOUBLE PRECISION NOT NULL,
                    baseline_mae DOUBLE PRECISION NOT NULL,
                    model_comparison TEXT NOT NULL,
                    walk_forward TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """,
            )
            self._execute(
                connection,
                f"""
                CREATE TABLE IF NOT EXISTS watchlist (
                    user_id {user_id_type} NOT NULL
                        REFERENCES users(id) ON DELETE CASCADE,
                    symbol TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, symbol)
                )
                """,
            )
            if self.use_postgres:
                self._execute(
                    "ALTER TABLE forecast_runs ADD COLUMN IF NOT EXISTS "
                    "user_id BIGINT REFERENCES users(id) ON DELETE SET NULL"
                )
            else:
                columns = {
                    row["name"]
                    for row in self._execute(
                        connection, "PRAGMA table_info(forecast_runs)"
                    )
                }
                if "user_id" not in columns:
                    self._execute(
                        connection,
                        "ALTER TABLE forecast_runs "
                        "ADD COLUMN user_id INTEGER REFERENCES users(id) "
                        "ON DELETE SET NULL",
                    )
            self._execute(
                connection,
                """
                CREATE INDEX IF NOT EXISTS forecast_runs_symbol_created
                ON forecast_runs (symbol, created_at DESC)
                """,
            )

    def save(self, values: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as connection:
            insert = """
                INSERT INTO forecast_runs (
                    symbol, horizon, selected_method, future_price,
                    user_id, mae, rmse, baseline_mae, model_comparison,
                    walk_forward, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
            if self.use_postgres:
                insert += " RETURNING id"
            cursor = self._execute(
                connection,
                insert,
                (
                    values["symbol"],
                    values["horizon"],
                    values["selected_method"],
                    values["future_price"],
                    values.get("user_id"),
                    values["mae"],
                    values["rmse"],
                    values["baseline_mae"],
                    json.dumps(values["model_comparison"]),
                    json.dumps(values["walk_forward"]),
                    values["created_at"],
                ),
            )
            record_id = (
                cursor.fetchone()["id"] if self.use_postgres else cursor.lastrowid
            )
            record = self._execute(
                connection,
                "SELECT * FROM forecast_runs WHERE id = ?",
                (record_id,),
            ).fetchone()
        return self._deserialize(record)

    def list_recent(
        self, symbol: str | None, limit: int, user_id: int | None = None
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM forecast_runs"
        conditions = []
        parameters: tuple[Any, ...] = ()
        if symbol is not None:
            conditions.append("symbol = ?")
            parameters += (symbol,)
        if user_id is not None:
            conditions.append("user_id = ?")
            parameters += (user_id,)
        else:
            conditions.append("user_id IS NULL")
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC, id DESC LIMIT ?"
        parameters += (limit,)
        with self._connect() as connection:
            records = self._execute(connection, query, parameters).fetchall()
        return [self._deserialize(record) for record in records]

    def create_user(self, email: str, password_hash: str) -> dict[str, Any]:
        try:
            with self._connect() as connection:
                insert = (
                    "INSERT INTO users (email, password_hash, created_at) "
                    "VALUES (?, ?, ?)"
                )
                if self.use_postgres:
                    insert += " RETURNING id"
                cursor = self._execute(
                    connection,
                    insert,
                    (email, password_hash, datetime.now(UTC).isoformat()),
                )
                user_id = (
                    cursor.fetchone()["id"] if self.use_postgres else cursor.lastrowid
                )
                record = self._execute(
                    connection,
                    "SELECT id, email, created_at FROM users WHERE id = ?",
                    (user_id,),
                ).fetchone()
        except sqlite3.IntegrityError as error:
            raise DatabaseIntegrityError("User already exists.") from error
        except Exception as error:
            is_postgres_integrity_error = any(
                base.__name__ == "IntegrityError"
                and base.__module__.startswith("psycopg")
                for base in type(error).__mro__
            )
            if not is_postgres_integrity_error:
                raise
            raise DatabaseIntegrityError("User already exists.") from error
        return dict(record)

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            record = self._execute(
                connection,
                "SELECT id, email, password_hash, created_at FROM users WHERE email = ?",
                (email,),
            ).fetchone()
        return dict(record) if record is not None else None

    def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            record = self._execute(
                connection,
                "SELECT id, email, created_at FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        return dict(record) if record is not None else None

    def add_watchlist_symbol(self, user_id: int, symbol: str, created_at: str) -> bool:
        with self._connect() as connection:
            cursor = self._execute(
                connection,
                """
                INSERT INTO watchlist (user_id, symbol, created_at)
                VALUES (?, ?, ?) ON CONFLICT (user_id, symbol) DO NOTHING
                """,
                (user_id, symbol, created_at),
            )
        return cursor.rowcount == 1

    def list_watchlist(self, user_id: int) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = self._execute(
                connection,
                "SELECT symbol, created_at FROM watchlist "
                "WHERE user_id = ? ORDER BY created_at DESC, symbol",
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def remove_watchlist_symbol(self, user_id: int, symbol: str) -> bool:
        with self._connect() as connection:
            cursor = self._execute(
                connection,
                "DELETE FROM watchlist WHERE user_id = ? AND symbol = ?",
                (user_id, symbol),
            )
        return cursor.rowcount == 1

    def check_connection(self) -> None:
        try:
            with self._connect() as connection:
                self._execute(connection, "SELECT 1").fetchone()
        except sqlite3.Error as error:
            raise DatabaseUnavailableError(
                "The configured database is unavailable."
            ) from error

    def _execute(
        self, connection: Any, query: str, parameters: tuple[Any, ...] = ()
    ) -> Any:
        if self.use_postgres:
            query = query.replace("?", "%s")
        return connection.execute(query, parameters)

    @staticmethod
    def _deserialize(record: Any) -> dict[str, Any]:
        result = dict(record)
        result["model_comparison"] = json.loads(result["model_comparison"])
        result["walk_forward"] = json.loads(result["walk_forward"])
        return result
