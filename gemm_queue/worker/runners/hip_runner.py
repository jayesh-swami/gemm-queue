import asyncio
import json
import tempfile
from pathlib import Path

import numpy as np

from gemm_queue.common.enums import Kernel
from gemm_queue.worker.kernel_output_dto import KernelOutputDto
from gemm_queue.worker.kernel_runner import KernelRunner

DEFAULT_BINARY = Path(__file__).resolve().parents[1] / "kernels/bin/matmul"

# Generous enough for the largest naive run; only a stuck kernel hits it.
TIMEOUT_S = 600


class HipRunner(KernelRunner):
    """Runs a kernel through the compiled HIP binary (see kernels/code)."""

    def __init__(self, iters: int, binary: Path = DEFAULT_BINARY) -> None:
        """Fails right away if the binary isn't built, not on the first task."""
        if not binary.is_file():
            raise FileNotFoundError(f"kernel binary not found: {binary} (run `make kernels`)")
        self._binary = binary
        self._iters = iters

    async def run(self, kernel: Kernel, a: np.ndarray, b: np.ndarray) -> KernelOutputDto:
        """Write A, B to temp files -> run the binary -> read back C and the time.

        A crash, hang or garbage output comes back as a failed result.
        """
        m, k = a.shape
        n = b.shape[1]

        with tempfile.TemporaryDirectory(prefix="gemmq-") as tmp:
            a_path = Path(tmp) / "a.f32"
            b_path = Path(tmp) / "b.f32"
            out_path = Path(tmp) / "out.f32"
            await asyncio.to_thread(a.tofile, a_path)
            await asyncio.to_thread(b.tofile, b_path)

            proc = await asyncio.create_subprocess_exec(
                *self._command(kernel, m, n, k, a_path, b_path, out_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), TIMEOUT_S)
            except TimeoutError:
                proc.kill()
                await proc.wait()
                return KernelOutputDto.failed(f"timed out after {TIMEOUT_S}s")

            if proc.returncode != 0:
                detail = stderr.decode(errors="replace").strip()
                return KernelOutputDto.failed(detail or f"exit code {proc.returncode}")

            try:
                ms = float(json.loads(stdout)["ms"])
                c = await asyncio.to_thread(np.fromfile, out_path, np.float32)
                return KernelOutputDto.ok(c.reshape(m, n), ms)
            except (ValueError, KeyError, OSError) as exc:
                return KernelOutputDto.failed(f"could not read kernel output: {exc}")

    def _command(
        self, kernel: Kernel, m: int, n: int, k: int, a_path: Path, b_path: Path, out_path: Path
    ) -> list[str]:
        """The binary's command line, as a list (no shell involved)."""
        # Each flag stays next to its value; the formatter would put them on separate lines.
        # fmt: off
        return [
            str(self._binary),
            "--kernel", kernel.value,
            "--m", str(m), "--n", str(n), "--k", str(k),
            "--a", str(a_path), "--b", str(b_path), "--out", str(out_path),
            "--iters", str(self._iters),
        ]
        # fmt: on
