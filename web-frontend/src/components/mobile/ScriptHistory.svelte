<script lang="ts">
  import { onMount, createEventDispatcher } from 'svelte';
  import { fly } from 'svelte/transition';
  import { api } from '../../services/api';
  import { jobUtils } from '../../lib/jobUtils';
  
  const dispatch = createEventDispatcher<{
    select: { script: string };
  }>();
  
  interface JobScript {
    job_id: string;
    job_name: string;
    hostname: string;
    state: string;
    submit_time: string;
    script_content: string;
    resources: {
      time?: string;
      memory?: string;
      cpus?: number;
      gpus?: number;
    };
  }
  
  let scripts: JobScript[] = [];
  let loading = true;
  let error = '';
  let selectedHost = '';
  let searchTerm = '';
  let filterState = '';
  
  $: filteredScripts = scripts.filter(script => {
    const matchesHost = !selectedHost || script.hostname === selectedHost;
    const matchesState = !filterState || script.state === filterState;
    const matchesSearch = !searchTerm || 
      script.job_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      script.job_id.includes(searchTerm) ||
      script.hostname.toLowerCase().includes(searchTerm.toLowerCase());
    return matchesHost && matchesState && matchesSearch;
  });
  
  $: hosts = [...new Set(scripts.map(s => s.hostname))];
  $: states = [...new Set(scripts.map(s => s.state))];
  
  async function loadHistory() {
    try {
      loading = true;
      error = '';
      
      // Get jobs from all hosts
      const response = await api.get('/api/status');
      const allJobs = [];
      
      for (const host of Object.keys(response.data)) {
        const hostJobs = response.data[host].jobs || [];
        for (const job of hostJobs) {
          if (job.script_content) {
            allJobs.push({
              ...job,
              hostname: host,
              resources: parseResources(job.script_content)
            });
          }
        }
      }
      
      // Sort by submit time, most recent first
      scripts = allJobs.sort((a, b) => 
        new Date(b.submit_time).getTime() - new Date(a.submit_time).getTime()
      );
      
    } catch (err) {
      error = 'Failed to load script history';
      console.error('Error loading history:', err);
    } finally {
      loading = false;
    }
  }
  
  function parseResources(script: string): JobScript['resources'] {
    const resources: JobScript['resources'] = {};
    const lines = script.split('\n');
    
    lines.forEach(line => {
      if (line.includes('--time')) {
        resources.time = line.split('=')[1]?.trim();
      } else if (line.includes('--mem')) {
        resources.memory = line.split('=')[1]?.trim();
      } else if (line.includes('--cpus-per-task')) {
        resources.cpus = parseInt(line.split('=')[1]?.trim() || '0');
      } else if (line.includes('--gres=gpu:')) {
        resources.gpus = parseInt(line.match(/gpu:(\d+)/)?.[1] || '0');
      }
    });
    
    return resources;
  }
  
  function selectScript(script: JobScript) {
    dispatch('select', { script: script.script_content });
  }
  
  function formatDate(dateStr: string): string {
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const hours = Math.floor(diff / (1000 * 60 * 60));
    const days = Math.floor(hours / 24);
    
    if (hours < 1) return 'Just now';
    if (hours < 24) return `${hours}h ago`;
    if (days < 7) return `${days}d ago`;
    return date.toLocaleDateString();
  }
  
  // Use centralized job utilities
  
  onMount(() => {
    loadHistory();
  });
</script>

