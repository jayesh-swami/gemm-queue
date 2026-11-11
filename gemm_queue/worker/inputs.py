import numpy as np


def make_inputs(seed: int, m: int, n: int, k: int) -> tuple[np.ndarray, np.ndarray]:
    """A (M x K) and B (K x N), float32 in [-1, 1). Same seed, same matrices."""
    rng = np.random.default_rng(seed)
    a = rng.uniform(-1, 1, size=(m, k)).astype(np.float32)
    b = rng.uniform(-1, 1, size=(k, n)).astype(np.float32)
    return a, b
