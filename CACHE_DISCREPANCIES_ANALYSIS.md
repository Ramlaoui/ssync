# Cache and Data Flow Discrepancy Analysis

## Executive Summary

The CLI `status` command and UI show different results due to **multiple cache layers**, **different default parameters**, and **inconsistent array job filtering**. The main issues are:

1. **Limit mismatch**: CLI limits to 20 jobs by default, UI fetches all jobs
2. **Since mismatch**: CLI defaults to 1 day, UI fetches without time filter
3. **Array job filtering**: Inconsistent logic between CLI display filter and backend API grouping
4. **Multiple cache layers**: Backend cache middleware + JobDataManager cache + Frontend stores
5. **Dual frontend stores**: JobStateManager and jobs.ts can get out of sync

---

## Detailed Data Flow Analysis

### CLI Status Command Flow

```
CLI status command (cli/commands.py:58)
  ↓
  Default params: limit=20, since="1d" (cli/cli.py:45-47)
  ↓
API Client.get_jobs() (api/client.py:72-171)
  ↓
HTTP GET /api/status (web/app.py:838)
  ↓
JobDataManager.fetch_all_jobs() (job_data_manager.py:81-198)
  ├─ Per-host limit applied (line 404-411)
  ├─ Since filter applied (line 317-319)
  └─ Merges with cached jobs (line 382-401)
  ↓
Cache middleware (web/app.py:992-995, 1124-1128)
  ↓
Response to CLI
  ↓
CLI Display Filter (cli/display.py:15-57)
  └─ filter_array_jobs() removes parent entries when tasks exist
  ↓
Display to user
```

**Key Parameters:**
- `limit=20` (default)
- `since="1d"` (default)
- No `group_array_jobs` parameter
- User auto-detected unless specified

### UI Data Flow (JobStateManager)

```
JobStateManager.syncHost() (lib/JobStateManager.ts:475-633)
  ↓
  Params: group_array_jobs=true (line 515)
  ↓
HTTP GET /api/status?host={hostname}&group_array_jobs=true
  ↓
Backend /api/status (web/app.py:838)
  ↓
JobDataManager.fetch_all_jobs() (job_data_manager.py:81-198)
  ├─ NO limit applied (not passed)
  ├─ NO since filter (not passed)
  ├─ Array grouping applied (line 970-976, 1086-1089)
  └─ Returns ALL jobs
  ↓
WebSocket broadcast or API response
  ↓
JobStateManager cache (lib/JobStateManager.ts:127-151)
  ↓
UI components
```

**Key Parameters:**
- NO limit (fetches all jobs)
- NO since filter (fetches all time)
- `group_array_jobs=true`
- User auto-detected

### UI Data Flow (jobs.ts store)

```
jobsStore.fetchAllJobsProgressive() (stores/jobs.ts:305-450)
  ↓
  Conditionally adds group_array_jobs from preferences (line 360-369)
  ↓
HTTP GET /api/status (per host, line 388)
  ↓
Backend /api/status
  ↓
Frontend cache (stores/jobs.ts:95-105)
  ├─ Intelligent cache durations by state (lines 32-75)
  ├─ Completed: 5 min
  ├─ Running: 1-2 min
  └─ Pending: 30 sec
  ↓
UI components
```

---

## Critical Discrepancies

### 1. **LIMIT PARAMETER MISMATCH** ⚠️

**Problem:** CLI shows max 20 jobs, UI shows all jobs

- **CLI**: `limit=20` (cli/cli.py:47)
- **UI**: No limit parameter passed
- **Impact**: UI shows jobs that CLI doesn't show
- **Location**: JobDataManager applies per-host limit (job_data_manager.py:404-411)

**Example:**
```python
# CLI sees only 20 most recent jobs
ssync status --host jz

# UI sees ALL jobs from that host
```

### 2. **SINCE PARAMETER MISMATCH** ⚠️

**Problem:** CLI shows 1 day of history, UI shows all time

