import os
from pathlib import Path

import pytest

from ssync.watchers.service import WatcherService


@pytest.mark.unit
def test_watcher_service_lock_allows_single_owner(tmp_path, monkeypatch):
    lock_file = tmp_path / "watcher-service.lock"
    monkeypatch.setattr(WatcherService, "LOCK_FILE", lock_file)

    first = WatcherService()
    second = WatcherService()

    assert first._acquire_lock() is True
    assert second._acquire_lock() is False

    first._release_lock()
    assert second._acquire_lock() is True
    second._release_lock()


@pytest.mark.unit
def test_watcher_service_releases_lock_cleanly(tmp_path, monkeypatch):
    lock_file = tmp_path / "watcher-service.lock"
    monkeypatch.setattr(WatcherService, "LOCK_FILE", lock_file)

    service = WatcherService()
    assert service._acquire_lock() is True
    assert Path(lock_file).read_text() == str(os.getpid())

    service._release_lock()
    assert service._lock_handle is None
