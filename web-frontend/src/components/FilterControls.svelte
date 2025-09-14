<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { Search, X } from 'lucide-svelte';
  import type { JobFilters, HostInfo } from '../types/api';
  
  export let filters: JobFilters;
  export let hosts: HostInfo[] = [];
  export let search = '';
  export let isMobile = false;
  export let hideSearch = false;
  
  const dispatch = createEventDispatcher<{
    change: void;
  }>();
  
  // State options
  const stateOptions = [
    { value: 'R', label: 'Running', color: '#22c55e' },
    { value: 'PD', label: 'Pending', color: '#f59e0b' },
    { value: 'CD', label: 'Completed', color: '#3b82f6' },
    { value: 'F', label: 'Failed', color: '#ef4444' },
  ];
  
  function handleSearchInput(e: Event) {
    search = (e.target as HTMLInputElement).value;
    dispatch('change');
  }
  
  function toggleState(value: string) {
    if (filters.state === value) {
      filters.state = '';
    } else {
      filters.state = value;
      // Clear activeOnly when selecting a specific state
      filters.activeOnly = false;
    }
    filters.completedOnly = false;
    dispatch('change');
  }
  
  function toggleActiveOnly() {
    filters.activeOnly = !filters.activeOnly;
    if (filters.activeOnly) {
      filters.completedOnly = false;
      filters.state = ''; // Clear state filter when toggling active
    }
    dispatch('change');
  }
  
  function clearSearch() {
    search = '';
    dispatch('change');
  }
  
  function selectHost(hostname: string) {
    filters.host = hostname;
    dispatch('change');
  }
  
  $: hasActiveFilters = search || filters.state || filters.host || filters.activeOnly;
</script>

{#if !hideSearch}
<div class="filter-container">
  <!-- Search Bar -->
  <div class="search-bar">
    <div class="search-icon">
      <Search size={18} />
    </div>
    <input
      type="text"
      class="search-input"
      placeholder="Search jobs..."
      value={search}
      on:input={handleSearchInput}
    />
    {#if search}
      <button class="clear-btn" on:click={clearSearch}>
        <X size={16} />
      </button>
    {/if}
  </div>
</div>
{/if}

<style>
  .filter-container {
    padding: 1rem;
    background: white;
    border-bottom: 1px solid #f0f0f0;
  }
  
  .search-bar {
    position: relative;
  }
  
  .search-icon {
    position: absolute;
    left: 0.75rem;
    top: 50%;
    transform: translateY(-50%);
    color: #9ca3af;
    pointer-events: none;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  
  .search-input {
    width: 100%;
    padding: 0.5rem 2.5rem;
    border: 1px solid #e5e7eb;
    border-radius: 0.375rem;
    font-size: 0.875rem;
    transition: all 0.15s;
  }
  
  .search-input:focus {
    outline: none;
    border-color: #000;
  }
  
  .search-input::placeholder {
    color: #9ca3af;
  }
  
  .clear-btn {
    position: absolute;
    right: 0.5rem;
    top: 50%;
    transform: translateY(-50%);
    padding: 0.25rem;
    background: none;
    border: none;
    color: #6b7280;
    cursor: pointer;
    border-radius: 0.25rem;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.15s;
  }
  
  .clear-btn:hover {
    background: #f3f4f6;
    color: #000;
  }
  
  /* Mobile adjustments */
  @media (max-width: 768px) {
    .filter-container {
      padding: 0.75rem;
    }
  }
</style>