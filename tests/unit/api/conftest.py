import os

# The API modules read settings at import time. Fixed test values; env vars take
# precedence over .env, so the real .env is never used here.
os.environ.update(
    {
        "POSTGRES_USER": "test",
        "POSTGRES_PASSWORD": "test",
        "POSTGRES_DB": "test",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5432",
        "RABBITMQ_USER": "test",
        "RABBITMQ_PASSWORD": "test",
        "RABBITMQ_HOST": "localhost",
        "RABBITMQ_PORT": "5672",
        "API_KEY": "test-key",
    }
)

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from gemm_queue.db.models import Base
from gemm_queue.db.repositories import KernelJobRepository

API_KEY = "test-key"


@pytest.fixture
def session_factory():
    """In-memory SQLite with the real tables, standing in for Postgres.

    StaticPool keeps one shared connection, so FastAPI's worker threads all see
    the same data.
    """
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def job(session_factory):
    """A saved job with its five queued runs."""
    with session_factory() as session:
        job = KernelJobRepository(session).add(m=8, n=8, k=8, seed=1)
        session.commit()
        return job
