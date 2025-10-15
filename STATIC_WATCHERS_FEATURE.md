# Static Watchers for Completed Jobs

## Overview

Static watchers are a new watcher type that allows you to attach watchers to completed or canceled jobs for post-mortem analysis and debugging. Unlike regular watchers that run continuously, static watchers:

- **Run on manual trigger only** - they don't poll job output automatically
- **Work with completed/canceled jobs** - analyze jobs that have already finished
- **Support editing before running** - configure the watcher, then trigger when ready
- **Use cached job output** - analyze stdout/stderr from the cache

## Key Features

### 1. New STATIC State

Added a new `STATIC` state to `WatcherState` enum alongside `ACTIVE`, `PAUSED`, `COMPLETED`, etc.

```python
class WatcherState(Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    STATIC = "static"  # For completed/canceled jobs
    TRIGGERED = "triggered"
    DISABLED = "disabled"
    COMPLETED = "completed"
```

### 2. Automatic State Detection

When creating a watcher, the backend automatically checks the job state:

- **Running/Pending jobs** → Created as `ACTIVE` (normal behavior)
- **Completed/Failed/Canceled jobs** → Created as `STATIC` (new behavior)

### 3. Job Selection Includes All Jobs

The JobSelectionDialog now has an `includeCompletedJobs` flag:

```svelte
<JobSelectionDialog
  includeCompletedJobs={true}
  ...
/>
```

This allows users to select from all jobs (including completed ones) when creating watchers.

### 4. Manual Trigger Support

Static watchers can be manually triggered via:

- **UI**: Play button on watcher card
- **API**: `POST /api/watchers/{watcher_id}/trigger`

The trigger endpoint reads from cached job output (stdout/stderr) and runs pattern matching + actions.

### 5. Visual Indicators

**State Icon**: `▶` (play icon) in purple color (#8b5cf6)

**Badge**: "Static" badge with play icon showing the watcher only runs on trigger

**Tooltip**: "Static watcher - runs on manual trigger only (for completed/canceled jobs)"

## User Flow

### Creating a Static Watcher

1. User clicks "Create Watcher" on Watchers page
2. JobSelectionDialog opens showing **all jobs** (including completed/canceled)
3. User selects a completed job
4. WatcherCreator opens - user configures pattern and actions
5. User clicks "Create Watcher"
6. Backend detects job is completed → creates watcher with `state='static'`
7. Watcher appears in list with purple play icon and "Static" badge

### Running a Static Watcher

1. User finds static watcher in list (purple indicator, "Static" badge)
2. User clicks **play button** (▶) on watcher card
3. Backend:
   - Fetches cached job output (stdout/stderr)
   - Runs pattern matching against cached output
   - Executes actions for each match
   - Logs events to database
4. UI shows trigger result message (success/failure with match count)

### Editing Then Running

1. User creates static watcher (or copies existing one)
2. Watcher is created but not yet triggered
3. User clicks "Edit" button to open WatcherDetailDialog
4. User adjusts pattern, captures, conditions, or actions
5. User saves changes
6. User clicks play button to run with updated configuration

## Use Cases

### Post-Mortem Analysis

```bash
# Job failed overnight - analyze what went wrong
1. Navigate to Watchers page
2. Create watcher on failed job
3. Pattern: "(ERROR|FATAL|Exception): (.+)"
4. Action: log_event with captured error message
5. Click play to find all errors in output
```

### Extracting Metrics from Completed Jobs

```bash
# Training job completed - extract final metrics
1. Create watcher on completed job
2. Pattern: "Final metrics: loss=([\d.]+), acc=([\d.]+)"
3. Captures: [loss, accuracy]
4. Actions: store_metric for both
5. Trigger to extract and store metrics
```

### Testing Watcher Patterns

```bash
# Test watcher pattern before applying to running jobs
1. Create watcher on completed job with known output
2. Configure pattern and actions
3. Trigger to verify matches
4. Adjust pattern if needed
5. Copy to running jobs once confirmed working
```

### Bulk Analysis

```bash
# Analyze multiple completed jobs with same pattern
1. Create watcher on one completed job
2. Test with trigger
3. Copy watcher
4. Multi-select other completed jobs
5. Apply to all - each creates a static watcher
6. Trigger each to analyze all jobs
```

## Implementation Details

### Backend Changes

**File**: `src/ssync/models/watcher.py`
- Added `STATIC = "static"` to `WatcherState` enum

**File**: `src/ssync/web/app.py`
- `create_watcher()`: Auto-detect job state and set `state='static'` for completed jobs
- `trigger_watcher_manually()`: Allow STATIC state alongside ACTIVE
- Skip automatic monitoring for STATIC watchers

### Frontend Changes

**File**: `web-frontend/src/components/JobSelectionDialog.svelte`
- Added `includeCompletedJobs` prop
- Filter logic includes all jobs when flag is true

**File**: `web-frontend/src/pages/WatchersPage.svelte`
- Set `includeCompletedJobs={true}` on JobSelectionDialog

**File**: `web-frontend/src/components/WatcherCard.svelte`
- Added purple play icon for STATIC state
- Added "Static" badge with tooltip
- Play button visible for STATIC watchers
- Updated tooltip to explain static mode

## API Reference

### Create Watcher (Auto-detect)

```bash
POST /api/watchers
{
  "job_id": "12345",
  "hostname": "cluster1",
  "name": "Error Detector",
  "pattern": "ERROR: (.+)",
  "captures": ["error_msg"],
  "actions": [
    {
      "type": "log_event",
      "params": { "message": "Error: $error_msg" }
    }
  ]
}

# Response includes state='static' if job is completed
{
  "id": 42,
  "state": "static",  # Auto-set based on job state
  ...
}
```

### Trigger Static Watcher

```bash
POST /api/watchers/{watcher_id}/trigger

# Response
{
  "success": true,
  "message": "Triggered successfully",
  "matches": 5,
  "timer_mode": false
}
```

## Testing

### Manual Testing Steps

1. **Create a completed job**:
   ```bash
   echo -e '#!/bin/bash\necho "Test output"\necho "ERROR: Test error"' > test.sh
   sbatch test.sh  # Wait for completion
   ```

2. **Create static watcher via UI**:
   - Navigate to Watchers page
   - Click "Create Watcher"
   - Select the completed job
   - Pattern: `ERROR: (.+)`
   - Captures: `[error_msg]`
   - Action: `log_event(message="Found: $error_msg")`
   - Create

3. **Verify static state**:
   - Watcher should show purple play icon
   - Should have "Static" badge
   - Should not be automatically running

4. **Trigger manually**:
   - Click play button
   - Verify trigger message shows success
   - Check events tab for logged event

5. **Verify in database**:
   ```python
   from ssync.cache import get_cache
   cache = get_cache()
   with cache._get_connection() as conn:
       cursor = conn.execute(
           "SELECT * FROM job_watchers WHERE state = 'static'"
       )
       print(list(cursor))
   ```

## Benefits

1. **Post-mortem debugging** - Analyze failed jobs after completion
2. **Pattern testing** - Test watcher patterns on known output before applying to running jobs
3. **Historical analysis** - Extract metrics from old jobs
4. **No resource waste** - Watchers don't consume resources polling finished jobs
5. **Flexible workflow** - Edit → Test → Refine loop for pattern development

## Future Enhancements

- **Batch trigger**: Trigger multiple static watchers at once
- **Scheduled triggers**: Auto-trigger static watchers on a schedule
- **Output range selection**: Trigger on specific line ranges
- **Diff mode**: Compare output between two jobs
- **Template library**: Save successful static watcher patterns as templates
