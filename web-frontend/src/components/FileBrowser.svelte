<script lang="ts">
  import { api } from "../services/api";
  import type { AxiosError } from "axios";
  import { createEventDispatcher } from "svelte";
  import { Search, Home, Folder, FolderOpen, File, ArrowUp, Loader2, AlertCircle, Key } from "lucide-svelte";
  import Button from "../lib/components/ui/Button.svelte";

  const dispatch = createEventDispatcher<{
    pathSelected: string;
    directoryChanged: string;
  }>();

  export let sourceDir = "";
  export let initialPath = "/";

  // Browser state
  let localEntries: { name: string; path: string; is_dir: boolean }[] = [];
  let filteredEntries: { name: string; path: string; is_dir: boolean }[] = [];
  let currentLocalPath = "/";
  let maxEntries = 100;
  let showHiddenFiles = false;
  let showFilesInBrowser = false;
  let loading = false;
  let error: string | null = null;
  let searchQuery = "";

  // Fuzzy search functionality
  function fuzzyMatch(query: string, target: string): { score: number; matches: number[] } {
    if (!query) return { score: 1, matches: [] };

    const queryLower = query.toLowerCase();
    const targetLower = target.toLowerCase();

    // Exact match gets highest score
    if (targetLower.includes(queryLower)) {
      const startIndex = targetLower.indexOf(queryLower);
      return {
        score: 100 - startIndex,
        matches: Array.from({ length: query.length }, (_, i) => startIndex + i)
      };
    }

    // Fuzzy matching
    let queryIndex = 0;
    let matches: number[] = [];
    let score = 0;

    for (let i = 0; i < target.length && queryIndex < queryLower.length; i++) {
      if (targetLower[i] === queryLower[queryIndex]) {
        matches.push(i);
        score += (target.length - i) / target.length * 10; // Earlier matches score higher
        queryIndex++;
      }
    }

    if (queryIndex === queryLower.length) {
      return { score, matches };
    }

    return { score: 0, matches: [] };
  }

  function filterEntries() {
    if (!searchQuery.trim()) {
      filteredEntries = localEntries;
      return;
    }

    const results = localEntries
      .map(entry => ({
        ...entry,
        matchResult: fuzzyMatch(searchQuery, entry.name)
      }))
      .filter(entry => entry.matchResult.score > 0)
      .sort((a, b) => {
        // Sort by type first (dirs, then files), then by score
        if (a.is_dir !== b.is_dir) {
          return a.is_dir ? -1 : 1;
        }
        return b.matchResult.score - a.matchResult.score;
      });

    filteredEntries = results;
  }

  // Reactive filtering
  $: {
    // Trigger when either localEntries or searchQuery changes
    localEntries;
    searchQuery;
    filterEntries();
  }

  // Load directory browser in background on mount
  setTimeout(() => {
    // Try initialPath first, but only if it's likely to be allowed
    const allowedPaths = ["/home", "/Users", "/opt", "/mnt", "/tmp", "/var/tmp"];
    const isAllowedPath = initialPath && allowedPaths.some(allowed => initialPath.startsWith(allowed));

    if (isAllowedPath) {
      loadLocalPath(initialPath).catch(() => {
        // Fallback to user home
        loadLocalPath("/home").catch(() => {});
      });
    } else {
      // Start with user home directory as it's most likely to work
      loadLocalPath("/home").catch(() => {
        // Try other allowed paths
        tryAllowedPaths();
      });
    }
  }, 100);

  // Try different allowed paths to find one that works
  async function tryAllowedPaths() {
    const allowedPaths = ["/tmp", "/opt", "/mnt", "/var/tmp"];
    for (const path of allowedPaths) {
      try {
        await loadLocalPath(path);
        break; // Success, stop trying
      } catch (error) {
        continue; // Try next path
      }
    }
  }

  // Load entries for a server-local path using backend API
  async function loadLocalPath(path: string): Promise<void> {
    loading = true;
    error = null;
    searchQuery = ""; // Clear search when navigating

    try {
      const response = await api.get('/api/local/list', {
        params: {
          path,
          limit: maxEntries,
          show_hidden: showHiddenFiles,
          dirs_only: !showFilesInBrowser,
        },
      });
      localEntries = response.data.entries || [];
      currentLocalPath = response.data.path || path;
      // Immediately update filtered entries
      filteredEntries = localEntries;

    } catch (err: unknown) {
      const axiosError = err as AxiosError;

      if (axiosError.response?.status === 401) {
        error = "Authentication required. Please configure your API key in settings.";
      } else if (axiosError.response?.status === 403) {
        const responseText = axiosError.response?.data?.detail || '';
        if (responseText.includes('Access denied') || responseText.includes('Path must be under')) {
          error = `Access denied. For security, only these directories are allowed: /home, /Users, /opt, /mnt, /tmp, /var/tmp, and your user directory.`;
        } else {
          error = "Access forbidden. Please configure your API key in settings.";
        }
      } else if (axiosError.response?.status === 404) {
        error = `Directory not found: ${path}`;
      } else {
        error = `Failed to list directory: ${axiosError.message || 'Unknown error'}`;
      }

      localEntries = [];
      filteredEntries = [];
    } finally {
      loading = false;
    }
  }

  function selectCurrentLocalPath(): void {
    if (currentLocalPath) {
      sourceDir = currentLocalPath;
      dispatch("pathSelected", currentLocalPath);
    }
  }

  function navigateUp(): void {
    if (currentLocalPath && currentLocalPath !== "/") {
      const parentPath =
        currentLocalPath.split("/").slice(0, -1).join("/") || "/";
      loadLocalPath(parentPath);
    }
  }

  function goToHome(): void {
    loadLocalPath("/home");
  }

  function handleDirectoryClick(entryPath: string): void {
    loadLocalPath(entryPath);
  }

  function handleOptionsChange(): void {
    if (currentLocalPath) {
      loadLocalPath(currentLocalPath);
    }
  }

  // Quick path navigation (only allowed paths) - disabled for now
  const quickPaths = [];
