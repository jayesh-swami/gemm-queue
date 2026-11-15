"""Submit a stream of jobs, to watch the system work in Grafana.

uv run python scripts/load.py --jobs 20 --size 1024 --every 1
"""

import argparse
import json
import time
import urllib.request

from gemm_queue.api.settings import settings

parser = argparse.ArgumentParser()
parser.add_argument("--jobs", type=int, default=20)
parser.add_argument("--size", type=int, default=1024, help="M = N = K")
parser.add_argument("--every", type=float, default=1.0, help="seconds between jobs")
parser.add_argument("--url", default="http://localhost:8000")
args = parser.parse_args()

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
