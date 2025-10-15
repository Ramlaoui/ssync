# Static Watcher State Fix

## Problem

Static watchers created for completed/canceled jobs were immediately turning into "completed" state, making them un-triggerable from the UI.

## Root Cause Analysis

The issue had multiple potential causes:

1. **Job lookup failures** - If `manager.get_job_info()` fails or returns None for completed jobs, the watcher defaults to 'active' state
2. **Missing UNKNOWN state** - Jobs in UNKNOWN state weren't being recognized as terminal states
3. **Insufficient logging** - Couldn't diagnose what was happening during creation

## The Fix

### 1. **Improved State Detection Logic**

**Before:**
```python
try:
    job_info = manager.get_job_info(job_id, hostname)
    if job_info and job_info.state in [JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED, JobState.TIMEOUT]:
        state = "static"
except Exception as e:
    logger.debug(f"Could not determine job state: {e}")
    # Falls through - uses default 'active' state
```

**After:**
```python
try:
    job_info = manager.get_job_info(job_id, hostname)

    if job_info:
        # Check for terminal states (including UNKNOWN)
        if job_info.state in [JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED, JobState.TIMEOUT, JobState.UNKNOWN]:
            state = "static"
            logger.info(f"Creating STATIC watcher for finished job {job_id} (state: {job_info.state.value})")
        else:
            logger.info(f"Creating ACTIVE watcher for running job {job_id} (state: {job_info.state.value})")
    else:
        # Job not found - likely completed and purged from queue
        state = "static"
        logger.info(f"Job {job_id} not found in queue - creating STATIC watcher (job likely completed)")
except Exception as e:
    # If lookup fails, assume static for safety
    logger.warning(f"Could not determine job state for {job_id}: {e} - defaulting to STATIC")
    state = "static"
```

### 2. **Key Improvements**

✅ **Added JobState.UNKNOWN** - Now recognized as a terminal state

✅ **Fallback to STATIC** - If job not found or lookup fails, defaults to STATIC instead of ACTIVE

✅ **Enhanced Logging** - Every code path logs what state is being created and why

✅ **Defensive Programming** - Assumes completed rather than running when uncertain

### 3. **Why This Matters**

**Scenario 1: Completed job purged from queue**
- **Before**: `get_job_info()` returns None → defaults to 'active' → cleanup marks as 'completed' → can't trigger
- **After**: `get_job_info()` returns None → creates as 'static' → stays 'static' → can trigger

**Scenario 2: Job in UNKNOWN state**
- **Before**: Not recognized as terminal → creates as 'active' → cleanup marks as 'completed'
- **After**: Recognized as terminal → creates as 'static' → stays 'static'

**Scenario 3: SLURM connection error**
- **Before**: Exception caught, falls through to default 'active'
- **After**: Exception caught, explicitly defaults to 'static' with warning log

## Testing the Fix

### Test Case 1: Create watcher on completed job

```bash
# 1. Find a completed job
ssync status --host <hostname>

# 2. Create watcher via UI on completed job
#    - Select job from "Completed / Canceled" tab
#    - Configure pattern and actions
#    - Click "Create Watcher"

# 3. Verify state
python3 -c "
from ssync.cache import get_cache
cache = get_cache()
with cache._get_connection() as conn:
    cursor = conn.execute('SELECT id, job_id, name, state FROM job_watchers ORDER BY created_at DESC LIMIT 1')
    row = cursor.fetchone()
    print(f'Latest watcher: ID={row[0]}, Job={row[1]}, Name={row[2]}, State={row[3]}')
"

# Expected: State should be 'static', not 'completed'
```

### Test Case 2: Verify watcher stays triggerable

```bash
# 1. Create static watcher as above
# 2. Wait 10 seconds
# 3. Click play button in UI
# 4. Should see: "✓ Found X match(es) and executed actions" or "✗ No matches found (searched Y lines)"
```

## Verification

Check the logs to confirm state is being set correctly:

```bash
tail -f ~/.config/ssync/api-server.log | grep "Creating.*watcher"
```

You should see:
- `"Creating STATIC watcher for finished job 12345 (state: completed)"` - for completed jobs
- `"Job 12345 not found in queue - creating STATIC watcher"` - for purged jobs
- `"Could not determine job state for 12345: ... - defaulting to STATIC"` - for errors

## Database Verification

```python
from ssync.cache import get_cache

cache = get_cache()
with cache._get_connection() as conn:
    # Count watchers by state
    cursor = conn.execute('''
        SELECT state, COUNT(*)
        FROM job_watchers
        GROUP BY state
    ''')
    print("Watchers by state:")
    for row in cursor:
        print(f"  {row[0]}: {row[1]}")

    # Show recent static watchers
    cursor = conn.execute('''
        SELECT id, job_id, name, state, created_at
        FROM job_watchers
        WHERE state = 'static'
        ORDER BY created_at DESC
        LIMIT 5
    ''')
    print("\nRecent static watchers:")
    for row in cursor:
        print(f"  ID={row[0]}, Job={row[1]}, Name={row[2]}, State={row[3]}, Created={row[4]}")
```

## Additional Notes

- **STATIC watchers don't run automatically** - They require manual triggering via the play button
- **STATIC watchers are never auto-completed** - The cleanup function only touches 'active' watchers
- **STATIC watchers persist** - They stay in the database until manually deleted
- **UI shows play button** - Static watchers have a visible play button (▶) for manual triggering

## Next Steps

1. Restart the API server to load the new code
2. Create a test watcher on a completed job
3. Verify it stays in 'static' state
4. Test manual triggering with the play button
5. Check logs to confirm proper state detection

---

**Result**: Static watchers should now remain in 'static' state and be manually triggerable from the UI! 🎉
