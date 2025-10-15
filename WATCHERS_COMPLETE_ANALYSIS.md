# Watchers System - Complete Analysis

## Executive Summary

The watchers system is a **comprehensive job monitoring and automation framework** with three distinct creation methods:

1. **In-Script Definitions** - Embed watchers directly in SLURM scripts
2. **Web UI** - Visual builder with templates and live preview
3. **CLI** - Attach watchers to running jobs via command line

This multi-interface approach makes watchers accessible to all user types: researchers writing scripts, administrators managing jobs via UI, and power users scripting workflows.

---

## Part 1: In-Script Watcher Definitions (Script-as-Code)

### Overview
The most powerful feature is the ability to **embed watcher definitions directly in SLURM scripts** using special comment directives. This enables "infrastructure as code" for job monitoring.

### Syntax: Two Formats

#### 1. Inline Format (Single Line)
```bash
#WATCHER pattern="REGEX" captures=[var1,var2] condition="expr" action=ACTION_TYPE(param=value)
```

**Examples:**
```bash
# Simple error detection
#WATCHER pattern="ERROR|FAIL" action=log_event(message="Error detected")

# Capture and store metrics
#WATCHER pattern="loss: ([\d.]+)" captures=[loss] action=store_metric(name="train_loss", value="$loss")

# Conditional triggering
#WATCHER pattern="GPU (\d+)%" captures=[usage] condition="int(usage) > 90" action=cancel_job

# Multiple captures
#WATCHER pattern="Epoch (\d+)/(\d+)" captures=[current,total] action=log_event(message="Progress: $current/$total")
```

#### 2. Block Format (Multi-Line)
```bash
#WATCHER_BEGIN
# name: My Watcher Name
# pattern: "REGEX_HERE"
# interval: 30
# captures: [var1, var2]
# condition: "float(var1) > 10"
# timer_mode_enabled: true
# timer_interval_seconds: 60
# actions:
#   - log_event(message="Triggered")
#   - store_metric(name="my_metric", value="$var1")
#WATCHER_END
```

**Example:**
```bash
#WATCHER_BEGIN
# name: Training Loss Monitor
# pattern: "epoch (\d+): loss=([\d.]+), acc=([\d.]+)"
# interval: 10
# captures: [epoch, loss, accuracy]
# condition: "float(loss) < 0.5 and float(accuracy) > 0.95"
# timer_mode_enabled: true
# timer_interval_seconds: 300
# actions:
#   - store_metric(name="training_loss", value="$loss")
#   - store_metric(name="accuracy", value="$accuracy")
#   - log_event(message="Milestone: Epoch $epoch - Loss $loss, Acc $accuracy")
#   - run_command(command="cp model.pt checkpoints/model_epoch_$epoch.pt")
#WATCHER_END
```

### Parser Implementation

**Location**: `src/ssync/script_processor.py`

**Key Method**: `ScriptProcessor.extract_watchers(script_content)`

**Flow:**
```python
1. Scan script line by line
2. Detect #WATCHER_BEGIN / #WATCHER / #WATCHER_END
3. Parse watcher definition (YAML-like for blocks, key=value for inline)
4. Build WatcherDefinition objects
5. Remove watcher directives from script (clean script for execution)
6. Return (watchers_list, clean_script)
```

**Parser Features:**
- Handles both inline and block formats
- Supports quoted strings, arrays, function-like syntax
- Auto-adds default `log_event` action if none specified
- Flexible action names: `log`, `log_event`, `cancel`, `cancel_job`, etc.
- Validates minimum requirements (pattern is mandatory)

### Integration with Job Submission

**Called During:**
1. `ssync submit script.sh` - Via `manager.py:173`
2. `ssync launch script.sh source_dir` - Via `launch.py:446`

**Workflow:**
```
User submits script
    ↓
ScriptProcessor.extract_watchers(script_content)
    ↓
Returns: [WatcherDefinition, ...] + clean_script
    ↓
Job submitted with clean_script (watchers removed)
    ↓
Job ID received
    ↓
WatcherEngine.start_watchers_for_job(job_id, hostname, watchers)
    ↓
Async monitoring begins
```

**Key Insight**: Watchers are **extracted before submission** and stored separately. The actual job script has watcher directives removed, so they don't interfere with execution.

### Example: Complete SLURM Script with Watchers

