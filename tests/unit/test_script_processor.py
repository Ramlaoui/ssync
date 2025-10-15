"""Unit tests for script_processor.py."""

import pytest

from ssync.models.watcher import ActionType, WatcherAction, WatcherDefinition
from ssync.script_processor import ScriptProcessor
from ssync.utils.slurm_params import SlurmParams


class TestEnsureShebang:
    """Tests for ensure_shebang method."""

    @pytest.mark.unit
    def test_adds_shebang_when_missing(self):
        content = "echo 'hello world'"
        result = ScriptProcessor.ensure_shebang(content)
        assert result.startswith("#!/bin/bash\n")
        assert "echo 'hello world'" in result

    @pytest.mark.unit
    def test_preserves_existing_shebang(self):
        content = "#!/bin/sh\necho 'hello'"
        result = ScriptProcessor.ensure_shebang(content)
        assert result.startswith("#!/bin/sh\n")
        assert result.count("#!/bin/") == 1

    @pytest.mark.unit
    def test_preserves_python_shebang(self):
        content = "#!/usr/bin/env python3\nprint('hello')"
        result = ScriptProcessor.ensure_shebang(content)
        assert result.startswith("#!/usr/bin/env python3\n")

    @pytest.mark.unit
    def test_handles_empty_content(self):
        content = ""
        result = ScriptProcessor.ensure_shebang(content)
        assert result == "#!/bin/bash\n"

    @pytest.mark.unit
    def test_handles_whitespace_only_content(self):
        content = "   \n  \n"
        result = ScriptProcessor.ensure_shebang(content)
        assert result.startswith("#!/bin/bash\n")


class TestIsSlurmScript:
    """Tests for is_slurm_script method."""

    @pytest.mark.unit
    def test_detects_sbatch_directive(self, temp_dir):
        script_path = temp_dir / "test.sh"
        script_path.write_text("#!/bin/bash\n#SBATCH --job-name=test\necho 'test'")
        assert ScriptProcessor.is_slurm_script(script_path) is True

    @pytest.mark.unit
    def test_detects_no_sbatch_directive(self, temp_dir):
        script_path = temp_dir / "test.sh"
        script_path.write_text("#!/bin/bash\necho 'test'")
        assert ScriptProcessor.is_slurm_script(script_path) is False

    @pytest.mark.unit
    def test_handles_nonexistent_file(self, temp_dir):
        script_path = temp_dir / "nonexistent.sh"
        assert ScriptProcessor.is_slurm_script(script_path) is False

    @pytest.mark.unit
    def test_detects_multiple_sbatch_directives(self, temp_dir):
        script_path = temp_dir / "test.sh"
        script_path.write_text(
            "#!/bin/bash\n#SBATCH --job-name=test\n#SBATCH --time=01:00:00\necho 'test'"
        )
        assert ScriptProcessor.is_slurm_script(script_path) is True


