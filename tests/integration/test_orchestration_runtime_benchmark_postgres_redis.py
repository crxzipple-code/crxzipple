from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text

from crxzipple.core.config import load_settings


@pytest.mark.integration
@pytest.mark.benchmark
def test_orchestration_runtime_benchmark_uses_postgres_and_redis_infra() -> None:
    if os.environ.get("CRXZIPPLE_RUN_ORCHESTRATION_BENCHMARK_INTEGRATION") != "1":
        pytest.skip("Postgres/Redis orchestration benchmark integration is opt-in.")

    settings = load_settings()
    assert settings.database_url.startswith(("postgresql://", "postgresql+psycopg://"))
    assert settings.events_backend == "redis"
    assert settings.events_redis_url.startswith("redis://")

    engine = create_engine(settings.database_url)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        engine.dispose()

    from redis import Redis

    redis_client = Redis.from_url(settings.events_redis_url)
    assert redis_client.ping() is True
