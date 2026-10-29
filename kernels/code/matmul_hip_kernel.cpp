#include <hip/hip_runtime.h>
#include <hip/hip_fp16.h>
#include <rocblas/rocblas.h>
#include <string>
#include <vector>
#include "hip_helpers.h"

#define TILE_DIM 16

#define ROCBLAS_CHECK(call)                                             \
    do {                                                                \
        rocblas_status s = (call);                                      \
        if (s != rocblas_status_success) {                              \
            fprintf(stderr, "rocBLAS error: %s at %s:%d\n",             \
                    rocblas_status_to_string(s), __FILE__, __LINE__);   \
            std::exit(1);                                               \
        }                                                               \
    } while (0)

__global__ void multiply_two_arrays_naive(float array1[], float array2[], float result[], int M, int N, int K) {

    int row = blockIdx.y * blockDim.y + threadIdx.y;
    int col = blockIdx.x * blockDim.x + threadIdx.x;

    if (row < M && col < N) {
      float res = 0.0f;
      for(int i = 0; i < K; i++) {
          res += array1[row * K + i] * array2[i * N + col];
      }
      result[row * N + col] = res;
    }
}

__global__ void multiply_two_arrays_lds_optimized(float array1[], float array2[], float result[], int M, int N, int K) {

    int row = blockIdx.y * TILE_DIM + threadIdx.y;
    int col = blockIdx.x * TILE_DIM + threadIdx.x;

    __shared__ float lds1[TILE_DIM][TILE_DIM];
    __shared__ float lds2[TILE_DIM][TILE_DIM];

    float res = 0.0f;

    for(int tile = 0; tile < (K + TILE_DIM - 1)/TILE_DIM; tile++) {

      if(row < M && tile * TILE_DIM + threadIdx.x < K) {
        lds1[threadIdx.y][threadIdx.x] = array1[row * K + (tile * TILE_DIM + threadIdx.x)];
      } else {
        lds1[threadIdx.y][threadIdx.x] = 0.0f;
      }

      if(col < N && tile * TILE_DIM + threadIdx.y < K) {
        lds2[threadIdx.y][threadIdx.x] = array2[(tile * TILE_DIM + threadIdx.y) * N + col];
      } else {
        lds2[threadIdx.y][threadIdx.x] = 0.0f;
      }

      __syncthreads();

      for(int i = 0; i < TILE_DIM; i++) {
        res += lds1[threadIdx.y][i] * lds2[i][threadIdx.x];
      }

      __syncthreads();
    }
    if(row < M && col < N) {
      result[row * N + col] = res;
    }
}

__global__ void multiply_two_arrays_half2(__half array1[], __half array2[], __half result[], int M, int N, int K)  {
    int tx = threadIdx.x;
    int ty = threadIdx.y;

    int row = blockIdx.y * 32 + ty;
    int col = (blockIdx.x * 16 + tx) * 2;

    __shared__ __half ldsA[32][32];
    __shared__ __half2 ldsB[32][16];

    const __half2* A = (const __half2*)array1;
    const __half2* B = (const __half2*)array2;
    const __half2 zero = __float2half2_rn(0.0f);

    float acc0 = 0.0f;
    float acc1 = 0.0f;

    for (int t = 0; t < (K + 31) / 32; ++t) {

        int a_col = t * 32 + tx * 2;
        ((__half2*)ldsA)[ty * 16 + tx] = (row < M && a_col < K) ? A[(row * K + a_col) / 2] : zero;

        int b_row = t * 32 + ty;
        ldsB[ty][tx] = (b_row < K && col < N) ? B[(b_row * N + col) / 2] : zero;

        __syncthreads();

        for (int k = 0; k < 32; ++k) {
            float a = __half2float(ldsA[ty][k]);
            float2 b = __half22float2(ldsB[k][tx]);
            acc0 += a * b.x;
            acc1 += a * b.y;
        }

        __syncthreads();
    }

    if (row < M && col < N) {
        ((__half2*)result)[(row * N + col) / 2] = __floats2half2_rn(acc0, acc1);
    }
}