class TestExtractWatchers:
    """Tests for extract_watchers method."""

    @pytest.mark.unit
    def test_extract_block_watcher(self, script_with_watchers):
        watchers, clean_script = ScriptProcessor.extract_watchers(script_with_watchers)
        assert len(watchers) >= 1

        # Find the block watcher
        block_watcher = next((w for w in watchers if w.name == "Loss Monitor"), None)
        assert block_watcher is not None
        assert block_watcher.pattern == "Loss: ([0-9.]+)"
        assert block_watcher.interval_seconds == 60
        assert block_watcher.captures == ["loss"]
        assert block_watcher.condition == "float(loss) > 5.0"
        assert len(block_watcher.actions) == 2

        # Check that watcher blocks are removed from clean script
        assert "#WATCHER_BEGIN" not in clean_script
        assert "#WATCHER_END" not in clean_script
        assert "echo \"Training model...\"" in clean_script

    @pytest.mark.unit
    def test_extract_inline_watcher(self, script_with_watchers):
        watchers, clean_script = ScriptProcessor.extract_watchers(script_with_watchers)

        # Find the inline watcher
        inline_watcher = next(
            (w for w in watchers if w.pattern == "Error|Exception"), None
        )
        assert inline_watcher is not None
        assert inline_watcher.interval_seconds == 30
        assert len(inline_watcher.actions) == 1
        assert inline_watcher.actions[0].type == ActionType.CANCEL_JOB

    @pytest.mark.unit
    def test_no_watchers_returns_empty_list(self, basic_script):
        watchers, clean_script = ScriptProcessor.extract_watchers(basic_script)
        assert len(watchers) == 0
        assert clean_script == basic_script

    @pytest.mark.unit
    def test_malformed_watcher_block_ignored(self):
        script = """#!/bin/bash
#WATCHER_BEGIN
# this is not valid
# no pattern field
#WATCHER_END
echo "test"
"""
        watchers, clean_script = ScriptProcessor.extract_watchers(script)
        assert len(watchers) == 0  # Invalid block should be ignored

    @pytest.mark.unit
    def test_multiple_watcher_blocks(self):
        script = """#!/bin/bash
#WATCHER_BEGIN
# pattern: "Loss: ([0-9.]+)"
# interval: 60
#WATCHER_END

#WATCHER_BEGIN
# pattern: "Accuracy: ([0-9.]+)"
# interval: 30
#WATCHER_END

echo "Training"
"""
        watchers, clean_script = ScriptProcessor.extract_watchers(script)
        assert len(watchers) == 2
        assert watchers[0].pattern == "Loss: ([0-9.]+)"
        assert watchers[1].pattern == "Accuracy: ([0-9.]+)"

    @pytest.mark.unit
    def test_watcher_with_timer_mode(self):
        script = """#!/bin/bash
#WATCHER_BEGIN
# pattern: "Progress: (\\d+)%"
# interval: 60
# timer_mode_enabled: true
# timer_interval_seconds: 30
#WATCHER_END
echo "test"
"""
        watchers, _ = ScriptProcessor.extract_watchers(script)
        assert len(watchers) == 1
        assert watchers[0].timer_mode_enabled is True
        assert watchers[0].timer_interval_seconds == 30

    @pytest.mark.unit
    def test_watcher_with_special_characters_in_pattern(self):
        script = r"""#!/bin/bash
#WATCHER pattern="[\d+]\s+ERROR.*" action=log
echo "test"
"""
        watchers, _ = ScriptProcessor.extract_watchers(script)
        assert len(watchers) == 1
        assert "[\\d+]\\s+ERROR.*" in watchers[0].pattern or "[\d+]\s+ERROR.*" in watchers[0].pattern

    @pytest.mark.unit
    def test_empty_script_returns_empty(self):
        watchers, clean_script = ScriptProcessor.extract_watchers("")
        assert len(watchers) == 0
        assert clean_script == ""

    @pytest.mark.unit
    def test_watcher_with_captures_array(self):
        script = """#!/bin/bash
#WATCHER_BEGIN
# pattern: "Loss: ([0-9.]+), Accuracy: ([0-9.]+)"
# interval: 60
# captures: [loss, accuracy]
#WATCHER_END
"""
        watchers, _ = ScriptProcessor.extract_watchers(script)
        assert len(watchers) == 1
        assert watchers[0].captures == ["loss", "accuracy"]


