# gemm-queue Makefile
# Run `make` to see all targets. Add new ones as the project needs them.
# Recipes must be indented with tabs, not spaces.

COMPOSE ?= podman compose

.DEFAULT_GOAL := help
.PHONY: help db mq down kernels run-api

help: ## Show this list
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

db: ## Start Postgres, wait until healthy
	$(COMPOSE) up -d db

mq: ## Start RabbitMQ (management UI on localhost:15672)
	$(COMPOSE) up -d mq

down: ## Stop all services (data is kept)
	$(COMPOSE) down

kernels: ## Build the HIP GEMM binary (run inside the ROCm container)
	mkdir -p gemm_queue/worker/kernels/bin
	hipcc -O3 gemm_queue/worker/kernels/code/matmul_hip_kernel.cpp -lrocblas -o gemm_queue/worker/kernels/bin/matmul

run-api: ## Run the python api
	uv run uvicorn gemm_queue.api.main:app --reload

