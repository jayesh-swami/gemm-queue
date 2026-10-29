#pragma once

#include <hip/hip_runtime.h>
#include <cstdio>
#include <cstdlib>

#define HIP_CHECK(call)                                                 \
    do {                                                                \
        hipError_t e = (call);                                          \
        if (e != hipSuccess) {                                          \
            fprintf(stderr, "HIP error: %s at %s:%d\n",                 \
                    hipGetErrorString(e), __FILE__, __LINE__);          \
            std::exit(1);                                               \
        }                                                               \
    } while (0)
