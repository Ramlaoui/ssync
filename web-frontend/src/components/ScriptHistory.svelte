<script lang="ts">
  import { run, preventDefault, stopPropagation, createBubbler } from 'svelte/legacy';

  const bubble = createBubbler();
  import { onMount, createEventDispatcher } from 'svelte';
  import { slide, fade } from 'svelte/transition';
  import { api } from '../services/api';
  import type { JobInfo } from '../types/api';
  import { jobUtils } from '../lib/jobUtils';
  import { X, History, FileText, Calendar, Server, Hash, Clock, CheckCircle, XCircle, AlertCircle } from 'lucide-svelte';

  const dispatch = createEventDispatcher();

  interface Props {
    isOpen?: boolean;
    currentHost?: string | null;
    embedded?: boolean; // New prop to indicate if embedded in another component
    isMobile?: boolean;
  }

  let {
    isOpen = $bindable(false),
    currentHost = null,
    embedded = false,
    isMobile = false
  }: Props = $props();
  
  interface ScriptHistoryItem {
    job_id: string;
    job_name: string;
    hostname: string;
    submit_time: string;
    state: string;
    script_content?: string;
    cached_at?: string;
  }
  
  let loading = $state(true);
  let scripts: ScriptHistoryItem[] = $state([]);
  let filteredScripts: ScriptHistoryItem[] = $state([]);
  let selectedScript: ScriptHistoryItem | null = $state(null);
  let searchTerm = $state('');
  let filterHost = $state('all');
  let filterState = $state('all');
  let showPreview = $state(false);
  let previewContent = $state('');
  let errorMessage = $state('');
  let availableHosts: string[] = $state([]);
  
  // Infinite scroll
  let displayCount = $state(20);
  let scrollContainer: HTMLElement = $state();
  let displayedScripts = $derived(filteredScripts.slice(0, displayCount));

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
    console.log('isOpen:', isOpen);

    // Debug localStorage
    const localStorageData = localStorage.getItem('scriptHistory');
    console.log('localStorage scriptHistory raw:', localStorageData);

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
          console.error('Failed to fetch hosts:', e);
          errorMessage = 'Failed to fetch hosts. Please check your connection and try again.';
          scripts = [];
          return;
        }
      }

      console.log('Will check hosts:', hosts);

      if (hosts.length === 0) {
        console.warn('No hosts available to check for script history');
        errorMessage = 'No Slurm hosts are configured or available';
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
      
      console.log(`\n=== Total scripts loaded from API: ${allScripts.length} ===`);

      // Always also check localStorage (not just when API returns 0)
      console.log('Checking localStorage for additional scripts...');
      try {
        const localHistory = JSON.parse(localStorage.getItem('scriptHistory') || '[]');
        console.log(`Found ${localHistory.length} scripts in localStorage`);

        // Add localStorage scripts that aren't already in allScripts
        const existingIds = new Set(allScripts.map(s => s.job_id));
        const newScripts = localHistory.filter(s => !existingIds.has(s.job_id));
        console.log(`Adding ${newScripts.length} unique scripts from localStorage`);
        allScripts.push(...newScripts);
      } catch (e) {
        console.error('Failed to load from localStorage:', e);
      }

      console.log(`Total scripts after localStorage: ${allScripts.length}`);
      console.log('All scripts:', allScripts);

      // Sort by submit time (newest first)
      scripts = allScripts.sort((a, b) => {
        const dateA = new Date(a.submit_time || 0).getTime();
        const dateB = new Date(b.submit_time || 0).getTime();
        return dateB - dateA;
      });

      // Extract unique hosts from scripts for the filter dropdown
      availableHosts = Array.from(new Set(scripts.map(s => s.hostname))).sort();
      console.log('Available hosts for filter:', availableHosts);

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
  run(() => {
    if (isOpen) {
      console.log('ScriptHistory isOpen changed, loading scripts...');
      loadScriptHistory();
    }
  });
  
  // Re-filter whenever search or filters change
  run(() => {
    searchTerm, filterHost, filterState, filterScripts();
  });

  // Reset display count when filters change
  run(() => {
    if (searchTerm || filterHost || filterState) {
      displayCount = 20;
    }
  });
</script>

{#if isOpen}
  <!-- Overlay for mobile/desktop -->
  <div
    class="sidebar-overlay"
    onclick={stopPropagation(preventDefault(close))}
    onkeydown={() => {}}
    role="presentation"
    transition:fade={{ duration: 200 }}
  ></div>

  <!-- Sidebar -->
  <div
    class="sidebar-container {isMobile ? 'mobile' : 'desktop'}"
    onclick={stopPropagation(bubble("click"))}
    onkeydown={() => {}}
    role="dialog"
    aria-modal="true"
    tabindex="-1"
    transition:slide={{ duration: 300, axis: "x" }}
  >
    <div class="sidebar-header">
      <div class="sidebar-title">
        <History class="w-5 h-5" />
        <h2>Script History</h2>
      </div>
      <button class="close-btn" onclick={close}>
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
          {#each availableHosts as host}
            <option value={host}>{host}</option>
          {/each}
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

    <div
      class="sidebar-body"
      bind:this={scrollContainer}
      onscroll={handleScroll}
    >
      {#if loading}
        <div class="loading">
          <div class="spinner"></div>
          <p>Loading script history...</p>
        </div>
      {:else if errorMessage}
        <div class="error-state">
          <p>Error</p>
          <small>{errorMessage}</small>
          <button class="retry-btn" onclick={loadScriptHistory}>Retry</button>
        </div>
      {:else if displayedScripts.length === 0}
        <div class="empty-state">
          <p>No scripts found</p>
          <small>
            {#if scripts.length === 0}
              No job scripts are available from the configured hosts. Try
              submitting some jobs first, or check if your hosts are accessible.
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
              onclick={() => selectScript(script)}
              onkeydown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  selectScript(script);
                }
              }}
              role="button"
              tabindex="0"
            >
              <div class="script-header">
                <div class="script-info">
                  <h3>{script.job_name}</h3>
                  <div class="script-meta">
                    <span class="job-id">
                      <Hash
                        class="w-3 h-3"
                        style="display: inline; vertical-align: middle;"
                      />
                      {script.job_id}
                    </span>
                    {#if !embedded}
                      <span class="hostname">
                        <Server
                          class="w-3 h-3"
                          style="display: inline; vertical-align: middle;"
                        />
                        {script.hostname}
                      </span>
                    {/if}
                    <span
                      class="state"
                      style="color: {jobUtils.getStateColor(script.state)}"
                    >
                      {#if script.state === "CD"}
                        <CheckCircle
                          class="w-3 h-3"
                          style="display: inline; vertical-align: middle;"
                        />
                      {:else if script.state === "F"}
                        <XCircle
                          class="w-3 h-3"
                          style="display: inline; vertical-align: middle;"
                        />
                      {:else if script.state === "R"}
                        <Clock
                          class="w-3 h-3"
                          style="display: inline; vertical-align: middle;"
                        />
                      {:else}
                        <AlertCircle
                          class="w-3 h-3"
                          style="display: inline; vertical-align: middle;"
                        />
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
                <span class="submit-time">{formatDate(script.submit_time)}</span
                >
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
          <button
            class="collapse-btn"
            onclick={() => (showPreview = false)}
            aria-label="Collapse preview"
          >
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M7 10l5 5 5-5z" />
            </svg>
          </button>
        </div>
        <pre class="script-preview">{previewContent}</pre>
      </div>
    {/if}

    <div class="sidebar-footer">
      <button class="cancel-btn" onclick={close}>Cancel</button>
      <button
        class="use-btn"
        disabled={!selectedScript?.script_content}
        onclick={useScript}
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
    background: color-mix(in srgb, var(--foreground) 30%, transparent);
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
    background: var(--card);
    box-shadow: -4px 0 24px
      color-mix(in srgb, var(--foreground) 10%, transparent);
    display: flex;
    flex-direction: column;
    z-index: 1000;
    overflow: hidden;
  }

  .sidebar-header {
    padding: 1.25rem 1.5rem;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: var(--card);
  }

  .sidebar-title {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    color: var(--foreground);
  }

  .sidebar-title h2 {
    margin: 0;
    font-size: 1.125rem;
    font-weight: 600;
  }

  .close-btn {
    background: none;
    border: none;
    color: var(--muted-foreground);
    cursor: pointer;
    padding: 0.5rem;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 0.5rem;
    transition: all 0.2s;
  }

  .close-btn:hover {
    background: var(--secondary);
    color: var(--foreground);
  }

  .sidebar-filters {
    display: flex;
    gap: 1rem;
    padding: 1rem 1.5rem;
    background: var(--secondary);
    border-bottom: 1px solid var(--border);
  }

  .search-input {
    flex: 1;
    padding: 0.5rem 1rem;
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 0.875rem;
    background: var(--secondary);
    color: var(--foreground);
  }

  .search-input:focus {
    outline: none;
    border-color: var(--accent);
  }

  .filter-select {
    padding: 0.5rem 1rem;
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 0.875rem;
    background: var(--secondary);
    color: var(--foreground);
    cursor: pointer;
  }

  .filter-select:focus {
    outline: none;
    border-color: var(--accent);
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
    color: var(--muted-foreground);
  }

  .spinner {
    width: 40px;
    height: 40px;
    border: 3px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 1s linear infinite;
    margin-bottom: 1rem;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  .empty-state {
    text-align: center;
    padding: 3rem;
    color: var(--muted-foreground);
  }

  .empty-state p {
    margin: 0 0 0.5rem 0;
    font-size: 1.1rem;
  }

  .error-state {
    text-align: center;
    padding: 3rem;
    color: var(--destructive);
  }

  .error-state p {
    margin: 0 0 0.5rem 0;
    font-size: 1.1rem;
    font-weight: 600;
  }

  .error-state small {
    display: block;
    margin-bottom: 1rem;
    color: var(--muted-foreground);
  }

  .retry-btn {
    padding: 0.5rem 1rem;
    background: var(--accent);
    color: var(--card);
    border: none;
    border-radius: 6px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
  }

  .retry-btn:hover {
    background: color-mix(in srgb, var(--accent) 80%, transparent);
    transform: translateY(-2px);
  }

  .scripts-grid {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .script-card {
    background: var(--secondary);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1rem;
    cursor: pointer;
    transition: all 0.2s;
  }

  .script-card:hover {
    border-color: var(--accent);
    transform: translateY(-2px);
    box-shadow: 0 4px 12px
      color-mix(in srgb, var(--foreground) 10%, transparent);
  }

  .script-card.selected {
    border-color: var(--accent);
    background: color-mix(in srgb, var(--accent) 5%, var(--secondary));
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
    color: var(--foreground);
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
    background: color-mix(in srgb, var(--foreground) 3%, transparent);
    border-radius: 4px;
    color: var(--foreground);
  }

  .script-badge {
    padding: 0.25rem 0.5rem;
    background: color-mix(in srgb, var(--success) 10%, transparent);
    color: var(--success);
    border-radius: 4px;
    font-size: 0.625rem;
    font-weight: 500;
  }

  .script-badge.unavailable {
    background: color-mix(in srgb, var(--muted-foreground) 10%, transparent);
    color: var(--muted-foreground);
  }

  .script-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-top: 0.75rem;
    border-top: 1px solid var(--border);
    font-size: 0.75rem;
    color: var(--muted-foreground);
  }

  .cached {
    padding: 0.125rem 0.375rem;
    background: color-mix(in srgb, var(--accent) 10%, transparent);
    color: var(--accent);
    border-radius: 4px;
    font-size: 0.625rem;
  }

  .loading-more {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    color: var(--muted-foreground);
  }

  .loading-more .spinner {
    width: 24px;
    height: 24px;
    margin-bottom: 0.5rem;
  }

  .loading-more p {
    font-size: 0.875rem;
    color: var(--muted-foreground);
  }

  .preview-section {
    background: var(--secondary);
    border-top: 1px solid var(--border);
    max-height: 200px;
    display: flex;
    flex-direction: column;
  }

  .preview-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.75rem 1.5rem;
    border-bottom: 1px solid var(--border);
  }

  .preview-header h3 {
    margin: 0;
    font-size: 0.875rem;
    color: var(--foreground);
  }

  .collapse-btn {
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: none;
    color: var(--muted-foreground);
    cursor: pointer;
    border-radius: 4px;
    transition: all 0.2s;
  }

  .collapse-btn:hover {
    background: var(--secondary);
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
    font-family: "JetBrains Mono", monospace;
    font-size: 0.75rem;
    line-height: 1.5;
    color: var(--foreground);
    overflow: auto;
    white-space: pre-wrap;
    word-break: break-all;
  }

  .sidebar-footer {
    display: flex;
    justify-content: flex-end;
    gap: 1rem;
    padding: 1.5rem;
    border-top: 1px solid var(--border);
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
    border: 1px solid var(--border);
    color: var(--foreground);
  }

  .cancel-btn:hover {
    background: var(--secondary);
  }

  .use-btn {
    background: var(--accent);
    border: none;
    color: var(--card);
  }

  .use-btn:hover:not(:disabled) {
    background: color-mix(in srgb, var(--accent) 80%, transparent);
  }

  .use-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  @media (max-width: 768px) {
    .sidebar-overlay {
      right: 75%;
      background: color-mix(in srgb, var(--foreground) 20%, transparent);
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
