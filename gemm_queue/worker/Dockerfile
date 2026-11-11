# GPU worker: ROCm runtime + rocBLAS, the compiled HIP binary, and the Python worker.
# Build from the repo root: docker-compose.yml sets context: .
FROM docker.io/rocm/dev-ubuntu-24.04:7.2.1

# GPU the kernels are compiled for (gfx1151 = Radeon 8060S). No GPU is visible
# during the build, so hipcc can't detect it.
ARG GPU_ARCH=gfx1151

RUN apt-get update \
    && apt-get install -y --no-install-recommends rocblas-dev make \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_INSTALL_DIR=/opt/python

WORKDIR /app

# Dependencies first, so code changes don't re-download them.
COPY pyproject.toml uv.lock .python-version README.md ./
RUN uv sync --locked --no-dev --no-install-project

COPY Makefile ./
COPY gemm_queue/worker/kernels/code gemm_queue/worker/kernels/code
RUN make kernels HIPCC_FLAGS="-O3 --offload-arch=${GPU_ARCH}"

COPY gemm_queue gemm_queue
RUN uv sync --locked --no-dev

CMD ["uv", "run", "--no-sync", "python", "-m", "gemm_queue.worker"]
