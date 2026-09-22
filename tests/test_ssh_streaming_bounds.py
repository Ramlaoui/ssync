"""Regression tests for bounded local SSH command streaming."""

import io
import sys
import time

import pytest

from ssync.ssh.connection import SSHConnection

CAPTURE_LIMIT = 1024 * 1024


@pytest.mark.unit
def test_streaming_bounds_capture_but_delivers_large_no_newline_output():
    """Callbacks see all output while the returned capture keeps a bounded tail."""
    output_size = 2 * CAPTURE_LIMIT
    command = [
        sys.executable,
        "-c",
        (
            "import sys; "
            f"sys.stdout.write('x' * {output_size}); sys.stdout.flush(); "
            f"sys.stderr.write('y' * {output_size}); sys.stderr.flush()"
        ),
    ]
    stdout_stream = io.StringIO()
    stderr_stream = io.StringIO()

    result = SSHConnection._run_streaming_command(
        command,
        timeout=10,
        out_stream=stdout_stream,
        err_stream=stderr_stream,
    )

    assert result.returncode == 0
    assert len(result.stdout) <= CAPTURE_LIMIT
    assert len(result.stderr) <= CAPTURE_LIMIT
    assert b"stdout truncated" in result.stdout
    assert b"stderr truncated" in result.stderr
    assert stdout_stream.getvalue() == "x" * output_size
    assert stderr_stream.getvalue() == "y" * output_size


@pytest.mark.unit
def test_streaming_uses_incremental_utf8_decode_for_short_writes():
    """A multibyte character split across reads is delivered once decoded."""
    command = [
        sys.executable,
        "-c",
        (
            "import sys,time; "
            "sys.stdout.buffer.write(b'\\xc3'); sys.stdout.flush(); "
            "time.sleep(0.1); "
            "sys.stdout.buffer.write(b'\\xa9\\n'); sys.stdout.flush()"
        ),
    ]
    stdout_stream = io.StringIO()

    result = SSHConnection._run_streaming_command(
        command,
        timeout=5,
        out_stream=stdout_stream,
    )

    assert result.returncode == 0
    assert result.stdout == b"\xc3\xa9\n"
    assert stdout_stream.getvalue() == "é\n"


@pytest.mark.unit
def test_streaming_timeout_kills_descendant_holding_pipe():
    """A descendant inheriting the pipes cannot make timeout cleanup hang."""
    child_code = "import time; time.sleep(30)"
    parent_code = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
        "sys.stdout.write('parent\\n'); sys.stdout.flush(); "
        "time.sleep(30)"
    )
    started = time.monotonic()
    result = SSHConnection._run_streaming_command(
        [sys.executable, "-c", parent_code],
        timeout=0.2,
        out_stream=io.StringIO(),
        err_stream=io.StringIO(),
    )
    elapsed = time.monotonic() - started

    assert result.returncode == 124
    assert elapsed < 4
    assert len(result.stdout) <= CAPTURE_LIMIT
    assert len(result.stderr) <= CAPTURE_LIMIT
    assert b"Command timed out after 0.2 seconds" in result.stderr


@pytest.mark.unit
def test_streaming_cleanup_kills_descendant_after_leader_exits():
    """A successful leader cannot leave pipe-holding descendants behind."""
    child_code = "import time; time.sleep(30)"
    parent_code = (
        "import subprocess,sys; "
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}])"
    )
    started = time.monotonic()
    result = SSHConnection._run_streaming_command(
        [sys.executable, "-c", parent_code],
        timeout=5,
        out_stream=io.StringIO(),
        err_stream=io.StringIO(),
    )
    elapsed = time.monotonic() - started

    assert result.returncode == 0
    assert elapsed < 4


@pytest.mark.parametrize(
    "message",
    [
        b"scp: log: No such file or directory",
        b"scp: log: Permission denied",
        b"No space left on device",
    ],
)
def test_missing_or_inaccessible_log_keeps_control_master(monkeypatch, message):
    import subprocess
    from types import SimpleNamespace
    from unittest.mock import Mock

    from ssync.ssh.native import NativeSSH

    run = Mock(return_value=SimpleNamespace(returncode=1, stderr=message))
    cleanup = Mock()
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(NativeSSH, "cleanup_control_master", cleanup)
    conn = SSHConnection("cluster", "user@cluster")
    with pytest.raises(Exception, match="Failed to download file"):
        conn._run_scp_command(["scp", "remote:log", "local"], direction="download")
    assert run.call_count == 1
    cleanup.assert_not_called()
