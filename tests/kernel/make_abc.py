"""Writes a.bin, b.bin and the expected c.bin next to this file.

A is MxK, B is KxN, C = A @ B is MxN, all raw row-major float32.
2048^3 is large enough to give meaningful timings (~17 GFLOP per run).
"""

from pathlib import Path

import numpy as np

M, K, N = 2048, 2048, 2048

here = Path(__file__).parent
rng = np.random.default_rng(0)

a = rng.uniform(-1, 1, size=(M, K)).astype(np.float32)
b = rng.uniform(-1, 1, size=(K, N)).astype(np.float32)
c = (a.astype(np.float64) @ b.astype(np.float64)).astype(np.float32)

a.tofile(here / "a.bin")
b.tofile(here / "b.bin")
c.tofile(here / "c.bin")
print(f"wrote a.bin ({M}x{K}), b.bin ({K}x{N}), c.bin ({M}x{N}) to {here}")
