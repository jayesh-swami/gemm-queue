# GEMM-Queue

`gemm-queue` benchmarks custom GPU matrix multiplication kernels as a service. You upload two matrices, or pick dimensions and let it generate random ones. A worker then runs three hand-written AMD HIP kernels (naive, tiled shared-memory, and packed FP16), checks each result against a NumPy reference, and reports time, GFLOPS, and speedup.

It’s built like a small HPC job system: a FastAPI front door, a PostgreSQL-backed queue, and a GPU worker behind a pluggable runner interface. That interface lets the whole pipeline be tested without a GPU.
