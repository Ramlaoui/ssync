"""Unit tests for slurm/parser.py."""

import pytest

from ssync.models.job import JobState
from ssync.slurm.parser import SlurmParser


class TestMapSlurmState:
    """Tests for map_slurm_state method."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "state_str,expected",
        [
            ("PENDING", JobState.PENDING),
            ("pending", JobState.PENDING),
            ("RUNNING", JobState.RUNNING),
            ("running", JobState.RUNNING),
            ("COMPLETED", JobState.COMPLETED),
            ("completed", JobState.COMPLETED),
            ("FAILED", JobState.FAILED),
            ("failed", JobState.FAILED),
            ("CANCELLED", JobState.CANCELLED),
            ("CANCELED", JobState.CANCELLED),  # Alternative spelling
            ("TIMEOUT", JobState.TIMEOUT),
            ("timeout", JobState.TIMEOUT),
        ],
    )
    def test_map_squeue_states(self, state_str, expected):
        """Test mapping of squeue state strings."""
        result = SlurmParser.map_slurm_state(state_str, from_sacct=False)
        assert result == expected

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "state_str,expected",
        [
            ("BOOT_FAIL", JobState.FAILED),
            ("NODE_FAIL", JobState.FAILED),
            ("OUT_OF_MEMORY", JobState.FAILED),
        ],
    )
    def test_map_failure_states(self, state_str, expected):
        """Test mapping of various failure states."""
        result = SlurmParser.map_slurm_state(state_str, from_sacct=False)
        assert result == expected

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "state_str,expected",
        [
            ("COMPLETED", JobState.COMPLETED),
            ("FAILED", JobState.FAILED),
            ("BOOT_FAIL", JobState.FAILED),
            ("DEADLINE", JobState.FAILED),
            ("NODE_FAIL", JobState.FAILED),
            ("OUT_OF_MEMORY", JobState.FAILED),
            ("PREEMPTED", JobState.FAILED),
            ("CANCELLED", JobState.CANCELLED),
            ("TIMEOUT", JobState.TIMEOUT),
        ],
    )
    def test_map_sacct_states(self, state_str, expected):
        """Test mapping of sacct state strings."""
        result = SlurmParser.map_slurm_state(state_str, from_sacct=True)
        assert result == expected

    @pytest.mark.unit
    def test_map_unknown_state_squeue(self):
        """Test that unknown squeue states return UNKNOWN."""
        result = SlurmParser.map_slurm_state("WEIRD_STATE", from_sacct=False)
        assert result == JobState.UNKNOWN

    @pytest.mark.unit
    def test_map_unknown_state_sacct(self):
        """Test that unknown sacct states return UNKNOWN."""
        result = SlurmParser.map_slurm_state("WEIRD_STATE", from_sacct=True)
        assert result == JobState.UNKNOWN

    @pytest.mark.unit
    def test_map_sacct_state_with_reason(self):
        """Test that sacct states with reasons are handled correctly."""
        # sacct sometimes includes reasons like "FAILED by 1:0"
        result = SlurmParser.map_slurm_state("FAILED by 1:0", from_sacct=True)
        assert result == JobState.FAILED

    @pytest.mark.unit
    def test_map_empty_state(self):
        """Test handling of empty state string."""
        result = SlurmParser.map_slurm_state("", from_sacct=False)
        assert result == JobState.UNKNOWN


class TestExpandSlurmPathVars:
    """Tests for expand_slurm_path_vars method."""

    @pytest.mark.unit
    def test_expand_job_id(self):
        path = "/path/to/output-%j.log"
        var_dict = {"j": "12345", "i": "12345", "u": "testuser", "x": "test_job"}
        result = SlurmParser.expand_slurm_path_vars(path, var_dict)
        assert result == "/path/to/output-12345.log"

    @pytest.mark.unit
    def test_expand_username(self):
        path = "/home/%u/logs/output.log"
        var_dict = {"j": "12345", "i": "12345", "u": "testuser", "x": "test_job"}
        result = SlurmParser.expand_slurm_path_vars(path, var_dict)
        assert result == "/home/testuser/logs/output.log"

    @pytest.mark.unit
    def test_expand_job_name(self):
        path = "/logs/%x/%j.out"
        var_dict = {"j": "12345", "i": "12345", "u": "testuser", "x": "my_job"}
        result = SlurmParser.expand_slurm_path_vars(path, var_dict)
        assert result == "/logs/my_job/12345.out"

    @pytest.mark.unit
    def test_expand_multiple_variables(self):
        path = "/home/%u/jobs/%x/output-%j.log"
        var_dict = {"j": "12345", "i": "12345", "u": "testuser", "x": "test_job"}
        result = SlurmParser.expand_slurm_path_vars(path, var_dict)
        assert result == "/home/testuser/jobs/test_job/output-12345.log"

    @pytest.mark.unit
    def test_expand_no_variables(self):
        path = "/absolute/path/to/output.log"
        var_dict = {"j": "12345", "i": "12345", "u": "testuser", "x": "test_job"}
        result = SlurmParser.expand_slurm_path_vars(path, var_dict)
        assert result == path

    @pytest.mark.unit
    def test_expand_empty_path(self):
        var_dict = {"j": "12345", "i": "12345", "u": "testuser", "x": "test_job"}
        result = SlurmParser.expand_slurm_path_vars("", var_dict)
        assert result == ""

    @pytest.mark.unit
    def test_expand_none_path(self):
        var_dict = {"j": "12345", "i": "12345", "u": "testuser", "x": "test_job"}
        result = SlurmParser.expand_slurm_path_vars(None, var_dict)
        assert result is None

    @pytest.mark.unit
    def test_expand_missing_variable_value(self):
        path = "/path/%j/%u/%x.log"
        var_dict = {"j": "12345", "i": "", "u": "", "x": ""}  # Empty values
        result = SlurmParser.expand_slurm_path_vars(path, var_dict)
        assert result == "/path/12345//.log"


class TestCreateVarDict:
    """Tests for create_var_dict method."""

    @pytest.mark.unit
    def test_create_var_dict_from_squeue_fields(self):
        fields = ["12345", "test_job", "RUNNING", "testuser", "gpu"]
        var_dict = SlurmParser.create_var_dict(fields)

        assert var_dict["j"] == "12345"
        assert var_dict["i"] == "12345"
        assert var_dict["u"] == "testuser"
        assert var_dict["x"] == "test_job"

    @pytest.mark.unit
    def test_create_var_dict_from_sacct_fields(self):
        field_names = ["JobID", "JobName", "State", "User"]
        fields = ["12345", "test_job", "COMPLETED", "testuser"]
        var_dict = SlurmParser.create_var_dict(fields, field_names)

        assert var_dict["j"] == "12345"
        assert var_dict["i"] == "12345"
        assert var_dict["u"] == "testuser"
        assert var_dict["x"] == "test_job"

    @pytest.mark.unit
    def test_create_var_dict_with_missing_fields(self):
        fields = ["12345"]  # Only job ID
        var_dict = SlurmParser.create_var_dict(fields)

        assert var_dict["j"] == "12345"
        assert var_dict["i"] == "12345"
        assert var_dict["u"] == ""  # Missing field returns empty
        assert var_dict["x"] == ""  # Missing field returns empty

    @pytest.mark.unit
    def test_create_var_dict_sacct_missing_fields(self):
        field_names = ["JobID", "JobName", "State"]
        fields = ["12345", "test_job"]  # Missing State field
        var_dict = SlurmParser.create_var_dict(fields, field_names)

        assert var_dict["j"] == "12345"
        assert var_dict["x"] == "test_job"
        assert var_dict["u"] == ""  # User not in field_names


class TestFromSqueuFields:
    """Tests for from_squeue_fields method."""

    @pytest.mark.unit
    def test_parse_basic_squeue_fields(self):
        from ssync.slurm.fields import SQUEUE_FIELDS

        # Create fields matching SQUEUE_FIELDS order
        fields = ["12345", "test_job", "RUNNING", "testuser", "gpu", "1", "4", "8G",
                  "01:00:00", "00:15:30", "", "/home/testuser/work",
                  "slurm-12345.out", "slurm-12345.err", "2024-01-15T10:30:00",
                  "2024-01-15T10:30:05", "default", "normal", "1000", "node001"]

        job_info = SlurmParser.from_squeue_fields(fields, "cluster.example.com")

        assert job_info.job_id == "12345"
        assert job_info.name == "test_job"
        assert job_info.state == JobState.RUNNING
        assert job_info.user == "testuser"
        assert job_info.partition == "gpu"
        assert job_info.hostname == "cluster.example.com"

    @pytest.mark.unit
    def test_parse_squeue_with_missing_fields(self):
        fields = ["12345", "test_job", "RUNNING"]  # Minimal fields

        job_info = SlurmParser.from_squeue_fields(fields, "cluster.example.com")

        assert job_info.job_id == "12345"
        assert job_info.name == "test_job"
        assert job_info.state == JobState.RUNNING
        assert job_info.hostname == "cluster.example.com"

    @pytest.mark.unit
    def test_parse_squeue_array_job_underscore_format(self):
        fields = ["12345_0", "array_job", "RUNNING", "testuser"]

        job_info = SlurmParser.from_squeue_fields(fields, "cluster.example.com")

        assert job_info.job_id == "12345_0"
        assert job_info.array_job_id == "12345"
        assert job_info.array_task_id == "0"

    @pytest.mark.unit
    def test_parse_squeue_array_job_bracket_format(self):
        fields = ["12345[0-9]", "array_job", "PENDING", "testuser"]

        job_info = SlurmParser.from_squeue_fields(fields, "cluster.example.com")

        assert job_info.job_id == "12345[0-9]"
        assert job_info.array_job_id == "12345"
        assert job_info.array_task_id == "0-9"

    @pytest.mark.unit
    def test_parse_squeue_expands_path_variables(self):
        from ssync.slurm.fields import SQUEUE_FIELDS

        fields = ["12345", "test_job", "RUNNING", "testuser", "gpu", "1", "4", "8G",
                  "01:00:00", "00:15:30", "", "/home/testuser/work",
                  "output-%j.log", "error-%j.log"]

        job_info = SlurmParser.from_squeue_fields(fields, "cluster.example.com")

        assert job_info.stdout_file == "output-12345.log"
        assert job_info.stderr_file == "error-12345.log"


class TestFromSacctFields:
    """Tests for from_sacct_fields method."""

    @pytest.mark.unit
    def test_parse_basic_sacct_fields(self):
        from ssync.slurm.fields import SACCT_FIELDS

        fields = ["12345", "test_job", "COMPLETED", "testuser", "gpu", "1", "4",
                  "8G", "01:00:00", "00:45:30", "", "/home/testuser/work",
                  "slurm-12345.out", "slurm-12345.err", "2024-01-15T10:30:00",
                  "2024-01-15T10:30:05", "2024-01-15T11:15:35", "node001",
                  "0:0", "default", "normal", "1000"]

        job_info = SlurmParser.from_sacct_fields(fields, "cluster.example.com")

        assert job_info.job_id == "12345"
        assert job_info.name == "test_job"
        assert job_info.state == JobState.COMPLETED
        assert job_info.user == "testuser"
        assert job_info.hostname == "cluster.example.com"

    @pytest.mark.unit
    def test_parse_sacct_failed_job(self):
        from ssync.slurm.fields import SACCT_FIELDS

        # Fields must match SACCT_FIELDS order: JobID, JobName, State, User, Partition, AllocNodes,
        # AllocCPUS, ReqMem, Timelimit, Elapsed, Submit, Start, End, WorkDir, NodeList, Reason...
        fields = ["12346", "failed_job", "FAILED", "testuser", "cpu", "1", "2",
                  "4G", "00:30:00", "00:05:00", "", "", "", "", "", "NonZeroExitCode"]

        job_info = SlurmParser.from_sacct_fields(fields, "cluster.example.com")

        assert job_info.state == JobState.FAILED
        assert job_info.reason == "NonZeroExitCode"

    @pytest.mark.unit
    def test_parse_sacct_array_job(self):
        fields = ["54321_5", "array_job", "COMPLETED", "testuser"]

        job_info = SlurmParser.from_sacct_fields(fields, "cluster.example.com")

        assert job_info.job_id == "54321_5"
        assert job_info.array_job_id == "54321"
        assert job_info.array_task_id == "5"

    @pytest.mark.unit
    def test_parse_sacct_with_custom_field_names(self):
        # Test with different field ordering
        custom_fields = ["User", "JobID", "JobName", "State"]
        fields = ["testuser", "12345", "my_job", "COMPLETED"]

        job_info = SlurmParser.from_sacct_fields(
            fields, "cluster.example.com", field_names=custom_fields
        )

        assert job_info.job_id == "12345"
        assert job_info.name == "my_job"
        assert job_info.user == "testuser"
        assert job_info.state == JobState.COMPLETED

    @pytest.mark.unit
    def test_parse_sacct_with_missing_optional_fields(self):
        fields = ["12345", "test_job", "COMPLETED"]

        job_info = SlurmParser.from_sacct_fields(fields, "cluster.example.com")

        assert job_info.job_id == "12345"
        assert job_info.name == "test_job"
        assert job_info.user is None  # Missing optional field

    @pytest.mark.unit
    def test_parse_sacct_expands_path_variables(self):
        from ssync.slurm.fields import SACCT_FIELDS

        # Use custom field names to properly map StdOut and StdErr fields
        custom_fields = ["JobID", "JobName", "State", "User", "Partition", "AllocNodes",
                         "AllocCPUS", "ReqMem", "Timelimit", "Elapsed", "WorkDir",
                         "StdOut", "StdErr"]
        fields = ["12345", "test_job", "COMPLETED", "testuser", "gpu", "1", "4",
                  "8G", "01:00:00", "00:45:30", "/home/testuser/work",
                  "/home/%u/output-%j.log", "/home/%u/error-%j.log"]

        job_info = SlurmParser.from_sacct_fields(fields, "cluster.example.com", field_names=custom_fields)

        assert job_info.stdout_file == "/home/testuser/output-12345.log"
        assert job_info.stderr_file == "/home/testuser/error-12345.log"

    @pytest.mark.unit
    def test_parse_sacct_timeout_state(self):
        fields = ["12345", "long_job", "TIMEOUT", "testuser"]

        job_info = SlurmParser.from_sacct_fields(fields, "cluster.example.com")

        assert job_info.state == JobState.TIMEOUT

    @pytest.mark.unit
    def test_parse_sacct_cancelled_state(self):
        fields = ["12345", "cancelled_job", "CANCELLED", "testuser"]

        job_info = SlurmParser.from_sacct_fields(fields, "cluster.example.com")

        assert job_info.state == JobState.CANCELLED

    @pytest.mark.unit
    def test_parse_sacct_out_of_memory_state(self):
        fields = ["12345", "oom_job", "OUT_OF_MEMORY", "testuser"]

        job_info = SlurmParser.from_sacct_fields(fields, "cluster.example.com")

        assert job_info.state == JobState.FAILED


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.unit
    def test_handle_very_long_node_list(self):
        # Simulate a job running on many nodes
        long_node_list = ",".join([f"node{i:04d}" for i in range(1000)])
        fields = ["12345", "big_job", "RUNNING", "testuser", "cpu", "1000", "4000",
                  "1000G", "24:00:00", "01:00:00", "", "/work", "out.log", "err.log",
                  "2024-01-15T10:00:00", "2024-01-15T10:00:05", "default", "normal",
                  "1000", long_node_list]

        job_info = SlurmParser.from_squeue_fields(fields, "cluster.example.com")

        assert job_info.node_list == long_node_list
        assert len(job_info.node_list) > 5000  # Should handle long strings

    @pytest.mark.unit
    def test_handle_job_name_with_special_characters(self):
        # Job names can have special characters
        fields = ["12345", "job-name_with.special:chars", "RUNNING", "testuser"]

        job_info = SlurmParser.from_squeue_fields(fields, "cluster.example.com")

        assert job_info.name == "job-name_with.special:chars"

    @pytest.mark.unit
    def test_handle_empty_field_values(self):
        # Some fields might be empty strings
        fields = ["12345", "", "RUNNING", "", "", "", "", "", "", "", "", "", "", ""]

        job_info = SlurmParser.from_squeue_fields(fields, "cluster.example.com")

        assert job_info.job_id == "12345"
        assert job_info.name == ""
        # Should not crash on empty fields

    @pytest.mark.unit
    def test_handle_unicode_in_job_name(self):
        # Test UTF-8 characters in job name
        fields = ["12345", "训练模型_🚀", "RUNNING", "testuser"]

        job_info = SlurmParser.from_squeue_fields(fields, "cluster.example.com")

        assert job_info.name == "训练模型_🚀"

    @pytest.mark.unit
    def test_handle_array_job_range_with_step(self):
        # Array jobs can have ranges with steps like [0-99:2]
        fields = ["54321[0-99:2]", "array_job", "PENDING", "testuser"]

        job_info = SlurmParser.from_squeue_fields(fields, "cluster.example.com")

        assert job_info.array_job_id == "54321"
        assert job_info.array_task_id == "0-99:2"

    @pytest.mark.unit
    def test_handle_array_job_list_format(self):
        # Array jobs can have lists like [1,3,5,7]
        fields = ["54321[1,3,5,7]", "array_job", "PENDING", "testuser"]

        job_info = SlurmParser.from_squeue_fields(fields, "cluster.example.com")

        assert job_info.array_job_id == "54321"
        assert job_info.array_task_id == "1,3,5,7"
