"""Unit tests for API client output requests."""

import pytest

from ssync.api.client import APIClient


@pytest.mark.unit
def test_get_job_output_sends_all_query_param(monkeypatch):
    calls = {}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"stdout": "full-output"}

    def fake_get(url, **kwargs):
        calls["url"] = url
        calls["kwargs"] = kwargs
        return _Response()

    monkeypatch.setattr("ssync.api.client.requests.get", fake_get)

    client = APIClient(base_url="https://ssync.test", api_key="secret")
    assert client.get_job_output(
        job_id="1234",
        host="entalpic",
        output_type="stdout",
        full_output=True,
    ) == {"stdout": "full-output"}

    assert calls["url"] == "https://ssync.test/api/jobs/1234/output"
    assert calls["kwargs"]["params"] == {
        "host": "entalpic",
        "output_type": "stdout",
        "all": "true",
    }
