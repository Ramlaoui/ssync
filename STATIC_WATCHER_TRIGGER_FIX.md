# Static Watcher Trigger Improvements

## Problem

Static watchers for completed jobs were not triggering properly on the first attempt. The issues were:

1. **Limited output scanning**: Only the last 100 lines were checked, missing patterns earlier in the output
2. **Cache-only approach**: If job output wasn't in cache, no fallback to fetch from SLURM
3. **Poor error messages**: Users couldn't tell if the watcher ran but found nothing, or if there was an error

## Solution

### 1. **Full Output Scanning**

**Before:**
```python
# Only last 100 lines
lines = combined_output.split("\n")
content = "\n".join(lines[-100:]) if len(lines) > 100 else combined_output
```

**After:**
```python
# Use ALL output
content = stdout_content + "\n" + stderr_content
```

Now searches through the **entire job output**, not just the tail.

### 2. **Fallback to SLURM**

**New Flow:**
```
1. Try to get output from cache (compressed format)
   ↓
2. If cache is empty, fetch directly from SLURM output files
   ↓
3. If both fail, return clear error message
```

**Implementation:**
```python
# Try cache first
if cached_job and (cached_job.stdout_compressed or cached_job.stderr_compressed):
    # Decompress and use cached output
    ...

# Fallback to SLURM if cache is empty
if not stdout_content and not stderr_content:
    job_info = manager.get_job_info(job_id, hostname)
    if job_info.stdout_path:
        conn = get_connection(hostname)
        result = conn.run(f"cat {job_info.stdout_path}")
        stdout_content = result.stdout
```

### 3. **Better Error Messages**

**Before:**
- Success: "Watcher checked but no patterns matched"
- No context on what was searched or why it failed

**After:**
- **Match found**: `"✓ Found 5 match(es) and executed actions"`
- **No match**: `"✗ No matches found (searched 1,234 lines, 45,678 chars)"`
- **No output**: `"No output available for job 12345. The job output may not be cached yet or the output files may not be accessible."`

### 4. **Respect output_type Setting**

Now correctly uses the watcher's `output_type` setting:
- `stdout` → Only searches stdout
- `stderr` → Only searches stderr
- `both` → Searches both combined

```python
output_type = watcher.definition.output_type
if output_type == 'stdout':
    content = stdout_content
elif output_type == 'stderr':
    content = stderr_content
else:  # both
    content = stdout_content + "\n" + stderr_content
```

### 5. **Enhanced Logging**

Added comprehensive logging at each step:

```python
logger.info("Using cached output - stdout: 12345 chars, stderr: 678 chars")
logger.info("Cache empty, fetching output from SLURM for job 12345")
logger.info("Fetched stdout from SLURM: 12345 chars")
logger.info("Triggering watcher with job output (1234 lines, 45678 chars)")
logger.warning("No output found (cache and SLURM both empty)")
```

Makes debugging much easier!

## Usage Examples

### Example 1: Pattern in Middle of Output

**Job output** (1000 lines):
```
Line 1: Starting job...
Line 2: Loading data...
...
Line 500: ERROR: Connection timeout  ← Pattern here
...
Line 1000: Job finished
```

**Before**: ❌ Pattern at line 500 not found (only checked last 100 lines)

**After**: ✅ Scans all 1000 lines, finds pattern at line 500

### Example 2: Uncached Job

**Scenario**: Job completed but output not yet in cache

**Before**:
- ❌ No cached output → Returns "No cached output found, using sample text"
- Pattern never matched

**After**:
- ✓ Cache empty → Fetches from SLURM output files
- ✓ Searches fetched output
- ✓ Returns `"✓ Found 3 match(es) and executed actions"`

### Example 3: Clear Feedback

**Before**:
```
User clicks play
→ "Watcher checked but no patterns matched"
→ User confused: Did it work? Was there output?
```

**After**:
```
User clicks play
→ "✗ No matches found (searched 1,234 lines, 45,678 chars)"
→ User knows: It worked, searched all output, just no matches
```

## Testing Checklist

- [x] Static watcher on completed job with pattern in first 50 lines
- [x] Static watcher on completed job with pattern in last 50 lines
- [x] Static watcher on completed job with pattern in middle (line 500+)
- [x] Static watcher on job with cached output
- [x] Static watcher on job without cached output (fetches from SLURM)
- [x] Static watcher on job with no output files
- [x] Message shows correct match count
- [x] Message shows lines/chars searched when no match
- [x] Logging provides debugging information

## API Response Format

### Success with matches:
```json
{
  "success": true,
  "message": "✓ Found 5 match(es) and executed actions",
  "matches": true,
  "match_count": 5,
  "timer_mode": false
}
```

### Success but no matches:
```json
{
  "success": true,
  "message": "✗ No matches found (searched 1,234 lines, 45,678 chars)",
  "matches": false,
  "timer_mode": false
}
```

### No output available:
```json
{
  "success": false,
  "message": "No output available for job 12345. The job output may not be cached yet or the output files may not be accessible.",
  "matches": false,
  "timer_mode": false
}
```

## Performance Considerations

**Memory**: For very large outputs (100MB+), the full scan might use significant memory. Consider adding:
- Streaming pattern matching for huge files
- Configurable max output size
- Chunked reading

**Network**: Fetching from SLURM adds SSH overhead. Cache is much faster when available.

**Current limits**: No hard limit on output size, but SSH timeouts may apply.

## Future Enhancements

1. **Partial output scanning**: Option to scan first/last N lines only for performance
2. **Line range selector**: Let user specify which lines to search (e.g., lines 100-500)
3. **Streaming search**: For very large files, search without loading entire file into memory
4. **Output preview**: Show snippet of matched lines in UI
5. **Search statistics**: Track how long pattern matching took
6. **Cached results**: Cache match results to avoid re-scanning on repeated triggers

---

Static watchers should now trigger reliably on completed jobs! 🎉
