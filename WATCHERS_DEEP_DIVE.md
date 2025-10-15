# Watchers System - Deep Dive Analysis

## Overview

The watchers system is a sophisticated real-time monitoring and automation framework for SLURM jobs. It allows users to define patterns to watch for in job output and automatically trigger actions when those patterns are matched. This creates a powerful event-driven workflow system on top of SLURM.

## Architecture

### Backend Components

#### 1. Data Models (`src/ssync/models/watcher.py`)
- **WatcherState**: Enum defining watcher lifecycle states (ACTIVE, PAUSED, TRIGGERED, DISABLED, COMPLETED)
- **ActionType**: Enum of built-in actions (CANCEL_JOB, RESUBMIT, NOTIFY_EMAIL, RUN_COMMAND, STORE_METRIC, LOG_EVENT)
- **WatcherDefinition**: Configuration for what to watch (pattern, interval, captures, condition, actions)
- **WatcherInstance**: Runtime state (job_id, hostname, last_position, trigger_count, variables, timer_mode_active)
- **WatcherEvent**: Historical record of each trigger (timestamp, matched_text, captured_vars, action_result)

#### 2. Watcher Engine (`src/ssync/watchers/engine.py`)
The core monitoring engine that runs asynchronously:

**Key Features:**
- **Asynchronous Monitoring**: Each watcher runs as an independent asyncio task
- **Two Operation Modes**:
  - **Pattern Matching Mode**: Continuously reads new job output and matches regex patterns
  - **Timer Mode**: After first match, switches to periodic execution using cached variables
- **Smart Backoff**: Adjusts polling frequency based on activity (1x to 5x interval)
- **Position Tracking**: Remembers file position to only read new content (like `tail -f`)
- **Health Monitoring**: Automatic restart of stalled watchers, cleanup of orphaned watchers
- **Rate Limiting**: Max 10 actions per minute per watcher to prevent abuse

**Core Methods:**
- `start_watchers_for_job()`: Initialize watchers when job starts
- `_monitor_watcher()`: Main monitoring loop for each watcher
- `_check_patterns()`: Regex matching with capture group extraction
- `_execute_action()`: Delegates to ActionExecutor
- `cleanup_orphaned_watchers()`: Removes watchers for completed jobs
- `check_and_restart_watchers()`: Health check and recovery

**Monitoring Flow:**
```python
while not shutdown:
    1. Get fresh watcher state from DB
    2. Check if job still exists and is active
    3. If timer_mode_active:
        - Load cached variables from DB
        - Execute all actions with those variables
        - Increment trigger count
        - Sleep for timer_interval_seconds
    4. Else (pattern matching mode):
        - Get new output since last_position
        - Match regex pattern against new content
        - Extract capture groups
        - Evaluate condition (if specified)
        - Execute actions for each match
        - If timer_mode_enabled: switch to timer mode
        - Increment trigger count
        - Sleep with backoff
    5. Handle errors with exponential backoff
```

#### 3. Action Executor (`src/ssync/watchers/actions.py`)
Executes watcher actions with variable substitution:

**Supported Actions:**
- **cancel_job**: Cancels the SLURM job via `scancel`
- **resubmit**: Cancels current job and submits modified version
- **notify_email**: Sends email via `mail` command on host
- **notify_slack**: Sends webhook notification (logged for now)
- **run_command**: Executes allowed commands on host (with security whitelist)
- **store_metric**: Stores captured values in watcher_variables table
- **log_event**: Logs message to backend logger

**Variable Substitution:**
- `$0` or `${_matched_text}`: The full matched text
- `$1`, `$2`, `$N`: Capture groups by position
- `$variable_name`: Named capture variables
- `${JOB_ID}`, `${HOSTNAME}`: Built-in variables

**Security:**
- Command whitelist for run_command action
- Path validation for file operations
- Parameter sanitization
- Async execution with timeout (120s)

#### 4. Database Schema (`src/ssync/cache.py`)

