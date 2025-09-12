<script lang="ts">
  import { onMount, createEventDispatcher } from 'svelte';
  import { api } from '../services/api';
  import type { JobInfo } from '../types/api';
  
  const dispatch = createEventDispatcher();
  
  export let isOpen = false;
  export let currentHost: string | null = null;
  
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
  
  // Pagination
  const ITEMS_PER_PAGE = 10;
  let currentPage = 1;
  $: totalPages = Math.ceil(filteredScripts.length / ITEMS_PER_PAGE);
  $: paginatedScripts = filteredScripts.slice(
    (currentPage - 1) * ITEMS_PER_PAGE,
    currentPage * ITEMS_PER_PAGE
  );
  
  async function loadScriptHistory() {
    console.log('=== Loading script history ===');
    console.log('Current host:', currentHost);
    loading = true;
    errorMessage = '';
    try {
      // Fetch recent jobs from all hosts or specific host
      const hosts = currentHost ? [currentHost] : ['jz', 'adastra', 'entalpic'];
      console.log('Will check hosts:', hosts);
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
      console.log('Paginated scripts:', paginatedScripts);
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
      
      // Host filter
      if (filterHost !== 'all' && script.hostname !== filterHost) {
        return false;
      }
      
      // State filter
      if (filterState !== 'all' && script.state !== filterState) {
        return false;
      }
      
      return true;
    });
    
    console.log(`Filtered to ${filteredScripts.length} scripts from ${scripts.length} total`);
    currentPage = 1;
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
  
  function getStateColor(state: string): string {
    switch(state) {
      case 'R': return '#10b981';
      case 'PD': return '#f59e0b';
      case 'CD': return '#3b82f6';
      case 'F': return '#ef4444';
      case 'CA': return '#6b7280';
      default: return '#6b7280';
    }
  }
  
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
</script>