```bash
#!/bin/bash
#SBATCH --job-name=ml-training
#SBATCH --time=24:00:00
#SBATCH --mem=32G
#SBATCH --gpus=1

# Watch for CUDA OOM and auto-cancel
#WATCHER pattern="(CUDA out of memory|OutOfMemoryError)" action=cancel_job

# Track training progress
#WATCHER pattern="Epoch (\d+)/(\d+)" captures=[current,total] action=store_metric(name="epoch", value="$current")

# Monitor loss and checkpoint on improvement
#WATCHER_BEGIN
# name: Loss Monitor with Checkpointing
# pattern: "Val Loss: ([\d.]+)"
# captures: [val_loss]
# condition: "float(val_loss) < 0.3"
# timer_mode_enabled: true
# timer_interval_seconds: 300
# actions:
#   - log_event(message="Good validation loss: $val_loss")
#   - run_command(command="cp best_model.pt checkpoints/best_$(date +%s).pt")
#WATCHER_END

# Load environment
module load cuda/11.8

# Run training
python train.py --epochs 100 --batch-size 32
```

---

## Part 2: Web UI Creation (Visual Builder)

### Component: WatcherCreator (`web-frontend/src/components/WatcherCreator.svelte`)

**Design Philosophy**: Progressive disclosure - simple by default, advanced options available

### Creation Flow

#### Step 1: Basic Setup
- **Name**: Auto-generated (`Watcher for Job {job_id}`), user can edit
- **Pattern**: Regex input with validation
- **Quick Templates**: Pre-built patterns for common use cases
  - Error Detection: `(error|ERROR|Error)`
  - Progress Tracking: `(\d+)% complete`
  - GPU Memory: `GPU memory: (\d+)MB`
  - Loss Tracking: `loss: ([\d\.]+)`
- **Job Output Preview**: Side-by-side view of recent job output to help write patterns

#### Step 2: Actions (Always Visible)
- Visual action builder with categories:
  - **Logging & Metrics**: log_event, store_metric
  - **Notifications**: notify_email, notify_slack
  - **Job Control**: cancel_job, resubmit, pause_watcher
  - **Custom**: run_command
- Add multiple actions
- Each action has type-specific parameter inputs
- Variable substitution hints shown: `$variable`, `$1`, `$0`, `${JOB_ID}`

#### Step 3: Advanced Options (Collapsible)
- **Capture Groups**: Auto-extracted from regex pattern
- **Condition**: Python expression for filtering
- **Output Type**: stdout / stderr / both
- **Max Triggers**: Limit trigger count (auto-disable after N triggers)
- **Timer Mode**:
  - Enable timer mode
  - Timer interval (separate from pattern matching interval)

#### Step 4: Submit
- Validation: pattern, actions, syntax
- POST to `/api/watchers`
- Success feedback + auto-close
- Triggers refresh on parent page

### Component: AttachWatchersDialog (Legacy Wizard)

Older wizard-style interface with template categories:
- **Monitoring**: GPU, CPU tracking
- **Machine Learning**: Loss tracker, epoch checkpoints
- **Error Handling**: Error detector, warning monitor
- **Custom**: Blank template

Still functional but less streamlined than WatcherCreator.

### Job Selection Flow

**Scenario 1: Single Running Job**
```
User clicks "Create Watcher"
    ↓
jobStateManager.getAllJobs() → 1 running job
    ↓
Auto-select job
    ↓
Open WatcherCreator directly
```

**Scenario 2: Multiple Running Jobs**
```
User clicks "Create Watcher"
    ↓
jobStateManager.getAllJobs() → N running jobs
    ↓
Show JobSelectionDialog
    ↓
User selects job
    ↓
Open WatcherCreator with selected job
```

### Copy & Reuse Feature

**Flow:**
```
User clicks "Copy" on existing WatcherCard
    ↓
Store watcher config: { name, pattern, captures, actions, ... }
    ↓
Also store in localStorage as backup
    ↓
Show JobSelectionDialog (pre-select original job if still running)
    ↓
User selects target job
    ↓
Open WatcherCreator with pre-filled config
    ↓
User can edit before submitting
```

**Use Cases:**
- Apply same watcher to multiple jobs
- Create variations of existing watchers
- Share watcher configs between team members (via localStorage export)

---

## Part 3: CLI Creation & Management

### Command: `ssync attach-watchers`