class TestParseActionString:
    """Tests for _parse_action_string method."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "action_str,expected_type",
        [
            ("cancel", ActionType.CANCEL_JOB),
            ("cancel_job", ActionType.CANCEL_JOB),
            ("resubmit", ActionType.RESUBMIT),
            ("notify_email", ActionType.NOTIFY_EMAIL),
            ("notify_slack", ActionType.NOTIFY_SLACK),
            ("email", ActionType.NOTIFY_EMAIL),
            ("slack", ActionType.NOTIFY_SLACK),
            ("run_command", ActionType.RUN_COMMAND),
            ("command", ActionType.RUN_COMMAND),
            ("store_metric", ActionType.STORE_METRIC),
            ("metric", ActionType.STORE_METRIC),
            ("log", ActionType.LOG_EVENT),
            ("log_event", ActionType.LOG_EVENT),
        ],
    )
    def test_parse_action_types(self, action_str, expected_type):
        action_type, params = ScriptProcessor._parse_action_string(action_str)
        assert action_type == expected_type

    @pytest.mark.unit
    def test_parse_action_with_params_parentheses(self):
        action_str = "notify_email(recipient=admin@example.com,subject=Alert)"
        action_type, params = ScriptProcessor._parse_action_string(action_str)
        assert action_type == ActionType.NOTIFY_EMAIL
        assert params["recipient"] == "admin@example.com"
        assert params["subject"] == "Alert"

    @pytest.mark.unit
    def test_parse_action_with_message(self):
        action_str = "notify_email High loss detected"
        action_type, params = ScriptProcessor._parse_action_string(action_str)
        assert action_type == ActionType.NOTIFY_EMAIL
        assert params["message"] == "High loss detected"

    @pytest.mark.unit
    def test_parse_unknown_action_returns_none(self):
        action_str = "unknown_action_type"
        action_type, params = ScriptProcessor._parse_action_string(action_str)
        assert action_type is None
        assert params == {}

    @pytest.mark.unit
    def test_parse_empty_action_returns_none(self):
        action_type, params = ScriptProcessor._parse_action_string("")
        assert action_type is None
        assert params == {}


class TestParseInlineWatcher:
    """Tests for _parse_inline_watcher method."""

    @pytest.mark.unit
    def test_parse_simple_inline_watcher(self):
        line = 'pattern="Error" action=cancel'
        watcher = ScriptProcessor._parse_inline_watcher(line)
        assert watcher is not None
        assert watcher.pattern == "Error"
        assert len(watcher.actions) == 1
        assert watcher.actions[0].type == ActionType.CANCEL_JOB

    @pytest.mark.unit
    def test_parse_inline_watcher_with_interval(self):
        line = 'pattern="Loss: ([0-9.]+)" interval=30 action=log'
        watcher = ScriptProcessor._parse_inline_watcher(line)
        assert watcher is not None
        assert watcher.interval_seconds == 30

    @pytest.mark.unit
    def test_parse_inline_watcher_with_captures(self):
        line = 'pattern="Loss: ([0-9.]+)" captures=[loss] action=store_metric'
        watcher = ScriptProcessor._parse_inline_watcher(line)
        assert watcher is not None
        assert watcher.captures == ["loss"]

    @pytest.mark.unit
    def test_parse_inline_watcher_with_condition(self):
        line = 'pattern="Loss: ([0-9.]+)" captures=[loss] condition="float(loss)>5.0" action=cancel'
        watcher = ScriptProcessor._parse_inline_watcher(line)
        assert watcher is not None
        assert watcher.condition == "float(loss)>5.0"

    @pytest.mark.unit
    def test_parse_inline_watcher_with_name(self):
        line = 'name="Loss Monitor" pattern="Loss: ([0-9.]+)" action=log'
        watcher = ScriptProcessor._parse_inline_watcher(line)
        assert watcher is not None
        assert watcher.name == "Loss Monitor"

    @pytest.mark.unit
    def test_parse_inline_watcher_without_pattern_returns_none(self):
        line = 'action=cancel interval=30'  # Missing pattern
        watcher = ScriptProcessor._parse_inline_watcher(line)
        assert watcher is None

    @pytest.mark.unit
    def test_parse_inline_watcher_adds_default_action(self):
        line = 'pattern="Error"'  # No action specified
        watcher = ScriptProcessor._parse_inline_watcher(line)
        assert watcher is not None
        assert len(watcher.actions) == 1
        assert watcher.actions[0].type == ActionType.LOG_EVENT  # Default action


class TestParseWatcherBlock:
    """Tests for _parse_watcher_block method."""

    @pytest.mark.unit
    def test_parse_complete_watcher_block(self):
        block = """name: Loss Monitor
pattern: "Loss: ([0-9.]+)"
interval: 60
captures: [loss]
condition: float(loss) > 5.0
actions:
  - notify_email
  - cancel_job