- **CLI**: `since="1d"` (cli/cli.py:45)
- **UI**: No since parameter
- **Impact**: UI shows completed jobs from weeks/months ago that CLI doesn't show
- **Location**: JobDataManager uses since for completed jobs (job_data_manager.py:317-319)

**Example:**
```bash
# CLI shows jobs from last 24 hours
ssync status --host jz

# UI shows ALL jobs ever submitted (that are cached)
```

### 3. **ARRAY JOB FILTERING INCONSISTENCY** ⚠️

**Problem:** Different filtering logic in different places

**CLI Path:**
1. Backend doesn't group arrays (no `group_array_jobs` param)
2. Returns raw SLURM data with parent + individual tasks
3. CLI display filter removes parents (display.py:15-57)

**UI Path (JobStateManager):**
1. Passes `group_array_jobs=true` (JobStateManager.ts:515)
2. Backend groups array tasks (app.py:970-976)
3. UI gets pre-grouped data

**UI Path (jobs.ts):**
1. Only passes `group_array_jobs=true` if preferences enabled (jobs.ts:360-369)
2. Depends on user preference
3. May get ungrouped data

**Impact:**
- Inconsistent array job display between CLI and UI
- UI might show parent entries that CLI filters out
- Different views depending on which store component uses

### 4. **MULTIPLE CACHE LAYERS** ⚠️

**Cache Layer 1: Backend Cache Middleware**
- Location: `web/app.py:906-907, 992-995, 1124-1128`
- Type: Date-range aware cache for repeated queries
- Invalidation: Based on date range and filters

**Cache Layer 2: JobDataManager Cache**
- Location: `cache.py` via `job_data_manager.py`
- Type: SQLite-based persistent cache
- Contains: Job info, scripts, outputs
- Merging: Lines 382-401 in job_data_manager.py

**Cache Layer 3: Frontend jobs.ts Store**
- Location: `stores/jobs.ts:95-105`
- Type: In-memory with intelligent expiration
- Durations: 30s (pending) to 5min (completed)

**Cache Layer 4: JobStateManager**
- Location: `lib/JobStateManager.ts:127-151`
- Type: In-memory reactive cache
- Lifetime: 30s (pending) to 5min (completed)

**Impact:**
- Data can be stale in one layer but fresh in another
- No coordination between cache layers
- Cache invalidation issues when data changes
- UI might show cached data while CLI shows fresh data

### 5. **DUAL FRONTEND STORES** ⚠️

**Problem:** Two different stores managing same data

**Store 1: JobStateManager**
- Modern, centralized manager
- WebSocket + API polling
- Used by: JobsPage?, new components?

**Store 2: jobs.ts**
- Older store
- API-only
- Used by: Most existing components

**Impact:**
- Components using different stores see different data
- Stores can get out of sync
- Double fetching from same endpoints
- Confusing for developers

---

## Per-Host Limit Behavior

**Backend Logic** (job_data_manager.py:404-411):
```python
if limit:
    # Sort by submit time (newest first) before limiting
    jobs.sort(key=lambda job: job.submit_time or "", reverse=True)
    original_count = len(jobs)
    jobs = jobs[:limit]
    logger.info(
        f"Applied per-host limit of {limit} to {hostname}, "
        f"reduced from {original_count} to {len(jobs)} jobs"
    )
```

**What this means:**
- Limit is applied **per host** not globally
- If you have 3 hosts and limit=20:
  - CLI could show up to 60 jobs (20 per host)
  - But only after merging with cache
- Sorting happens **before** limiting (newest first)

---

## Array Job Filtering

### CLI Logic (display.py:15-57)

```python
def filter_array_jobs(jobs: List[JobInfo]) -> List[JobInfo]:
    """Filter out array parent entries when individual tasks exist."""

    # Identify individual tasks (numeric array_task_id)
    array_tasks = defaultdict(list)
    for job in jobs:
        if job.array_job_id and job.array_task_id and job.array_task_id.isdigit():
            array_tasks[job.array_job_id].append(job)

    # Identify parent jobs (array_task_id with brackets like [0-4])
    parent_jobs = {}
    for job in jobs:
        if job.array_job_id and job.array_task_id and '[' in job.array_task_id:
            parent_jobs[job.array_job_id] = job

    # Only add parent if NO individual tasks exist for that array_job_id
    # This prevents showing misleading parent entries
```