**Usage:**
```bash
# Simple inline watcher
ssync attach-watchers JOB_ID --host HOSTNAME --pattern "ERROR" --action CANCEL_JOB

# Complex watcher from JSON file
ssync attach-watchers JOB_ID --host HOSTNAME --watcher-file watchers.json

# With options
ssync attach-watchers JOB_ID --host HOSTNAME \
    --pattern "Loss: ([\d.]+)" \
    --action RUN_COMMAND \
    --interval 30 \
    --output-type stdout
```

**Watcher File Format** (`watchers.json`):
```json
[
  {
    "name": "Error Detector",
    "pattern": "ERROR|FATAL",
    "interval_seconds": 10,
    "output_type": "both",
    "actions": [
      {
        "type": "log_event",
        "params": { "message": "Critical error detected" }
      },
      {
        "type": "cancel_job",
        "params": { "reason": "Critical error" }
      }
    ]
  }
]
```

### CLI Watcher Management Commands

**View watchers:**
```bash
ssync watchers list [--job-id JOB_ID] [--state active|paused|completed]
```

**View events:**
```bash
ssync watchers events [--job-id JOB_ID] [--watcher-id ID] [--limit N]
```

**Statistics:**
```bash
ssync watchers stats [--json]
```

**Real-time monitoring:**
```bash
ssync watchers monitor [--job-id JOB_ID] [--interval 5]
```

**Control:**
```bash
# Pause watcher
ssync watchers pause WATCHER_ID

# Resume watcher
ssync watchers resume WATCHER_ID

# Delete watcher
ssync watchers delete WATCHER_ID
```

---

## Complete Watcher Lifecycle

### 1. Creation (3 Paths)

**Path A: In-Script**
```bash
User writes script with #WATCHER directives
    ↓
ssync submit script.sh
    ↓
ScriptProcessor.extract_watchers()
    ↓
Watchers stored in DB during submission
    ↓
Clean script submitted to SLURM
    ↓
WatcherEngine.start_watchers_for_job()
```

**Path B: Web UI**
```
User clicks "Create" on WatchersPage
    ↓
JobSelectionDialog (if multiple jobs)
    ↓
WatcherCreator opens
    ↓
User configures watcher
    ↓
POST /api/watchers
    ↓
Stored in job_watchers table
    ↓
WatcherEngine picks up new watcher
    ↓
Async monitoring starts
```

**Path C: CLI**
```
User runs: ssync attach-watchers JOB_ID --host HOST --pattern "..."
    ↓
CLI builds watcher JSON
    ↓
POST /api/jobs/{job_id}/watchers
    ↓
Stored in DB
    ↓
Engine starts monitoring
```

### 2. Monitoring Loop

```python
while not shutdown:
    # Get fresh state
    watcher = db.get_watcher(watcher_id)

    if watcher.state != ACTIVE:
        break

    # Check job still running
    job = get_job_info(job_id)
    if not job or job.state in [COMPLETED, FAILED, CANCELLED]:
        update_watcher_state(watcher_id, COMPLETED)
        break

    if watcher.timer_mode_active:
        # Timer mode: periodic execution with cached variables
        variables = db.get_watcher_variables(watcher_id)
        for action in watcher.actions:
            if evaluate_condition(action.condition, variables):
                execute_action(action, variables)
        increment_trigger_count()
        check_max_triggers()
        sleep(timer_interval_seconds)
    else:
        # Pattern matching mode
        new_output = get_new_output(job, last_position)

        if new_output:
            matches = regex.finditer(pattern, new_output)

            for match in matches:
                # Extract captures
                captured_vars = extract_captures(match, capture_names)

                # Store variables
                db.update_watcher_variables(watcher_id, captured_vars)

                # Check condition
                if evaluate_condition(condition, captured_vars):
                    # Execute actions
                    for action in watcher.actions:
                        execute_action(action, captured_vars)

                    increment_trigger_count()

                    # Switch to timer mode if enabled
                    if timer_mode_enabled:
                        watcher.timer_mode_active = True
                        db.update_watcher_timer_mode(watcher_id, True)

                    check_max_triggers()

        # Update position
        update_last_position(new_position)

        # Sleep with backoff
        sleep(interval_seconds * backoff_factor)
```

### 3. Action Execution