static void usage(const char* prog) {
    fprintf(stderr,
            "usage: %s --kernel naive|lds|half2|rocblas|rocblas_half --m M --n N --k K --a A.bin --b B.bin --out C.bin [--iters I]\n"
            "  A is MxK, B is KxN, C is MxN; all files are raw row-major float32\n",
            prog);
    exit(2);
}

static std::vector<float> read_matrix(const char* path, size_t count) {
    std::vector<float> data(count);
    FILE* f = fopen(path, "rb");
    if (!f || fread(data.data(), sizeof(float), count, f) != count) {
        fprintf(stderr, "could not read %zu floats from %s\n", count, path);
        exit(1);
    }
    fclose(f);
    return data;
}

static void write_matrix(const char* path, const std::vector<float>& data) {
    FILE* f = fopen(path, "wb");
    if (!f || fwrite(data.data(), sizeof(float), data.size(), f) != data.size()) {
        fprintf(stderr, "could not write %s\n", path);
        exit(1);
    }
    fclose(f);
}

// Copies a matrix to the GPU, converting it to fp16 when `half` is set.
static void* to_device(const std::vector<float>& host, bool half) {
    void* dev;
    if (half) {
        std::vector<__half> tmp(host.size());
        for (size_t i = 0; i < host.size(); i++) tmp[i] = __float2half(host[i]);
        HIP_CHECK(hipMalloc(&dev, tmp.size() * sizeof(__half)));
        HIP_CHECK(hipMemcpy(dev, tmp.data(), tmp.size() * sizeof(__half), hipMemcpyHostToDevice));
    } else {
        HIP_CHECK(hipMalloc(&dev, host.size() * sizeof(float)));
        HIP_CHECK(hipMemcpy(dev, host.data(), host.size() * sizeof(float), hipMemcpyHostToDevice));
    }
    return dev;
}

// Copies a matrix back from the GPU, converting it from fp16 when `half` is set.
static void from_device(std::vector<float>& host, const void* dev, bool half) {
    if (half) {
        std::vector<__half> tmp(host.size());
        HIP_CHECK(hipMemcpy(tmp.data(), dev, tmp.size() * sizeof(__half), hipMemcpyDeviceToHost));
        for (size_t i = 0; i < host.size(); i++) host[i] = __half2float(tmp[i]);
    } else {
        HIP_CHECK(hipMemcpy(host.data(), dev, host.size() * sizeof(float), hipMemcpyDeviceToHost));
    }
}

static void launch(const std::string& kernel, rocblas_handle handle, void* a, void* b, void* c, int M, int N, int K) {
    if (kernel == "rocblas") {
        const float alpha = 1.0f;
        const float beta = 0.0f;
        ROCBLAS_CHECK(rocblas_sgemm(handle, rocblas_operation_none, rocblas_operation_none,
                                    N, M, K, &alpha, (float*)b, N, (float*)a, K, &beta, (float*)c, N));
    } else if (kernel == "rocblas_half") {
        // fp16 in and out with fp32 accumulation, the same as half2
        const float alpha = 1.0f;
        const float beta = 0.0f;
        ROCBLAS_CHECK(rocblas_gemm_ex(handle, rocblas_operation_none, rocblas_operation_none,
                                      N, M, K, &alpha,
                                      b, rocblas_datatype_f16_r, N,
                                      a, rocblas_datatype_f16_r, K, &beta,
                                      c, rocblas_datatype_f16_r, N,
                                      c, rocblas_datatype_f16_r, N,
                                      rocblas_datatype_f32_r, rocblas_gemm_algo_standard, 0, 0));
    } else if (kernel == "naive") {
        dim3 block(16, 16);
        dim3 grid((N + 15) / 16, (M + 15) / 16);
        multiply_two_arrays_naive<<<grid, block>>>((float*)a, (float*)b, (float*)c, M, N, K);
    } else if (kernel == "lds") {
        dim3 block(TILE_DIM, TILE_DIM);
        dim3 grid((N + TILE_DIM - 1) / TILE_DIM, (M + TILE_DIM - 1) / TILE_DIM);
        multiply_two_arrays_lds_optimized<<<grid, block>>>((float*)a, (float*)b, (float*)c, M, N, K);
    } else {
        dim3 block(16, 32);
        dim3 grid((N + 31) / 32, (M + 31) / 32);
        multiply_two_arrays_half2<<<grid, block>>>((__half*)a, (__half*)b, (__half*)c, M, N, K);
    }
}