**job_watchers table:**
```sql
CREATE TABLE job_watchers (
    id INTEGER PRIMARY KEY,
    job_id TEXT NOT NULL,
    hostname TEXT NOT NULL,
    name TEXT,
    pattern TEXT NOT NULL,
    interval_seconds INTEGER DEFAULT 60,
    captures_json TEXT,              -- JSON array of capture names
    condition TEXT,                   -- Python expression for filtering
    actions_json TEXT NOT NULL,       -- JSON array of action objects
    last_check TEXT,
    last_position INTEGER DEFAULT 0,
    trigger_count INTEGER DEFAULT 0,
    state TEXT DEFAULT 'active',
    timer_mode_enabled INTEGER DEFAULT 0,
    timer_interval_seconds INTEGER DEFAULT 30,
    timer_mode_active INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
)
```

**watcher_events table:**
```sql
CREATE TABLE watcher_events (
    id INTEGER PRIMARY KEY,
    watcher_id INTEGER NOT NULL,
    job_id TEXT NOT NULL,
    hostname TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    matched_text TEXT,
    captured_vars_json TEXT,         -- JSON of captured variables
    action_type TEXT NOT NULL,
    action_result TEXT,
    success BOOLEAN NOT NULL
)
```

**watcher_variables table:**
```sql
CREATE TABLE watcher_variables (
    watcher_id INTEGER NOT NULL,
    variable_name TEXT NOT NULL,
    variable_value TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (watcher_id, variable_name)
)
```

### Frontend Components

#### 1. Main Watchers Page (`web-frontend/src/pages/WatchersPage.svelte`)

**Features:**
- **Dual Tab Interface**:
  - Watchers tab: List all watchers with search/filter
  - Events tab: View historical trigger events
- **Two View Modes**:
  - Grid view: Flat card layout
  - Grouped view: Grouped by job
- **Search & Filters**:
  - Fuzzy search across job_id, name, hostname, pattern
  - Filter by state: all/active/paused/completed
- **Real-time Updates**: WebSocket connection for live event stream
- **Actions**:
  - Create new watcher
  - Copy existing watcher to another job
  - Refresh data

**Data Flow:**
```
1. onMount:
   - Load all watchers via /api/watchers
   - Load events via /api/watchers/events
   - Connect WebSocket for real-time updates

2. User clicks "Create":
   - If 1 running job: Open WatcherCreator directly
   - If multiple: Show JobSelectionDialog first

3. User clicks "Copy" on watcher:
   - Store watcher config
   - Show JobSelectionDialog
   - Open WatcherCreator with pre-filled config

4. WebSocket message received:
   - Update watcher state changes
   - Add new events to list
   - Increment trigger counts
```

#### 2. Watcher Card (`web-frontend/src/components/WatcherCard.svelte`)

**Compact View:**
- State indicator (colored dot with animation)
- Watcher name + job link
- Trigger count, hostname, interval, last check
- Pattern preview with action count
- Action buttons (pause/resume, trigger, edit, copy)

**Expanded View:**
- Capture groups list
- Condition expression
- Full actions list with details
- Last trigger result (match text, captured vars, action result)
- View events / View job output buttons

**Interactions:**
- Click card: Expand/collapse details
- Timer indicator: Shows if watcher in timer mode
- Manual trigger: Force execute actions immediately
- Copy: Emit event to parent with watcher config

#### 3. Watcher Creator (`web-frontend/src/components/WatcherCreator.svelte`)

**Streamlined Creation Flow:**
1. **Basic Setup**:
   - Auto-generated name (can edit)
   - Pattern input with live validation
   - Quick templates (error detection, progress, GPU, loss)
   - Job output preview (side-by-side with pattern)

2. **Actions** (Progressive Disclosure):
   - Visual action builder with categories
   - Add/edit/remove actions
   - Parameter inputs based on action type
   - Variable substitution hints

3. **Advanced Options** (Collapsible):
   - Capture groups (extracted from regex)
   - Condition expression
   - Output type (stdout/stderr/both)
   - Max triggers limit
   - Timer mode configuration

