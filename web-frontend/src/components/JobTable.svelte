<script lang="ts">
  import { stopPropagation } from 'svelte/legacy';

  import { createEventDispatcher, onMount, onDestroy } from 'svelte';
  import type { JobInfo } from '../types/api';
  import LoadingSpinner from './LoadingSpinner.svelte';
  import { jobUtils } from '../lib/jobUtils';
  
  interface Props {
    jobs?: JobInfo[];
    loading?: boolean;
  }

  let { jobs = [], loading = false }: Props = $props();
  
  const dispatch = createEventDispatcher<{
    jobSelect: JobInfo;
  }>();
  
  // Sorting state
  let sortBy: keyof JobInfo = $state('submit_time');
  let sortDesc = $state(true);
  
  // Filter state
  let hostFilter = $state('');
  let statusFilter = $state('');
  let userFilter = $state('');
  
  // Dropdown visibility
  let showHostFilter = $state(false);
  let showStatusFilter = $state(false);
  let showUserFilter = $state(false);
  
  // Get unique values for filters - filter out undefined jobs first
  let uniqueHosts = $derived([...new Set(jobs.filter(j => j).map(j => j.hostname).filter(Boolean))]);
  let uniqueStatuses = $derived([...new Set(jobs.filter(j => j && j.state).map(j => j.state))]);
  let uniqueUsers = $derived([...new Set(jobs.filter(j => j).map(j => j.user).filter(Boolean))]);

  // Filter and sort functions
  function filterAndSortJobs(jobs: JobInfo[]): JobInfo[] {
    let filtered = [...jobs];
    
    // Apply filters
    if (hostFilter) {
      filtered = filtered.filter(j => j.hostname === hostFilter);
    }
    if (statusFilter) {
      filtered = filtered.filter(j => j.state === statusFilter);
    }
    if (userFilter) {
      filtered = filtered.filter(j => j.user === userFilter);
    }
    
    // Apply sorting
    return filtered.sort((a, b) => {
      let aVal = a[sortBy];
      let bVal = b[sortBy];
      
      // Handle null/undefined
      if (aVal === null || aVal === undefined) aVal = '';
      if (bVal === null || bVal === undefined) bVal = '';
      
      // Compare
      if (aVal < bVal) return sortDesc ? 1 : -1;
      if (aVal > bVal) return sortDesc ? -1 : 1;
      return 0;
    });
  }
  
  function handleSort(column: keyof JobInfo) {
    if (sortBy === column) {
      sortDesc = !sortDesc;
    } else {
      sortBy = column;
      sortDesc = false;
    }
  }
  
  function resetFilters() {
    hostFilter = '';
    statusFilter = '';
    userFilter = '';
    sortBy = 'submit_time';
    sortDesc = true;
  }
  
  function toggleHostFilter() {
    showHostFilter = !showHostFilter;
    showStatusFilter = false;
    showUserFilter = false;
  }
  
  function toggleStatusFilter() {
    showStatusFilter = !showStatusFilter;
    showHostFilter = false;
    showUserFilter = false;
  }
  
  function toggleUserFilter() {
    showUserFilter = !showUserFilter;
    showHostFilter = false;
    showStatusFilter = false;
  }
  
  function selectHost(host: string) {
    hostFilter = hostFilter === host ? '' : host;
    showHostFilter = false;
  }
  
  function selectStatus(status: string) {
    statusFilter = statusFilter === status ? '' : status;
    showStatusFilter = false;
  }
  
  function selectUser(user: string) {
    userFilter = userFilter === user ? '' : user;
    showUserFilter = false;
  }
  
  // Close dropdowns on outside click
  function handleClickOutside(event: MouseEvent) {
    const target = event.target as HTMLElement;
    // Only close dropdowns if clicking outside ALL filter dropdowns, menus, and sortable headers
    if (!target.closest('.filter-dropdown') && 
        !target.closest('.dropdown-menu') && 
        !target.closest('.sortable') &&
        !target.closest('th')) {
      showHostFilter = false;
      showStatusFilter = false;
      showUserFilter = false;
    }
  }
  
  // Add/remove click listener
  onMount(() => {
    document.addEventListener('click', handleClickOutside);
  });
  
  onDestroy(() => {
    document.removeEventListener('click', handleClickOutside);
  });
  
  function handleJobClick(job: JobInfo) {
    dispatch('jobSelect', job);
  }
  
  // Use centralized job utilities
  
  function formatTime(time: string | null): string {
    if (!time) return '-';
    const date = new Date(time);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    
    // Less than 1 minute
    if (diff < 60000) return 'Just now';
    
    // Less than 1 hour
    if (diff < 3600000) {
      const mins = Math.floor(diff / 60000);
      return `${mins}m ago`;
    }
    
    // Less than 24 hours
    if (diff < 86400000) {
      const hours = Math.floor(diff / 3600000);
      return `${hours}h ago`;
    }
    
    // Format as date
    return date.toLocaleDateString('en-US', { 
      month: 'short', 
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  }
  
  function formatDuration(duration: string | null): string {
    if (!duration) return '-';
    
    // Parse duration (HH:MM:SS or DD-HH:MM:SS)
    const parts = duration.split(/[-:]/);
    if (parts.length === 3) {
      const [h, m, s] = parts.map(Number);
      if (h > 0) return `${h}h ${m}m`;
      if (m > 0) return `${m}m ${s}s`;
      return `${s}s`;
    } else if (parts.length === 4) {
      const [d, h, m, s] = parts.map(Number);
      if (d > 0) return `${d}d ${h}h`;
      return `${h}h ${m}m`;
    }
    
    return duration;
  }
  
  let processedJobs = $derived(filterAndSortJobs(jobs));
  let hasActiveFilters = $derived(hostFilter || statusFilter || userFilter);
</script>

<div class="relative overflow-hidden bg-white rounded-lg border border-gray-200">
  {#if hasActiveFilters}
    <div class="flex flex-wrap items-center gap-2 p-4 bg-gray-50 border-b border-gray-200">
      <span class="text-sm font-medium text-gray-600">Active filters:</span>
      {#if hostFilter}
        <span class="inline-flex items-center gap-1 px-3 py-1 text-sm bg-blue-100 text-blue-800 rounded-full">
          Host: {hostFilter}
          <button onclick={() => hostFilter = ''} class="ml-1 text-blue-600 hover:text-blue-800 font-bold">×</button>
        </span>
      {/if}
      {#if statusFilter}
        <span class="inline-flex items-center gap-1 px-3 py-1 text-sm bg-blue-100 text-blue-800 rounded-full">
          Status: {jobUtils.getStateLabel(statusFilter)}
          <button onclick={() => statusFilter = ''} class="ml-1 text-blue-600 hover:text-blue-800 font-bold">×</button>
        </span>
      {/if}
      {#if userFilter}
        <span class="inline-flex items-center gap-1 px-3 py-1 text-sm bg-blue-100 text-blue-800 rounded-full">
          User: {userFilter}
          <button onclick={() => userFilter = ''} class="ml-1 text-blue-600 hover:text-blue-800 font-bold">×</button>
        </span>
      {/if}
      <button class="px-3 py-1 text-sm text-gray-600 hover:text-gray-800 border border-gray-300 rounded-md hover:bg-gray-50" onclick={resetFilters}>Reset all</button>
    </div>
  {/if}
  
  <table class="w-full border-collapse">
    <thead class="bg-gray-50">
      <tr>
        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100" onclick={stopPropagation(() => handleSort('job_id'))}>
          <span>Job ID</span>
          {#if sortBy === 'job_id'}
            <span class="ml-1 text-gray-400">{sortDesc ? '↓' : '↑'}</span>
          {/if}
        </th>
        <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100" onclick={stopPropagation(() => handleSort('name'))}>
          <span>Name</span>
          {#if sortBy === 'name'}
            <span class="ml-1 text-gray-400">{sortDesc ? '↓' : '↑'}</span>
          {/if}
        </th>
        <th class="filter-dropdown">
          <button class="filter-header" onclick={stopPropagation(toggleUserFilter)}>
            <span>User</span>
            <span class="filter-icon">{userFilter ? '●' : '▼'}</span>
          </button>
          {#if showUserFilter}
            <div class="dropdown-menu">
              <button 
                class="dropdown-item"
                class:selected={!userFilter}
                onclick={() => selectUser('')}
              >
                All Users
              </button>
              {#each uniqueUsers.sort() as user}
                <button 
                  class="dropdown-item"
                  class:selected={userFilter === user}
                  onclick={() => selectUser(user)}
                >
                  {user}
                </button>
              {/each}
            </div>
          {/if}
        </th>
        <th class="filter-dropdown">
          <button class="filter-header" onclick={stopPropagation(toggleHostFilter)}>
            <span>Host</span>
            <span class="filter-icon">{hostFilter ? '●' : '▼'}</span>
          </button>
          {#if showHostFilter}
            <div class="dropdown-menu">
              <button 
                class="dropdown-item"
                class:selected={!hostFilter}
                onclick={() => selectHost('')}
              >
                All Hosts
              </button>
              {#each uniqueHosts.sort() as host}
                <button 
                  class="dropdown-item"
                  class:selected={hostFilter === host}
                  onclick={() => selectHost(host)}
                >
                  {host}
                </button>
              {/each}
            </div>
          {/if}
        </th>
        <th class="filter-dropdown">
          <button class="filter-header" onclick={stopPropagation(toggleStatusFilter)}>
            <span>Status</span>
            <span class="filter-icon">{statusFilter ? '●' : '▼'}</span>
          </button>
          {#if showStatusFilter}
            <div class="dropdown-menu">
              <button 
                class="dropdown-item"
                class:selected={!statusFilter}
                onclick={() => selectStatus('')}
              >
                All Statuses
              </button>
              {#each uniqueStatuses.sort() as status}
                <button 
                  class="dropdown-item"
                  class:selected={statusFilter === status}
                  onclick={() => selectStatus(status)}
                >
                  <span 
                    class="status-dot"
                    style="background-color: {jobUtils.getStateColor(status)}"
                  ></span>
                  {jobUtils.getStateLabel(status)}
                </button>
              {/each}
            </div>
          {/if}
        </th>
        <th class="sortable" onclick={stopPropagation(() => handleSort('submit_time'))}>
          <span>Submitted</span>
          {#if sortBy === 'submit_time'}
            <span class="sort-icon">{sortDesc ? '↓' : '↑'}</span>
          {/if}
        </th>
        <th>Duration</th>
      </tr>
    </thead>
    <tbody>
      {#if loading}
        <tr>
          <td colspan="7" class="loading-cell">
            <LoadingSpinner size="md" message="Loading jobs..." />
          </td>
        </tr>
      {:else if processedJobs.length === 0}
        <tr>
          <td colspan="7" class="loading-cell">
            <LoadingSpinner size="md" message="Loading jobs..." />
          </td>
        </tr>
      {:else}
        {#each processedJobs as job (job.job_id + job.hostname)}
          <tr class="job-row" onclick={() => handleJobClick(job)}>
            <td class="job-id">{job.job_id}</td>
            <td class="job-name" title={job.name}>
              <div class="job-name-wrapper">
                <span class="job-name-text">{job.name || '-'}</span>
              </div>
            </td>
            <td class="job-user">{job.user || '-'}</td>
            <td><span class="job-host">{job.hostname}</span></td>
            <td class="status-cell">
              <span 
                class="status-badge status-{job.state.toLowerCase()}"
              >
                {jobUtils.getStateLabel(job.state)}
              </span>
            </td>
            <td class="job-time">{formatTime(job.submit_time)}</td>
            <td class="job-duration">{formatDuration(job.runtime)}</td>
          </tr>
        {/each}
      {/if}
    </tbody>
  </table>
</div>

<style>
  .table-container {
    width: calc(100% - 3rem);
    margin: 1.5rem auto;
    background: linear-gradient(145deg, #ffffff 0%, #f8f9fa 100%);
    border-radius: 1rem;
    box-shadow:
      0 0 0 1px rgba(0, 0, 0, 0.05),
      0 2px 4px rgba(0, 0, 0, 0.06),
      0 12px 24px rgba(0, 0, 0, 0.06),
      0 24px 48px rgba(0, 0, 0, 0.04);
    position: relative;
    overflow: hidden; /* Contain the table content */
    border: 1px solid rgba(0, 0, 0, 0.08);
  }
  
  .table-container::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 1px;
    background: linear-gradient(90deg, 
      transparent 0%, 
      rgba(148, 163, 184, 0.15) 50%, 
      transparent 100%);
    z-index: 1;
  }
  
  /* Active filters bar */
  .active-filters {
    padding: 0.875rem 1rem;
    background: rgba(243, 244, 246, 0.9);
    border-bottom: 1px solid rgba(148, 163, 184, 0.2);
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
  }
  
  .filter-label {
    font-size: 0.813rem;
    color: #6b7280;
    font-weight: 500;
  }
  
  .filter-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.25rem 0.75rem;
    background: linear-gradient(135deg, #ffffff, #f9fafb);
    border: 1px solid rgba(0, 0, 0, 0.08);
    border-radius: 9999px;
    font-size: 0.75rem;
    color: #1f2937;
    font-weight: 500;
    box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.04);
  }
  
  .remove-filter {
    background: none;
    border: none;
    color: #9ca3af;
    cursor: pointer;
    padding: 0;
    margin-left: 0.25rem;
    font-size: 1rem;
    line-height: 1;
    transition: color 0.15s;
  }
  
  .remove-filter:hover {
    color: #374151;
  }
  
  .reset-filters {
    padding: 0.25rem 0.875rem;
    background: linear-gradient(135deg, #3b82f6, #2563eb);
    border: none;
    border-radius: 0.375rem;
    font-size: 0.75rem;
    font-weight: 600;
    color: white;
    cursor: pointer;
    transition: all 0.2s;
    box-shadow: 0 1px 3px 0 rgba(59, 130, 246, 0.3);
  }
  
  .reset-filters:hover {
    background: linear-gradient(135deg, #2563eb, #1d4ed8);
    box-shadow: 0 2px 4px 0 rgba(59, 130, 246, 0.4);
    transform: translateY(-1px);
  }
  
  .job-table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    font-size: 0.813rem;
  }
  
  thead {
    background: linear-gradient(180deg,
      rgba(241, 243, 245, 1) 0%,
      rgba(229, 231, 235, 1) 100%);
    border-bottom: 1px solid rgba(107, 114, 128, 0.25);
    position: sticky;
    top: 0;
    z-index: 10;
    backdrop-filter: blur(8px);
  }
  
  th {
    padding: 0.75rem 1rem;
    text-align: left;
    font-weight: 600;
    color: #334155;
    white-space: nowrap;
    user-select: none;
    height: 44px;
    font-size: 0.75rem;
    text-transform: none;
    letter-spacing: 0.025em;
    position: relative;
  }
  
  th:not(:last-child)::after {
    content: '';
    position: absolute;
    right: 0;
    top: 20%;
    bottom: 20%;
    width: 1px;
    background: linear-gradient(180deg,
      transparent 0%,
      rgba(0, 0, 0, 0.1) 50%,
      transparent 100%);
  }
  
  th.sortable {
    cursor: pointer;
    transition: background 0.15s;
  }
  
  th.sortable:hover {
    background: rgba(0, 0, 0, 0.03);
  }
  
  .sort-icon {
    margin-left: 0.25rem;
    color: #9ca3af;
    font-size: 0.75rem;
  }
  
  /* Filter dropdown styles */
  .filter-dropdown {
    position: relative;
  }
  
  .filter-header {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    background: none;
    border: none;
    padding: 0.625rem 0.875rem;
    font-weight: 600;
    color: #475569;
    cursor: pointer;
    width: 100%;
    text-align: left;
    transition: background 0.15s;
    font-size: 0.75rem;
  }
  
  .filter-header:hover {
    background: #f3f4f6;
  }
  
  .filter-icon {
    margin-left: auto;
    font-size: 0.625rem;
    color: #9ca3af;
  }
  
  .dropdown-menu {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    min-width: 160px;
    max-height: 320px;
    overflow-y: auto;
    background: white;
    border: 1px solid rgba(148, 163, 184, 0.15);
    border-radius: 0.5rem;
    box-shadow: 
      0 0 0 1px rgba(0, 0, 0, 0.03),
      0 10px 40px -10px rgba(0, 0, 0, 0.15), 
      0 4px 6px -2px rgba(0, 0, 0, 0.05);
    z-index: 50;
    animation: dropdownSlide 0.15s cubic-bezier(0.4, 0, 0.2, 1);
  }
  
  @keyframes dropdownSlide {
    from {
      opacity: 0;
      transform: translateY(-8px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
  
  .dropdown-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    width: 100%;
    padding: 0.5rem 0.75rem;
    background: none;
    border: none;
    text-align: left;
    font-size: 0.813rem;
    color: #374151;
    cursor: pointer;
    transition: background 0.15s;
  }
  
  .dropdown-item:hover {
    background: #f9fafb;
  }
  
  .dropdown-item.selected {
    background: #f3f4f6;
    font-weight: 600;
  }
  
  .status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  
  tbody tr {
    position: relative;
    transition: all 0.15s cubic-bezier(0.4, 0, 0.2, 1);
    height: 44px;
    background: white;
  }
  
  tbody tr::after {
    content: '';
    position: absolute;
    left: 1rem;
    right: 1rem;
    bottom: 0;
    height: 1px;
    background: linear-gradient(90deg,
      transparent 0%,
      rgba(0, 0, 0, 0.06) 10%,
      rgba(0, 0, 0, 0.06) 90%,
      transparent 100%);
  }
  
  tbody tr:hover {
    background: rgba(59, 130, 246, 0.04);
    cursor: pointer;
    box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
  }
  
  tbody tr:hover::after {
    background: linear-gradient(90deg, 
      transparent 0%, 
      rgba(59, 130, 246, 0.15) 10%, 
      rgba(59, 130, 246, 0.15) 90%, 
      transparent 100%);
  }
  
  tbody tr:nth-child(odd) {
    background: rgba(248, 250, 252, 0.5);
  }
  
  tbody tr:nth-child(odd):hover {
    background: rgba(59, 130, 246, 0.05);
    box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
  }
  
  td {
    padding: 0.75rem 1rem;
    color: #0f172a;
    height: 44px;
    max-height: 44px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 0.8125rem;
    position: relative;
  }
  
  .job-id {
    font-family: 'SF Mono', 'Monaco', 'Cascadia Code', 'Consolas', monospace;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.025em;
    color: #475569;
  }
  
  .job-name {
    max-width: 200px;
    min-width: 120px;
  }
  
  .job-name-wrapper {
    display: inline-flex;
    align-items: center;
    position: relative;
  }
  
  .job-name-text {
    font-weight: 600;
    color: #0f172a;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  
  tbody tr:hover .job-name-text {
    color: #3b82f6;
  }
  
  .job-user {
    color: #475569;
    font-weight: 500;
  }
  
  .job-host {
    font-family: 'SF Mono', 'Monaco', 'Cascadia Code', 'Consolas', monospace;
    font-size: 0.65rem;
    font-weight: 700;
    color: #475569;
    background: linear-gradient(135deg, #e0e7ff, #dbeafe);
    padding: 0.125rem 0.5rem;
    border-radius: 0.25rem;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border: 1px solid #c7d2fe;
    text-align: center;
    min-width: fit-content;
    letter-spacing: 0.05em;
  }
  
  .status-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.25rem;
    padding: 0.25rem 0.5rem;
    border-radius: 0.5rem;
    font-size: 0.625rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    position: relative;
    transition: all 0.15s;
    border: 1px solid;
    min-width: 80px; /* Consistent width */
    text-align: center;
  }
  
  .status-badge::before {
    content: '';
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
    animation: pulse 2s infinite;
    flex-shrink: 0;
  }
  
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.6; }
  }
  
  /* Modern status badge colors - more solid, less glassy */
  .status-r {
    background: #bbf7d0;
    color: #14532d;
    border-color: #4ade80;
  }
  
  .status-pd {
    background: #fde68a;
    color: #78350f;
    border-color: #fbbf24;
  }
  
  .status-cd {
    background: #bfdbfe;
    color: #1e3a8a;
    border-color: #3b82f6;
  }
  
  .status-f {
    background: #fecaca;
    color: #991b1b;
    border-color: #ef4444;
  }
  
  .status-ca {
    background: #e5e7eb;
    color: #1f2937;
    border-color: #6b7280;
  }
  
  .status-to {
    background: #ddd6fe;
    color: #581c87;
    border-color: #8b5cf6;
  }
  
  .status-cg {
    background: #a7f3d0;
    color: #064e3b;
    border-color: #10b981;
  }
  
  .job-time, .job-duration {
    color: #475569;
    font-size: 0.75rem;
    font-weight: 500;
    text-align: right;
    white-space: nowrap;
  }
  
  .job-duration {
    min-width: 60px;
  }
  
  .status-cell {
    text-align: center;
    padding: 0.625rem 0.5rem; /* Reduce horizontal padding for centered content */
  }
  
  .loading-cell {
    text-align: center;
    padding: 2rem;
  }

  .empty-cell {
    text-align: center;
    padding: 2rem;
    color: #6b7280;
  }
  
  /* Progressive column hiding for responsive behavior */
  
  /* First breakpoint: Hide duration column before it gets squeezed */
  @media (max-width: 1050px) {
    th:nth-child(7), td:nth-child(7) { /* Duration */
      display: none;
    }
    .job-name {
      max-width: 180px;
    }
  }
  
  @media (max-width: 950px) {
    .job-name {
      max-width: 160px;
    }
  }
  
  /* Second breakpoint: Hide user column */
  @media (max-width: 800px) {
    th:nth-child(3), td:nth-child(3) { /* User */
      display: none;
    }
    .job-name {
      max-width: 140px;
    }
  }
  
  /* Third breakpoint: Start shortening job names more aggressively */
  @media (max-width: 700px) {
    .job-name {
      max-width: 120px;
    }
    .job-table {
      font-size: 0.78rem;
    }
  }
  
  /* Fourth breakpoint: Hide submitted time */
  @media (max-width: 600px) {
    th:nth-child(6), td:nth-child(6) { /* Submitted */
      display: none;
    }
    .job-name {
      max-width: 100px;
    }
  }
  
  /* Mobile optimization */
  @media (max-width: 768px) {
    .table-container {
      width: calc(100% - 2rem);
      margin: 1rem auto;
      border-radius: 0.75rem;
    }

    .job-table {
      font-size: 0.75rem;
    }

    th, td {
      padding: 0.375rem 0.5rem;
    }
  }
  
  /* Very small screens: Further optimization */
  @media (max-width: 480px) {
    .table-container {
      width: calc(100% - 1rem);
      margin: 0.5rem auto;
      border-radius: 0.5rem;
    }

    .job-name {
      max-width: 80px;
    }

    th, td {
      padding: 0.25rem 0.375rem;
    }

    .job-table {
      font-size: 0.7rem;
    }
  }
</style>