"""
        watcher = ScriptProcessor._parse_watcher_block(block)
        assert watcher is not None
        assert watcher.name == "Loss Monitor"
        assert watcher.pattern == "Loss: ([0-9.]+)"
        assert watcher.interval_seconds == 60
        assert watcher.captures == ["loss"]
        assert watcher.condition == "float(loss) > 5.0"
        assert len(watcher.actions) == 2

    @pytest.mark.unit
    def test_parse_minimal_watcher_block(self):
        block = 'pattern: "Error"'
        watcher = ScriptProcessor._parse_watcher_block(block)
        assert watcher is not None
        assert watcher.pattern == "Error"
        # Should have default action added
        assert len(watcher.actions) == 1
        assert watcher.actions[0].type == ActionType.LOG_EVENT

    @pytest.mark.unit
    def test_parse_watcher_with_commented_lines(self):
        block = """# name: Test Watcher
# pattern: "Error"
# interval: 30
"""
        watcher = ScriptProcessor._parse_watcher_block(block)
        assert watcher is not None
        assert watcher.name == "Test Watcher"
        assert watcher.pattern == "Error"
        assert watcher.interval_seconds == 30

    @pytest.mark.unit
    def test_parse_watcher_with_timer_mode(self):
        block = """pattern: "Progress"
timer_mode_enabled: true
timer_interval_seconds: 45
"""
        watcher = ScriptProcessor._parse_watcher_block(block)
        assert watcher is not None
        assert watcher.timer_mode_enabled is True
        assert watcher.timer_interval_seconds == 45

    @pytest.mark.unit
    def test_parse_watcher_with_json_captures(self):
        block = """pattern: "Loss: ([0-9.]+), Acc: ([0-9.]+)"
captures: ["loss", "accuracy"]
"""
        watcher = ScriptProcessor._parse_watcher_block(block)
        assert watcher is not None
        assert watcher.captures == ["loss", "accuracy"]

    @pytest.mark.unit
    def test_parse_watcher_without_pattern_returns_none(self):
        block = """name: Invalid Watcher
interval: 60
"""
        watcher = ScriptProcessor._parse_watcher_block(block)
        assert watcher is None

    @pytest.mark.unit
    def test_parse_empty_block_returns_none(self):
        watcher = ScriptProcessor._parse_watcher_block("")
        assert watcher is None

    @pytest.mark.unit
    def test_parse_watcher_with_single_action(self):
        block = """pattern: "Error"
