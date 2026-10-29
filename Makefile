# gemm-queue Makefile
# Run `make` to see all targets. Add new ones as the project needs them.
# Recipes must be indented with tabs, not spaces.

COMPOSE ?= podman compose
HIPCC ?= hipcc
HIPFLAGS ?= -O3

KERNEL_SRC := kernels/code/matmul_hip_kernel.cpp
KERNEL_BIN := kernels/bin/matmul

.DEFAULT_GOAL := help
.PHONY: db down kernels

help: ## Show this list
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

db: ## Start Postgres, wait until healthy
	$(COMPOSE) up -d db

down: ## Stop Postgres (data is kept)
	$(COMPOSE) down

kernels: $(KERNEL_BIN) ## Build the HIP GEMM binary (run inside the ROCm container)

$(KERNEL_BIN): $(KERNEL_SRC) kernels/code/hip_helpers.h
	@mkdir -p $(dir $@)
	$(HIPCC) $(HIPFLAGS) $(KERNEL_SRC) -lrocblas -o $@
