from dataclasses import dataclass
from typing import Self

import numpy as np


@dataclass(frozen=True)
class KernelOutputDto:
    """What a KernelRunner returns for one run.

    A failed run is an expected outcome (non-zero exit, timeout, unsupported
    shape) and is returned, not raised. Exceptions are reserved for things
    that are actually broken.
    """

    success: bool
    message: str
    c: np.ndarray | None = None
    ms: float | None = None

    @classmethod
    def ok(cls, c: np.ndarray, ms: float) -> Self:
        return cls(success=True, message="", c=c, ms=ms)

    @classmethod
    def failed(cls, message: str) -> Self:
        return cls(success=False, message=message)