action: cancel_job
"""
        watcher = ScriptProcessor._parse_watcher_block(block)
        assert watcher is not None
        assert len(watcher.actions) == 1
        assert watcher.actions[0].type == ActionType.CANCEL_JOB


class TestAddSlurmDirectives:
    """Tests for add_slurm_directives method."""

    @pytest.mark.unit
    def test_adds_job_name_directive(self):
        content = "#!/bin/bash\necho 'test'"
        result = ScriptProcessor.add_slurm_directives(content, job_name="my_job")
        assert "#SBATCH --job-name=my_job" in result

    @pytest.mark.unit
    def test_adds_multiple_directives(self):
        content = "#!/bin/bash\necho 'test'"
        result = ScriptProcessor.add_slurm_directives(
            content,
            job_name="test_job",
            cpus=4,
            mem=8,
            time=60,
            partition="gpu",
        )
        assert "#SBATCH --job-name=test_job" in result
        assert "#SBATCH --cpus-per-task=4" in result
        assert "#SBATCH --mem=8G" in result
        assert "#SBATCH --time=01:00:00" in result
        assert "#SBATCH --partition=gpu" in result

    @pytest.mark.unit
    def test_inserts_after_shebang(self):
        content = "#!/bin/bash\necho 'first line'"
        result = ScriptProcessor.add_slurm_directives(content, job_name="test")
        lines = result.split("\n")
        assert lines[0] == "#!/bin/bash"
        assert lines[1].startswith("#SBATCH")

    @pytest.mark.unit
    def test_inserts_at_beginning_without_shebang(self):
        content = "echo 'first line'"
        result = ScriptProcessor.add_slurm_directives(content, job_name="test")
        lines = result.split("\n")
        assert lines[0].startswith("#SBATCH")

    @pytest.mark.unit
    def test_handles_none_values(self):
        content = "#!/bin/bash\necho 'test'"
        result = ScriptProcessor.add_slurm_directives(
            content, job_name=None, cpus=None, mem=None
        )
        # Should not add directives for None values
        assert result == content

    @pytest.mark.unit
    def test_adds_output_and_error_files(self):
        content = "#!/bin/bash\necho 'test'"
        result = ScriptProcessor.add_slurm_directives(
            content,
            output="/path/to/output.log",
            error="/path/to/error.log",
        )
        assert "#SBATCH --output=/path/to/output.log" in result
        assert "#SBATCH --error=/path/to/error.log" in result

    @pytest.mark.unit
    def test_adds_constraint_and_account(self):
        content = "#!/bin/bash\necho 'test'"
        result = ScriptProcessor.add_slurm_directives(
            content,
            constraint="gpu_v100",
            account="my_account",
        )
        assert "#SBATCH --constraint=gpu_v100" in result
        assert "#SBATCH --account=my_account" in result

    @pytest.mark.unit
    def test_adds_node_and_task_configuration(self):
        content = "#!/bin/bash\necho 'test'"
        result = ScriptProcessor.add_slurm_directives(
            content,
            nodes=2,
            ntasks_per_node=4,
            gpus_per_node=2,
        )
        assert "#SBATCH --nodes=2" in result
        assert "#SBATCH --ntasks-per-node=4" in result
        assert "#SBATCH --gpus-per-node=2" in result


class TestPrepareScript:
    """Tests for prepare_script method."""

    @pytest.mark.unit
    def test_prepares_basic_script(self, temp_dir, basic_script):
        # Create source script
        source = temp_dir / "source.sh"
        source.write_text(basic_script)

        # Prepare script
        target_dir = temp_dir / "target"
        result_path = ScriptProcessor.prepare_script(source, target_dir)

        assert result_path.exists()
        assert result_path.name == "source.slurm"
        assert result_path.parent == target_dir

        # Check content has shebang
        content = result_path.read_text()
        assert content.startswith("#!/bin/bash")

    @pytest.mark.unit
    def test_adds_slurm_directives_to_non_slurm_script(self, temp_dir):
        # Create a plain shell script
        source = temp_dir / "plain.sh"
        source.write_text("echo 'hello'")

        params = SlurmParams(
            job_name="test_job",
            cpus_per_task=4,
            mem_gb=8,
            time_min=60,
        )

        target_dir = temp_dir / "target"
        result_path = ScriptProcessor.prepare_script(source, target_dir, params)

        content = result_path.read_text()
        assert "#SBATCH --job-name=test_job" in content
        assert "#SBATCH --cpus-per-task=4" in content
        assert "#SBATCH --mem=8G" in content

    @pytest.mark.unit
    def test_preserves_existing_slurm_directives(self, temp_dir):
        # Create a script with existing SLURM directives
        source = temp_dir / "slurm.sh"
        source.write_text("#!/bin/bash\n#SBATCH --job-name=existing\necho 'test'")

        target_dir = temp_dir / "target"
        result_path = ScriptProcessor.prepare_script(source, target_dir)

        content = result_path.read_text()
        # Should not add new directives if already present
        assert "#SBATCH --job-name=existing" in content

    @pytest.mark.unit
    def test_creates_target_directory(self, temp_dir):
        source = temp_dir / "test.sh"
        source.write_text("#!/bin/bash\necho 'test'")

        target_dir = temp_dir / "new" / "nested" / "dir"
        assert not target_dir.exists()

        result_path = ScriptProcessor.prepare_script(source, target_dir)
        assert target_dir.exists()
        assert result_path.exists()

    @pytest.mark.unit
    def test_makes_script_executable(self, temp_dir):
        source = temp_dir / "test.sh"
        source.write_text("#!/bin/bash\necho 'test'")

        target_dir = temp_dir / "target"
        result_path = ScriptProcessor.prepare_script(source, target_dir)

        # Check that file is executable
        import stat
        st = result_path.stat()
        assert st.st_mode & stat.S_IXUSR  # User executable bit set
