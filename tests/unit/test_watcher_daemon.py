from pathlib import Path

from ssync.watchers.daemon import WatcherDaemon


def test_watcher_daemon_script_path_points_to_runner():
    script_path = WatcherDaemon.script_path()

    assert script_path == Path.cwd() / "utils" / "run_watchers.py"
    assert script_path.exists()
