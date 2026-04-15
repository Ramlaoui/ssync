import signal
from pathlib import Path
from unittest.mock import Mock, patch

from ssync.watchers.daemon import WatcherDaemon


def test_watcher_daemon_script_path_points_to_runner():
    script_path = WatcherDaemon.script_path()

    assert script_path == Path(__file__).resolve().parents[2] / "utils" / "run_watchers.py"
    assert script_path.exists()


def test_run_watchers_bootstrap_points_to_project_src():
    runner = Path(__file__).resolve().parents[2] / "utils" / "run_watchers.py"
    content = runner.read_text()

    assert 'parents[1] / "src"' in content


@patch("subprocess.run")
def test_list_run_watcher_processes_finds_all_runner_processes(mock_run):
    mock_run.return_value = Mock(
        returncode=0,
        stdout=(
            "123 /home/aliramlaoui/projects/ssync-workspace/ssync/utils/run_watchers.py\n"
            "456 /home/aliramlaoui/projects/ssync-workspace/ssync-relaunch-watchers/utils/run_watchers.py\n"
            "789 python something_else.py\n"
        ),
    )

    processes = WatcherDaemon._list_run_watcher_processes()

    assert processes == [
        (123, "/home/aliramlaoui/projects/ssync-workspace/ssync/utils/run_watchers.py"),
        (
            456,
            "/home/aliramlaoui/projects/ssync-workspace/ssync-relaunch-watchers/utils/run_watchers.py",
        ),
    ]


@patch("time.sleep")
@patch("os.kill")
@patch.object(WatcherDaemon, "_list_run_watcher_processes")
def test_stop_all_terminates_all_runner_processes(
    mock_list_processes, mock_kill, _mock_sleep
):
    mock_list_processes.side_effect = [
        [(123, "old run_watchers.py"), (456, "new run_watchers.py")],
        [],
        [],
    ]

    stopped = WatcherDaemon.stop_all()

    assert stopped == 2
    mock_kill.assert_any_call(123, signal.SIGTERM)
    mock_kill.assert_any_call(456, signal.SIGTERM)
