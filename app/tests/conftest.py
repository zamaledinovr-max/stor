"""Shared pytest fixtures.

Tests run against a real SQLite database file created by the application
lifespan, so SQLAlchemy models, middlewares, dependency overrides and the
storage layer are exercised end to end. PostgreSQL-specific behaviour is
covered by the migration test instructions in the README.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from urllib.parse import urlencode

os.environ["APP_ENV"] = "test"
os.environ["APP_SECRET_KEY"] = "test-secret-key-long-enough-for-validation-0001"
os.environ["TELEGRAM_BOT_TOKEN"] = "123456:TEST-BOT-TOKEN"
os.environ["TELEGRAM_WEBAPP_URL"] = "http://localhost:8000"
os.environ["TELEGRAM_ADMIN_IDS"] = "900001,900002"
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["LOG_LEVEL"] = "WARNING"

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

TEST_SECRET = "test-secret-key-long-enough-for-validation-0001"
TEST_BOT_TOKEN = "123456:TEST-BOT-TOKEN"
ADMIN_ID = 900001


def settings_kwargs(tmp_path: Path, **overrides) -> dict:
    kwargs: dict = {
        "app_env": "test",
        "app_secret_key": TEST_SECRET,
        "telegram_bot_token": TEST_BOT_TOKEN,
        "telegram_webapp_url": "http://localhost:8000",
        "telegram_admin_ids": f"{ADMIN_ID},900002",
        "database_url": f"sqlite+pysqlite:///{(tmp_path / 'test.db').as_posix()}",
        "app_auto_create_tables": True,
        "local_storage_dir": tmp_path / "media",
        "frontend_dir": tmp_path / "missing-frontend",
        # Most tests exercise the catalog without the moderation step; the
        # moderated flow has its own tests that switch this flag on.
        "listing_moderation_enabled": False,
        "rate_limit_requests_per_minute_per_ip": 0,
        "log_level": "WARNING",
    }
    kwargs.update(overrides)
    return kwargs


def build_init_data(
    bot_token: str = TEST_BOT_TOKEN,
    user_id: int = 1001,
    *,
    auth_date: int | None = None,
    user: dict | None = None,
    extra_fields: dict | None = None,
) -> str:
    payload = user or {
        "id": user_id,
        "first_name": "Тест",
        "last_name": "Пользователь",
        "username": f"user{user_id}",
        "language_code": "ru",
    }
    fields = {
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        "query_id": f"AAH{user_id}",
        "user": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
    }
    if extra_fields:
        fields.update(extra_fields)
    data_check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    return urlencode(fields)


@pytest.fixture()
def client_factory(tmp_path: Path):
    clients: list[TestClient] = []
    counter = {"value": 0}

    def _factory(**overrides) -> TestClient:
        counter["value"] += 1
        directory = tmp_path / f"app{counter['value']}"
        directory.mkdir(parents=True, exist_ok=True)
        settings = Settings(_env_file=None, **settings_kwargs(directory, **overrides))
        application = create_app(settings)
        test_client = TestClient(application)
        test_client.__enter__()
        clients.append(test_client)
        return test_client

    yield _factory

    for test_client in clients:
        test_client.__exit__(None, None, None)


@pytest.fixture()
def client(client_factory) -> TestClient:
    return client_factory()


@pytest.fixture()
def session_factory(client: TestClient):
    return client.app.state.session_factory


@pytest.fixture()
def auth_headers(client: TestClient):
    def _headers(user_id: int = 1001, **kwargs) -> dict[str, str]:
        return {"Authorization": f"tma {build_init_data(user_id=user_id, **kwargs)}"}

    return _headers


@pytest.fixture()
def create_listing(client: TestClient, auth_headers):
    def _create(user_id: int = 1001, headers: dict | None = None, **payload):
        body = {
            "kind": "sell",
            "title": "iPhone 12 128 ГБ",
            "description": "Комплект, чехол в подарок.",
            "condition": "good",
            "price_amount": "35000",
            "district": "Центр",
        }
        body.update(payload)
        return client.post(
            "/api/listings",
            json=body,
            headers=headers if headers is not None else auth_headers(user_id),
        )

    return _create
