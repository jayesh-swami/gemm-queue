# API: FastAPI, the results consumer, and the built frontend.
# Build from the repo root after `make build-frontend` (`make api` does both).
FROM docker.io/library/python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /bin/uv
# Use the image's Python instead of downloading one.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies first, so code changes don't re-download them.
COPY pyproject.toml uv.lock .python-version README.md ./
RUN uv sync --locked --no-default-groups --group api --no-install-project

COPY gemm_queue gemm_queue
RUN uv sync --locked --no-default-groups --group api

EXPOSE 8000
# Bring the schema up to date, then serve. 0.0.0.0 is inside the container only;
# compose publishes the port on 127.0.0.1.
CMD ["sh", "-c", "uv run --no-sync alembic -c gemm_queue/api/alembic.ini upgrade head && exec uv run --no-sync uvicorn gemm_queue.api.main:app --host 0.0.0.0 --port 8000"]
