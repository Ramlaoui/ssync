# Test Recommendations for Backend Coverage

## Current Status

**Overall Coverage:** 13%
**Passing Tests:** 243/243 (100%)
**Well-Tested Modules:**
- script_processor.py: 91%
- slurm/parser.py: 96%
- web/security.py: 75%
- utils/slurm_params.py: 83%

## High-Priority Modules to Test

### 1. Cache System (cache.py) - **CRITICAL**
**Current Coverage:** 9% (597 statements)
**Priority:** 🔴 HIGHEST

The cache is central to the application, handling job persistence, array jobs, watchers, and output storage.

#### Recommended Tests (Est. 150-200 tests):

**Database Operations (25 tests)**
- `test_cache_init_creates_tables` - Verify all tables created
- `test_cache_init_creates_indices` - Check index creation
- `test_cache_init_migration_safe` - Test adding columns to existing DB
- `test_get_connection_thread_safe` - Verify thread safety
- `test_close_connection_cleanup` - Connection cleanup

**Job Caching (30 tests)**
- `test_cache_job_basic` - Cache simple job
- `test_cache_job_preserves_script` - Script preservation on update
- `test_cache_job_merge_job_info` - Merge logic for existing jobs
- `test_cache_job_updates_is_active` - Active status management
- `test_get_cached_job_by_id` - Retrieval by job ID
- `test_get_cached_job_hostname_filter` - Filter by hostname
- `test_get_cached_job_max_age_validation` - Age validation
- `test_get_cached_jobs_active_only` - Active job filtering
- `test_get_cached_jobs_with_limit` - Limit functionality
- `test_cache_job_with_compression` - Compressed output storage
- `test_update_job_outputs_compressed` - Update compressed outputs
- `test_update_job_script_existing` - Update script for existing job
- `test_update_job_script_create_minimal` - Create minimal entry if missing
- `test_mark_job_completed` - Mark as completed
- `test_check_outputs_fetched_after_completion` - Fetch status check
- `test_mark_outputs_fetched_after_completion` - Mark fetch status

**Array Job Metadata (20 tests)**
- `test_update_array_metadata_creates_entry` - Create array job entry
- `test_update_array_metadata_updates_existing` - Update existing entry
- `test_update_array_metadata_skips_parent_brackets` - Skip bracket entries
- `test_recalculate_array_stats` - Statistics calculation
- `test_get_array_job_metadata` - Metadata retrieval
- `test_get_array_job_metadata_not_found` - Handle missing
- `test_get_array_tasks` - Get all tasks for array job
- `test_get_array_tasks_with_limit` - Limited task retrieval
- `test_array_task_stats_counting` - State counting accuracy
- `test_array_metadata_preserves_script` - Script preservation

**Date Range Caching (15 tests)**
- `test_parse_since_to_dates_hours` - Parse "12h" format
- `test_parse_since_to_dates_days` - Parse "7d" format
- `test_parse_since_to_dates_weeks` - Parse "2w" format
- `test_parse_since_to_dates_months` - Parse "1m" format
- `test_generate_cache_key` - Key generation
- `test_check_date_range_cache_hit` - Cache hit scenario
- `test_check_date_range_cache_miss` - Cache miss scenario
- `test_cache_date_range_query` - Store query results
- `test_cleanup_expired_ranges` - Remove expired entries
- `test_date_range_increment_hit_count` - Hit counter

**Cleanup & Maintenance (15 tests)**
- `test_cleanup_old_entries_preserves_scripts` - Script preservation
- `test_cleanup_old_entries_force_cleanup` - Force mode
- `test_cleanup_old_entries_max_age_zero` - No cleanup when age=0
- `test_cleanup_by_size` - Size-based cleanup
- `test_cleanup_by_size_preserves_scripts` - Script preservation in size cleanup
- `test_verify_cached_jobs` - Verification against SLURM state
- `test_clear_all` - Clear all caches
- `test_export_cache_data_all` - Export all jobs
- `test_export_cache_data_filtered` - Export specific jobs