int main(int argc, char** argv) {
    std::string kernel;
    const char* a_path = nullptr;
    const char* b_path = nullptr;
    const char* out_path = nullptr;
    int M = 0, N = 0, K = 0, iters = 10;

    for (int i = 1; i + 1 < argc; i += 2) {
        std::string flag = argv[i];
        const char* value = argv[i + 1];

        if (flag == "--kernel") kernel = value;
        else if (flag == "--m") M = atoi(value);
        else if (flag == "--n") N = atoi(value);
        else if (flag == "--k") K = atoi(value);
        else if (flag == "--a") a_path = value;
        else if (flag == "--b") b_path = value;
        else if (flag == "--out") out_path = value;
        else if (flag == "--iters") iters = atoi(value);
        else usage(argv[0]);
    }

    bool use_rocblas = kernel == "rocblas" || kernel == "rocblas_half";
    bool half = kernel == "half2" || kernel == "rocblas_half";
    if (kernel != "naive" && kernel != "lds" && kernel != "half2" && !use_rocblas) usage(argv[0]);
    if (!a_path || !b_path || !out_path || M < 1 || N < 1 || K < 1 || iters < 1) usage(argv[0]);
    if (kernel == "half2" && (K % 2 != 0 || N % 2 != 0)) {
        fprintf(stderr, "half2 needs K and N to be even\n");
        return 1;
    }

    std::vector<float> a = read_matrix(a_path, (size_t)M * K);
    std::vector<float> b = read_matrix(b_path, (size_t)K * N);
    std::vector<float> c((size_t)M * N);

    void* d_a = to_device(a, half);
    void* d_b = to_device(b, half);
    void* d_c = to_device(c, half);

    rocblas_handle handle = nullptr;
    if (use_rocblas) {
        ROCBLAS_CHECK(rocblas_create_handle(&handle));
    }

    // warm-up run, which also surfaces launch errors before timing
    launch(kernel, handle, d_a, d_b, d_c, M, N, K);
    HIP_CHECK(hipGetLastError());
    HIP_CHECK(hipDeviceSynchronize());

    hipEvent_t start, stop;
    HIP_CHECK(hipEventCreate(&start));
    HIP_CHECK(hipEventCreate(&stop));
    HIP_CHECK(hipEventRecord(start));
    for (int i = 0; i < iters; i++) {
        launch(kernel, handle, d_a, d_b, d_c, M, N, K);
    }
    HIP_CHECK(hipEventRecord(stop));
    HIP_CHECK(hipEventSynchronize(stop));
    HIP_CHECK(hipGetLastError());

    float total_ms = 0.0f;
    HIP_CHECK(hipEventElapsedTime(&total_ms, start, stop));
    double ms = total_ms / iters;

    // a GEMM does M*N*K multiply-adds, i.e. 2*M*N*K floating-point ops
    double tflops = 2.0 * M * N * K / (ms * 1e-3) / 1e12;

    from_device(c, d_c, half);
    write_matrix(out_path, c);

    printf("{\"kernel\": \"%s\", \"m\": %d, \"n\": %d, \"k\": %d, \"iters\": %d, \"ms\": %.6f, \"tflops\": %.4f}\n",
           kernel.c_str(), M, N, K, iters, ms, tflops);

    HIP_CHECK(hipFree(d_a));
    HIP_CHECK(hipFree(d_b));
    HIP_CHECK(hipFree(d_c));
    if (handle) {
        ROCBLAS_CHECK(rocblas_destroy_handle(handle));
    }
    return 0;
}
