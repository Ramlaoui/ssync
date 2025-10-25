# Debugging Runtime Errors Guide

## What We've Added

### 1. Comprehensive Watcher Data Validation
- **File**: `src/stores/watchers.ts`
- **Feature**: All watcher data is now validated before being added to the store
- **Logging**: Set `DEBUG_WATCHERS = true` (line 6) to enable verbose logging

### 2. Error Logging
When invalid data is detected, you'll see logs like:
```
[Watchers] Invalid watcher from fetchJobWatchers(12345) - missing required fields:
{
  watcher: {...},
  hasId: true,
  hasState: false,  // <-- This tells you what's missing
  hasJobId: true,
  stack: "Error: ..."  // <-- Shows where it came from
}
```

### 3. Null-Safety Checks
All forEach loops and filters now check for null/undefined before accessing `.state`:
- `WatchersPage.svelte` lines 381-384, 427-432
- `DashboardPage.svelte` lines 55-59, 99-107
- `JobsPage.svelte` lines 131-139
- `WatchersPageClassic.svelte` lines 118-120, 211-213
- `WatchersTab.svelte` lines 42, 59-91

## How to Investigate the Error

### Step 1: Check Browser Console
1. Open DevTools (F12)
2. Go to Console tab
3. Look for logs starting with `[Watchers]`

### Step 2: Identify the Source
When you see the error, check the console for:
```
[Watchers] Invalid watcher from <SOURCE> - missing required fields
```

The `<SOURCE>` will tell you where the bad data came from:
- `fetchJobWatchers(jobId)` - API response for specific job
- `fetchAllWatchers` - Global watchers endpoint
- `WebSocket watcher_update` - Real-time WebSocket update
- `WebSocket watcher_state_change` - State change event

### Step 3: Check the Data
The log will show you the actual watcher object and which fields are missing:
```javascript
{
  watcher: {
    id: 123,
    job_id: "456",
    state: undefined  // <-- Problem!
  },
  hasId: true,
  hasState: false,    // <-- This confirms it
  hasJobId: true
}
```

### Step 4: Investigate Backend
If data is coming from API/WebSocket, check backend logs:

```bash
# Check backend logs for the specific job ID
grep "job_id.*456" ~/.config/ssync/logs/app.log

# Or check real-time logs
tail -f ~/.config/ssync/logs/app.log | grep -i watcher
```

### Step 5: Check WebSocket Messages
If the issue is from WebSocket updates:

1. In DevTools, go to Network tab
2. Filter by WS (WebSocket)
3. Click on the WebSocket connection
4. Check Messages tab
5. Look for malformed messages

## Common Scenarios

### Scenario 1: Stale Data After 5+ Minutes
**Symptoms**: Error appears after leaving page open
**Cause**: WebSocket sending partial updates
**Solution**: Check WebSocket handler in backend for incomplete data

### Scenario 2: Error on Page Load
**Symptoms**: Error immediately when opening job details
**Cause**: API returning incomplete watcher data
**Solution**: Check API endpoint `/api/jobs/{job_id}/watchers`

### Scenario 3: Error After Specific Action
**Symptoms**: Error after pausing/resuming watcher
**Cause**: State update logic sending incomplete data
**Solution**: Check `pauseWatcher`/`resumeWatcher` in backend

## Debugging Commands

### Enable Verbose Logging
Edit `src/stores/watchers.ts`:
```typescript
const DEBUG_WATCHERS = true;  // Line 6
```
Then rebuild: `npm run build`

### Disable Logging (for production)
```typescript
const DEBUG_WATCHERS = false;
```

### Monitor WebSocket in Real-Time
```javascript
// Run in browser console
const originalSend = WebSocket.prototype.send;
WebSocket.prototype.send = function(...args) {
  console.log('[WS Send]', args);
  return originalSend.apply(this, args);
};
```

## Next Steps

1. **Reproduce the error** with debugging enabled
2. **Capture console logs** showing the invalid data
3. **Identify the source** (API endpoint or WebSocket event)
4. **Fix the backend** to always include required fields (id, state, job_id)
5. **Test the fix** by leaving page open for 5+ minutes

## Backend Fix Checklist

If you find the backend is sending incomplete data:

- [ ] Check watcher serialization in `src/ssync/web/app.py`
- [ ] Verify database query includes all fields
- [ ] Check WebSocket message format
- [ ] Ensure state transitions preserve all fields
- [ ] Add backend validation before sending to frontend

## File Locations

**Frontend**:
- Watcher store: `web-frontend/src/stores/watchers.ts`
- Watcher components: `web-frontend/src/components/Watchers*.svelte`
- Pages using watchers: `web-frontend/src/pages/WatchersPage.svelte`

**Backend**:
- Watcher endpoints: `src/ssync/web/app.py`
- Watcher database: `src/ssync/cache.py`
- WebSocket handlers: `src/ssync/web/app.py` (search for `@app.websocket`)