**Host Fetch State (10 tests)**
- `test_get_host_fetch_state_exists` - Get existing state
- `test_get_host_fetch_state_not_found` - Handle missing
- `test_update_host_fetch_state_new` - Create new state
- `test_update_host_fetch_state_increment_count` - Increment fetch count
- `test_get_cached_completed_job_ids` - Fast ID lookup
- `test_get_cached_completed_jobs` - Full job retrieval

**Cache Statistics (10 tests)**
- `test_get_cache_stats_empty` - Stats for empty cache
- `test_get_cache_stats_with_data` - Stats with data
- `test_cache_stats_by_hostname` - Hostname grouping
- `test_cache_stats_range_hits` - Range cache statistics

**Edge Cases & Error Handling (15 tests)**
- `test_cache_job_with_null_values` - Handle None fields
- `test_cache_job_with_enum_serialization` - Enum to JSON
- `test_row_to_cached_data_missing_columns` - Handle missing columns
- `test_cache_invalid_job_state` - Unknown state handling
- `test_cache_concurrent_access` - Thread safety
- `test_cache_database_locked` - Handle DB lock
- `test_cache_disk_full` - Handle disk full error

---

### 2. SLURM Client (slurm/client.py) - **CRITICAL**
**Current Coverage:** 4% (488 statements)
**Priority:** 🔴 HIGHEST

Core SLURM operations that communicate with the cluster.

#### Recommended Tests (Est. 80-100 tests):

**Field Detection (10 tests)**
- `test_get_available_sacct_fields_success` - Detect fields successfully
- `test_get_available_sacct_fields_cached` - Use cached fields
- `test_get_available_sacct_fields_failure_fallback` - Fallback to basic
- `test_get_available_sacct_fields_filters_wanted` - Select wanted fields
- `test_get_available_sacct_fields_missing_essential` - Handle missing essential

**Active Jobs (squeue) (15 tests)**
- `test_get_active_jobs_with_user_filter` - Filter by user
- `test_get_active_jobs_auto_detect_user` - Auto-detect user
- `test_get_active_jobs_no_filter` - All users
- `test_get_active_jobs_by_job_ids` - Filter by job IDs
- `test_get_active_jobs_by_state` - State filtering
- `test_get_active_jobs_empty_result` - No jobs
- `test_get_active_jobs_gets_output_paths_from_scontrol` - Path resolution
- `test_get_active_jobs_expands_slurm_placeholders` - Placeholder expansion
- `test_get_active_jobs_array_jobs` - Array job parsing

**Completed Jobs (sacct) (20 tests)**
- `test_get_completed_jobs_with_since` - Date filtering
- `test_get_completed_jobs_relative_time` - "now-24hours" format
- `test_get_completed_jobs_absolute_time` - Absolute timestamp
- `test_get_completed_jobs_with_user` - User filtering
- `test_get_completed_jobs_with_state_filter` - State filtering
- `test_get_completed_jobs_exclude_ids` - Exclude specific IDs
- `test_get_completed_jobs_with_cached_ids` - Skip cached jobs
- `test_get_completed_jobs_chunked_large_range` - Chunking for large ranges
- `test_get_completed_jobs_expands_placeholders` - Path expansion
- `test_get_completed_jobs_corrects_output_paths` - Path correction

**Job Details (15 tests)**
- `test_get_job_details_from_squeue` - Get from squeue
- `test_get_job_details_from_sacct_fallback` - Fallback to sacct
- `test_get_job_details_merges_cached_submit_line` - Merge from cache
- `test_get_job_details_not_found` - Handle missing job
- `test_get_job_final_state` - Final state retrieval
- `test_get_job_final_state_array_parent` - Array parent aggregation
- `test_get_job_final_state_aggregates_states` - State aggregation

**scontrol Operations (15 tests)**
- `test_get_job_details_from_scontrol` - Parse scontrol output
- `test_get_job_details_from_scontrol_parses_paths` - Extract paths
- `test_get_job_details_from_scontrol_parses_command` - Extract submit_line
- `test_get_job_details_from_scontrol_not_found` - Handle missing
- `test_get_job_output_files` - Get output file paths
- `test_get_job_batch_script` - Retrieve batch script
- `test_get_job_batch_script_not_available` - Handle unavailable script

