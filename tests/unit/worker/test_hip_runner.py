"""HipRunner against a stub binary, so the subprocess handling runs without a GPU."""

import sys
import tempfile

import numpy as np
import pytest

from gemm_queue.common.enums import Kernel
from gemm_queue.worker.inputs import make_inputs
from gemm_queue.worker.runners import HipRunner, hip_runner

# Mimics the real binary's CLI. STUB_MODE picks the behaviour.
STUB = f"""#!{sys.executable}
import argparse, json, os, sys, time
import numpy as np

p = argparse.ArgumentParser()
for name in ("kernel", "a", "b", "out"):
    p.add_argument("--" + name)
for name in ("m", "n", "k", "iters"):
    p.add_argument("--" + name, type=int)
args = p.parse_args()

mode = os.environ.get("STUB_MODE", "ok")
if mode == "fail":
    print("boom: kernel launch failed", file=sys.stderr)
    sys.exit(1)
if mode == "hang":
    time.sleep(60)
if mode == "garbage":
    print("not json")
    sys.exit(0)

a = np.fromfile(args.a, np.float32).reshape(args.m, args.k)
b = np.fromfile(args.b, np.float32).reshape(args.k, args.n)
(a @ b).tofile(args.out)
print(json.dumps({{"kernel": args.kernel, "ms": 1.5, "iters": args.iters}}))
"""


@pytest.fixture
def stub(tmp_path):
    path = tmp_path / "matmul"
    path.write_text(STUB)
    path.chmod(0o755)
    return path


@pytest.fixture
def runner(stub):
    return HipRunner(iters=2, binary=stub)


@pytest.fixture(autouse=True)
def own_tempdir(tmp_path, monkeypatch):
    """Point tempfile at an empty dir, so tests can check the runner cleans up."""
    temp = tmp_path / "tmp"
    temp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp))
    return temp


def test_missing_binary_fails_at_construction(tmp_path):
    with pytest.raises(FileNotFoundError, match="make kernels"):
        HipRunner(iters=2, binary=tmp_path / "nope")


def test_command_passes_sizes_and_iters(runner, stub):
    cmd = runner._command(Kernel.LDS, 3, 4, 5, "a", "b", "c")
    assert cmd[0] == str(stub)
    assert cmd[cmd.index("--kernel") + 1] == "lds"
    assert cmd[cmd.index("--m") + 1 :][:5] == ["3", "--n", "4", "--k", "5"]
    assert cmd[cmd.index("--iters") + 1] == "2"


async def test_success_returns_c_and_ms(runner, own_tempdir):
    a, b = make_inputs(5, 30, 20, 10)
    out = await runner.run(Kernel.NAIVE, a, b)

    assert out.success
    assert out.ms == 1.5
    np.testing.assert_allclose(out.c, a @ b, rtol=1e-6)
    assert list(own_tempdir.iterdir()) == []


async def test_column_major_inputs_are_written_row_major(runner):
    a, b = make_inputs(5, 30, 20, 10)
    a_f, b_f = np.asfortranarray(a), np.asfortranarray(b)
    out = await runner.run(Kernel.NAIVE, a_f, b_f)
    np.testing.assert_allclose(out.c, a @ b, rtol=1e-6)


async def test_nonzero_exit_returns_stderr(runner, monkeypatch, own_tempdir):
    monkeypatch.setenv("STUB_MODE", "fail")
    a, b = make_inputs(5, 8, 8, 8)
    out = await runner.run(Kernel.NAIVE, a, b)

    assert not out.success
    assert out.message == "boom: kernel launch failed"
    assert list(own_tempdir.iterdir()) == []


async def test_hang_is_killed_after_the_timeout(runner, monkeypatch, own_tempdir):
    monkeypatch.setenv("STUB_MODE", "hang")
    monkeypatch.setattr(hip_runner, "TIMEOUT_S", 1)
    a, b = make_inputs(5, 8, 8, 8)
    out = await runner.run(Kernel.NAIVE, a, b)

    assert not out.success
    assert out.message == "timed out after 1s"
    assert list(own_tempdir.iterdir()) == []


async def test_garbage_output_is_a_failed_result(runner, monkeypatch):
    monkeypatch.setenv("STUB_MODE", "garbage")
    a, b = make_inputs(5, 8, 8, 8)
    out = await runner.run(Kernel.NAIVE, a, b)

    assert not out.success
    assert out.message.startswith("could not read kernel output")