```python
def execute_action(action, variables):
    # Variable substitution
    params = substitute_variables(action.params, variables)

    # Execute based on type
    match action.type:
        case CANCEL_JOB:
            conn.run(f"scancel {job_id}")
            engine.stop_watchers_for_job(job_id)

        case RESUBMIT:
            cancel_job(job_id)
            modify_script(params['modifications'])
            new_job_id = submit_job(modified_script)

        case NOTIFY_EMAIL:
            conn.run(f'echo "{message}" | mail -s "{subject}" {recipient}')

        case RUN_COMMAND:
            if command_allowed(params['command']):
                conn.run(params['command'], timeout=120)

        case STORE_METRIC:
            db.store_variable(watcher_id, metric_name, metric_value)

        case LOG_EVENT:
            logger.info(params['message'])

    # Log event
    db.log_watcher_event(watcher_id, matched_text, captured_vars, action_type, result, success)
```

### 4. State Transitions

```
ACTIVE → PAUSED (user action)
PAUSED → ACTIVE (user action)
ACTIVE → TRIGGERED (max_triggers reached)
ACTIVE → DISABLED (too many failures)
ACTIVE → COMPLETED (job finished)
TRIGGERED → (terminal state)
DISABLED → (terminal state)
COMPLETED → (terminal state)
```

### 5. Cleanup

**Automatic:**
- `cleanup_orphaned_watchers()` runs periodically
- Checks if job still exists for each active watcher
- Stops monitoring for completed/failed jobs
- Marks watcher as COMPLETED

**Manual:**
- User can delete watcher via UI or CLI
- Engine cancels async task immediately
- Database record deleted
- Associated events/variables remain for history

---

## Advanced Features Deep Dive

### 1. Timer Mode: Two-Phase Execution

**Problem**: Some workflows need:
- Phase 1: Wait for initial condition (e.g., "training started")
- Phase 2: Periodic execution (e.g., save checkpoint every 5 minutes)

**Solution**: Timer mode switches behavior after first match

**Example:**
```bash
#WATCHER_BEGIN
# name: Periodic Checkpoint Saver
# pattern: "Training started"
# timer_mode_enabled: true
# timer_interval_seconds: 300  # 5 minutes
# actions:
#   - run_command(command="python save_checkpoint.py")
#WATCHER_END
```

**Behavior:**
```
Job Output: "Initializing model..."
Watcher: [Pattern Matching Mode] → No match, keep polling

Job Output: "Training started"
Watcher: [Pattern Matching Mode] → MATCH! Execute actions once
Watcher: Switch to Timer Mode

[5 minutes pass]
Watcher: [Timer Mode] → Execute actions (no new output needed)

[5 minutes pass]
Watcher: [Timer Mode] → Execute actions again

... continues until job ends or max_triggers reached
```

**Key Implementation Details:**
- Variables captured during initial match are **cached in DB**
- Timer mode re-uses these cached variables for all subsequent executions
- No new output parsing required in timer mode
- More efficient for periodic actions
- Can still check per-action conditions against cached variables

### 2. Capture Groups & Variable Substitution

**Regex Captures:**
```python
pattern = r"epoch (\d+): loss=([\d.]+), acc=([\d.]+)"
captures = ["epoch", "loss", "accuracy"]

# Match: "epoch 5: loss=0.234, acc=0.876"
# Results in:
variables = {
    "epoch": "5",
    "loss": "0.234",
    "accuracy": "0.876"
}
```

**Substitution Syntax:**
```bash
# Named variables
"Epoch $epoch had loss $loss"  → "Epoch 5 had loss 0.234"

# Positional (by capture order)
"$1 / $2 / $3"  → "5 / 0.234 / 0.876"

# Full match
"Matched: $0"  → "Matched: epoch 5: loss=0.234, acc=0.876"

# Built-in variables
"Job ${JOB_ID} on ${HOSTNAME}"  → "Job 12345 on cluster1"

# In conditions
"float(loss) < 0.5"  → Uses variables["loss"]
```

**Implementation:**
```python
def substitute_variables(params, variables, job_id, hostname):
    all_vars = {
        "JOB_ID": job_id,
        "HOSTNAME": hostname,
        **variables
    }

    for key, value in params.items():
        if isinstance(value, str):
            # Handle $0 (full match)
            if "$0" in value and "_matched_text" in variables:
                value = value.replace("$0", variables["_matched_text"])

            # Handle $1, $2, etc.
            for i, capture_name in enumerate(sorted(variables.keys())):
                value = value.replace(f"${i+1}", variables[capture_name])

            # Handle named variables
            for var_name, var_value in all_vars.items():
                value = value.replace(f"${var_name}", str(var_value))
                value = value.replace(f"${{{var_name}}}", str(var_value))

        params[key] = value

    return params
```