4. **Submit**:
   - Validates all fields
   - Posts to `/api/watchers` endpoint
   - Shows success/error feedback
   - Closes and triggers refresh

#### 4. Attach Watchers Dialog (`web-frontend/src/components/AttachWatchersDialog.svelte`)

**Legacy interface with wizard steps:**
1. Template selection (with categories)
2. Pattern configuration
3. Actions builder
4. Review and submit

**Features:**
- Template library with categories (Monitoring, ML, Error Handling, Custom)
- Pattern tester with live matching
- Job output viewer
- Action configuration with parameter validation

### API Endpoints

#### Watcher Management

**GET /api/jobs/{job_id}/watchers** - Get watchers for a job
```typescript
Response: {
  job_id: string,
  watchers: Watcher[],
  count: number
}
```

**GET /api/watchers** - List all watchers (with pagination)
```typescript
Query: { state?: string, limit?: number }
Response: { watchers: Watcher[], count: number }
```

**POST /api/watchers** - Create new watcher
```typescript
Body: {
  job_id: string,
  hostname: string,
  name: string,
  pattern: string,
  interval_seconds?: number,
  captures?: string[],
  condition?: string,
  actions: Action[],
  timer_mode_enabled?: boolean,
  timer_interval_seconds?: number
}
```

**PUT /api/watchers/{watcher_id}** - Update watcher config

**DELETE /api/watchers/{watcher_id}** - Delete watcher

**POST /api/watchers/{watcher_id}/pause** - Pause active watcher

**POST /api/watchers/{watcher_id}/resume** - Resume paused watcher

**POST /api/watchers/{watcher_id}/trigger** - Manually trigger watcher
```typescript
Response: {
  timer_mode: boolean,
  success: boolean,
  message: string,
  matches?: number
}
```

#### Events & Statistics

**GET /api/watchers/events** - Get watcher events
```typescript
Query: { job_id?: string, watcher_id?: number, limit?: number }
Response: { events: WatcherEvent[], count: number }
```

**GET /api/watchers/stats** - Get global statistics
```typescript
Response: {
  total_watchers: number,
  watchers_by_state: Record<string, number>,
  total_events: number,
  events_by_action: Record<string, { total, success, failed }>,
  events_last_hour: number,
  top_watchers: Array<{ watcher_id, job_id, name, event_count }>
}
```

#### WebSocket Protocol

**Connection**: `ws://host/ws/watchers` or `ws://host/ws/watchers/{job_id}`

**Message Types:**
```typescript
// Watcher triggered
{
  type: 'watcher_event',
  event: WatcherEvent
}

// State changed
{
  type: 'watcher_state_change',
  watcher_id: number,
  state: string
}
```

## Key Features & Design Decisions

### 1. Timer Mode
**Problem**: Some actions should run periodically after initial condition is met, without requiring new pattern matches.

**Solution**: Two-phase operation:
- Phase 1 (Pattern Matching): Watch output until pattern matches
- Phase 2 (Timer Mode): Switch to periodic execution with cached variables

**Example Use Case**:
```yaml
# Save checkpoint every 30s after first loss is logged
pattern: "loss: ([\d.]+)"
captures: ["loss"]
timer_mode_enabled: true
timer_interval_seconds: 30
actions:
  - type: run_command
    params:
      command: "cp model.pt checkpoints/model_loss_$loss.pt"
```

### 2. Capture Groups & Variable Substitution
**Problem**: Need to extract values from output and use them in actions.

**Solution**:
- Named capture groups in pattern
- Store in watcher_variables table
- Substitute in action parameters: `$variable`, `$1`, `$0`

**Example**:
```yaml
pattern: "epoch (\d+): loss=([\d.]+), acc=([\d.]+)"
captures: ["epoch", "loss", "accuracy"]
actions:
  - type: store_metric
    params:
      name: "training_loss"
      value: "$loss"
  - type: log_event
    params:
      message: "Epoch $epoch: loss=$loss, accuracy=$accuracy"
```

