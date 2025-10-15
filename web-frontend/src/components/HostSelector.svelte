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

<div class="flex flex-col gap-3 {variant === 'compact' ? 'compact' : ''}">
  <div class="flex justify-between items-center px-0.5">
    <h3 class="m-0 text-xs font-semibold text-slate-400 uppercase tracking-wider select-none">Hosts</h3>
    <span class="bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded-[10px] text-[0.7rem] font-semibold min-w-[20px] text-center">{hosts.length}</span>
  </div>
  
  {#if hosts.length === 0}
    <div class="flex flex-col items-center py-8 px-4 text-slate-400 text-center">
      <svg class="w-12 h-12 opacity-30 mb-2" viewBox="0 0 24 24" fill="currentColor">
        <path d="M19,3H5A2,2 0 0,0 3,5V19A2,2 0 0,0 5,21H19A2,2 0 0,0 21,19V5A2,2 0 0,0 19,3M19,5V19H5V5H19M13.96,12.29L11.21,15.83L9.25,13.47L6.5,17H17.5L13.96,12.29Z" />
      </svg>
      <p class="m-0 text-sm">No hosts configured</p>
    </div>
  {:else}
    <div class="flex flex-col gap-1.5">
      <!-- All hosts option -->
      <button
        class="flex justify-between items-center py-3 px-4 bg-white border border-slate-200 rounded-lg cursor-pointer font-inherit transition-all duration-150 w-full text-left hover:bg-slate-50 hover:border-slate-300 hover:translate-x-0.5 disabled:opacity-50 disabled:cursor-not-allowed {selectedHost === '' ? 'bg-blue-600 border-blue-600 text-white shadow-md shadow-blue-600/30' : ''}"
        on:click={() => selectHost('')}
        disabled={loading}
        aria-pressed={selectedHost === ''}
      >
        <span class="text-sm text-slate-700 transition-colors duration-150 {selectedHost === '' ? '!text-white !font-medium' : ''}">All Hosts</span>
        <span class="bg-emerald-500 text-white px-2.5 py-1 rounded-xl text-xs font-semibold min-w-[28px] text-center transition-all duration-150">{getTotalJobs()}</span>
      </button>
      
      <!-- Individual hosts -->
      {#each hosts as host}
        <button
          class="flex justify-between items-center py-3 px-4 bg-white border border-slate-200 rounded-lg cursor-pointer font-inherit transition-all duration-150 w-full text-left hover:bg-slate-50 hover:border-slate-300 hover:translate-x-0.5 disabled:opacity-50 disabled:cursor-not-allowed {selectedHost === host.hostname ? 'bg-blue-600 border-blue-600 text-white shadow-md shadow-blue-600/30' : ''}"
          on:click={() => selectHost(host.hostname)}
          disabled={loading}
          aria-pressed={selectedHost === host.hostname}
        >
          <span class="text-sm text-slate-700 transition-colors duration-150 {selectedHost === host.hostname ? '!text-white !font-medium' : ''}">{host.hostname}</span>
          {#if jobCounts.has(host.hostname)}
            {@const count = jobCounts.get(host.hostname) || 0}
            <span class="px-2.5 py-1 rounded-xl text-xs font-semibold min-w-[28px] text-center transition-all duration-150 {count > 0 ? 'bg-amber-400 text-white' : selectedHost === host.hostname ? 'bg-white/20 text-white' : 'bg-slate-100 text-slate-600'}">
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
    user-select: none;
    -webkit-user-select: none;
    -moz-user-select: none;
    -ms-user-select: none;
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
  

  /* Compact variant adjustments handled in HTML with Tailwind classes */
</style>