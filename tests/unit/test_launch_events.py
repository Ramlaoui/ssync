"""Unit tests for launch event streaming and CLI follow-up behavior."""

import asyncio
from pathlib import Path

import pytest

from ssync.cli import commands
from ssync.launch_events import LaunchEventManager


@pytest.mark.unit
@pytest.mark.asyncio
async def test_launch_event_manager_buffers_events_and_terminal_status():
    manager = LaunchEventManager()
    await manager.start()

    try:
        emitter = manager.create_emitter("launch-123", "entalpic")
        emitter.stage("accepted", message="Accepted")
        emitter.log("sync", "sending incremental file list", stream="stdout")
        emitter.stage("submit_started", message="Submitting job")
        emitter.result(success=True, message="Job launched", job_id="4242")

        await asyncio.sleep(0)

        status = manager.get_status("launch-123")

        assert status is not None
        assert status["terminal"] is True
        assert status["success"] is True
        assert status["job_id"] == "4242"
        assert status["stage"] == "completed"
        assert [event["type"] for event in status["events"]] == [
            "launch_stage",
            "launch_log",
            "launch_stage",
            "launch_result",
        ]

        snapshot, queue = await manager.subscribe("launch-123")
        assert snapshot["terminal"] is True
        assert snapshot["events"][-1]["type"] == "launch_result"
        assert queue.empty()
    finally:
        await manager.stop()


@pytest.mark.unit
def test_launch_command_follows_async_launch(monkeypatch, tmp_path):
    script_path = tmp_path / "job.sh"
    script_path.write_text("#!/bin/bash\necho hello\n")
    source_dir = tmp_path / "src"
    source_dir.mkdir()

    outputs = []

    class _FakeAPIClient:
        def __init__(self, base_url=None, verbose=False):
            self.verbose = verbose

        def ensure_server_running(self, config_path):
            return True, None

        def launch_job(self, **kwargs):
            return {
                "success": True,
                "launch_id": "launch-abc",
                "job_id": None,
                "message": "Launch started",
                "hostname": "entalpic",
            }

        def stream_launch_events(self, launch_id):
            assert launch_id == "launch-abc"
            yield {
                "type": "launch_stage",
                "launch_id": launch_id,
                "hostname": "entalpic",
                "sequence": 1,
                "timestamp": "2026-01-01T00:00:00+00:00",
                "stage": "sync_started",
                "message": "Syncing files",
            }
            yield {
                "type": "launch_log",
                "launch_id": launch_id,
                "hostname": "entalpic",
                "sequence": 2,
                "timestamp": "2026-01-01T00:00:01+00:00",
                "source": "sync",
                "stream": "stdout",
                "message": "job.sh",
            }
            yield {
                "type": "launch_result",
                "launch_id": launch_id,
                "hostname": "entalpic",
                "sequence": 3,
                "timestamp": "2026-01-01T00:00:02+00:00",
                "success": True,
                "job_id": "5150",
                "message": "Job launched successfully (5150)",
            }

        def get_launch_status(self, launch_id):
            raise AssertionError("status fallback should not be used")

    monkeypatch.setattr(commands, "APIClient", _FakeAPIClient)
    monkeypatch.setattr(
        commands.click,
        "echo",
        lambda message="", err=False: outputs.append((message, err)),
    )

    command = commands.LaunchCommand(
        config_path=Path("/tmp/ssync-config.yaml"),
        slurm_hosts=[],
        verbose=True,
    )

    success = command.execute(
        script_path=script_path,
        source_dir=source_dir,
        host="entalpic",
    )

    assert success is True
    assert outputs == [
        ("Launch started", False),
        ("Syncing files", False),
        ("[sync/stdout] job.sh", False),
        ("Job launched successfully with ID: 5150", False),
    ]