<div class="script-history">
  {#if loading}
    <div class="loading">
      <div class="spinner"></div>
      <p>Loading history...</p>
    </div>
    
  {:else if error}
    <div class="error">
      <svg viewBox="0 0 24 24" class="error-icon">
        <path d="M12,2C17.53,2 22,6.47 22,12C22,17.53 17.53,22 12,22C6.47,22 2,17.53 2,12C2,6.47 6.47,2 12,2M15.59,7L12,10.59L8.41,7L7,8.41L10.59,12L7,15.59L8.41,17L12,13.41L15.59,17L17,15.59L13.41,12L17,8.41L15.59,7Z" />
      </svg>
      <p>{error}</p>
      <button class="retry-btn" on:click={loadHistory}>Retry</button>
    </div>
    
  {:else}
    <!-- Filters -->
    <div class="filters">
      <input 
        type="search"
        bind:value={searchTerm}
        placeholder="Search jobs..."
        class="search-input"
      />
      
      <div class="filter-row">
        <select bind:value={selectedHost} class="filter-select">
          <option value="">All Hosts</option>
          {#each hosts as host}
            <option value={host}>{host}</option>
          {/each}
        </select>
        
        <select bind:value={filterState} class="filter-select">
          <option value="">All States</option>
          {#each states as state}
            <option value={state}>{state}</option>
          {/each}
        </select>
      </div>
    </div>
    
    <!-- Script List -->
    <div class="script-list">
      {#if filteredScripts.length === 0}
        <div class="empty">
          <svg viewBox="0 0 24 24" class="empty-icon">
            <path d="M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M12,20C7.59,20 4,16.41 4,12C4,7.59 7.59,4 12,4C16.41,4 20,7.59 20,12C20,16.41 16.41,20 12,20M15,12A3,3 0 0,1 12,15A3,3 0 0,1 9,12A3,3 0 0,1 12,9A3,3 0 0,1 15,12Z" />
          </svg>
          <p>No scripts found</p>
        </div>
      {:else}
        {#each filteredScripts as script, i}
          <div 
            class="script-card"
            on:click={() => selectScript(script)}
            in:fly={{ y: 20, delay: i * 50, duration: 300 }}
          >
            <div class="card-header">
              <div class="card-title">
                <h4>{script.job_name || `Job ${script.job_id}`}</h4>
                <span class="job-id">#{script.job_id}</span>
              </div>
              <span class="state-badge {jobUtils.getStateColorClass(script.state)}">
                {script.state}
              </span>
            </div>
            
            <div class="card-meta">
              <span class="meta-item">
                <svg viewBox="0 0 24 24">
                  <path d="M3,15H21V13H3V15M3,19H21V17H3V19M3,11H21V9H3V11M3,5V7H21V5H3Z" />
                </svg>
                {script.hostname}
              </span>
              <span class="meta-item">
                <svg viewBox="0 0 24 24">
                  <path d="M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M16.2,16.2L11,13V7H12.5V12.2L17,14.9L16.2,16.2Z" />
                </svg>
                {formatDate(script.submit_time)}
              </span>
            </div>
            
            <div class="card-resources">
              {#if script.resources.time}
                <span class="resource-badge">
                  <svg viewBox="0 0 24 24">
                    <path d="M12,20A8,8 0 0,0 20,12A8,8 0 0,0 12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20M12,2A10,10 0 0,1 22,12A10,10 0 0,1 12,22C6.47,22 2,17.5 2,12A10,10 0 0,1 12,2M12.5,7V12.25L17,14.92L16.25,16.15L11,13V7H12.5Z" />
                  </svg>
                  {script.resources.time}
                </span>
              {/if}
              
              {#if script.resources.memory}
                <span class="resource-badge">
                  <svg viewBox="0 0 24 24">
                    <path d="M17,17H7V7H17M21,11V9H19V7C19,5.89 18.1,5 17,5H15V3H13V5H11V3H9V5H7C5.89,5 5,5.89 5,7V9H3V11H5V13H3V15H5V17A2,2 0 0,0 7,19H9V21H11V19H13V21H15V19H17A2,2 0 0,0 19,17V15H21V13H19V11M13,13H11V11H13M15,9H9V15H15V9Z" />
                  </svg>
                  {script.resources.memory}
                </span>
              {/if}
              
              {#if script.resources.cpus}
                <span class="resource-badge">
                  <svg viewBox="0 0 24 24">
                    <path d="M17,17H7V7H17M21,11V9H19V7C19,5.89 18.1,5 17,5H15V3H13V5H11V3H9V5H7C5.89,5 5,5.89 5,7V9H3V11H5V13H3V15H5V17A2,2 0 0,0 7,19H9V21H11V19H13V21H15V19H17A2,2 0 0,0 19,17V15H21V13H19V11M13,13H11V11H13M15,9H9V15H15V9Z" />
                  </svg>
                  {script.resources.cpus} CPU{script.resources.cpus > 1 ? 's' : ''}
                </span>
              {/if}
              
              {#if script.resources.gpus}
                <span class="resource-badge gpu">
                  <svg viewBox="0 0 24 24">
                    <path d="M2,7V17H6V7H2M7,19H17V5H7V19M18,7V17H22V7H18Z" />
                  </svg>
                  {script.resources.gpus} GPU{script.resources.gpus > 1 ? 's' : ''}
                </span>
              {/if}
            </div>
          </div>
        {/each}
      {/if}
    </div>
  {/if}
</div>

<style>
  .script-history {
    display: flex;
    flex-direction: column;
    height: 100%;
  }
  
  /* Loading & Error States */
  .loading,
  .error,
  .empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 3rem;
    text-align: center;
  }
  
  .spinner {
    width: 48px;
    height: 48px;
    border: 3px solid #2a3142;
    border-top-color: #3b82f6;
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }
  
  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }
  
  .error-icon,
  .empty-icon {
    width: 48px;
    height: 48px;
    color: #6b7280;
    margin-bottom: 1rem;
  }
  
  .error-icon {
    color: #ef4444;
  }
  
  .retry-btn {
    margin-top: 1rem;
    padding: 0.5rem 1rem;
    background: #2a3142;
    border: none;
    border-radius: 6px;
    color: #e4e8f1;
    cursor: pointer;
  }
  
  /* Filters */
  .filters {
    padding: 1rem;
    background: #141925;
    border-bottom: 1px solid #2a3142;
    position: sticky;
    top: 0;
    z-index: 10;
  }
  
  .search-input {
    width: 100%;
    padding: 0.75rem;
    background: #1e2433;
    border: 1px solid #2a3142;
    border-radius: 8px;
    color: #e4e8f1;
    font-size: 0.9rem;
    margin-bottom: 0.75rem;
    outline: none;
  }
  
  .search-input:focus {
    border-color: #3b82f6;
  }
  
  .filter-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.5rem;
  }
  
  .filter-select {
    padding: 0.5rem;
    background: #1e2433;
    border: 1px solid #2a3142;
    border-radius: 6px;
    color: #e4e8f1;
    font-size: 0.875rem;
    outline: none;
  }
  
  /* Script List */
  .script-list {
    flex: 1;
    overflow-y: auto;
    padding: 1rem;
  }
  
  .script-card {
    background: #141925;
    border: 1px solid #2a3142;
    border-radius: 12px;
    padding: 1rem;
    margin-bottom: 0.75rem;
    cursor: pointer;
    transition: all 0.2s;
    -webkit-tap-highlight-color: transparent;
  }
  
  .script-card:active {
    background: #1e2433;
    transform: scale(0.98);
  }
  
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 0.75rem;
  }
  
  .card-title {
    flex: 1;
  }
  
  .card-title h4 {
    margin: 0;
    color: #e4e8f1;
    font-size: 1rem;
    font-weight: 600;
  }
  
  .job-id {
    color: #6b7280;
    font-size: 0.75rem;
    margin-top: 0.25rem;
  }
  
  .state-badge {
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
  }
  
  .state-badge.success {
    background: rgba(16, 185, 129, 0.2);
    color: #10b981;
  }
  
  .state-badge.info {
    background: rgba(59, 130, 246, 0.2);
    color: #3b82f6;
  }
  
  .state-badge.error {
    background: rgba(239, 68, 68, 0.2);
    color: #ef4444;
  }
  
  .state-badge.warning {
    background: rgba(245, 158, 11, 0.2);
    color: #f59e0b;
  }
  
  .state-badge.default {
    background: rgba(107, 114, 128, 0.2);
    color: #6b7280;
  }
  
  .card-meta {
    display: flex;
    gap: 1rem;
    margin-bottom: 0.75rem;
  }
  
  .meta-item {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    color: #6b7280;
    font-size: 0.8rem;
  }
  
  .meta-item svg {
    width: 14px;
    height: 14px;
  }
  
  .card-resources {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }
  
  .resource-badge {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.25rem 0.5rem;
    background: #1e2433;
    border: 1px solid #2a3142;
    border-radius: 4px;
    color: #9ca3af;
    font-size: 0.75rem;
  }
  
  .resource-badge.gpu {
    background: rgba(168, 85, 247, 0.1);
    border-color: rgba(168, 85, 247, 0.3);
    color: #a855f7;
  }
  
  .resource-badge svg {
    width: 12px;
    height: 12px;
  }
</style>