**Output Reading (15 tests)**
- `test_read_job_output_compressed_small_file` - Small file uncompressed
- `test_read_job_output_compressed_large_file` - Large file compressed
- `test_read_job_output_compressed_very_large_truncated` - Truncation
- `test_read_job_output_content` - Plain text reading
- `test_read_job_output_file_not_found` - Handle missing file

**Utility Functions (10 tests)**
- `test_get_username_from_whoami` - Get username
- `test_get_username_provided` - Use provided username
- `test_cancel_job_success` - Cancel job successfully
- `test_cancel_job_failure` - Handle cancel failure
- `test_check_slurm_availability_true` - SLURM available
- `test_check_slurm_availability_false` - SLURM not available

---

### 3. Sync Manager (sync.py) - **HIGH**
**Current Coverage:** 6% (180 statements)
**Priority:** 🟠 HIGH

File synchronization with security validations.

#### Recommended Tests (Est. 40-50 tests):

**Path Validation (20 tests)**
- `test_validate_path_allowed_path` - Valid allowed path
- `test_validate_path_forbidden_path` - Reject forbidden path
- `test_validate_path_wildcard_allowed` - Wildcard matching
- `test_validate_path_absolute_not_allowed` - Reject absolute paths
- `test_validate_path_home_not_allowed` - Reject home directory
- `test_validate_path_tmp_not_allowed` - Reject /tmp
- `test_validate_path_no_restrictions` - Restrictions disabled
- `test_validate_path_multiple_forbidden` - Multiple forbidden patterns

**Directory Size Checking (8 tests)**
- `test_check_directory_size_under_limit` - Valid size
- `test_check_directory_size_over_limit` - Reject oversized
- `test_check_directory_size_du_failure` - Handle du failure
- `test_check_directory_size_timeout` - Handle timeout

**Gitignore Processing (12 tests)**
- `test_collect_rsync_filter_rules_basic` - Basic gitignore
- `test_collect_rsync_filter_rules_negation` - ! negation rules
- `test_collect_rsync_filter_rules_nested` - Nested gitignores
- `test_collect_rsync_filter_rules_directory_rules` - Directory patterns
- `test_collect_rsync_filter_rules_max_depth` - Depth limiting
- `test_collect_rsync_filter_rules_comments` - Ignore comments

**Sync Operations (15 tests)**
- `test_sync_to_host_success` - Successful sync
- `test_sync_to_host_path_validation_fails` - Reject invalid path
- `test_sync_to_host_size_check_fails` - Reject oversized directory
- `test_sync_to_host_with_password` - Password authentication
- `test_sync_to_host_with_key` - Key authentication
- `test_sync_to_host_with_exclude` - Exclude patterns
- `test_sync_to_host_with_include` - Include patterns
- `test_sync_to_host_with_gitignore` - Use gitignore
- `test_sync_to_all_hosts` - Sync to multiple hosts

---

### 4. Job Models (models/job.py) - **MEDIUM**
**Current Coverage:** 54% (92 statements)
**Priority:** 🟡 MEDIUM

#### Recommended Tests (Est. 15-20 tests):

**GPU Info Parsing (15 tests)**
- `test_gpu_info_no_tres` - No TRES data
- `test_gpu_info_no_gpu` - No GPU in TRES
- `test_gpu_info_requested_basic` - Parse requested GPU
- `test_gpu_info_requested_with_type` - Parse GPU type
- `test_gpu_info_allocated_basic` - Parse allocated GPU
- `test_gpu_info_allocated_with_type` - Parse GPU type
- `test_gpu_info_both_requested_and_allocated` - Both present
- `test_gpu_info_malformed_tres` - Handle malformed data
- `test_gpu_info_multiple_resources` - GPU among other resources
- `test_gpu_info_different_gpu_types` - Different GPU models

