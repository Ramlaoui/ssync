# Timer Mode Manual Trigger Implementation

## Overview
Enhanced the watcher system to support manual triggering of timer mode actions through the UI. Previously, manual triggers would only perform pattern matching even for watchers already in timer mode.

## Changes Made

### 1. Backend - Watcher Engine (`src/ssync/watchers/engine.py`)
- Added `execute_timer_actions()` method to manually execute timer mode actions
- Executes all configured actions using cached variables from initial pattern match
- Updates trigger count and respects max_triggers limit
- Returns detailed success/failure messages for UI feedback

### 2. API Endpoint (`src/ssync/web/app.py`)
- Modified `/api/watchers/{watcher_id}/trigger` endpoint
- Detects if watcher is in timer mode (`timer_mode_active`)
- Routes to timer action execution instead of pattern matching when in timer mode
- Returns `timer_mode: true` flag in response for UI handling

### 3. Frontend - WatcherCard Component (`web-frontend/src/components/WatcherCard.svelte`)
- Updated manual trigger handler to recognize timer mode responses
- Shows different messages for timer mode vs pattern matching triggers
- Displays timer clock icon (⏱️) for timer mode actions
- Shows detailed action results in trigger message

## How It Works

### For Timer Mode Watchers:
1. User clicks manual trigger button on an active timer mode watcher
2. API checks `timer_mode_active` flag
3. If true, executes `execute_timer_actions()` instead of pattern matching
4. Actions run with cached variables from initial pattern match
5. UI shows timer-specific feedback message

### For Regular Watchers:
1. User clicks manual trigger button
2. API performs pattern matching on recent output
3. If pattern matches, executes actions and may activate timer mode
4. UI shows pattern matching feedback

## Use Case: WandB Sync

Perfect for periodic syncing scenarios:

```python
watcher = {
    "name": "wandb_periodic_sync",
    "pattern": r"wandb: Run (\S+) created",
    "captures": ["run_id"],
    "timer_mode_enabled": True,
    "timer_interval_seconds": 300,  # Auto-sync every 5 minutes
    "actions": [{
        "type": "RUN_COMMAND",
        "params": {
            "command": "wandb sync ${run_id} --include-offline"
        }
    }]
}
```

### Workflow:
1. Watcher detects wandb run creation → captures run_id
2. Switches to timer mode → executes sync every 5 minutes
3. User can manually trigger sync anytime via UI button
4. Manual trigger executes same sync command immediately

## Testing

Run the test script to verify functionality:
```bash
python test_timer_mode_trigger.py
```

Expected output shows:
- Timer mode actions execute successfully when active
- Proper failure when timer mode is not active
- Graceful handling of missing watchers

## Benefits

1. **User Control**: Manual sync/action execution without waiting for timer
2. **Visual Feedback**: Clear indication of timer mode status and actions
3. **Debugging**: Easy testing of timer actions without modifying intervals
4. **Flexibility**: Works for any time-dependent action (backups, syncs, monitoring)