### 3. Condition Evaluation

**Sandboxed Python Expressions:**
```python
def evaluate_condition(condition: str, variables: Dict[str, Any]) -> bool:
    # Create safe evaluation context
    safe_context = {
        "float": float,
        "int": int,
        "str": str,
        "len": len,
        "abs": abs,
        "min": min,
        "max": max,
        **variables  # User's captured variables
    }

    # Evaluate with restricted builtins
    result = eval(condition, {"__builtins__": {}}, safe_context)
    return bool(result)
```

**Security:**
- No access to `__import__`, `exec`, `compile`, etc.
- Only safe built-in functions available
- Cannot access filesystem or network
- Cannot modify variables (read-only context)

**Examples:**
```python
# Numeric comparisons
"float(loss) < 0.5"
"int(epoch) >= 100"
"float(gpu_memory) / float(gpu_total) > 0.9"

# Boolean logic
"float(loss) < 0.5 and float(accuracy) > 0.95"
"int(error_count) > 0 or int(warning_count) > 10"

# String operations
"len(message) > 100"
"'FATAL' in error_level"

# Math operations
"abs(float(loss) - float(target_loss)) < 0.01"
"min(float(val1), float(val2)) > 10"
```

### 4. Rate Limiting & Backoff

**Rate Limiting (Per Watcher):**
```python
rate_limit_window = 60  # 1 minute
max_actions_per_window = 10

if action_count_in_window >= max_actions_per_window:
    logger.warning("Rate limit reached, skipping actions")
    continue

# Execute action
action_count_in_window += 1
```

**Adaptive Backoff:**
```python
backoff_factor = 1.0  # Initial

# No matches found
if not matches_found:
    backoff_factor = min(backoff_factor * 1.1, 5.0)  # Slowly increase

# Match found
else:
    backoff_factor = 1.0  # Reset to normal

sleep_time = interval_seconds * backoff_factor
```

**Benefits:**
- Reduces CPU/network usage when no activity
- Prevents runaway execution
- Automatically tunes to job output frequency

### 5. File Position Tracking

**Implementation:**
```python
# Get file size
file_size = int(conn.run(f"stat -c %s '{output_file}'").stdout.strip())

# Handle file rotation/truncation
if file_size < last_position:
    logger.warning("File truncated, resetting position")
    last_position = 0

# Read only new content (like tail -f)
max_read_size = 1024 * 1024  # 1MB per read
new_content = conn.run(
    f"tail -c +{last_position + 1} '{output_file}' | head -c {max_read_size}"
).stdout

# Update position
new_position = last_position + len(new_content.encode())
db.update_watcher_position(watcher_id, new_position)
```

**Advantages:**
- Extremely efficient - only reads new bytes
- Handles log rotation gracefully
- Prevents re-processing same output
- Limits memory usage (max 1MB per iteration)

---

## Real-World Use Case Examples

### Use Case 1: Adaptive Resource Management

**Scenario**: Training job needs more memory if OOM occurs

```bash
#WATCHER_BEGIN
# name: OOM Handler
# pattern: "(CUDA out of memory|OutOfMemoryError)"
# actions:
#   - log_event(message="OOM detected, resubmitting with more memory")
#   - cancel_job(reason="Out of memory")
#   - resubmit(modifications={"mem": "64G"})
#WATCHER_END
```

### Use Case 2: Early Stopping

**Scenario**: Stop training if loss diverges

```bash
#WATCHER pattern="loss: ([\d.]+)" captures=[loss] condition="float(loss) > 10.0" action=cancel_job
```

### Use Case 3: Milestone Checkpointing

**Scenario**: Save checkpoint when accuracy milestones are reached

```bash
#WATCHER_BEGIN
# name: Milestone Checkpointer
# pattern: "Val Accuracy: ([\d.]+)%"
# captures: [accuracy]
# condition: "float(accuracy) >= 95.0"
# actions:
#   - run_command(command="cp model.pt checkpoints/model_95pct_$(date +%s).pt")
#   - notify_email(subject="Milestone Reached", message="95% accuracy achieved!")
#   - pause_watcher
#WATCHER_END
```

