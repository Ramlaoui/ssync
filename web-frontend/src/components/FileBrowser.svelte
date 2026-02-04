<script lang="ts">
  import { run } from 'svelte/legacy';

  import { api } from "../services/api";
  import type { AxiosError } from "axios";
  import { createEventDispatcher } from "svelte";
  import { Search, Home, Folder, FolderOpen, File, ArrowUp, Loader2, AlertCircle, Key } from "lucide-svelte";
  import Button from "../lib/components/ui/Button.svelte";

  const dispatch = createEventDispatcher<{
    pathSelected: string;
    directoryChanged: string;
  }>();

  interface Props {
    sourceDir?: string;
    initialPath?: string;
    class?: string;
  }

  let { sourceDir = $bindable(""), initialPath = "/", class: className = "" }: Props = $props();

  interface MatchResult {
    score: number;
    matches: number[];
  }

  interface LocalEntry {
    name: string;
    path: string;
    is_dir: boolean;
    matchResult?: MatchResult;
  }

  // Browser state
  let localEntries: LocalEntry[] = $state([]);
  let filteredEntries: LocalEntry[] = $state([]);
  let currentLocalPath = $state("/");
  let maxEntries = 100;
  let showHiddenFiles = $state(false);
  let showFilesInBrowser = $state(false);
  let loading = $state(false);
  let error: string | null = $state(null);
  let searchQuery = $state("");

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
  run(() => {
    // Trigger when either localEntries or searchQuery changes
    localEntries;
    searchQuery;
    filterEntries();
  });

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
        const responseData = axiosError.response?.data as { detail?: string } | undefined;
        const responseText = responseData?.detail || '';
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

<div class={`flex flex-col h-full bg-white dark:bg-card rounded-lg border border-gray-200 dark:border-border ${className}`.trim()}>
  <!-- Simplified Header -->
  <div class="flex-shrink-0 p-4 border-b border-gray-200 dark:border-border bg-gray-50 dark:bg-secondary rounded-t-lg">
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
            class="block w-full pl-10 pr-3 py-2 border border-gray-300 dark:border-border rounded-md leading-5 bg-white dark:bg-input placeholder-gray-500 dark:placeholder-gray-400 text-gray-900 dark:text-foreground focus:outline-none focus:placeholder-gray-400 focus:ring-1 focus:ring-blue-500 dark:focus:ring-accent focus:border-blue-500 dark:focus:border-accent text-sm disabled:bg-gray-100 dark:disabled:bg-secondary disabled:cursor-not-allowed"
            disabled={loading}
          />
        </div>
      </div>
      <div class="flex items-center gap-2">
        <button
          class="inline-flex items-center justify-center p-2 border border-gray-300 dark:border-border rounded-md shadow-sm bg-white dark:bg-card text-gray-700 dark:text-foreground hover:bg-gray-50 dark:hover:bg-secondary focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 dark:focus:ring-accent disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-white dark:disabled:hover:bg-card"
          onclick={navigateUp}
          disabled={currentLocalPath === "/" || loading}
          title="Go up one level"
        >
          <ArrowUp class="w-4 h-4" />
        </button>
        <button
          class="inline-flex items-center justify-center p-2 border border-gray-300 dark:border-border rounded-md shadow-sm bg-white dark:bg-card text-gray-700 dark:text-foreground hover:bg-gray-50 dark:hover:bg-secondary focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 dark:focus:ring-accent disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-white dark:disabled:hover:bg-card"
          onclick={goToHome}
          disabled={loading}
          title="Go to home"
        >
          <Home class="w-4 h-4" />
        </button>
        <button
          class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-blue-600 dark:bg-accent hover:bg-blue-700 dark:hover:bg-accent/90 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 dark:focus:ring-accent disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-blue-600 dark:disabled:hover:bg-accent"
          onclick={selectCurrentLocalPath}
          disabled={!currentLocalPath || loading}
        >
          Select Directory
        </button>
      </div>
    </div>

    <!-- Options -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-4">
        <label class="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
          <input
            type="checkbox"
            bind:checked={showHiddenFiles}
            onchange={handleOptionsChange}
            disabled={loading}
            class="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 dark:border-border rounded disabled:opacity-50"
          />
          <span>Show hidden files</span>
        </label>

        <label class="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
          <input
            type="checkbox"
            bind:checked={showFilesInBrowser}
            onchange={handleOptionsChange}
            disabled={loading}
            class="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 dark:border-border rounded disabled:opacity-50"
          />
          <span>Show files</span>
        </label>
      </div>

      <div class="text-sm text-gray-500 dark:text-gray-400 font-medium">
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
            onclick={() => entry.is_dir ? handleDirectoryClick(entry.path) : null}
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
  :global(.select-btn) {
    flex-shrink: 0;
  }

  .error-section {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 1rem;
    background: var(--error-bg);
    border-bottom: 1px solid color-mix(in srgb, var(--destructive) 20%, transparent);
    color: var(--destructive);
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
    background: var(--secondary);
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
    background: var(--warning-bg);
    color: var(--warning);
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
