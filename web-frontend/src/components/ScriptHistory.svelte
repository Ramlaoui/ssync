<script lang="ts">
  import { onMount, createEventDispatcher } from 'svelte';
  import { slide, fade } from 'svelte/transition';
  import { api } from '../services/api';
  import type { JobInfo } from '../types/api';
  import { jobUtils } from '../lib/jobUtils';
  import { X, History, FileText, Calendar, Server, Hash, Clock, CheckCircle, XCircle, AlertCircle } from 'lucide-svelte';

  const dispatch = createEventDispatcher();

  export let isOpen = false;
  export let currentHost: string | null = null;
  export let embedded = false; // New prop to indicate if embedded in another component
  export let isMobile = false;
  
  interface ScriptHistoryItem {
    job_id: string;
    job_name: string;
    hostname: string;
    submit_time: string;
    state: string;
    script_content?: string;
    cached_at?: string;
  }
  
  let loading = true;
  let scripts: ScriptHistoryItem[] = [];
  let filteredScripts: ScriptHistoryItem[] = [];
  let selectedScript: ScriptHistoryItem | null = null;
  let searchTerm = '';
  let filterHost = 'all';
  let filterState = 'all';
  let showPreview = false;
  let previewContent = '';
  let errorMessage = '';
  
  // Infinite scroll
  let displayCount = 20;
  let scrollContainer: HTMLElement;
  $: displayedScripts = filteredScripts.slice(0, displayCount);

  function handleScroll(event: Event) {
    const element = event.target as HTMLElement;
    const threshold = 100; // Load more when within 100px of bottom

    if (element.scrollHeight - element.scrollTop - element.clientHeight < threshold) {
      if (displayCount < filteredScripts.length) {
        displayCount = Math.min(displayCount + 20, filteredScripts.length);
      }
    }
  }
  
  async function loadScriptHistory() {
    console.log('=== Loading script history ===');
    console.log('Current host:', currentHost);
    loading = true;
    errorMessage = '';
    try {
      // Fetch available hosts dynamically
      let hosts = [];
      if (currentHost) {
        hosts = [currentHost];
      } else {
        try {
          console.log('Fetching available hosts...');
          const hostsResponse = await api.get('/api/hosts');
          hosts = hostsResponse.data.map(host => host.hostname);
          console.log('Available hosts:', hosts);
        } catch (e) {
          console.warn('Failed to fetch hosts, using fallback:', e);
          // Fallback to hardcoded hosts if API fails
          hosts = ['jz', 'adastra', 'entalpic'];
        }
      }

      console.log('Will check hosts:', hosts);

      if (hosts.length === 0) {
        console.warn('No hosts available to check for script history');
        errorMessage = 'No SLURM hosts are configured or available';
        scripts = [];
        return;
      }

      const allScripts: ScriptHistoryItem[] = [];

      for (const host of hosts) {
        try {
          console.log(`\nFetching jobs from ${host}...`);
          const response = await api.get(`/api/status`, {
            params: {
              host: host,
              limit: 20
            }
          });
          
          // The API returns a list of JobStatusResponse objects
          // Each has a hostname and jobs array
          console.log(`Response type: ${typeof response.data}, isArray: ${Array.isArray(response.data)}`);
          console.log('Response data:', response.data);
          
          let jobs = [];
          if (Array.isArray(response.data)) {
            // Find the response for this host
            const hostResponse = response.data.find(r => r.hostname === host);
            console.log(`Host response for ${host}:`, hostResponse);
            jobs = hostResponse?.jobs || [];
          } else if (response.data?.jobs) {
            jobs = response.data.jobs;
          }
          console.log(`Found ${jobs.length} jobs from ${host}`);
          
          for (const job of jobs) {
            // Try to fetch script from cache
            try {
              console.log(`  Fetching script for job ${job.job_id}...`);
              const scriptResponse = await api.get(`/api/jobs/${job.job_id}/script`, {
                params: { host: host }
              });
              console.log(`  Script response:`, scriptResponse.data);
              
              // The API returns script_content, not script
              if (scriptResponse.data?.script_content) {
                console.log(`  ✓ Script found for job ${job.job_id} (${scriptResponse.data.script_content.length} chars)`);
                allScripts.push({
                  job_id: job.job_id,
                  job_name: job.name || 'Unnamed Job',
                  hostname: host,
                  submit_time: job.submit_time,
                  state: job.state,
                  script_content: scriptResponse.data.script_content,
                  cached_at: scriptResponse.data.cached_at
                });
              } else {
                console.log(`  ✗ No script_content field in response for job ${job.job_id}`);
              }
            } catch (e) {
              // Script not available, don't add to the list
              console.log(`  ✗ Error fetching script for job ${job.job_id}:`, e);
            }
          }
        } catch (err) {
          console.error(`Failed to load scripts from ${host}:`, err);
        }
      }
      
      console.log(`\n=== Total scripts loaded: ${allScripts.length} ===`);
      console.log('All scripts:', allScripts);
      
      // Sort by submit time (newest first)
      scripts = allScripts.sort((a, b) => {
        const dateA = new Date(a.submit_time || 0).getTime();
        const dateB = new Date(b.submit_time || 0).getTime();
        return dateB - dateA;
      });
      
      console.log('After sorting, scripts array:', scripts);
      filterScripts();
      console.log('After filtering, filteredScripts:', filteredScripts);
      console.log('Displayed scripts:', displayedScripts);
    } catch (err) {
      console.error('Failed to load script history:', err);
      errorMessage = `Failed to load script history: ${err.message || 'Unknown error'}`;
      scripts = [];
    } finally {
      loading = false;
    }
  }
  
  function filterScripts() {
    console.log('Filtering scripts with:', { searchTerm, filterHost, filterState });
    
    filteredScripts = scripts.filter(script => {
      // Search filter
      if (searchTerm && searchTerm.trim()) {
        const term = searchTerm.toLowerCase().trim();
        const matches = 
          (script.job_name?.toLowerCase() || '').includes(term) ||
          (script.job_id?.toLowerCase() || '').includes(term) ||
          (script.hostname?.toLowerCase() || '').includes(term) ||
          (script.script_content?.toLowerCase() || '').includes(term);
        if (!matches) return false;
      }
      
      // Host filter - when embedded, only show jobs from currentHost
      if (embedded && currentHost && script.hostname !== currentHost) {
        return false;
      } else if (!embedded && filterHost !== 'all' && script.hostname !== filterHost) {
        return false;
      }
      
      // State filter
      if (filterState !== 'all' && script.state !== filterState) {
        return false;
      }
      
      return true;
    });
    
    console.log(`Filtered to ${filteredScripts.length} scripts from ${scripts.length} total`);
  }
  
  function selectScript(script: ScriptHistoryItem) {
    selectedScript = script;
    if (script.script_content) {
      previewContent = script.script_content;
      showPreview = true;
    }
  }
  
  function useScript() {
    if (selectedScript?.script_content) {
      dispatch('select', {
        script: selectedScript.script_content,
        jobName: selectedScript.job_name,
        hostname: selectedScript.hostname
      });
      close();
    }
  }
  
  function close() {
    isOpen = false;
    dispatch('close');
  }
  
  function formatDate(dateStr: string): string {
    if (!dateStr) return 'Unknown';
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  }
  
  // Use centralized job utilities
  
  function getStateName(state: string): string {
    switch(state) {
      case 'R': return 'Running';
      case 'PD': return 'Pending';
      case 'CD': return 'Completed';
      case 'F': return 'Failed';
      case 'CA': return 'Cancelled';
      default: return state;
    }
  }
  
  onMount(() => {
    // Load history if already open when component mounts
    if (isOpen) {
      loadScriptHistory();
    }
  });
  
  // Watch for changes to isOpen and load history when opened
  $: if (isOpen && loading && scripts.length === 0) {
    loadScriptHistory();
  }
  
  // Re-filter whenever search or filters change
  $: searchTerm, filterHost, filterState, filterScripts();

  // Reset display count when filters change
  $: if (searchTerm || filterHost || filterState) {
    displayCount = 20;
  }