### 3. Condition Filtering
**Problem**: Only trigger actions when captured values meet certain criteria.

**Solution**: Python expression evaluated with safe context:
```python
condition: "float(loss) < 0.5"  # Only trigger if loss below threshold
condition: "int(epoch) % 10 == 0"  # Only every 10th epoch
condition: "float(accuracy) > 0.95 and float(loss) < 0.1"  # Combined
```

**Safety**: Sandboxed eval with limited builtins (float, int, str, len, abs, min, max)

### 4. Progressive Disclosure UI
**Problem**: Watchers can be simple or complex - need to support both without overwhelming users.

**Solution**:
- Start with minimal required fields (name, pattern, one action)
- "Advanced Options" section for captures, conditions, timer mode
- Quick templates for common use cases
- Live job output preview to help write patterns

### 5. Copy & Reuse
**Problem**: Users often want to apply same watcher to multiple jobs.

**Solution**:
- Copy button on each watcher card
- Stores full config including actions
- Opens job selection dialog
- Pre-fills WatcherCreator with copied config
- User can edit before attaching to new job

### 6. Real-time Feedback
**Problem**: Users need to know when watchers trigger and what actions execute.

**Solution**:
- WebSocket connection for instant event notifications
- "Last Trigger" section in expanded card shows full details
- Events tab with filterable history
- Manual trigger button for testing

### 7. Orphan Cleanup
**Problem**: Watchers for completed/failed jobs waste resources.

**Solution**:
- `cleanup_orphaned_watchers()` runs periodically
- Checks if job still exists and is active
- Automatically stops and marks as COMPLETED
- Health check restarts stalled watchers

## Performance Optimizations

### Backend
1. **Compiled Regex Caching**: Store compiled patterns in `_pattern_cache`
2. **Incremental Reading**: Only read new bytes since `last_position`
3. **Adaptive Backoff**: Slow down polling when no matches (1x to 5x interval)
4. **Connection Pooling**: Reuse SSH connections via fabric
5. **Async Tasks**: Each watcher runs independently without blocking
6. **Database Indices**: Optimized queries on job_id, hostname, state, timestamp

### Frontend
1. **WebSocket Updates**: Avoid constant polling, push updates from server
2. **Virtual Scrolling**: (Not implemented yet, but recommended for large lists)
3. **Debounced Search**: Wait for user to finish typing before filtering
4. **Lazy Loading**: Only load events when Events tab is opened
5. **Component Memoization**: Derived stores prevent unnecessary re-renders

## Security Considerations

### Command Execution
**Whitelist Approach**: Only allow specific command prefixes:
- Safe: `echo`, `logger`, `date`, `ls`, `cat`, `mkdir`, `cp`, `mv`, `touch`, `grep`, `find`, `tail`, `head`, `wc`
- Python: `uv run`, `uvx`, `python`, `pip`
- Tools: `wandb`

**Validation**: Check each part of compound commands (split by `&&` and `;`)

**Execution Context**:
- Run in job's working directory when possible
- Timeout after 120 seconds
- Non-blocking async execution

### Input Sanitization
- Job IDs: Alphanumeric + underscore/hyphen only
- Hostnames: Valid hostname format
- Patterns: Max 1000 characters
- Conditions: Max 500 characters
- Action params: Max 10KB JSON

### API Authentication
- Optional API key verification
- Rate limiting: 100 req/min burst, 10 req/min sustained
- HTTPS by default

## Common Use Cases

### 1. Training Loss Monitoring
```yaml
name: "Training Loss Tracker"
pattern: "Epoch \\d+, Loss: ([\\d.]+)"
captures: ["loss"]
interval_seconds: 10
actions:
  - type: store_metric
    params:
      name: "train_loss"
      value: "$loss"
  - type: log_event
    params:
      message: "Training loss: $loss"
```

