# Job Watchers Documentation

## Overview

Watchers are a powerful feature that allows you to monitor SLURM job outputs in real-time and trigger actions based on pattern matches. This enables automated responses to job events, failures, or specific conditions.

## Features

- **Pattern Matching**: Use regular expressions to detect specific patterns in job output
- **Variable Capture**: Extract values from matched patterns for use in conditions and actions  
- **Conditional Execution**: Only trigger actions when specific conditions are met
- **Built-in Actions**: Cancel jobs, resubmit with modifications, send notifications, and more
- **Performance Optimized**: Intelligent polling with backoff, incremental output reading

## Syntax

### Inline Watchers

Simple one-line watchers for basic monitoring:

```bash
#WATCHER pattern="ERROR|FAIL" action=notify_email
#WATCHER pattern="loss: ([0-9.]+)" captures=[loss] condition="float(loss) > 5" action=cancel_job
```

### Block Watchers

More complex watchers with multiple actions:

```bash
#WATCHER_BEGIN
# name: loss_monitor
# pattern: "epoch (\d+).*loss: ([\d.]+)"
# interval: 60
# captures: [epoch, loss]
# condition: float(loss) > 5.0
# actions:
#   - cancel_job(reason="Loss too high")
#   - notify_email(subject="Training diverged")
#WATCHER_END
```

## Watcher Properties

- **name**: Optional name for the watcher
- **pattern**: Regular expression to match in job output
- **interval**: Check interval in seconds (default: 60)
- **captures**: List of variable names for captured groups
- **condition**: Python expression that must evaluate to True
- **actions**: List of actions to execute when pattern matches
- **max_triggers**: Maximum number of times to trigger (optional)
- **output_type**: Monitor "stdout", "stderr", or "both" (default: "stdout")

## Built-in Actions

### cancel_job
Cancel the current job:
```bash
action=cancel_job(reason="Job failed")
```

### resubmit
Cancel and resubmit job with modifications:
```bash
action=resubmit(modifications={"mem": "16G", "time": "120"}, cancel_original=true)
```

### notify_email  
Send email notification:
```bash
action=notify_email(to="user@example.com", subject="Alert", message="Job ${JOB_ID} triggered")
```

### notify_slack
Send Slack notification (requires webhook configuration):
```bash
action=notify_slack(channel="#alerts", message="Job failed: ${JOB_ID}")
```

### run_command
Execute a shell command (limited to safe commands):
```bash
action=run_command(command="echo 'Event triggered' | logger")
```

### store_metric
Store a metric value for later analysis:
```bash
action=store_metric(name="max_loss", value="${loss}")
```

### log_event
Log an event to the system log:
```bash
action=log_event(message="Checkpoint saved", level="INFO")
```

## Variables

### Built-in Variables
- `${JOB_ID}`: Current job ID
- `${HOSTNAME}`: Cluster hostname
- Any captured variables from pattern matches

### Variable Substitution
Variables can be used in action parameters:
```bash
action=notify_email(message="Loss is ${loss} at epoch ${epoch}")
```

## Examples

### Monitor Training Loss
```bash
#WATCHER_BEGIN
# pattern: "loss: ([\d.]+)"
# captures: [loss]
# condition: float(loss) > 10.0
# actions:
#   - cancel_job(reason="Loss diverged")
#   - resubmit(modifications={"learning-rate": "0.0001"})
#WATCHER_END
```

### Detect OOM Errors
```bash
#WATCHER pattern="out of memory|OOM" action=resubmit(modifications={"mem": "32G"})
```

### Track Progress
```bash
#WATCHER_BEGIN
# pattern: "Progress: (\d+)%"
# captures: [progress]
# condition: int(progress) % 25 == 0
# action: notify_slack(message="Job ${JOB_ID} is ${progress}% complete")
#WATCHER_END
```

### Monitor Multiple Conditions
```bash
#WATCHER pattern="WARNING" action=log_event(level="WARNING")
#WATCHER pattern="ERROR" action=notify_email
#WATCHER pattern="CRITICAL|FATAL" action=cancel_job
```

## Performance Considerations

- Watchers use intelligent polling with exponential backoff when no matches are found
- Output is read incrementally (only new lines since last check)
- Multiple watchers for the same job share SSH connections
- Watchers automatically stop when jobs complete
- Failed watchers are disabled after 5 consecutive failures

## Configuration

Set environment variables for notifications:
- `SSYNC_EMAIL`: Default email recipient
- `SSYNC_SLACK_WEBHOOK`: Slack webhook URL

## Limitations

- Maximum 10 watchers per job (configurable)
- Pattern length limited to 1000 characters
- Condition expressions must be safe Python expressions
- Some actions (like run_command) are restricted for security

## Debugging

Check watcher status and events:
```python
from ssync.cache import get_cache
cache = get_cache()

# Query watcher events in database
with cache._get_connection() as conn:
    cursor = conn.execute(
        "SELECT * FROM watcher_events WHERE job_id = ? ORDER BY timestamp DESC",
        (job_id,)
    )
    for row in cursor.fetchall():
        print(f"{row['timestamp']}: {row['action_type']} - {row['action_result']}")
```