</script>

<div class="flex flex-col h-full bg-white rounded-lg border border-gray-200">
  <!-- Simplified Header -->
  <div class="flex-shrink-0 p-4 border-b border-gray-200 bg-gray-50 rounded-t-lg">
    <!-- Search and Navigation bar -->
    <div class="flex items-center gap-3 mb-3">
      <div class="flex-1 relative">
        <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
          <Search class="w-4 h-4 text-gray-400" />
        </div>
        <div class="w-full">
          <input
            bind:value={searchQuery}
            placeholder="Search in {currentLocalPath || '/'}"
            class="block w-full pl-10 pr-3 py-2 border border-gray-300 rounded-md leading-5 bg-white placeholder-gray-500 focus:outline-none focus:placeholder-gray-400 focus:ring-1 focus:ring-blue-500 focus:border-blue-500 text-sm disabled:bg-gray-100 disabled:cursor-not-allowed"
            disabled={loading}
          />
        </div>
      </div>
      <div class="flex items-center gap-2">
        <button
          class="inline-flex items-center justify-center p-2 border border-gray-300 rounded-md shadow-sm bg-white text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-white"
          on:click={navigateUp}
          disabled={currentLocalPath === "/" || loading}
          title="Go up one level"
        >
          <ArrowUp class="w-4 h-4" />
        </button>
        <button
          class="inline-flex items-center justify-center p-2 border border-gray-300 rounded-md shadow-sm bg-white text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-white"
          on:click={goToHome}
          disabled={loading}
          title="Go to home"
        >
          <Home class="w-4 h-4" />
        </button>
        <button
          class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-blue-600"
          on:click={selectCurrentLocalPath}
          disabled={!currentLocalPath || loading}
        >
          Select Directory
        </button>
      </div>
    </div>

    <!-- Options -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-4">
        <label class="flex items-center gap-2 text-sm text-gray-600">
          <input
            type="checkbox"
            bind:checked={showHiddenFiles}
            on:change={handleOptionsChange}
            disabled={loading}
            class="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded disabled:opacity-50"
          />
          <span>Show hidden files</span>
        </label>

        <label class="flex items-center gap-2 text-sm text-gray-600">
          <input
            type="checkbox"
            bind:checked={showFilesInBrowser}
            on:change={handleOptionsChange}
            disabled={loading}
            class="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded disabled:opacity-50"
          />
          <span>Show files</span>
        </label>
      </div>

      <div class="text-sm text-gray-500 font-medium">
        {#if searchQuery}
          {filteredEntries.length} matches
        {:else}
          {localEntries.length} entries
        {/if}
      </div>
    </div>
  </div>

  <!-- Error display -->
  {#if error}
    <div class="error-section">
      <AlertCircle class="w-5 h-5 text-red-500" />
      <div class="error-content">
        <p class="error-message">{error}</p>
        {#if error.includes('Authentication') || error.includes('API key')}
          <Button
            variant="outline"
            size="sm"
            on:click={() => window.location.hash = '#/settings'}
            class="mt-2"
          >
            <Key class="w-4 h-4 mr-2" />
            Configure API Key
          </Button>
        {/if}
      </div>
      <Button
        variant="ghost"
        size="sm"
        on:click={() => loadLocalPath(currentLocalPath)}
        disabled={loading}
      >
        Retry
      </Button>
    </div>
  {/if}

  <!-- Directory listing -->
  <div class="browser-content">
    {#if loading}
      <div class="loading-section">
        <Loader2 class="w-5 h-5 animate-spin text-blue-600" />
        <span>Loading directory...</span>
      </div>
    {:else if filteredEntries.length > 0}
      <div class="entries-list">
        {#each filteredEntries as entry}
          <button
            class="entry-item"
            class:directory={entry.is_dir}
            class:file={!entry.is_dir}
            on:click={() => entry.is_dir ? handleDirectoryClick(entry.path) : null}
            disabled={!entry.is_dir}
          >
            <div class="entry-icon">
              {#if entry.is_dir}
                <Folder class="w-4 h-4 text-blue-600" />
              {:else}
                <File class="w-4 h-4 text-gray-500" />
              {/if}
            </div>

            <div class="entry-details">
              <span class="entry-name">
                {#if searchQuery && entry.matchResult}
                  {#each entry.name.split('') as char, i}
                    <span class:highlight={entry.matchResult.matches.includes(i)}>
                      {char}
                    </span>
                  {/each}
                {:else}
                  {entry.name}
                {/if}
              </span>
              {#if entry.is_dir}
                <span class="entry-type">Directory</span>
              {:else}
                <span class="entry-type">File</span>
              {/if}
            </div>

            {#if entry.is_dir}
              <div class="entry-action">
                <span class="action-text">Open</span>
              </div>
            {/if}
          </button>
        {/each}
      </div>
    {:else if !loading && !error}
      <div class="empty-section">
        <Folder class="w-8 h-8 text-gray-400" />
        <span class="empty-message">
          {searchQuery ? 'No matching directories found' : 'No directories found'}
        </span>
        {#if searchQuery}
          <Button
            variant="ghost"
            size="sm"
            on:click={() => searchQuery = ''}
            class="mt-2"
          >
            Clear search
          </Button>
        {/if}
      </div>
    {/if}
  </div>
</div>

<style>
  .file-browser {
    --border-color: #e2e8f0;
    --hover-color: #f8fafc;
    --text-primary: #1f2937;
    --text-secondary: #6b7280;
    --text-muted: #9ca3af;
    background: transparent;
    border: none;
    padding: 0;
  }

  .browser-header {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    padding-bottom: 0.75rem;
    border-bottom: 1px solid #e5e7eb;
    margin-bottom: 0.75rem;
  }

  .search-nav-bar {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    justify-content: space-between;
  }

  .search-container {
    flex: 1;
    max-width: 400px;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .search-icon-button {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 0.375rem;
    color: #6b7280;
    flex-shrink: 0;
    transition: all 0.15s;
  }

  .search-icon-button:hover {
    background: #f9fafb;
    border-color: #d1d5db;
  }

  .search-input-wrapper {
    flex: 1;
    display: flex;
    align-items: center;
  }

  .nav-buttons {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .nav-btn {
    padding: 0.375rem;
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 0.375rem;
    color: #6b7280;
    cursor: pointer;
    transition: all 0.15s;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
  }

  .nav-btn:hover:not(:disabled) {
    background: #f3f4f6;
    color: #111827;
  }

  .nav-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }


  .path-text {
    font-size: 0.875rem;
    color: #374151;
    font-family: 'SF Mono', 'Monaco', 'Courier New', monospace;
    font-weight: 500;
  }

  .select-btn {
    padding: 0.375rem 0.875rem;
    background: #3b82f6;
    color: white;
    border: none;
    border-radius: 0.375rem;
    font-size: 0.813rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
    white-space: nowrap;
  }

  .select-btn:hover:not(:disabled) {
    background: #2563eb;
  }

  .select-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }


  .search-icon {
    width: 1rem;
    height: 1rem;
    color: #6b7280;
  }

  .search-input-native {
    padding: 0.375rem 0.75rem;
    width: 100%;
    border-radius: 0.375rem;
    border: 1px solid #e5e7eb;
    font-size: 0.875rem;
    background: white;
    transition: all 0.15s;
    height: 32px;
    line-height: 1.5;
    box-sizing: border-box;
  }

  .search-input-native:focus {
    outline: none;
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  .search-input-native:disabled {
    background: #f9fafb;
    cursor: not-allowed;
  }
  .selected-indicator {
    font-size: 0.75rem;
    color: #16a34a;
    font-weight: 600;
    margin-left: auto;
    white-space: nowrap;
  }

  .path-text {
    font-family: 'SF Mono', 'Monaco', 'Courier New', monospace;
    font-size: 0.875rem;
    color: var(--text-primary);
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  :global(.select-btn) {
    flex-shrink: 0;
  }

  .options-section {
    display: flex;
    align-items: center;
    gap: 1rem;
    flex-wrap: wrap;
    font-size: 0.875rem;
  }

  .option-checkbox {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    cursor: pointer;
    color: var(--text-secondary);
  }

  .option-checkbox input {
    margin: 0;
    cursor: pointer;
  }

  .entry-count {
    color: var(--text-muted);
    font-size: 0.875rem;
    margin-left: auto;
  }

  .error-section {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 1rem;
    background: #fef2f2;
    border-bottom: 1px solid #fecaca;
    color: #dc2626;
  }

  .error-content {
    flex: 1;
  }

  .error-message {
    margin: 0;
    font-size: 0.875rem;
    font-weight: 500;
  }

  .browser-content {
    max-height: 400px;
    overflow-y: auto;
  }

  .loading-section {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.75rem;
    padding: 2rem;
    color: var(--text-secondary);
    font-style: italic;
  }

  .entries-list {
    padding: 0.5rem;
  }

  .entry-item {
    width: 100%;
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.75rem;
    border: none;
    background: none;
    text-align: left;
    border-radius: 8px;
    transition: all 0.2s ease;
    cursor: pointer;
  }

  .entry-item:hover:not(:disabled) {
    background: var(--hover-color);
  }

  .entry-item:disabled {
    cursor: not-allowed;
    opacity: 0.6;
  }

  .entry-item.directory:hover:not(:disabled) {
    background: #f8fafc;
  }

  .entry-icon {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .entry-details {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .entry-name {
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--text-primary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .entry-name .highlight {
    background: #fbbf24;
    color: #92400e;
    padding: 0.125rem 0.25rem;
    border-radius: 3px;
    font-weight: 600;
  }

  .entry-type {
    font-size: 0.75rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .entry-action {
    flex-shrink: 0;
    opacity: 0;
    transition: opacity 0.2s ease;
  }

  .entry-item:hover .entry-action {
    opacity: 1;
  }

  .action-text {
    font-size: 0.75rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .empty-section {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    color: var(--text-muted);
    gap: 0.75rem;
  }

  .empty-message {
    font-style: italic;
    text-align: center;
  }

  /* Mobile responsive */
  @media (max-width: 768px) {
    .browser-header {
      padding: 0.75rem;
    }

    .nav-section {
      flex-direction: column;
      gap: 0.75rem;
    }

    .quick-nav {
      gap: 0.25rem;
    }

    :global(.quick-nav-btn) {
      padding: 0.5rem;
      font-size: 0.75rem;
    }

    .nav-text {
      display: none;
    }

    .path-section {
      flex-direction: column;
      gap: 0.75rem;
      align-items: stretch;
    }

    .options-section {
      flex-direction: column;
      align-items: flex-start;
      gap: 0.5rem;
    }

    .entry-count {
      margin-left: 0;
    }

    .browser-content {
      max-height: 300px;
    }

    .entry-item {
      padding: 1rem 0.75rem;
    }

    .entry-action {
      opacity: 1;
    }
  }
</style>