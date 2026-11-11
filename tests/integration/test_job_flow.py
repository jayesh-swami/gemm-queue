from helpers import wait_until


def test_job_runs_end_to_end(client):
    """API -> gemm.tasks -> worker (fake runner) -> gemm.results -> consumer -> DB."""
    res = client.post("/jobs", json={"m": 64, "n": 48, "k": 33})
    assert res.status_code == 202
    job_id = res.json()["job_id"]

    def finished_job():
        job = client.get(f"/jobs/{job_id}").json()
        return job if job["status"] in ("done", "failed") else None

    job = wait_until(finished_job)

    assert job["status"] == "done"
    assert job["finished_at"] is not None
    runs = {r["kernel"]: r for r in job["kernel_runs"]}

    # K = 33 is odd, so half2 fails and the rest run normally
    assert runs.pop("half2")["error"] == "half2 needs K and N to be even"
    for run in runs.values():
        assert run["status"] == "done"
        assert run["passed"] is True
        assert run["tflops"] > 0
