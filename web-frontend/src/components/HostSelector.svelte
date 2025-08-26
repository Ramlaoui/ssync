<script lang="ts">
  import type { HostInfo } from '../types/api';
  import { createEventDispatcher } from 'svelte';
  
  export let hosts: HostInfo[] = [];
  export let selectedHost = '';
  export let jobCounts: Map<string, number> = new Map();
  export let loading = false;
  export let variant: 'sidebar' | 'compact' = 'sidebar';
  
  const dispatch = createEventDispatcher<{
    select: string;
  }>();
  
  function selectHost(hostname: string) {
    if (loading) return;
    const newHost = selectedHost === hostname ? '' : hostname;
    dispatch('select', newHost);
  }
  
  function getTotalJobs(): number {
    let total = 0;
    jobCounts.forEach(count => total += count);
    return total;
  }
</script>

<div class="host-selector" class:compact={variant === 'compact'}>
  <div class="section-header">
    <h3 class="section-title">Hosts</h3>
    <span class="host-count">{hosts.length}</span>
  </div>
  
  {#if hosts.length === 0}
    <div class="empty-state">
      <svg class="empty-icon" viewBox="0 0 24 24" fill="currentColor">
        <path d="M19,3H5A2,2 0 0,0 3,5V19A2,2 0 0,0 5,21H19A2,2 0 0,0 21,19V5A2,2 0 0,0 19,3M19,5V19H5V5H19M13.96,12.29L11.21,15.83L9.25,13.47L6.5,17H17.5L13.96,12.29Z" />
      </svg>
      <p>No hosts configured</p>
    </div>
  {:else}
    <div class="host-list">
      <!-- All hosts option -->
      <button
        class="host-item"
        class:active={selectedHost === ''}
        on:click={() => selectHost('')}
        disabled={loading}
        aria-pressed={selectedHost === ''}
      >
        <span class="host-name">All Hosts</span>
        <span class="job-count total">{getTotalJobs()}</span>
      </button>
      
      <!-- Individual hosts -->
      {#each hosts as host}
        <button
          class="host-item"
          class:active={selectedHost === host.hostname}
          on:click={() => selectHost(host.hostname)}
          disabled={loading}
          aria-pressed={selectedHost === host.hostname}
        >
          <span class="host-name">{host.hostname}</span>
          {#if jobCounts.has(host.hostname)}
            {@const count = jobCounts.get(host.hostname) || 0}
            <span class="job-count" class:has-jobs={count > 0}>
              {count}
            </span>
          {/if}
        </button>
      {/each}
    </div>
  {/if}
</div>

<style>
  .host-selector {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  
  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0 0.125rem;
  }
  
  .section-title {
    margin: 0;
    font-size: 0.75rem;
    font-weight: 600;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  
  .host-count {
    background: #f1f5f9;
    color: #64748b;
    padding: 0.125rem 0.375rem;
    border-radius: 10px;
    font-size: 0.7rem;
    font-weight: 600;
    min-width: 20px;
    text-align: center;
  }
  
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 2rem 1rem;
    color: #94a3b8;
    text-align: center;
  }
  
  .empty-icon {
    width: 48px;
    height: 48px;
    opacity: 0.3;
    margin-bottom: 0.5rem;
  }
  
  .empty-state p {
    margin: 0;
    font-size: 0.9rem;
  }
  
  .host-list {
    display: flex;
    flex-direction: column;
    gap: 0.375rem;
  }
  
  .host-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.75rem 1rem;
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    cursor: pointer;
    font: inherit;
    transition: all 0.15s ease;
    width: 100%;
    text-align: left;
  }
  
  .host-item:hover:not(:disabled) {
    background: #f8fafc;
    border-color: #cbd5e1;
    transform: translateX(2px);
  }
  
  .host-item:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  
  .host-item.active {
    background: #3b82f6;
    border-color: #3b82f6;
    color: white;
    box-shadow: 0 1px 3px rgba(59, 130, 246, 0.3);
  }
  
  .host-item.active .host-name {
    color: white;
    font-weight: 500;
  }
  
  .host-item.active .job-count {
    background: rgba(255, 255, 255, 0.2);
    color: white;
  }
  
  .host-name {
    font-size: 0.925rem;
    color: #334155;
    transition: color 0.15s ease;
  }
  
  .job-count {
    background: #f1f5f9;
    color: #64748b;
    padding: 0.25rem 0.625rem;
    border-radius: 12px;
    font-size: 0.8rem;
    font-weight: 600;
    min-width: 28px;
    text-align: center;
    transition: all 0.15s ease;
  }
  
  .job-count.total {
    background: #10b981;
    color: white;
  }
  
  .job-count.has-jobs {
    background: #fbbf24;
    color: #78350f;
  }
  
  /* Compact variant - not used but kept for future use */
  .compact .host-list {
    flex-direction: row;
    flex-wrap: wrap;
    gap: 0.5rem;
  }
  
  .compact .host-item {
    width: auto;
    padding: 0.5rem 1rem;
    border-radius: 20px;
  }
</style>