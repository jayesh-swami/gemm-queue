"""Submit a stream of jobs, to watch the system work in Grafana.

uv run python scripts/load.py --jobs 20 --size 1024 --every 1 --procs 4

Each process submits --jobs jobs, one every --every seconds, so the total
rate is procs / every jobs per second.
"""

import argparse
import json
import time
import urllib.request
from multiprocessing import Pool

from gemm_queue.api.settings import settings


def submit(args: argparse.Namespace) -> None:
    for _ in range(args.jobs):
        request = urllib.request.Request(
            f"{args.url}/jobs",
            data=json.dumps({"m": args.size, "n": args.size, "k": args.size}).encode(),
            headers={"Content-Type": "application/json", "X-API-Key": settings.api_key},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            print(json.load(response))
        time.sleep(args.every)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=20, help="jobs per process")
    parser.add_argument("--size", type=int, default=1024, help="M = N = K")
    parser.add_argument("--every", type=float, default=1.0, help="seconds between jobs")
    parser.add_argument("--procs", type=int, default=1, help="processes submitting in parallel")
    parser.add_argument("--url", default="http://localhost:8000")
    args = parser.parse_args()

    with Pool(args.procs) as pool:
        pool.map(submit, [args] * args.procs)


if __name__ == "__main__":
    main()
