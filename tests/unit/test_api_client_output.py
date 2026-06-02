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


@pytest.mark.unit
def test_download_job_output_sends_force_refresh_query_param(monkeypatch):
    calls = {}

    class _Response:
        headers = {"Content-Disposition": 'attachment; filename="job_1234_stdout.log"'}
        content = b"full-output"

        def raise_for_status(self):
            return None

    def fake_get(url, **kwargs):
        calls["url"] = url
        calls["kwargs"] = kwargs
        return _Response()

    monkeypatch.setattr("ssync.api.client.requests.get", fake_get)

    client = APIClient(base_url="https://ssync.test", api_key="secret")
    assert client.download_job_output(
        job_id="1234",
        host="entalpic",
        output_type="stdout",
        force_refresh=True,
    ) == ("job_1234_stdout.log", b"full-output")

    assert calls["url"] == "https://ssync.test/api/jobs/1234/output/download"
    assert calls["kwargs"]["params"] == {
        "host": "entalpic",
        "output_type": "stdout",
        "compressed": "false",
        "force_refresh": "true",
    }