**JobState Enum (5 tests)**
- `test_job_state_values` - Verify enum values
- `test_job_state_comparison` - Enum comparison
- `test_job_state_serialization` - Serialize to string

---

### 5. SSH Connection Management (ssh/*) - **MEDIUM**
**Current Coverage:** 22-30%
**Priority:** 🟡 MEDIUM

#### Recommended Tests (Est. 30-40 tests):

**Native SSH (ssh/native.py) (20 tests)**
- `test_get_control_path` - Control path generation
- `test_check_control_master_valid` - Valid socket check
- `test_check_control_master_stale` - Stale socket detection
- `test_start_control_master` - Start SSH multiplexing
- `test_stop_control_master` - Stop multiplexing
- `test_build_ssh_command` - Command building
- `test_ssh_run_command` - Execute command
- `test_ssh_run_command_timeout` - Timeout handling
- `test_ssh_run_command_with_pty` - PTY mode
- `test_ssh_run_command_error_handling` - Error handling

**SSH Connection (ssh/connection.py) (15 tests)**
- `test_ssh_connection_init` - Initialize connection
- `test_ssh_connection_run` - Run command
- `test_ssh_connection_cd_context` - CD context manager
- `test_ssh_connection_put` - Upload file
- `test_ssh_connection_get` - Download file
- `test_ssh_connection_close` - Close connection
- `test_ssh_connection_health_check` - Health checking

**Connection Manager (connection.py) (10 tests)**
- `test_connection_manager_get_connection` - Get/create connection
- `test_connection_manager_reuse_connection` - Reuse existing
- `test_connection_manager_refresh` - Force refresh
- `test_connection_manager_close_all` - Close all connections
- `test_connection_manager_health_check` - Check connection health

---

### 6. Watchers (watchers/*) - **LOW** (But 0% Coverage!)
**Current Coverage:** 0%
**Priority:** 🟢 LOW (Feature-specific, not core)

Only test if watchers are a key feature. If not, document as "feature tests pending" and focus on core functionality first.

#### Recommended Tests (Est. 50-60 tests if needed):

**Watcher Engine (watchers/engine.py) (30 tests)**
- Pattern matching and trigger detection
- Timer mode activation
- Capture variable extraction
- Condition evaluation
- Action execution

**Watcher Actions (watchers/actions.py) (20 tests)**
- Email notification
- Slack notification
- Job cancellation
- Job resubmission
- Command execution
- Metric storage

---

## Implementation Priority

### Phase 1: Critical Core (2-3 weeks)
1. **Cache System Tests** (cache.py)
   - 150-200 tests
   - Focus: Database operations, job caching, array jobs
   - Estimated effort: 1.5 weeks

2. **SLURM Client Tests** (slurm/client.py)
   - 80-100 tests
   - Focus: Job queries, output reading, scontrol operations
   - Estimated effort: 1 week

### Phase 2: Important Features (1-2 weeks)
3. **Sync Manager Tests** (sync.py)
   - 40-50 tests
   - Focus: Path validation, gitignore handling, rsync operations
   - Estimated effort: 3-4 days

4. **Job Models Tests** (models/job.py)
   - 15-20 tests
   - Focus: GPU info parsing
   - Estimated effort: 1-2 days

