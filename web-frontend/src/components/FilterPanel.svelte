<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { JobFilters, HostInfo } from '../types/api';
  
  export let filters: JobFilters;
  export let hosts: HostInfo[]; 
  export let loading = false;
  export let search = '';
  
  const dispatch = createEventDispatcher<{
    change: void;
  }>();
  
  const timeRangeOptions = [
    { value: '1h', label: 'Last Hour' },
    { value: '1d', label: 'Last Day' },
    { value: '1w', label: 'Last Week' },
    { value: '1m', label: 'Last Month' },
  ];
  
  const stateOptions = [
    { value: '', label: 'All States' },
    { value: 'R', label: 'Running' },
    { value: 'PD', label: 'Pending' },
    { value: 'CD', label: 'Completed' },
    { value: 'F', label: 'Failed' },
    { value: 'CA', label: 'Cancelled' },
    { value: 'TO', label: 'Timeout' },
  ];
  
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
    search = '';
    handleChange();
  }
</script>

<div class="filter-panel">
  <div class="panel-header">
    <h3 class="panel-title">Filters</h3>
    <button 
      class="clear-button" 
      on:click={clearFilters}
      disabled={loading}
      aria-label="Clear all filters"
    >
      <svg viewBox="0 0 24 24" fill="currentColor">
        <path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z" />
      </svg>
      Clear
    </button>
  </div>
  
  <div class="filter-grid">
    <div class="filter-group">
      <label for="search">Search</label>
      <input
        id="search"
        type="text"
        bind:value={search}
        on:input={handleChange}
        placeholder="Job name or ID..."
        disabled={loading}
      />
    </div>
    
    <div class="filter-group">
      <label for="user">User</label>
      <input
        id="user"
        type="text"
        bind:value={filters.user}
        on:input={handleChange}
        placeholder="username"
        disabled={loading}
      />
    </div>
    
    <div class="filter-row">
      <div class="filter-group">
        <label for="since">Time Range</label>
        <select id="since" bind:value={filters.since} on:change={handleChange} disabled={loading}>
          {#each timeRangeOptions as option}
            <option value={option.value}>{option.label}</option>
          {/each}
        </select>
      </div>
      
      <div class="filter-group small">
        <label for="limit">Limit</label>
        <input
          id="limit"
          type="number"
          bind:value={filters.limit}
          on:input={handleChange}
          min={1}
          max={100}
          disabled={loading}
        />
      </div>
    </div>
    
    <div class="filter-group">
      <label for="state">State</label>
      <select id="state" bind:value={filters.state} on:change={handleChange} disabled={loading}>
        {#each stateOptions as option}
          <option value={option.value}>{option.label}</option>
        {/each}
      </select>
    </div>
  </div>
  
  <div class="checkbox-group">
    <label class="checkbox-label">
      <input
        type="checkbox"
        bind:checked={filters.activeOnly}
        on:change={handleChange}
        disabled={loading}
      />
      <span>Active Jobs Only</span>
    </label>
    
    <label class="checkbox-label">
      <input
        type="checkbox"
        bind:checked={filters.completedOnly}
        on:change={handleChange}
        disabled={loading}
      />
      <span>Completed Jobs Only</span>
    </label>
  </div>
</div>

<style>
  .filter-panel {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 1rem;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .panel-title {
    margin: 0;
    font-size: 0.75rem;
    font-weight: 600;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    user-select: none;
    -webkit-user-select: none;
    -moz-user-select: none;
    -ms-user-select: none;
  }

  .clear-button {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.25rem 0.5rem;
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    color: #64748b;
    font-size: 0.8rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s ease;
  }
  
  .clear-button svg {
    width: 12px;
    height: 12px;
  }

  .clear-button:hover:not(:disabled) {
    background: #fee2e2;
    border-color: #fca5a5;
    color: #dc2626;
  }

  .clear-button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .filter-grid {
    display: flex;
    flex-direction: column;
    gap: 0.875rem;
  }

  .filter-row {
    display: grid;
    grid-template-columns: 2fr 1fr;
    gap: 0.75rem;
  }

  .filter-group {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .filter-group label {
    font-size: 0.7rem;
    font-weight: 600;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .filter-group input,
  .filter-group select {
    padding: 0.5rem 0.75rem;
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    font-size: 0.9rem;
    color: #334155;
    transition: all 0.15s ease;
    width: 100%;
  }

  .filter-group input:hover:not(:disabled),
  .filter-group select:hover:not(:disabled) {
    border-color: #cbd5e1;
  }

  .filter-group input:focus,
  .filter-group select:focus {
    outline: none;
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  .filter-group input:disabled,
  .filter-group select:disabled {
    background: #f8fafc;
    color: #94a3b8;
    cursor: not-allowed;
  }

  .filter-group input[type="number"] {
    -moz-appearance: textfield;
  }

  .filter-group input[type="number"]::-webkit-outer-spin-button,
  .filter-group input[type="number"]::-webkit-inner-spin-button {
    -webkit-appearance: none;
    margin: 0;
  }

  select {
    cursor: pointer;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%2394a3b8'%3E%3Cpath d='M7 10l5 5 5-5z'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 0.5rem center;
    background-size: 20px;
    padding-right: 2rem;
    appearance: none;
  }

  .checkbox-group {
    display: flex;
    flex-direction: column;
    gap: 0.625rem;
    padding-top: 0.25rem;
  }

  .checkbox-label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    cursor: pointer;
    font-size: 0.9rem;
    color: #475569;
  }

  .checkbox-label:hover {
    color: #334155;
  }

  .checkbox-label input[type="checkbox"] {
    width: 16px;
    height: 16px;
    cursor: pointer;
    accent-color: #3b82f6;
  }

  .checkbox-label input[type="checkbox"]:disabled {
    cursor: not-allowed;
    opacity: 0.5;
  }

  .checkbox-label input[type="checkbox"]:disabled ~ span {
    color: #94a3b8;
    cursor: not-allowed;
  }
</style>