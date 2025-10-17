# WebSocket Updates Fix - Running Time Display

## Problem
The running time on the sidebar was stuck/frozen at the initial load time because the backend monitoring task only sent updates when job **states changed** (PD → R, R → CD, etc.).

For jobs that remain in RUNNING state, no updates were sent, so the UI never received new elapsed_time data.

## Solution
Modified the backend WebSocket monitoring task to send updates in 3 scenarios:

### src/ssync/web/app.py (lines 3914-3922)
```python
# Send updates when:
# 1. Job is new (not in job_states)
# 2. Job state changed  
# 3. Job is RUNNING (to update elapsed_time in UI)
is_new = job_key not in job_states
state_changed = not is_new and job_states[job_key] != job.state
is_running = job.state == "R"

if is_new or state_changed or is_running:
    # Send update
```

## Changes Made

### 1. Backend: Send periodic updates for running jobs
**File**: `src/ssync/web/app.py:3914-3922`

Added logic to send updates for ALL running jobs every 10 seconds, not just when state changes.

### 2. Backend: Enhanced diagnostic logging
**Files**: `src/ssync/web/app.py:3894-3905, 3969-3974`

Added logging to show:
- When monitoring task runs
- How many jobs were fetched  
- Breakdown of updates (new jobs, state changes, running refreshes)

## Expected Behavior After Fix

### Backend Logs (every 10 seconds):
```
[DEBUG] Monitor task running - 1 clients connected
[DEBUG] Monitor task fetched 137 jobs
[INFO] Broadcasting 5 updates (0 new, 1 state changes, 4 running refreshes) to 1 clients
```

### Frontend Console (every 10 seconds when jobs are running):
```javascript
[JobStateManager] 📨 WebSocket message received, size: XXXX bytes
[JobStateManager] 📨 Parsed message type: batch_update
[JobStateManager] WebSocket message received: batch_update {type: 'batch_update', updates: Array(5), ...}
[JobStateManager] Processing 5 updates, 0 remaining
[JobStateManager] Updating existing job margaret:4241205 from websocket (no state change)
[JobStateManager] Updating existing job jz:780420 from websocket (no state change)
```

### UI Behavior:
- ✅ Running time updates every 10 seconds
- ✅ Elapsed time increments continuously
- ✅ No stuck/frozen timestamps
- ✅ Sidebar refreshes automatically

## How to Verify

### 1. Check Backend Logs
Enable debug logging to see monitoring task activity:
```bash
# In your backend terminal, you should see every 10 seconds:
[INFO] Broadcasting X updates to Y clients
```

### 2. Check Browser Console  
With a running job, you should see every 10 seconds:
```javascript
[JobStateManager] 📨 Parsed message type: batch_update
```

### 3. Watch the Sidebar
- Find a RUNNING job in the sidebar
- Watch the "Running for X" time
- It should update every 10 seconds automatically

## Performance Impact

**Minimal overhead** - only running jobs trigger updates:
- 0 running jobs = 0 updates per cycle
- 5 running jobs = 5 updates per 10 seconds = 0.5 updates/sec
- 20 running jobs = 20 updates per 10 seconds = 2 updates/sec

This is very reasonable and won't overload SLURM or the WebSocket connection.

## Testing

After restarting the backend:

1. **Submit a long-running test job:**
   ```bash
   echo '#!/bin/bash
   sleep 300
   echo "Long test"' | ssh <host> 'sbatch --time=00:10:00 --job-name=test-running-time'
   ```

2. **Watch the UI** - The job's running time should increment every 10 seconds

3. **Check logs** - Backend should log "Broadcasting X updates" every 10 seconds

## Files Modified

- `src/ssync/web/app.py` - Backend WebSocket monitoring task
  - Line 3894-3905: Added diagnostic logging
  - Line 3914-3922: Modified update detection logic
  - Line 3969-3974: Enhanced update count logging

## Restart Required

**Backend must be restarted** for changes to take effect:
```bash
# Stop and restart ssync web
pkill -f "ssync web"
ssync web

# Or with systemd
sudo systemctl restart ssync-web
```

No frontend rebuild needed - frontend already handles batch_update messages correctly.
