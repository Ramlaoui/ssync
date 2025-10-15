# Array Job Support in ssync

## Overview
Array jobs are now fully supported in ssync with intelligent grouping to reduce UI clutter and improve usability. This feature works for **all array jobs** - both existing ones already in your SLURM cluster and new ones you submit.

## How It Works

### Backend
1. **Job ID Validation**: Accepts all SLURM array job formats:
   - Individual tasks: `12345_67`
   - Parent job with range: `12345_[0-99]`
   - Parent job with list: `12345_[1,3,5,7]`

2. **Dynamic Grouping**: When `group_array_jobs=true` is passed to the API:
   - Array tasks are grouped by their parent job ID
   - Summary statistics are calculated (pending/running/completed/failed counts)
   - Groups are returned alongside regular jobs

3. **No Database Changes**: Grouping happens at runtime during API calls, not stored in database

### Frontend
1. **Toggle Control**: A new button in the job sidebar header lets you enable/disable array job grouping
2. **Preference Storage**: Your choice is saved in browser localStorage
3. **Collapsible Groups**: Array jobs display as expandable cards showing:
   - Parent job ID and name
   - Task count badges by state
   - Expandable list of individual tasks

## Using the Feature

### Enable Array Job Grouping
1. Look for the grouping icon in the job sidebar header (next to search and refresh)
2. Click to toggle between grouped and ungrouped view
3. Your preference is saved automatically

### View Array Jobs
When enabled, array jobs will show as:
- **Collapsed**: Single card with summary (e.g., "12345 - my_array_job - 100 tasks")
- **Expanded**: Click to see all individual tasks with their states

### Navigation
- Click on any individual task to view its details
- Array job IDs with special characters (brackets) are properly URL-encoded

## Benefits

1. **Reduces Clutter**: 100+ array tasks show as one group instead of 100+ individual entries
2. **Better Overview**: Quick visual summary with state counters
3. **Backward Compatible**: Works with all existing array jobs
4. **User Control**: Toggle between views based on your needs
5. **Performance**: Faster UI rendering with fewer DOM elements

## Technical Details

### API Endpoint
```bash
GET /api/status?group_array_jobs=true
```

### Response Format
```json
{
  "hostname": "cluster1",
  "jobs": [...],  // Regular jobs and parent array jobs
  "array_groups": [
    {
      "array_job_id": "12345",
      "job_name": "my_simulation",
      "total_tasks": 100,
      "pending_count": 20,
      "running_count": 30,
      "completed_count": 50,
      "failed_count": 0,
      "cancelled_count": 0,
      "tasks": [...]  // Individual task details
    }
  ]
}
```

### Files Modified
- **Backend**:
  - `src/ssync/web/security.py`: Updated job ID validation regex
  - `src/ssync/web/app.py`: Added grouping logic and parameter
  - `src/ssync/web/models.py`: Added ArrayJobGroup model

- **Frontend**:
  - `web-frontend/src/stores/preferences.ts`: UI preferences store
  - `web-frontend/src/stores/jobs.ts`: Added group_array_jobs parameter
  - `web-frontend/src/components/ArrayJobCard.svelte`: Array job display component
  - `web-frontend/src/components/JobSidebar.svelte`: Added grouping toggle
  - `web-frontend/src/types/api.ts`: TypeScript types for array groups
  - Multiple files: Fixed URL encoding for array job navigation

## Limitations & Future Work

1. **Current**: Grouping happens at the API level, not in the database
2. **Future**: Could add database-level grouping for better performance
3. **Future**: Could add array job submission support
4. **Future**: Could add bulk operations on array job groups

## Testing

To test array job grouping:
1. Submit an array job: `sbatch --array=0-99 myscript.sh`
2. Enable grouping in the UI (click the grouping toggle)
3. See your 100 tasks grouped as one expandable item
4. Click to expand and see individual tasks
5. Navigate to any task to view its details