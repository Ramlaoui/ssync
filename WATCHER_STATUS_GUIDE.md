# How to Check Watcher Status

## 🔍 Available Tools

### 1. **Command Line Tool** (`check_watchers.py`)

Quick status checks and queries:

```bash
# Show all active watchers
./check_watchers.py

# Show watchers for a specific job
./check_watchers.py --job-id 12345

# Show watcher events
./check_watchers.py --events

# Show statistics
./check_watchers.py --stats

# Filter events by job
./check_watchers.py --events --job-id 12345

# Get JSON output (for scripting)
./check_watchers.py --json
```

### 2. **Real-time Monitor** (`monitor_watchers.py`)

Live dashboard with auto-refresh:

```bash
# Start real-time monitor (updates every 2 seconds)
./monitor_watchers.py

# Monitor specific job
./monitor_watchers.py --job-id 12345

# Show once and exit
./monitor_watchers.py --once

# Custom refresh interval
./monitor_watchers.py --interval 5
```

### 3. **Web API Endpoints**

RESTful API for integration:

```bash
# Get watchers for a job
curl -X GET "http://localhost:8042/api/jobs/{job_id}/watchers"

# Get recent watcher events
curl -X GET "http://localhost:8042/api/watchers/events?limit=50"

# Get watcher statistics
curl -X GET "http://localhost:8042/api/watchers/stats"

# Pause a watcher
curl -X POST "http://localhost:8042/api/watchers/{watcher_id}/pause"

# Resume a watcher
curl -X POST "http://localhost:8042/api/watchers/{watcher_id}/resume"
```

### 4. **Direct Database Queries**

For advanced queries:

```python
from src.ssync.cache import get_cache

cache = get_cache()
with cache._get_connection() as conn:
    # Get all active watchers
    cursor = conn.execute("""
        SELECT * FROM job_watchers 
        WHERE state = 'active'
        ORDER BY created_at DESC
    """)
    for row in cursor:
        print(f"Watcher {row['id']}: {row['pattern']}")
    
    # Get recent events
    cursor = conn.execute("""
        SELECT * FROM watcher_events 
        ORDER BY timestamp DESC 
        LIMIT 10
    """)
    for row in cursor:
        print(f"Event: {row['action_type']} - {row['matched_text']}")
```

## 📊 Understanding Watcher States

- **`active`** - Currently monitoring job output
- **`paused`** - Temporarily stopped, can be resumed
- **`triggered`** - Hit max triggers limit
- **`disabled`** - Stopped due to errors
- **`completed`** - Job finished, watcher stopped

## 🎯 Common Use Cases

### Check if watchers are running for a job:
```bash
./check_watchers.py --job-id 12345
```

### See what patterns triggered:
```bash
./check_watchers.py --events --job-id 12345
```

### Monitor in real-time during job execution:
```bash
./monitor_watchers.py --job-id 12345
```

### Get overall system health:
```bash
./check_watchers.py --stats
```

## 📈 Example Output

### Watcher Status:
```
ACTIVE WATCHERS
ID | Job ID  | Name | Pattern         | State  | Triggers | Last Check
72 | job_123 | W72  | ERROR|FAIL      | active | 2        | 5m ago
73 | job_456 | loss | Loss: ([\d.]+)  | active | 10       | 1m ago
```

### Events:
```
WATCHER EVENTS
Time | Job ID  | Action     | Success | Matched
5m   | job_123 | log_event  | ✓       | ERROR: Memory allocation
10m  | job_456 | cancel_job | ✓       | Loss: 15.3
```

### Statistics:
```
Total Watchers: 5
Total Events: 127
Events in Last Hour: 15

Watchers by State:
  active: 3
  completed: 2

Events by Action:
  log_event: 89 (85 success, 4 failed)
  store_metric: 25 (25 success, 0 failed)
  cancel_job: 2 (2 success, 0 failed)
```

## 🔧 Troubleshooting

### No watchers showing up?
- Check if job has watchers defined: Look for `#WATCHER` in script
- Verify job was submitted with watchers enabled
- Check if watchers were parsed: `python test_watcher_parsing.py <script>`

### Watchers not triggering?
- Check pattern syntax with regex tester
- Verify output file paths are correct
- Check watcher state (might be paused/disabled)
- Look at last_position to see if output is being read

### Events not executing?
- Check action syntax in watcher definition
- Verify required environment variables (SSYNC_EMAIL, etc.)
- Check event success status in database
- Look at action_result for error messages

## 💡 Tips

1. Use `--json` output for scripting and automation
2. Monitor multiple jobs by omitting `--job-id` filter
3. Set up alerts based on watcher statistics
4. Use the API for integration with other tools
5. Check `last_position` to verify output reading progress

## 🚀 Quick Start Examples

```bash
# Submit a job with watchers
ssync submit my_script.sh --host cluster1

# Check if watchers started
./check_watchers.py --job-id <job_id>

# Monitor in real-time
./monitor_watchers.py --job-id <job_id>

# Check what triggered
./check_watchers.py --events --job-id <job_id>
```

The watcher status tools provide complete visibility into your job monitoring system!