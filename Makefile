# gemm-queue Makefile
# Run `make` to see all targets. Add new ones as the project needs them.
# Recipes must be indented with tabs, not spaces.

# The compose file lives in deploy/; the repo root stays the project directory, so .env,
# ./.pgdata and the project name (gemm-queue: volumes, container names) resolve as before.
COMPOSE ?= podman compose -f deploy/docker-compose.yml --project-directory .
HIPCC_FLAGS ?= -O3
# AMD GPU the worker image compiles the kernels for (rocminfo | grep gfx)
GPU_ARCH ?= gfx1151
# make up WORKERS=3 RUNNER=fake: how many workers and their runner (default: WORKER_RUNNER in .env)
WORKERS ?= 1
RUNNER ?=
# make up RESULTS=2: how many results consumers
RESULTS ?= 1

.DEFAULT_GOAL := help
.PHONY: help up db mq api results worker sweeper monitoring down migrate kernels run-api run-results run-worker run-sweeper run-frontend build-frontend test test-integration lint load-test

help: ## Show this list
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

db: ## Start Postgres, wait until healthy
	$(COMPOSE) up -d --wait db

mq: ## Start RabbitMQ (management UI on localhost:15672)
	$(COMPOSE) up -d --wait mq

up: api results worker sweeper monitoring ## Build and start everything; WORKERS=N RUNNER=fake|hip RESULTS=N

api: build-frontend ## Build and start the API container (serves the frontend)
	podman build -f deploy/api.Dockerfile -t gemm-queue-api .
	$(COMPOSE) up -d api

results: api ## Start RESULTS results consumers (default 1, uses the API image)
	$(COMPOSE) up -d --scale results=$(RESULTS) results
	$(COMPOSE) restart pushgateway  # forget metrics of removed replicas; live ones re-push in 5 s

worker: ## Build and start WORKERS workers (default 1); RUNNER=fake|hip overrides .env
	podman build -f deploy/worker.Dockerfile --build-arg GPU_ARCH=$(GPU_ARCH) -t gemm-queue-worker .
	$(if $(RUNNER),WORKER_RUNNER=$(RUNNER)) $(COMPOSE) up -d --scale worker=$(WORKERS) worker
	$(COMPOSE) restart pushgateway  # forget metrics of removed workers; live ones re-push in 5 s

sweeper: api ## Start the sweeper batch job (uses the API image)
	$(COMPOSE) up -d sweeper

monitoring: ## Start Prometheus, Pushgateway, Postgres exporter and Grafana (localhost:3000)
	$(COMPOSE) up -d pushgateway postgres-exporter prometheus grafana

down: ## Stop all services (data is kept)
	$(COMPOSE) down

migrate: ## Apply DB migrations (the API container also does this on start)
	uv run alembic -c gemm_queue/api/alembic.ini upgrade head

kernels: ## Build the HIP GEMM binary (run inside the ROCm container)
	mkdir -p gemm_queue/worker/kernels/bin
	hipcc $(HIPCC_FLAGS) gemm_queue/worker/kernels/code/matmul_hip_kernel.cpp -lrocblas -o gemm_queue/worker/kernels/bin/matmul

run-api: ## Run the python api
	uv run uvicorn gemm_queue.api.main:app --reload

run-results: ## Run the results consumer
	uv run python -m gemm_queue.results

run-worker: ## Run the worker (WORKER_RUNNER=fake|hip)
	uv run python -m gemm_queue.worker

run-sweeper: ## Run the sweeper on the host
	uv run python -m gemm_queue.batch.sweeper

run-frontend: ## Run the frontend dev server (proxies /jobs to run-api)
	cd gemm_queue/frontend && npm run dev

build-frontend: ## Build the frontend; run-api then serves it at localhost:8000
	cd gemm_queue/frontend && ([ -d node_modules ] || npm ci) && npm run build

test: ## Run the unit tests
	uv run pytest tests/unit

test-integration: ## Run the integration tests (needs make db mq)
	uv run pytest tests/integration

lint: ## Run all pre-commit hooks on every file
	uv run pre-commit run --all-files

load-test: ## Submit a stream of jobs to watch in Grafana (JOBS=20 SIZE=1024 EVERY=1 PROCS=1, JOBS per process)
	uv run python scripts/load.py --jobs $(or $(JOBS),20) --size $(or $(SIZE),1024) --every $(or $(EVERY),1) --procs $(or $(PROCS),1)
