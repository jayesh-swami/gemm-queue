# gemm-queue Makefile
# Run `make` to see all targets. Add new ones as the project needs them.
# Recipes must be indented with tabs, not spaces.

COMPOSE ?= podman compose
HIPCC_FLAGS ?= -O3

.DEFAULT_GOAL := help
.PHONY: help up db mq api worker down kernels run-api run-worker run-frontend build-frontend test test-integration

help: ## Show this list
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

db: ## Start Postgres, wait until healthy
	$(COMPOSE) up -d db

mq: ## Start RabbitMQ (management UI on localhost:15672)
	$(COMPOSE) up -d mq

up: api worker ## Build and start everything (app on localhost:8000)

api: build-frontend ## Build and start the API container (serves the frontend)
	podman build -f gemm_queue/api/Dockerfile -t gemm-queue-api .
	$(COMPOSE) up -d api

worker: ## Build and start the GPU worker container
	podman build -f gemm_queue/worker/Dockerfile -t gemm-queue-worker .
	$(COMPOSE) up -d worker

down: ## Stop all services (data is kept)
	$(COMPOSE) down

kernels: ## Build the HIP GEMM binary (run inside the ROCm container)
	mkdir -p gemm_queue/worker/kernels/bin
	hipcc $(HIPCC_FLAGS) gemm_queue/worker/kernels/code/matmul_hip_kernel.cpp -lrocblas -o gemm_queue/worker/kernels/bin/matmul

run-api: ## Run the python api
	uv run uvicorn gemm_queue.api.main:app --reload

run-worker: ## Run the worker (WORKER_RUNNER=fake|hip)
	uv run python -m gemm_queue.worker

run-frontend: ## Run the frontend dev server (proxies /jobs to run-api)
	cd gemm_queue/frontend && npm run dev

build-frontend: ## Build the frontend; run-api then serves it at localhost:8000
	cd gemm_queue/frontend && npm run build

test: ## Run the unit tests
	uv run pytest tests/unit

test-integration: ## Run the integration tests (needs make db mq)
	uv run pytest tests/integration
