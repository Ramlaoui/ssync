# Job Selection Dialog Tabs Feature

## Overview

Added a tab interface to the JobSelectionDialog component to separate **Running** jobs from **Completed/Canceled** jobs. This makes it much clearer and easier to navigate when selecting jobs for watcher creation, especially when dealing with static watchers for completed jobs.

## Features

### **Two Tabs**

1. **Running Tab**
   - Shows jobs with state `R` (Running) or `PD` (Pending)
   - Icon: Play icon (▶)
   - Default active tab
   - Badge shows count of running/pending jobs

2. **Completed / Canceled Tab**
   - Shows all other jobs (Completed, Failed, Timeout, Canceled, etc.)
   - Icon: Slash/canceled icon
   - Badge shows count of completed/canceled jobs
   - Only visible when `includeCompletedJobs={true}`

### **Smart Behavior**

- **Only shown when needed**: Tabs only appear when `includeCompletedJobs` is enabled
- **Separate search**: Search is scoped to the active tab
- **Auto-clear search**: Search term clears when switching tabs for better UX
- **Live counts**: Badge counts update in real-time as jobs change
- **Multi-select works per tab**: Selection state persists when switching tabs

## Visual Design

### Tab Appearance

**Inactive Tab**:
- Gray text (#6b7280)
- Gray background on hover (#f9fafb)
- Gray count badge (#f3f4f6 background)

**Active Tab**:
- Blue text (#3b82f6)
- Blue bottom border (2px)
- Blue count badge (#dbeafe background with #3b82f6 text)

### Tab Structure
```
[▶ Running (12)]  [⊘ Completed / Canceled (45)]
─────────────────────────────────────────────────
```

## Implementation Details

### State Management

```typescript
let activeTab: 'running' | 'other' = 'running';

// Separate jobs into two categories
$: runningJobs = jobs.filter(job => job.state === 'R' || job.state === 'PD');
$: otherJobs = jobs.filter(job => job.state !== 'R' && job.state !== 'PD');

// Display jobs from active tab
$: displayJobs = activeTab === 'running' ? runningJobs : otherJobs;

// Filter search within active tab
$: filteredJobs = displayJobs.filter(job => { /* search logic */ });
```

### Tab Switching

```typescript
function switchTab(tab: 'running' | 'other') {
  activeTab = tab;
  searchTerm = '';  // Clear search for better UX
}
```

### Conditional Rendering

Tabs only appear when the dialog includes completed jobs:

```svelte
{#if includeCompletedJobs}
  <div class="tabs-container">
    <!-- Tab buttons -->
  </div>
{/if}
```

## User Experience

### **Creating Watcher on Running Job**

1. Click "Create Watcher"
2. Dialog opens with **Running tab active** by default
3. See only running/pending jobs (12 shown in badge)
4. Select job, configure watcher
5. Creates as normal ACTIVE watcher

### **Creating Watcher on Completed Job**

1. Click "Create Watcher"
2. Dialog opens with **Running tab active** by default
3. Click **"Completed / Canceled" tab** (45 shown in badge)
4. See only completed/failed/canceled jobs
5. Select completed job, configure watcher
6. Creates as STATIC watcher (auto-detected)

### **Searching Within Tabs**

1. On Running tab, search for "train"
2. See filtered running jobs matching "train"
3. Switch to Completed tab
4. Search auto-clears
5. See all completed jobs
6. Search again to filter completed jobs

### **Multi-Select Across Tabs**

1. On Running tab, select 3 jobs
2. Switch to Completed tab
3. Previous selections from Running tab are preserved
4. Can select additional jobs from Completed tab
5. Create watchers on all selected jobs (mix of ACTIVE and STATIC)

## Benefits

1. **Clear separation** - Easy to distinguish between active and finished jobs
2. **Reduced clutter** - Each tab shows only relevant jobs
3. **Better discovery** - Users can easily find completed jobs for static watchers
4. **Visual feedback** - Badge counts show distribution at a glance
5. **Scoped search** - Search results are more relevant within each category
6. **Flexible workflow** - Supports both active and static watcher creation

## Integration Points

### WatchersPage.svelte

```svelte
<JobSelectionDialog
  includeCompletedJobs={true}  <!-- Enables tabs -->
  allowMultiSelect={true}
  on:select={handleJobSelection}
/>
```

### Backend Auto-Detection

When a completed job is selected:
1. Frontend sends job_id to watcher creation endpoint
2. Backend checks job state via `manager.get_job_info()`
3. If job is COMPLETED/FAILED/CANCELLED → creates as `state='static'`
4. If job is RUNNING/PENDING → creates as `state='active'`

## CSS Classes

```css
.tabs-container         /* Tab bar container */
.tab-button            /* Individual tab button */
.tab-button.active     /* Active tab state */
.tab-icon              /* Icon in tab */
.tab-count             /* Badge with count */
```

## Edge Cases Handled

1. **No jobs in tab**: Shows appropriate message ("No jobs match your search criteria")
2. **Only one tab has jobs**: Still shows both tabs with accurate counts (may be 0)
3. **Switching with active search**: Search clears to avoid confusion
4. **Multi-select across tabs**: Selections persist when switching
5. **Real-time updates**: Tab counts update as jobs complete/start

## Future Enhancements

1. **Remember last tab**: Save user's tab preference in localStorage
2. **Tab badges with colors**: Red for failed, yellow for timeout, etc.
3. **State breakdown tooltip**: Hover over "Other" tab to see breakdown (5 completed, 3 failed, 2 canceled)
4. **Quick filters per tab**: Add state filters within each tab
5. **Drag & drop between tabs**: Visual way to compare jobs
6. **Custom tab groups**: Let users create custom tab categories

## Testing Checklist

- [x] Tabs only appear when includeCompletedJobs is true
- [x] Running tab shows only R/PD jobs
- [x] Other tab shows only non-running jobs
- [x] Badge counts are accurate
- [x] Active tab has blue styling
- [x] Search is scoped to active tab
- [x] Search clears when switching tabs
- [x] Multi-select works across tabs
- [x] Tab switching is smooth and responsive
- [x] Mobile responsive (tabs stack or scroll on small screens)

## Accessibility

- Semantic HTML with `<button>` elements
- Keyboard navigation supported (Tab key to switch between tabs)
- Visual indicators (color, underline) for active state
- Clear labels with counts for screen readers
- Proper ARIA roles and states (could be enhanced with `role="tablist"`)

---

This tab interface significantly improves the UX for creating static watchers on completed jobs while maintaining a clean, intuitive interface for the common case of creating watchers on running jobs. 🎉
