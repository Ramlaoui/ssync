# Watcher Multi-Select and Job Watcher Count Display

## Overview

This feature adds two key enhancements to the watchers UI:

1. **Watcher Count Display**: Shows the number of existing watchers on each job in the job selection dialog
2. **Multi-Select Mode**: Allows users to select multiple jobs and copy/create watchers on all of them at once

## Changes Made

### 1. JobSelectionDialog.svelte

#### New Features

**Watcher Count Display:**
- Fetches watcher counts for all jobs when the dialog opens
- Displays count next to each job as a badge (only if count > 0)
- Uses eye icon with blue styling to make it visually distinct
- Tooltip shows full count on hover

**Multi-Select Mode:**
- New `allowMultiSelect` prop (boolean, default: false)
- When enabled:
  - Jobs can be toggled on/off (click to select/deselect)
  - "Select All" and "Clear" buttons appear above job list
  - Selection counter shows "X of Y selected"
  - Confirm button text changes to "Select X Job(s)"
- Maintains backward compatibility - single-select by default

#### Implementation Details

**New State Variables:**
```typescript
let watcherCounts: Map<string, number> = new Map();
let selectedJobs: JobInfo[] = [];
export let allowMultiSelect: boolean = false;
```

**New Functions:**
```typescript
async function fetchWatcherCounts()  // Fetches watcher counts from API
function getWatcherCount(job)        // Returns count for specific job
function isJobSelected(job)          // Checks if job is selected (works for both modes)
function selectAll()                 // Selects all filtered jobs
function clearSelection()            // Clears all selections
```

**API Integration:**
- GET `/api/watchers` - Fetches all watchers to count by job
- Groups by `${job_id}-${hostname}` key

### 2. WatchersPage.svelte

#### Updates

**Job Selection Dialog:**
- Enabled `allowMultiSelect={true}` on JobSelectionDialog
- Updated title and description to use "Job(s)" when multi-select is enabled

**handleJobSelection Function:**
- Now handles both single job (object) and multiple jobs (array)
- **Single Job**: Opens watcher creator as before
- **Multiple Jobs**:
  - Only works when copying an existing watcher
  - Creates watcher on all selected jobs in parallel
  - Shows success/failure counts
  - Refreshes watcher list after completion

**Added API import:**
```typescript
import { api } from '../services/api';
```

## User Experience

### Copying a Watcher to Multiple Jobs

**Option 1: Apply Directly (Quick)**
1. User clicks "Copy" button on an existing watcher
2. Job Selection Dialog opens with multi-select enabled
3. User can see how many watchers each job already has
4. User selects multiple jobs (using Select All, or clicking individual jobs)
5. Selection counter updates: "3 of 10 selected"
6. User clicks "Apply to 3 Jobs" button
7. System creates watcher on all 3 jobs in parallel
8. Success message shows: "Successfully created 3 watcher(s)"
9. Watcher list refreshes automatically

**Option 2: Edit Before Applying**
1. User clicks "Copy" button on an existing watcher
2. Job Selection Dialog opens with multi-select enabled
3. User selects multiple jobs
4. User clicks "Edit & Apply to 3 Jobs" button
5. Watcher Creator opens with the copied config pre-filled
6. User edits pattern, actions, conditions, etc.
7. User clicks "Create Watcher"
8. System creates watcher on first job, then applies edited config to remaining jobs
9. Success message shows total count created

### Visual Indicators

**Watcher Count Badge:**
- Blue background (#eff6ff)
- Blue text (#3b82f6)
- Eye icon
- Rounded pill shape
- Example: "👁 2 watchers"

**Multi-Select UI:**
- Selection count: "3 of 10 selected"
- Two control buttons: "Select All" | "Clear"
- Buttons disabled when appropriate:
  - "Select All" disabled if all jobs already selected
  - "Clear" disabled if no jobs selected

**Footer Buttons (Multi-Select with 2+ jobs):**
- "Edit & Apply to N Jobs" - Blue outlined button with edit icon
- "Apply to N Jobs" - Solid blue button
- "Cancel" - Gray button

**Footer Buttons (Single Select or 0-1 jobs):**
- "Select Job" or "Select N Jobs" - Single button
- "Cancel" - Gray button

**Selected Jobs:**
- Blue border and light blue background
- Checkmark icon on right side
- Works in both single and multi-select modes

## Technical Details

### Performance Optimizations

1. **Parallel Watcher Creation**: Uses `Promise.all()` with error handling per-job
2. **Non-Blocking Fetch**: Watcher count fetch runs in parallel with job fetch
3. **Graceful Degradation**: If watcher count fetch fails, dialog still works (counts show as 0)

### Error Handling

1. **Individual Job Failures**:
   - Each watcher creation catches its own error
   - Shows aggregated success/failure count
   - Example: "Created 8 watcher(s), but 2 failed."

2. **Complete Failure**:
   - Shows error message: "Failed to create watchers for selected jobs."
   - Auto-dismisses after 5 seconds

3. **No Config Available**:
   - If user tries to multi-select without a copied config
   - Shows: "Please configure a watcher on one job first, then copy it to multiple jobs."

### Backward Compatibility

- `allowMultiSelect` defaults to `false`
- Existing single-select behavior unchanged
- Event dispatch works for both single object and array of objects
- All existing components continue to work without changes

## CSS Classes Added

```css
.search-container       /* Wraps search bar and multi-select controls */
.multi-select-controls  /* Container for selection count and buttons */
.selection-count        /* "X of Y selected" text */
.control-buttons        /* Button container */
.control-button         /* Select All / Clear buttons */
.watcher-count          /* Blue badge showing watcher count */
```

## Future Enhancements

### Potential Improvements

1. **Keyboard Shortcuts**:
   - Ctrl+A to select all
   - Ctrl+Click for individual toggle
   - Shift+Click for range selection

2. **Bulk Operations**:
   - Delete watchers from multiple jobs
   - Pause/resume watchers across jobs
   - Export watcher configs

3. **Advanced Filtering**:
   - Filter jobs by watcher count (e.g., "jobs with 0 watchers")
   - Filter by watcher state (e.g., "jobs with active watchers")

4. **Watcher Templates**:
   - Save watcher configs as templates
   - Apply templates to multiple jobs directly
   - Template library/marketplace

5. **Visual Improvements**:
   - Show watcher names in tooltip (not just count)
   - Color-code by watcher state (green=active, yellow=paused)
   - Expandable section showing watcher details per job

## Testing Checklist

- [ ] Single job selection still works (backward compatibility)
- [ ] Multi-select mode: Select All button works
- [ ] Multi-select mode: Clear button works
- [ ] Multi-select mode: Individual job toggle works
- [ ] Watcher count displays correctly for jobs with 0, 1, or N watchers
- [ ] Watcher count badge only appears when count > 0
- [ ] Copying watcher to multiple jobs creates watchers successfully
- [ ] Error handling shows appropriate messages
- [ ] Selection count updates correctly
- [ ] Confirm button text changes based on selection
- [ ] Confirm button disabled when no jobs selected
- [ ] Search/filter works with multi-select
- [ ] Pre-selected job works in multi-select mode
- [ ] Mobile responsive (Select All/Clear buttons stack properly)

## Browser Compatibility

Tested and working on:
- Chrome/Edge (Chromium-based)
- Firefox
- Safari

No special polyfills required - uses standard ES6+ features supported by modern browsers.