### Use Case 4: Multi-Stage Pipeline

**Scenario**: Automatically start next pipeline stage when current completes

```bash
#WATCHER_BEGIN
# name: Pipeline Stage 1 → 2 Trigger
# pattern: "Stage 1 completed successfully"
# actions:
#   - log_event(message="Stage 1 done, launching stage 2")
#   - run_command(command="sbatch stage2_script.sh")
#   - pause_watcher
#WATCHER_END
```

### Use Case 5: Collaborative Training

**Scenario**: Notify team on Slack when training starts, progresses, and completes

```bash
# Training started
#WATCHER pattern="Training started" action=notify_slack(message="Training job ${JOB_ID} started on ${HOSTNAME}")

# Progress updates every 10 epochs
#WATCHER pattern="Epoch (\d+):" captures=[epoch] condition="int(epoch) % 10 == 0" action=notify_slack(message="Training progress: epoch $epoch")

# Training completed
#WATCHER pattern="Training completed" action=notify_slack(message="Training finished! Final model saved.")
```

### Use Case 6: Resource Monitoring Dashboard

**Scenario**: Collect metrics for external monitoring system

```bash
#WATCHER_BEGIN
# name: GPU Metrics Collector
# pattern: "GPU (\d+): Memory (\\d+)/(\\d+)MB, Util (\\d+)%"
# captures: [gpu_id, mem_used, mem_total, utilization]
# interval: 30
# timer_mode_enabled: true
# actions:
#   - store_metric(name="gpu_${gpu_id}_memory_mb", value="$mem_used")
#   - store_metric(name="gpu_${gpu_id}_utilization", value="$utilization")
#   - run_command(command="curl -X POST http://metrics-server/api/metrics -d '{\"gpu\": $gpu_id, \"memory\": $mem_used, \"util\": $utilization}'")
#WATCHER_END
```

---

## Comparison of Creation Methods

| Feature | In-Script | Web UI | CLI |
|---------|-----------|--------|-----|
| **Ease of Use** | Medium (requires syntax knowledge) | Easy (visual builder) | Medium (command-line) |
| **Reproducibility** | ★★★★★ (version controlled with script) | ★★★☆☆ (manual recreation) | ★★★★☆ (scriptable with JSON files) |
| **Flexibility** | ★★★★★ (full feature set) | ★★★★☆ (most features) | ★★★★☆ (full features via JSON) |
| **Learning Curve** | Steep (regex + syntax) | Gentle (templates + help) | Medium (CLI familiarity) |
| **Collaboration** | ★★★★★ (shared with script) | ★★☆☆☆ (requires manual copying) | ★★★★☆ (JSON files shareable) |
| **Iteration Speed** | Slow (edit script, resubmit) | Fast (live preview, instant feedback) | Medium (script edits, API calls) |
| **Best For** | Production workflows, reproducible research | Ad-hoc monitoring, exploration | Automation, batch operations |

---

## Best Practices

### 1. Start Simple, Then Enhance
```bash
# Start with basic error detection
#WATCHER pattern="ERROR" action=log_event

# Add capture once working
#WATCHER pattern="ERROR: (.+)" captures=[error_msg] action=log_event(message="$error_msg")

# Add condition for specific errors
#WATCHER pattern="ERROR: (.+)" captures=[error_msg] condition="'CUDA' in error_msg" action=cancel_job
```

### 2. Use Timer Mode for Periodic Actions
```bash
# BAD: This will re-parse output every 5 minutes even if no new output
#WATCHER pattern="Training started" interval=300 action=run_command(command="python checkpoint.py")

# GOOD: Switch to timer mode after first match
#WATCHER pattern="Training started" timer_mode_enabled=true timer_interval_seconds=300 action=run_command(command="python checkpoint.py")
```

### 3. Set Max Triggers for One-Time Events
```bash
# Prevent repeated notifications for same milestone
#WATCHER pattern="Accuracy: ([\d.]+)%" captures=[acc] condition="float(acc) >= 95" max_triggers=1 action=notify_email
```

### 4. Test Patterns Before Deployment
```python
# Use test_watcher_parsing.py to validate syntax
pattern = r"loss: ([\d.]+)"
test_text = "epoch 5: loss: 0.234"
# Verify it matches correctly before adding to script
```