{#if isOpen}
<div class="modal-overlay" on:click={close}>
  <div class="modal-container" on:click|stopPropagation>
    <div class="modal-header">
      <h2>Script History</h2>
      <button class="close-btn" on:click={close}>
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"/>
        </svg>
      </button>
    </div>
    
    <div class="modal-filters">
      <input 
        type="text"
        placeholder="Search scripts..."
        bind:value={searchTerm}
        class="search-input"
      />
      
      <select bind:value={filterHost} class="filter-select">
        <option value="all">All Hosts</option>
        <option value="jz">Jean Zay</option>
        <option value="adastra">Adastra</option>
        <option value="entalpic">Entalpic</option>
        <option value="mbp">Local</option>
      </select>
      
      <select bind:value={filterState} class="filter-select">
        <option value="all">All States</option>
        <option value="CD">Completed</option>
        <option value="R">Running</option>
        <option value="PD">Pending</option>
        <option value="F">Failed</option>
        <option value="CA">Cancelled</option>
      </select>
    </div>
    
    <div class="modal-body">
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
      {:else if paginatedScripts.length === 0}
        <div class="empty-state">
          <p>No scripts found</p>
          <small>Try adjusting your filters or submit some jobs first</small>
        </div>
      {:else}
        <div class="scripts-grid">
          {#each paginatedScripts as script}
            <div 
              class="script-card"
              class:selected={selectedScript?.job_id === script.job_id}
              on:click={() => selectScript(script)}
            >
              <div class="script-header">
                <div class="script-info">
                  <h3>{script.job_name}</h3>
                  <div class="script-meta">
                    <span class="job-id">#{script.job_id}</span>
                    <span class="hostname">{script.hostname}</span>
                    <span 
                      class="state"
                      style="color: {getStateColor(script.state)}"
                    >
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
        
        {#if totalPages > 1}
          <div class="pagination">
            <button 
              on:click={() => currentPage--}
              disabled={currentPage === 1}
              class="page-btn"
            >
              Previous
            </button>
            <span class="page-info">
              Page {currentPage} of {totalPages}
            </span>
            <button 
              on:click={() => currentPage++}
              disabled={currentPage === totalPages}
              class="page-btn"
            >
              Next
            </button>
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
    
    <div class="modal-footer">
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
</div>
{/if}

<style>
  .modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    animation: fadeIn 0.2s;
  }
  
  @keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
  }
  
  .modal-container {
    background: var(--color-bg-primary);
    border-radius: 12px;
    width: 90%;
    max-width: 900px;
    max-height: 80vh;
    display: flex;
    flex-direction: column;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
    animation: slideUp 0.3s;
  }
  
  @keyframes slideUp {
    from {
      opacity: 0;
      transform: translateY(20px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
  
  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1.5rem;
    border-bottom: 1px solid var(--color-border);
  }
  
  .modal-header h2 {
    margin: 0;
    font-size: 1.25rem;
    color: var(--color-text-primary);
  }
  
  .close-btn {
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: none;
    color: var(--color-text-secondary);
    cursor: pointer;
    border-radius: 6px;
    transition: all 0.2s;
  }
  
  .close-btn:hover {
    background: var(--color-bg-secondary);
  }
  
  .close-btn svg {
    width: 20px;
    height: 20px;
  }
  
  .modal-filters {
    display: flex;
    gap: 1rem;
    padding: 1rem 1.5rem;
    background: var(--color-bg-secondary);
    border-bottom: 1px solid var(--color-border);
  }
  
  .search-input {
    flex: 1;
    padding: 0.5rem 1rem;
    border: 1px solid var(--color-border);
    border-radius: 6px;
    font-size: 0.875rem;
    background: var(--color-bg-primary);
  }
  
  .search-input:focus {
    outline: none;
    border-color: var(--color-primary);
  }
  
  .filter-select {
    padding: 0.5rem 1rem;
    border: 1px solid var(--color-border);
    border-radius: 6px;
    font-size: 0.875rem;
    background: var(--color-bg-primary);
    cursor: pointer;
  }
  
  .filter-select:focus {
    outline: none;
    border-color: var(--color-primary);
  }
  
  .modal-body {
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
    color: var(--color-text-secondary);
  }
  
  .spinner {
    width: 40px;
    height: 40px;
    border: 3px solid var(--color-border);
    border-top-color: var(--color-primary);
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
    color: var(--color-text-secondary);
  }
  
  .empty-state p {
    margin: 0 0 0.5rem 0;
    font-size: 1.1rem;
  }
  
  .error-state {
    text-align: center;
    padding: 3rem;
    color: var(--color-error);
  }
  
  .error-state p {
    margin: 0 0 0.5rem 0;
    font-size: 1.1rem;
    font-weight: 600;
  }
  
  .error-state small {
    display: block;
    margin-bottom: 1rem;
    color: var(--color-text-secondary);
  }
  
  .retry-btn {
    padding: 0.5rem 1rem;
    background: var(--color-primary);
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .retry-btn:hover {
    background: var(--color-primary-dark);
    transform: translateY(-2px);
  }
  
  .scripts-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 1rem;
  }
  
  .script-card {
    background: var(--color-bg-secondary);
    border: 1px solid var(--color-border);
    border-radius: 8px;
    padding: 1rem;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .script-card:hover {
    border-color: var(--color-primary);
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  }
  
  .script-card.selected {
    border-color: var(--color-primary);
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
    color: var(--color-text-primary);
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
    background: var(--color-bg-primary);
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
    border-top: 1px solid var(--color-border);
    font-size: 0.75rem;
    color: var(--color-text-secondary);
  }
  
  .cached {
    padding: 0.125rem 0.375rem;
    background: rgba(59, 130, 246, 0.1);
    color: #3b82f6;
    border-radius: 4px;
    font-size: 0.625rem;
  }
  
  .pagination {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 1rem;
    margin-top: 1.5rem;
    padding-top: 1.5rem;
    border-top: 1px solid var(--color-border);
  }
  
  .page-btn {
    padding: 0.5rem 1rem;
    background: var(--color-bg-secondary);
    border: 1px solid var(--color-border);
    border-radius: 6px;
    color: var(--color-text-primary);
    font-size: 0.875rem;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .page-btn:hover:not(:disabled) {
    background: var(--color-primary);
    color: white;
    border-color: var(--color-primary);
  }
  
  .page-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  
  .page-info {
    color: var(--color-text-secondary);
    font-size: 0.875rem;
  }
  
  .preview-section {
    background: var(--color-bg-secondary);
    border-top: 1px solid var(--color-border);
    max-height: 200px;
    display: flex;
    flex-direction: column;
  }
  
  .preview-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.75rem 1.5rem;
    border-bottom: 1px solid var(--color-border);
  }
  
  .preview-header h3 {
    margin: 0;
    font-size: 0.875rem;
    color: var(--color-text-primary);
  }
  
  .collapse-btn {
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: none;
    color: var(--color-text-secondary);
    cursor: pointer;
    border-radius: 4px;
    transition: all 0.2s;
  }
  
  .collapse-btn:hover {
    background: var(--color-bg-primary);
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
    color: var(--color-text-primary);
    overflow: auto;
    white-space: pre-wrap;
    word-break: break-all;
  }
  
  .modal-footer {
    display: flex;
    justify-content: flex-end;
    gap: 1rem;
    padding: 1.5rem;
    border-top: 1px solid var(--color-border);
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
    border: 1px solid var(--color-border);
    color: var(--color-text-primary);
  }
  
  .cancel-btn:hover {
    background: var(--color-bg-secondary);
  }
  
  .use-btn {
    background: var(--color-primary);
    border: none;
    color: white;
  }
  
  .use-btn:hover:not(:disabled) {
    background: var(--color-primary-dark);
  }
  
  .use-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  
  @media (max-width: 768px) {
    .modal-container {
      width: 100%;
      height: 100%;
      max-width: none;
      max-height: none;
      border-radius: 0;
    }
    
    .modal-filters {
      flex-direction: column;
    }
    
    .scripts-grid {
      grid-template-columns: 1fr;
    }
  }
</style>