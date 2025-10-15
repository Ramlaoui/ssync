# Watchers Quick Start Guide

## ✅ Feature Status: WORKING

The watchers feature has been successfully implemented and tested. Here's how to use it:

## Quick Examples

### 1. Simple Error Detection
```bash
#!/bin/bash
#SBATCH --job-name=my-job

#WATCHER pattern="ERROR|FAIL" action=log_event(message="Error detected")

# Your job code here
```

### 2. Monitor Training Metrics
```bash
#WATCHER pattern="loss: ([\d.]+)" captures=[loss] condition="float(loss) > 5" action=cancel_job

# This will cancel the job if loss exceeds 5
```

### 3. Handle OOM Errors
```bash
#WATCHER pattern="out of memory|OOM" action=resubmit(modifications={"mem": "32G"})

# Automatically resubmit with more memory on OOM
```

### 4. Progress Tracking
```bash
#WATCHER pattern="Step (\d+)/(\d+)" captures=[current,total] action=store_metric(name="progress", value="${current}")
```

## How to Test

1. **Test Parsing (No SLURM needed)**
```bash
.venv/bin/python test_watcher_parsing.py
```

2. **Test Demo (No SLURM needed)**
```bash
.venv/bin/python test_watcher_demo.py
```

3. **Submit Test Jobs (Requires SLURM)**
```bash
# Basic test
ssync submit test_watchers_basic.sh --host <your-host>

# ML simulation
ssync submit test_watchers_ml.sh --host <your-host>

# Comprehensive test
ssync submit test_watchers_comprehensive.sh --host <your-host>
```

## What's Working

✅ **Pattern Matching**: Regular expressions work correctly
✅ **Variable Capture**: Extract values from patterns using capture groups
✅ **Conditions**: Python expressions for conditional triggering
✅ **Actions**: All basic actions implemented:
  - `cancel_job`: Cancel the running job
  - `resubmit`: Resubmit with modified parameters
  - `log_event`: Log events to system log
  - `store_metric`: Store metrics in database
  - `notify_email`: Send email notifications (if configured)
  - `run_command`: Execute safe shell commands

✅ **Database Storage**: Watchers, events, and variables stored in SQLite
✅ **Async Execution**: Watchers run asynchronously without blocking
✅ **Integration**: Works with job submission via `submit` and `launch`

## Architecture

```
Script with #WATCHER directives
    ↓
ScriptProcessor.extract_watchers()
    ↓
WatcherEngine.start_watchers_for_job()
    ↓
Async monitoring tasks (one per watcher)
    ↓
Pattern matching + condition evaluation
    ↓
ActionExecutor.execute() when triggered
    ↓
Events logged to database
```

## Database Tables

- `job_watchers`: Watcher definitions and state
- `watcher_events`: Triggered events and results
- `watcher_variables`: Captured variables storage

## Monitoring Watcher Activity

Check the database for watcher events:

```python
from src.ssync.cache import get_cache

cache = get_cache()
with cache._get_connection() as conn:
    cursor = conn.execute("""
        SELECT job_id, action_type, matched_text, success, timestamp
        FROM watcher_events
        ORDER BY timestamp DESC
        LIMIT 10
    """)
    for row in cursor:
        print(f"{row['timestamp']}: Job {row['job_id']} - {row['action_type']}")
```

## Current Limitations

1. **Email/Slack**: Notifications log locally but need external configuration for actual delivery
2. **Command Execution**: Limited to safe commands (echo, logger, date, ls, cat) for security
3. **Resubmit**: Works but requires original script to be cached

## Next Steps for Production

1. Configure email settings:
   ```bash
   export SSYNC_EMAIL="your-email@example.com"
   ```

2. Configure Slack webhook:
   ```bash
   export SSYNC_SLACK_WEBHOOK="https://hooks.slack.com/..."
   ```

3. Add more watcher templates in config.yaml (future enhancement)

## Test Results Summary

✅ Pattern parsing: Working
✅ Variable capture: Working  
✅ Condition evaluation: Working
✅ Action execution: Working
✅ Database storage: Working
✅ Async monitoring: Working
✅ Job integration: Working

The watchers feature is ready for use!