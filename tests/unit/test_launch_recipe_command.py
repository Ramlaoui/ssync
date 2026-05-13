from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

from ssync.cli import commands


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _recipe_project(tmp_path: Path, *, include_host: bool = True) -> Path:
    repo = tmp_path / "repo"
    (repo / ".ssync").mkdir(parents=True)
    _write(repo / ".ssync/fragments/run/train.sh", 'python train.py "$CONFIG"\n')
    host_line = "host: entalpic\n" if include_host else ""
    recipe = repo / "experiments/demo/launch/train.yaml"
    _write(
        recipe,
        f"""
{host_line}job_name: recipe-job
vars:
  CONFIG: experiments/demo/train
run:
  script: .ssync/fragments/run/train.sh
sbatch:
  cpus: 8
  partition: gpu
  qos: qos_gpu-t4
  dependency: afterok:12345
""",
    )
    return recipe


@pytest.mark.unit
def test_launch_recipe_command_passes_rendered_script_to_launch(monkeypatch, tmp_path):
    recipe = _recipe_project(tmp_path)
    captured = {}

    def fake_launch(self, **kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(commands.LaunchCommand, "_launch_script_content", fake_launch)

    command = commands.LaunchRecipeCommand(
        config_path=Path("/tmp/ssync-config.yaml"),
        slurm_hosts=[],
        verbose=False,
    )

    success = command.execute(recipe_path=recipe, mem=32, partition="debug")

    assert success is True
    assert captured["host"] == "entalpic"
    assert captured["job_name"] == "recipe-job"
    assert captured["cpus"] == 8
    assert captured["mem"] == 32
    assert captured["partition"] == "debug"
    assert captured["qos"] == "qos_gpu-t4"
    assert captured["dependency"] == "afterok:12345"
    assert captured["source_dir"] == tmp_path / "repo"
    assert "export CONFIG=experiments/demo/train" in captured["script_content"]
    assert 'python train.py "$CONFIG"' in captured["script_content"]
    assert captured["launch_manifest"]["manifest_version"] == 1
    assert captured["launch_manifest"]["recipe_path"] == str(recipe)
    assert captured["launch_manifest"]["vars"]["CONFIG"] == "experiments/demo/train"
    assert captured["launch_manifest"]["sbatch"]["partition"] == "debug"
    assert captured["launch_manifest"]["sbatch"]["qos"] == "qos_gpu-t4"
    assert captured["launch_manifest"]["sbatch"]["dependency"] == "afterok:12345"


@pytest.mark.unit
def test_launch_recipe_command_applies_recipe_overrides(monkeypatch, tmp_path):
    recipe = _recipe_project(tmp_path)
    captured = {}

    def fake_launch(self, **kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(commands.LaunchCommand, "_launch_script_content", fake_launch)

    command = commands.LaunchRecipeCommand(
        config_path=Path("/tmp/ssync-config.yaml"),
        slurm_hosts=[],
        verbose=False,
    )

    success = command.execute(
        recipe_path=recipe,
        var_overrides=["CONFIG=experiments/demo/debug", "MAX_STEPS=5"],
        set_overrides=[
            "sbatch.time=5",
            "sbatch.partition=debug",
            "sbatch.qos=qos_gpu-dev",
            "sbatch.dependency=afterany:999",
        ],
    )

    assert success is True
    assert captured["time"] == 5
    assert captured["partition"] == "debug"
    assert captured["qos"] == "qos_gpu-dev"
    assert captured["dependency"] == "afterany:999"
    assert "export CONFIG=experiments/demo/debug" in captured["script_content"]
    assert "export MAX_STEPS=5" in captured["script_content"]
    assert captured["launch_manifest"]["cli_overrides"]["vars"] == {
        "CONFIG": "experiments/demo/debug",
        "MAX_STEPS": "5",
    }
    assert captured["launch_manifest"]["submit"]["sbatch"]["time"] == 5
    assert captured["launch_manifest"]["submit"]["sbatch"]["qos"] == "qos_gpu-dev"
    assert (
        captured["launch_manifest"]["submit"]["sbatch"]["dependency"]
        == "afterany:999"
    )


@pytest.mark.unit
def test_launch_recipe_command_applies_watcher_overrides(monkeypatch, tmp_path):
    recipe = _recipe_project(tmp_path)
    repo = recipe.parents[3]
    _write(repo / ".ssync/watchers/timeout_resume.yaml", 'pattern: "TIMEOUT"\n')
    captured = {}

    def fake_launch(self, **kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(commands.LaunchCommand, "_launch_script_content", fake_launch)

    command = commands.LaunchRecipeCommand(
        config_path=Path("/tmp/ssync-config.yaml"),
        slurm_hosts=[],
        verbose=False,
    )

    success = command.execute(
        recipe_path=recipe,
        add_watchers=["timeout_resume"],
    )

    assert success is True
    assert "#WATCHER_BEGIN" in captured["script_content"]
    assert captured["launch_manifest"]["watchers"][0]["name"] == "timeout_resume"
    assert captured["launch_manifest"]["cli_overrides"]["add_watchers"] == [
        "timeout_resume"
    ]


@pytest.mark.unit
def test_launch_recipe_command_rejects_invalid_overrides(monkeypatch, tmp_path):
    recipe = _recipe_project(tmp_path)
    outputs = []

    monkeypatch.setattr(
        commands.click,
        "echo",
        lambda message="", err=False: outputs.append((message, err)),
    )

    command = commands.LaunchRecipeCommand(
        config_path=Path("/tmp/ssync-config.yaml"),
        slurm_hosts=[],
        verbose=False,
    )

    success = command.execute(recipe_path=recipe, set_overrides=["partition=debug"])

    assert success is False
    assert outputs == [
        (
            "Invalid launch recipe override: Only sbatch.* overrides are supported: partition",
            True,
        )
    ]


@pytest.mark.unit
def test_launch_recipe_command_requires_host(monkeypatch, tmp_path):
    recipe = _recipe_project(tmp_path, include_host=False)
    outputs = []

    def fake_echo(message="", err=False):
        outputs.append((message, err))

    monkeypatch.setattr(commands.click, "echo", fake_echo)

    command = commands.LaunchRecipeCommand(
        config_path=Path("/tmp/ssync-config.yaml"),
        slurm_hosts=[],
        verbose=False,
    )

    success = command.execute(recipe_path=recipe)

    assert success is False
    assert outputs == [("Launch recipe does not define a host; pass --host.", True)]


@pytest.mark.unit
def test_launch_recipe_command_dry_run_does_not_launch(monkeypatch, tmp_path):
    recipe = _recipe_project(tmp_path, include_host=False)
    outputs = []

    def fake_launch(self, **kwargs):
        raise AssertionError("dry-run should not submit")

    def fake_echo(message="", err=False):
        outputs.append((message, err))

    monkeypatch.setattr(commands.LaunchCommand, "_launch_script_content", fake_launch)
    monkeypatch.setattr(commands.click, "echo", fake_echo)

    command = commands.LaunchRecipeCommand(
        config_path=Path("/tmp/ssync-config.yaml"),
        slurm_hosts=[],
        verbose=False,
    )

    success = command.execute(recipe_path=recipe, dry_run=True)

    assert success is True
    assert any(str(recipe) in message for message, _ in outputs)
    assert any("Host: <not set>" == message for message, _ in outputs)
    assert any("Sbatch:" == message for message, _ in outputs)
    assert any("Fragments:" == message for message, _ in outputs)
    assert any("Variables:" == message for message, _ in outputs)
    assert any("Rendered script:" == message for message, _ in outputs)
    assert any("python train.py" in message for message, _ in outputs)


@pytest.mark.unit
def test_launch_recipe_command_dry_run_json(monkeypatch, tmp_path):
    recipe = _recipe_project(tmp_path)
    outputs = []

    monkeypatch.setattr(
        commands.click, "echo", lambda message="", err=False: outputs.append(message)
    )

    command = commands.LaunchRecipeCommand(
        config_path=Path("/tmp/ssync-config.yaml"),
        slurm_hosts=[],
        verbose=False,
    )

    success = command.execute(recipe_path=recipe, dry_run=True, json_output=True)

    assert success is True
    assert '"recipe_path"' in outputs[0]
    assert '"submit"' in outputs[0]


@pytest.mark.unit
def test_manifest_command_auto_detects_host_and_prints_json(monkeypatch):
    class FakeAPIClient:
        def __init__(self, verbose=False):
            self.verbose = verbose

        def ensure_server_running(self, config_path):
            return True, None

        def get_jobs(self, job_ids):
            return [SimpleNamespace(hostname="entalpic")]

        def get_run_manifest(self, job_id, host):
            return {
                "manifest_version": 1,
                "recipe_path": "/repo/launch.yaml",
                "vars": {"A": "B"},
            }

    outputs = []
    monkeypatch.setattr(commands, "APIClient", FakeAPIClient)
    monkeypatch.setattr(
        commands.click,
        "echo",
        lambda message="", err=False: outputs.append((message, err)),
    )

    command = commands.ManifestCommand(
        config_path=Path("/tmp/ssync-config.yaml"),
        slurm_hosts=[SimpleNamespace(host=SimpleNamespace(hostname="entalpic"))],
        verbose=False,
    )

    success = command.execute("123", json_output=True)

    assert success is True
    assert outputs[0][1] is False
    assert '"recipe_path": "/repo/launch.yaml"' in outputs[0][0]


@pytest.mark.unit
def test_manifest_command_requires_host_when_job_is_ambiguous(monkeypatch):
    class FakeAPIClient:
        def __init__(self, verbose=False):
            self.verbose = verbose

        def ensure_server_running(self, config_path):
            return True, None

        def get_jobs(self, job_ids):
            return [SimpleNamespace(hostname="a"), SimpleNamespace(hostname="b")]

    outputs = []
    monkeypatch.setattr(commands, "APIClient", FakeAPIClient)
    monkeypatch.setattr(
        commands.click,
        "echo",
        lambda message="", err=False: outputs.append((message, err)),
    )

    command = commands.ManifestCommand(
        config_path=Path("/tmp/ssync-config.yaml"),
        slurm_hosts=[],
        verbose=False,
    )

    success = command.execute("123")

    assert success is False
    assert outputs == [
        ("Job 123 was found on multiple hosts: a, b. Specify --host.", True)
    ]


@pytest.mark.unit
def test_manifest_command_reports_missing_manifest(monkeypatch):
    class Response:
        status_code = 404

    class FakeAPIClient:
        def __init__(self, verbose=False):
            self.verbose = verbose

        def ensure_server_running(self, config_path):
            return True, None

        def get_run_manifest(self, job_id, host):
            raise requests.exceptions.HTTPError(response=Response())

    outputs = []
    monkeypatch.setattr(commands, "APIClient", FakeAPIClient)
    monkeypatch.setattr(
        commands.click,
        "echo",
        lambda message="", err=False: outputs.append((message, err)),
    )

    command = commands.ManifestCommand(
        config_path=Path("/tmp/ssync-config.yaml"),
        slurm_hosts=[SimpleNamespace(host=SimpleNamespace(hostname="entalpic"))],
        verbose=False,
    )

    success = command.execute("123", host="entalpic")

    assert success is False
    assert outputs == [("No run manifest found for job 123 on entalpic", True)]


@pytest.mark.unit
def test_rerender_command_prints_frozen_manifest_script(monkeypatch):
    class FakeAPIClient:
        def __init__(self, verbose=False):
            self.verbose = verbose

        def ensure_server_running(self, config_path):
            return True, None

        def get_run_manifest(self, job_id, host):
            return {
                "manifest_version": 1,
                "recipe_path": "/repo/launch.yaml",
                "script_sha256": "abc",
                "rendered_script": "#!/bin/bash\necho frozen\n",
            }

    outputs = []
    monkeypatch.setattr(commands, "APIClient", FakeAPIClient)
    monkeypatch.setattr(
        commands.click,
        "echo",
        lambda message="", err=False: outputs.append((message, err)),
    )

    command = commands.RerenderCommand(
        config_path=Path("/tmp/ssync-config.yaml"),
        slurm_hosts=[SimpleNamespace(host=SimpleNamespace(hostname="entalpic"))],
        verbose=False,
    )

    success = command.execute("123", host="entalpic")

    assert success is True
    assert ("Rerender mode: frozen manifest", False) in outputs
    assert any("echo frozen" in message for message, _ in outputs)


@pytest.mark.unit
def test_rerender_command_can_render_from_current_repo(monkeypatch, tmp_path):
    recipe = _recipe_project(tmp_path)

    class FakeAPIClient:
        def __init__(self, verbose=False):
            self.verbose = verbose

        def ensure_server_running(self, config_path):
            return True, None

        def get_run_manifest(self, job_id, host):
            return {
                "manifest_version": 1,
                "recipe_path": str(recipe),
                "cli_overrides": {"vars": {"CONFIG": "current"}},
                "rendered_script": "#!/bin/bash\necho old\n",
            }

    outputs = []
    monkeypatch.setattr(commands, "APIClient", FakeAPIClient)
    monkeypatch.setattr(
        commands.click,
        "echo",
        lambda message="", err=False: outputs.append((message, err)),
    )

    command = commands.RerenderCommand(
        config_path=Path("/tmp/ssync-config.yaml"),
        slurm_hosts=[SimpleNamespace(host=SimpleNamespace(hostname="entalpic"))],
        verbose=False,
    )

    success = command.execute("123", host="entalpic", from_current_repo=True)

    assert success is True
    assert ("Rerender mode: current repo", False) in outputs
    assert any("export CONFIG=current" in message for message, _ in outputs)