### Phase 3: Supporting Infrastructure (1 week)
5. **SSH Connection Tests** (ssh/*)
   - 30-40 tests
   - Focus: Connection management, command execution
   - Estimated effort: 3-4 days

### Phase 4: Optional Features (As needed)
6. **Watcher Tests** (watchers/*)
   - 50-60 tests if watchers are critical
   - Can be deferred if not a primary feature

---

## Test Writing Guidelines

### For Cache Tests (cache.py)
```python
@pytest.fixture
def temp_cache(tmp_path):
    """Temporary cache for testing."""
    from ssync.cache import JobDataCache
    cache = JobDataCache(cache_dir=tmp_path, max_age_days=30)
    yield cache
    cache.close()

@pytest.mark.unit
def test_cache_job_basic(temp_cache, sample_job_info):
    """Test caching a basic job."""
    temp_cache.cache_job(sample_job_info, script_content="#!/bin/bash\necho test")

    cached = temp_cache.get_cached_job(sample_job_info.job_id, sample_job_info.hostname)

    assert cached is not None
    assert cached.job_id == sample_job_info.job_id
    assert cached.script_content == "#!/bin/bash\necho test"
```

### For SLURM Client Tests (slurm/client.py)
```python
@pytest.fixture
def mock_ssh_connection():
    """Mock SSH connection for SLURM commands."""
    class MockResult:
        def __init__(self, stdout, stderr="", exited=0):
            self.stdout = stdout
            self.stderr = stderr
            self.exited = exited
            self.ok = exited == 0

    class MockConnection:
        def run(self, command, **kwargs):
            if "squeue" in command:
                return MockResult("12345|test|RUNNING|user|gpu|...")
            elif "sacct" in command:
                return MockResult("12345|test|COMPLETED|user|...")
            return MockResult("")

    return MockConnection()

@pytest.mark.unit
def test_get_active_jobs_with_user_filter(mock_ssh_connection):
    """Test getting active jobs with user filter."""
    from ssync.slurm.client import SlurmClient

    client = SlurmClient()
    jobs = client.get_active_jobs(
        mock_ssh_connection,
        "testhost",
        user="testuser"
    )

    assert len(jobs) > 0
    assert jobs[0].job_id == "12345"
```

### For Sync Tests (sync.py)
```python
@pytest.mark.unit
def test_validate_path_forbidden_path():
    """Test rejecting forbidden paths."""
    from ssync.sync import SyncManager
    from ssync.models.cluster import PathRestrictions

    restrictions = PathRestrictions(
        enabled=True,
        forbidden_paths=["/etc", "/sys"]
    )

    # Mock manager and create sync manager
    sync_manager = SyncManager(
        slurm_manager=None,  # Can be None for validation tests
        source_dir=Path("/etc/config"),
        path_restrictions=restrictions
    )

    is_valid, error = sync_manager._validate_path(Path("/etc/passwd"))

    assert not is_valid
    assert "forbidden" in error.lower()
```

---

## Expected Coverage Improvements

With all Phase 1-3 tests implemented:

| Module | Current | Target | Tests Added |
|--------|---------|--------|-------------|
| cache.py | 9% | 85%+ | 150-200 |
| slurm/client.py | 4% | 70%+ | 80-100 |
| sync.py | 6% | 80%+ | 40-50 |
| models/job.py | 54% | 95%+ | 15-20 |
| ssh/* | 22-30% | 70%+ | 30-40 |
| **Overall** | **13%** | **45-50%** | **~350 tests** |

---

## Benefits of This Test Suite

1. **Confidence in Refactoring** - Safe to improve code knowing tests will catch regressions
2. **Bug Prevention** - Catch issues before they reach production
3. **Documentation** - Tests serve as usage examples
4. **Faster Development** - Quick feedback loop for changes
5. **Better Code Quality** - Writing testable code leads to better design

---

## Getting Started

### Step 1: Set Up Test Infrastructure (1-2 days)
```bash
# Create test fixtures for SLURM responses
mkdir -p tests/fixtures/slurm_responses
touch tests/fixtures/slurm_responses/squeue_output.txt
touch tests/fixtures/slurm_responses/sacct_output.txt

# Add mock fixtures to conftest.py
# - mock_ssh_connection
# - mock_slurm_client
# - temp_cache
```

### Step 2: Start with Cache Tests (Week 1)
Focus on the most critical module first:
- Database initialization and migration
- Job caching (basic operations)
- Array job metadata
- Date range caching

### Step 3: Move to SLURM Client (Week 2)
Second most critical module:
- Active job queries
- Completed job queries
- Output file operations

### Step 4: Continue with Phase 2 & 3 (Weeks 3-4)

---

**Total Estimated Effort:** 4-5 weeks for comprehensive unit test coverage
**Immediate Priority:** Phases 1-2 (Cache + SLURM Client + Sync)
**Target Coverage After Phase 1-2:** 35-40% overall coverage

