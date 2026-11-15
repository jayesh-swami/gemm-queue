def test_ready_with_real_services(client):
    assert client.get("/ready").json() == {"status": "ready"}


def test_metrics_endpoint(client):
    client.post("/jobs", json={"m": 8, "n": 8, "k": 8})
    assert "api_jobs_submitted_total 1.0" in client.get("/metrics").text