### 5. Use Descriptive Names
```bash
# BAD
#WATCHER name="watcher1" pattern="ERROR" action=log

# GOOD
#WATCHER name="Critical Error Detector - Auto Cancel" pattern="FATAL|CRITICAL ERROR" action=cancel_job
```

### 6. Combine Multiple Actions Strategically
```bash
#WATCHER_BEGIN
# name: Comprehensive Error Handler
# pattern: "(ERROR|FATAL): (.+)"
# captures: [level, message]
# actions:
#   - log_event(message="$level: $message")  # Always log
#   - store_metric(name="error_count", value="1")  # Track count
#   - notify_email(subject="Error in Job ${JOB_ID}", message="$level: $message")  # Alert team
#   - cancel_job(reason="$level error detected")  # Stop job
#WATCHER_END
```

### 7. Use Conditions to Reduce Noise
```bash
# BAD: Logs every single loss value
#WATCHER pattern="loss: ([\d.]+)" captures=[loss] action=store_metric(name="loss", value="$loss")

# GOOD: Only store when loss is significant
#WATCHER pattern="loss: ([\d.]+)" captures=[loss] condition="float(loss) < 0.5" action=store_metric(name="good_loss", value="$loss")
```

---

## Troubleshooting

### Pattern Not Matching

**Check:**
1. Verify pattern syntax with regex tester
2. Ensure output_type matches where content appears (stdout vs stderr)
3. Check if output is buffered (add `flush=True` in Python)
4. View job output manually to confirm pattern exists

**Debug:**
```bash
# Enable verbose logging
export SSYNC_LOG_LEVEL=DEBUG

# Test pattern manually
ssync watchers trigger WATCHER_ID
```

### Actions Not Executing

**Check:**
1. Review watcher events table for error messages
2. Verify action parameters are valid
3. For run_command: ensure command is whitelisted
4. Check rate limiting (10 actions/min limit)

**Debug:**
```bash
# View recent events
ssync watchers events --watcher-id WATCHER_ID --limit 10

# Check watcher state
ssync watchers list --job-id JOB_ID
```

### High CPU Usage

**Solutions:**
1. Increase interval_seconds (default 30, try 60+)
2. Reduce number of active watchers
3. Simplify regex patterns (avoid catastrophic backtracking)
4. Set max_triggers to auto-disable
5. Use timer mode for periodic actions (more efficient)

### Orphaned Watchers

**Prevention:**
- Set max_triggers for one-time events
- Engine auto-cleans up completed jobs

**Manual Cleanup:**
```bash
# List all watchers
ssync watchers list --state all

# Delete specific watcher
ssync watchers delete WATCHER_ID
```

---

## Future Enhancement Ideas

1. **Watcher Templates Library**
   - User-contributed templates
   - Tags and search
   - Import/export as YAML

2. **Visual Pattern Builder**
   - Drag-and-drop regex components
   - Live testing against job output
   - Auto-generate capture groups

3. **Metric Visualization**
   - Built-in charts for stored metrics
   - Time-series analysis
   - Export to Prometheus/Grafana

4. **Watcher Composition**
   - Combine multiple watchers with AND/OR logic
   - Watcher groups (start/stop together)
   - Parent-child relationships

5. **Advanced Actions**
   - Custom action plugins (user Python code)
   - Action sequences with dependencies
   - Conditional action execution

6. **Multi-Job Watchers**
   - Watch multiple jobs with same watcher
   - Aggregate metrics across jobs
   - Notify when N jobs complete

7. **Dry Run Mode**
   - Test watcher without executing actions
   - Preview what would happen
   - Debugging tool

---

## Conclusion

The watchers system is a **mature, production-ready feature** with three complementary interfaces:

1. **In-Script Definitions** → Best for reproducibility, version control, production workflows
2. **Web UI** → Best for exploration, ad-hoc monitoring, visual learners
3. **CLI** → Best for automation, batch operations, power users

The architecture is well-designed with:
- Clean separation of concerns (parser, engine, actions)
- Efficient monitoring (incremental reading, backoff, rate limiting)
- Flexible execution (pattern matching + timer mode)
- Robust safety (sandboxed conditions, command whitelist, input validation)
- Complete observability (events, metrics, real-time updates)

**Recommendation**: Use in-script definitions as the primary method for production workflows, with Web UI for testing and CLI for operational tasks. This provides the best balance of reproducibility, usability, and automation.
