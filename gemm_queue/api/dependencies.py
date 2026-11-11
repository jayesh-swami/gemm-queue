from collections.abc import Iterator

from aio_pika.abc import AbstractChannel
from fastapi import Request
from sqlalchemy.orm import Session

from gemm_queue.api.db.session import SessionLocal


def get_mq_channel(request: Request) -> AbstractChannel:
    return request.app.state.mq_channel


def get_db_session() -> Iterator[Session]:
    # A sync generator dependency, so FastAPI opens and closes it in its
    # thread pool. Anything not committed by the endpoint is rolled back.
    with SessionLocal() as session:
        yield session