### 2. Error Auto-Cancel
```yaml
name: "CUDA OOM Error Handler"
pattern: "(CUDA out of memory|OutOfMemoryError)"
captures: ["error"]
max_triggers: 1
actions:
  - type: log_event
    params:
      message: "CUDA OOM detected: $error"
  - type: cancel_job
    params:
      reason: "CUDA out of memory"
  - type: notify_email
    params:
      subject: "Job ${JOB_ID} cancelled - CUDA OOM"
      message: "Error: $error"
```

### 3. Checkpoint Saver (Timer Mode)
```yaml
name: "Periodic Checkpoint"
pattern: "Model initialized"
timer_mode_enabled: true
timer_interval_seconds: 300  # Every 5 minutes
actions:
  - type: run_command
    params:
      command: "cp -r ./checkpoints ./backups/checkpoint_$(date +%s)"
```

### 4. GPU Memory Monitor
```yaml
name: "GPU Memory Alert"
pattern: "GPU (\\d+): (\\d+)MB / (\\d+)MB"
captures: ["gpu_id", "used", "total"]
condition: "float(used) / float(total) > 0.9"
interval_seconds: 60
actions:
  - type: log_event
    params:
      message: "GPU $gpu_id memory high: $used/$total MB"
  - type: notify_email
    params:
      subject: "High GPU memory usage"
```

### 5. Accuracy Milestone Tracker
```yaml
name: "Accuracy Milestones"
pattern: "Val Accuracy: ([\\d.]+)"
captures: ["accuracy"]
condition: "float(accuracy) >= 0.95"
max_triggers: 1
actions:
  - type: log_event
    params:
      message: "🎉 Reached 95% accuracy: $accuracy"
  - type: run_command
    params:
      command: "cp best_model.pt milestones/model_95pct.pt"
  - type: pause_watcher
```

## Future Enhancements

### Potential Features
1. **Watcher Templates Library**: User-shareable templates with tags
2. **Conditional Actions**: Per-action conditions (not just global)
3. **Action Sequences**: Execute actions in order with dependencies
4. **Custom Action Plugins**: User-defined Python action handlers
5. **Multi-Pattern Watchers**: OR/AND logic for multiple patterns
6. **Metric Visualization**: Built-in charts for stored metrics
7. **Watcher Groups**: Control multiple watchers together
8. **Export/Import**: Share watcher configs as YAML files
9. **Dry Run Mode**: Test watcher without executing actions
10. **Historical Replay**: Re-run watcher against past output

### Performance Ideas
1. **Bulk Operations**: Start/stop/delete multiple watchers at once
2. **Pattern Compiler**: Optimize regex patterns automatically
3. **Event Aggregation**: Batch similar events to reduce DB writes
4. **Sampling Mode**: Check only every Nth line for performance
5. **Distributed Engine**: Run watcher engine on compute nodes

## Troubleshooting Guide

### Watcher Not Triggering
1. Check pattern syntax with regex tester
2. Verify output_type matches where content appears (stdout vs stderr)
3. Check interval isn't too long
4. View job output to confirm pattern exists
5. Use manual trigger to test immediately

### Actions Not Executing
1. Check watcher events table for error messages
2. Verify action parameters are valid
3. For run_command: ensure command is whitelisted
4. Check rate limiting (max 10 actions/min)
5. Look for errors in backend logs

### Performance Issues
1. Reduce number of active watchers
2. Increase interval_seconds
3. Simplify regex patterns (avoid catastrophic backtracking)
4. Use condition to filter matches
5. Set max_triggers to auto-disable

### Orphaned Watchers
1. Run cleanup manually: Check `/api/watchers` for old watchers
2. Set max_triggers to auto-complete
3. Delete manually via API or DB
4. Restart watcher service to trigger cleanup

## Conclusion

The watchers system is a powerful, production-ready monitoring and automation framework that extends SLURM with event-driven capabilities. Its two-phase (pattern matching + timer mode) design, flexible action system, and real-time UI make it suitable for a wide range of use cases from simple error detection to complex ML training workflows.

The architecture balances simplicity for basic use cases with advanced features for power users, while maintaining security, performance, and reliability.