**Key insight:** SLURM returns both parent AND individual task entries. Parent entry shows state of REMAINING tasks which is misleading.

### Backend Grouping Logic (app.py:970-976)

```python
if group_array_jobs and host_jobs:
    display_jobs, array_groups = group_array_job_tasks(host_jobs)
```

This groups tasks into `ArrayJobGroup` objects but doesn't necessarily filter out parents.

---

## Cached Job Merging (job_data_manager.py:382-401)

```python
if not active_only:
    cached_jobs = self.cache.get_cached_completed_jobs(hostname, since=since_dt)

    # CRITICAL: Filter cached jobs by current user
    user_cached_jobs = []
    if cached_jobs:
        for cached_job in cached_jobs:
            if cached_job.user == effective_user:
                user_cached_jobs.append(cached_job)

    jobs = self._merge_with_cached_jobs(jobs, user_cached_jobs)
```

**Issues:**
1. Cache merge happens AFTER limit is applied to SLURM jobs
2. Could result in more than `limit` jobs total
3. User filter ensures you only see your own cached jobs
4. But if CLI auto-detects different user than UI, results differ

---

## Recommendations

### High Priority Fixes

1. **Align default parameters**:
   - UI should pass `limit` and `since` parameters matching CLI defaults
   - Or make CLI defaults configurable
   - Location to fix: `stores/jobs.ts:349-356`, `lib/JobStateManager.ts:512-515`

2. **Consolidate frontend stores**:
   - Migrate all components to use JobStateManager
   - Deprecate jobs.ts store
   - Remove duplicate fetching logic

3. **Consistent array job handling**:
   - Always pass `group_array_jobs=true` from UI
   - Ensure CLI and UI use same grouping/filtering logic
   - Location to fix: `stores/jobs.ts:360-369`

4. **Document cache behavior**:
   - Add cache TTL to API responses
   - Expose cache status in UI
   - Add cache invalidation controls

### Medium Priority

1. **Cache coordination**:
   - Add cache versioning/timestamps
   - Coordinate invalidation across layers
   - Expose cache metadata in responses

2. **User detection consistency**:
   - Pass explicit user to prevent auto-detection differences
   - Or ensure auto-detection is deterministic

3. **Logging improvements**:
   - Log which cache layer served data
   - Log parameter differences between requests
   - Track data flow through layers

### Low Priority

1. **Performance optimization**:
   - Consolidate cache layers
   - Reduce redundant fetches
   - Implement smarter cache invalidation

---

## Testing Checklist

To verify if CLI and UI match:

```bash
# Test 1: Basic status
ssync status --host <host>
# Check UI for same host - should show same jobs

# Test 2: With limit
ssync status --host <host> --limit 10
# UI should match if it passes limit parameter

# Test 3: With since filter
ssync status --host <host> --since 2h
# UI should match if it passes since parameter

# Test 4: Array jobs
ssync status --host <host> --job-id <array_parent_id>
# Check if both filter out parent correctly

# Test 5: Check cache staleness
# Run CLI twice, note if results change
# Check UI, see if it matches first or second run
```

---

## Files Requiring Changes

### Frontend
1. `web-frontend/src/stores/jobs.ts`
   - Add default limit/since parameters
   - Always pass group_array_jobs

2. `web-frontend/src/lib/JobStateManager.ts`
   - Add limit/since parameters
   - Coordinate with jobs.ts store

3. Components using jobs.ts
   - Migrate to JobStateManager
   - Or ensure consistent parameter passing

### Backend
1. `src/ssync/web/app.py`
   - Document cache behavior
   - Add cache metadata to responses

2. `src/ssync/cli/display.py`
   - Option to use backend array grouping instead of client-side filter

### Documentation
1. Add CACHE_BEHAVIOR.md explaining all cache layers
2. Update API documentation with default parameters
3. Add troubleshooting guide for data discrepancies