</script>

{#if isOpen}
<!-- Overlay for mobile/desktop -->
<div class="sidebar-overlay" on:click|preventDefault|stopPropagation={close} transition:fade={{ duration: 200 }}></div>

<!-- Sidebar -->
<div class="sidebar-container {isMobile ? 'mobile' : 'desktop'}" on:click|stopPropagation transition:slide={{ duration: 300, axis: 'x' }}>
  <div class="sidebar-header">
    <div class="sidebar-title">
      <History class="w-5 h-5" />
      <h2>Script History</h2>
    </div>
    <button class="close-btn" on:click={close}>
      <X class="w-5 h-5" />
    </button>
  </div>
    
    <div class="sidebar-filters">
      <input 
        type="text"
        placeholder="Search scripts..."
        bind:value={searchTerm}
        class="search-input"
      />
      
      {#if !embedded}
        <select bind:value={filterHost} class="filter-select">
          <option value="all">All Hosts</option>
          <option value="jz">Jean Zay</option>
          <option value="adastra">Adastra</option>
          <option value="entalpic">Entalpic</option>
          <option value="mbp">Local</option>
        </select>
      {/if}
      
      <select bind:value={filterState} class="filter-select">
        <option value="all">All States</option>
        <option value="CD">Completed</option>
        <option value="R">Running</option>
        <option value="PD">Pending</option>
        <option value="F">Failed</option>
        <option value="CA">Cancelled</option>
      </select>
    </div>
    
    <div class="sidebar-body" bind:this={scrollContainer} on:scroll={handleScroll}>
      {#if loading}
        <div class="loading">
          <div class="spinner"></div>
          <p>Loading script history...</p>
        </div>
      {:else if errorMessage}
        <div class="error-state">
          <p>Error</p>
          <small>{errorMessage}</small>
          <button class="retry-btn" on:click={loadScriptHistory}>Retry</button>
        </div>
      {:else if displayedScripts.length === 0}
        <div class="empty-state">
          <p>No scripts found</p>
          <small>
            {#if scripts.length === 0}
              No job scripts are available from the configured hosts. Try submitting some jobs first, or check if your hosts are accessible.
            {:else}
              Try adjusting your filters to see more results.
            {/if}
          </small>
        </div>
      {:else}
        <div class="scripts-grid">
          {#each displayedScripts as script}
            <div 
              class="script-card"
              class:selected={selectedScript?.job_id === script.job_id}
              on:click={() => selectScript(script)}
            >
              <div class="script-header">
                <div class="script-info">
                  <h3>{script.job_name}</h3>
                  <div class="script-meta">
                    <span class="job-id">
                      <Hash class="w-3 h-3" style="display: inline; vertical-align: middle;"/> {script.job_id}
                    </span>
                    {#if !embedded}
                      <span class="hostname">
                        <Server class="w-3 h-3" style="display: inline; vertical-align: middle;"/> {script.hostname}
                      </span>
                    {/if}
                    <span
                      class="state"
                      style="color: {jobUtils.getStateColor(script.state)}"
                    >
                      {#if script.state === 'CD'}
                        <CheckCircle class="w-3 h-3" style="display: inline; vertical-align: middle;"/>
                      {:else if script.state === 'F'}
                        <XCircle class="w-3 h-3" style="display: inline; vertical-align: middle;"/>
                      {:else if script.state === 'R'}
                        <Clock class="w-3 h-3" style="display: inline; vertical-align: middle;"/>
                      {:else}
                        <AlertCircle class="w-3 h-3" style="display: inline; vertical-align: middle;"/>
                      {/if}
                      {getStateName(script.state)}
                    </span>
                  </div>
                </div>
                {#if script.script_content}
                  <div class="script-badge">Script Available</div>
                {:else}
                  <div class="script-badge unavailable">No Script</div>
                {/if}
              </div>
              
              <div class="script-footer">
                <span class="submit-time">{formatDate(script.submit_time)}</span>
                {#if script.cached_at}
                  <span class="cached">Cached</span>
                {/if}
              </div>
            </div>
          {/each}
        </div>

        {#if displayCount < filteredScripts.length}
          <div class="loading-more">
            <div class="spinner"></div>
            <p>Scroll for more...</p>
          </div>
        {/if}
      {/if}
    </div>
    
    {#if showPreview && selectedScript}
      <div class="preview-section">
        <div class="preview-header">
          <h3>Script Preview</h3>
          <button class="collapse-btn" on:click={() => showPreview = false}>
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M7 10l5 5 5-5z"/>
            </svg>
          </button>
        </div>
        <pre class="script-preview">{previewContent}</pre>
      </div>
    {/if}
    
    <div class="sidebar-footer">
      <button class="cancel-btn" on:click={close}>Cancel</button>
      <button
        class="use-btn"
        disabled={!selectedScript?.script_content}
        on:click={useScript}
      >
        Use This Script
      </button>
    </div>
</div>
{/if}

<style>
  .sidebar-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.3);
    backdrop-filter: blur(2px);
    z-index: 999;
  }

  .sidebar-container {
    position: fixed;
    top: 0;
    right: 0;
    height: 100vh;
    width: 480px;
    max-width: 90%;
    background: white;
    box-shadow: -4px 0 24px rgba(0, 0, 0, 0.1);
    display: flex;
    flex-direction: column;
    z-index: 1000;
    overflow: hidden;
  }
  
  .sidebar-header {
    padding: 1.25rem 1.5rem;
    border-bottom: 1px solid #e5e7eb;
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: white;
  }

  .sidebar-title {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    color: #111827;
  }

  .sidebar-title h2 {
    margin: 0;
    font-size: 1.125rem;
    font-weight: 600;
  }
  
  .close-btn {
    background: none;
    border: none;
    color: #6b7280;
    cursor: pointer;
    padding: 0.5rem;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 0.5rem;
    transition: all 0.2s;
  }

  .close-btn:hover {
    background: #f3f4f6;
    color: #111827;
  }
  
  .sidebar-filters {
    display: flex;
    gap: 1rem;
    padding: 1rem 1.5rem;
    background: #f9fafb;
    border-bottom: 1px solid #e5e7eb;
  }
  
  .search-input {
    flex: 1;
    padding: 0.5rem 1rem;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    font-size: 0.875rem;
    background: #f9fafb;
  }
  
  .search-input:focus {
    outline: none;
    border-color: #6366f1;
  }
  
  .filter-select {
    padding: 0.5rem 1rem;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    font-size: 0.875rem;
    background: #f9fafb;
    cursor: pointer;
  }
  
  .filter-select:focus {
    outline: none;
    border-color: #6366f1;
  }
  
  .sidebar-body {
    flex: 1;
    overflow-y: auto;
    padding: 1.5rem;
  }
  
  .loading {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 3rem;
    color: #6b7280;
  }
  
  .spinner {
    width: 40px;
    height: 40px;
    border: 3px solid #e5e7eb;
    border-top-color: #6366f1;
    border-radius: 50%;
    animation: spin 1s linear infinite;
    margin-bottom: 1rem;
  }
  
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  
  .empty-state {
    text-align: center;
    padding: 3rem;
    color: #6b7280;
  }
  
  .empty-state p {
    margin: 0 0 0.5rem 0;
    font-size: 1.1rem;
  }
  
  .error-state {
    text-align: center;
    padding: 3rem;
    color: #ef4444;
  }
  
  .error-state p {
    margin: 0 0 0.5rem 0;
    font-size: 1.1rem;
    font-weight: 600;
  }
  
  .error-state small {
    display: block;
    margin-bottom: 1rem;
    color: #6b7280;
  }
  
  .retry-btn {
    padding: 0.5rem 1rem;
    background: #6366f1;
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .retry-btn:hover {
    background: #4f46e5;
    transform: translateY(-2px);
  }
  
  .scripts-grid {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  
  .script-card {
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 1rem;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .script-card:hover {
    border-color: #6366f1;
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  }
  
  .script-card.selected {
    border-color: #6366f1;
    background: rgba(59, 130, 246, 0.05);
  }
  
  .script-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 0.75rem;
  }
  
  .script-info h3 {
    margin: 0 0 0.5rem 0;
    font-size: 0.875rem;
    color: #111827;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  
  .script-meta {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
  }
  
  .job-id,
  .hostname,
  .state {
    font-size: 0.75rem;
    padding: 0.125rem 0.375rem;
    background: rgba(0, 0, 0, 0.03);
    border-radius: 4px;
  }
  
  .script-badge {
    padding: 0.25rem 0.5rem;
    background: rgba(16, 185, 129, 0.1);
    color: #10b981;
    border-radius: 4px;
    font-size: 0.625rem;
    font-weight: 500;
  }
  
  .script-badge.unavailable {
    background: rgba(107, 114, 128, 0.1);
    color: #6b7280;
  }
  
  .script-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-top: 0.75rem;
    border-top: 1px solid #e5e7eb;
    font-size: 0.75rem;
    color: #6b7280;
  }
  
  .cached {
    padding: 0.125rem 0.375rem;
    background: rgba(59, 130, 246, 0.1);
    color: #3b82f6;
    border-radius: 4px;
    font-size: 0.625rem;
  }
  
  .loading-more {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    color: #6b7280;
  }

  .loading-more .spinner {
    width: 24px;
    height: 24px;
    margin-bottom: 0.5rem;
  }

  .loading-more p {
    font-size: 0.875rem;
    color: #9ca3af;
  }
  
  .preview-section {
    background: #f9fafb;
    border-top: 1px solid #e5e7eb;
    max-height: 200px;
    display: flex;
    flex-direction: column;
  }
  
  .preview-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.75rem 1.5rem;
    border-bottom: 1px solid #e5e7eb;
  }
  
  .preview-header h3 {
    margin: 0;
    font-size: 0.875rem;
    color: #111827;
  }
  
  .collapse-btn {
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: none;
    color: #6b7280;
    cursor: pointer;
    border-radius: 4px;
    transition: all 0.2s;
  }
  
  .collapse-btn:hover {
    background: #f9fafb;
  }
  
  .collapse-btn svg {
    width: 16px;
    height: 16px;
    transform: rotate(180deg);
  }
  
  .script-preview {
    flex: 1;
    margin: 0;
    padding: 1rem 1.5rem;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
    line-height: 1.5;
    color: #111827;
    overflow: auto;
    white-space: pre-wrap;
    word-break: break-all;
  }
  
  .sidebar-footer {
    display: flex;
    justify-content: flex-end;
    gap: 1rem;
    padding: 1.5rem;
    border-top: 1px solid #e5e7eb;
  }
  
  .cancel-btn,
  .use-btn {
    padding: 0.625rem 1.25rem;
    border-radius: 6px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .cancel-btn {
    background: transparent;
    border: 1px solid #e5e7eb;
    color: #111827;
  }
  
  .cancel-btn:hover {
    background: #f9fafb;
  }
  
  .use-btn {
    background: #6366f1;
    border: none;
    color: white;
  }
  
  .use-btn:hover:not(:disabled) {
    background: #4f46e5;
  }
  
  .use-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  
  @media (max-width: 768px) {
    .sidebar-overlay {
      right: 75%;
      background: rgba(0, 0, 0, 0.2);
    }

    .sidebar-container {
      width: 75%;
      max-width: 320px;
      left: 25%;
      right: auto;
    }

    .sidebar-filters {
      flex-direction: column;
    }

    .scripts-grid {
      grid-template-columns: 1fr;
    }
  }
</style>