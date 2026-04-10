"""Unit tests for SyncManager gitignore translation."""

from pathlib import Path

import pytest

from ssync.sync import SyncManager


def _make_sync_manager(source_dir: Path) -> SyncManager:
    return SyncManager(slurm_manager=None, source_dir=source_dir)


@pytest.mark.unit
def test_collect_rsync_filter_rules_preserves_root_anchored_patterns(temp_dir):
    source_dir = temp_dir / "workspace"
    source_dir.mkdir()
    (source_dir / ".gitignore").write_text("/datasets/\n")

    sync_manager = _make_sync_manager(source_dir)

    assert sync_manager._collect_rsync_filter_rules() == ["- /datasets/***"]


@pytest.mark.unit
def test_collect_rsync_filter_rules_keeps_unanchored_patterns_unanchored(temp_dir):
    source_dir = temp_dir / "workspace"
    source_dir.mkdir()
    (source_dir / ".gitignore").write_text("datasets/\n")

    sync_manager = _make_sync_manager(source_dir)

    assert sync_manager._collect_rsync_filter_rules() == ["- datasets/***"]


@pytest.mark.unit
def test_collect_rsync_filter_rules_anchors_nested_gitignore_patterns_to_subdir(
    temp_dir,
):
    source_dir = temp_dir / "workspace"
    nested_dir = source_dir / "src"
    nested_dir.mkdir(parents=True)
    (nested_dir / ".gitignore").write_text("/generated/\n")

    sync_manager = _make_sync_manager(source_dir)

    assert sync_manager._collect_rsync_filter_rules() == ["- /src/generated/***"]
