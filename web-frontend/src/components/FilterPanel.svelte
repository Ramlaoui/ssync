<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { JobFilters, HostInfo } from '../types/api';
  
  export let filters: JobFilters;
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  export let hosts: HostInfo[]; // Available for future use
  export let loading = false;
  
  const dispatch = createEventDispatcher<{
    change: void;
  }>();
  
  function handleChange(): void {
    dispatch('change');
  }
  
  function clearFilters(): void {
    if (loading) return;
    
    filters.host = '';
    filters.user = '';
    filters.since = '1d';
    filters.limit = 20;
    filters.state = '';
    filters.activeOnly = false;
    filters.completedOnly = false;
    handleChange();
  }
</script>

<div class="filter-panel">
  <div class="filter-header">
    <h3>Filters</h3>
    <button 
      class="clear-btn" 
      on:click={clearFilters}
      disabled={loading}
      aria-label="Clear all filters"
    >
      Clear
    </button>
  </div>
  
  <div class="filter-group">
    <label for="user">User:</label>
    <input 
      id="user"
      type="text" 
      bind:value={filters.user} 
      on:input={handleChange}
      placeholder="username"
      disabled={loading}
    />
  </div>
  
  <div class="filter-group">
    <label for="since">Time Range:</label>
    <select id="since" bind:value={filters.since} on:change={handleChange} disabled={loading}>
      <option value="1h">Last Hour</option>
      <option value="1d">Last Day</option>
      <option value="1w">Last Week</option>
      <option value="1m">Last Month</option>
    </select>
  </div>
  
  <div class="filter-group">
    <label for="limit">Limit:</label>
    <input 
      id="limit"
      type="number" 
      bind:value={filters.limit} 
      on:input={handleChange}
      min="1"
      max="100"
      disabled={loading}
    />
  </div>
  
  <div class="filter-group">
    <label for="state">State:</label>
    <select id="state" bind:value={filters.state} on:change={handleChange} disabled={loading}>
      <option value="">All States</option>
      <option value="R">Running</option>
      <option value="PD">Pending</option>
      <option value="CD">Completed</option>
      <option value="F">Failed</option>
      <option value="CA">Cancelled</option>
      <option value="TO">Timeout</option>
    </select>
  </div>
  
  <div class="filter-group">
    <label>
      <input 
        type="checkbox" 
        bind:checked={filters.activeOnly} 
        on:change={handleChange}
        disabled={loading}
      />
      Active Jobs Only
    </label>
  </div>
  
  <div class="filter-group">
    <label>
      <input 
        type="checkbox" 
        bind:checked={filters.completedOnly} 
        on:change={handleChange}
        disabled={loading}
      />
      Completed Jobs Only
    </label>
  </div>
</div>

<style>
  .filter-panel {
    background: #f8f9fa;
    border-radius: 0.5rem;
    padding: 1rem;
    margin-bottom: 1rem;
  }

  .filter-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
  }

  .filter-header h3 {
    margin: 0;
    color: #495057;
  }

  .clear-btn {
    background: #6c757d;
    color: white;
    border: none;
    padding: 0.25rem 0.75rem;
    border-radius: 0.25rem;
    cursor: pointer;
    font-size: 0.8rem;
  }

  .clear-btn:hover:not(:disabled) {
    background: #5a6268;
  }
  
  .clear-btn:disabled {
    background: #adb5bd;
    cursor: not-allowed;
  }

  .filter-group {
    margin-bottom: 1rem;
  }

  .filter-group label {
    display: block;
    margin-bottom: 0.25rem;
    font-size: 0.9rem;
    font-weight: 500;
    color: #495057;
  }

  .filter-group input[type="text"],
  .filter-group input[type="number"],
  .filter-group select {
    width: 100%;
    padding: 0.375rem 0.75rem;
    border: 1px solid #ced4da;
    border-radius: 0.25rem;
    font-size: 0.9rem;
  }

  .filter-group input[type="text"]:focus,
  .filter-group input[type="number"]:focus,
  .filter-group select:focus {
    outline: none;
    border-color: #80bdff;
    box-shadow: 0 0 0 0.2rem rgba(0,123,255,.25);
  }

  .filter-group label:has(input[type="checkbox"]) {
    display: flex;
    align-items: center;
    cursor: pointer;
  }

  .filter-group input[type="checkbox"] {
    margin-right: 0.5rem;
    width: auto;
  }
</style>
