<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import axios, { type AxiosError } from 'axios';

  const dispatch = createEventDispatcher<{
    pathSelected: string;
  }>();

  export let sourceDir = '';
  
  // Browser state
  let localEntries: { name: string; path: string; is_dir: boolean }[] = [];
  let currentLocalPath = '/';
  let maxEntries = 50;
  let showHiddenFiles = false;
  let showFilesInBrowser = false;
  let loading = false;
  let error: string | null = null;

  const API_BASE = '/api';

  // Load directory browser in background on mount
  setTimeout(() => {
    loadLocalPath('/home').catch(() => {
      // Fallback to root if /home doesn't exist
      loadLocalPath('/').catch(() => {
        console.warn('Could not load directory browser');
      });
    });
  }, 100);

  // Load entries for a server-local path using backend API
  async function loadLocalPath(path: string): Promise<void> {
    loading = true;
    error = null;
    
    try {
      const response = await axios.get(`${API_BASE}/local/list`, { 
        params: { 
          path,
          limit: maxEntries,
          show_hidden: showHiddenFiles,
          dirs_only: !showFilesInBrowser
        } 
      });
      localEntries = response.data.entries;
      currentLocalPath = response.data.path;
      
      // Show warning if we hit the limit (as info, not error)
      if (localEntries.length >= maxEntries) {
        console.log(`Directory listing limited to ${maxEntries} entries.`);
      }
    } catch (err: unknown) {
      const axiosError = err as AxiosError;
      error = `Failed to list local path: ${axiosError.message}`;
    } finally {
      loading = false;
    }
  }

  function selectCurrentLocalPath(): void {
    if (currentLocalPath) {
      sourceDir = currentLocalPath;
      dispatch('pathSelected', currentLocalPath);
    }
  }

  function navigateUp(): void {
    if (currentLocalPath && currentLocalPath !== '/') {
      const parentPath = currentLocalPath.split('/').slice(0, -1).join('/') || '/';
      loadLocalPath(parentPath);
    }
  }

  function goToHome(): void {
    const homePath = '/home';
    loadLocalPath(homePath);
  }

  function goToRoot(): void {
    loadLocalPath('/');
  }

  function handleDirectoryClick(entryPath: string): void {
    loadLocalPath(entryPath);
  }

  function handleOptionsChange(): void {
    if (currentLocalPath) {
      loadLocalPath(currentLocalPath);
    }
  }
</script>

<div class="file-browser">
  <div class="browser-nav">
    <button type="button" on:click={goToRoot} class="nav-btn">Root</button>
    <button type="button" on:click={goToHome} class="nav-btn">Home</button>
    <button type="button" on:click={navigateUp} disabled={currentLocalPath === '/'} class="nav-btn">Up</button>
    <button type="button" on:click={() => loadLocalPath(currentLocalPath)} disabled={!currentLocalPath} class="nav-btn">Refresh</button>
  </div>

  <div class="browser-path">
    <strong>Current:</strong> {currentLocalPath || '/'}
    <button type="button" on:click={selectCurrentLocalPath} disabled={!currentLocalPath} class="select-btn">
      Select This Directory
    </button>
  </div>

  <div class="browser-options">
    <label class="checkbox-label">
      <input type="checkbox" bind:checked={showHiddenFiles} on:change={handleOptionsChange} />
      Show hidden files
    </label>
    <label class="checkbox-label">
      <input type="checkbox" bind:checked={showFilesInBrowser} on:change={handleOptionsChange} />
      Show files (directories only by default)
    </label>
    <div class="limit-info">Showing max {maxEntries} entries</div>
  </div>

  {#if error}
    <div class="browser-error">
      <span>{error}</span>
      <button type="button" on:click={() => loadLocalPath(currentLocalPath)} class="retry-btn">Retry</button>
    </div>
  {/if}

  <ul class="browser-list" class:loading>
    {#if loading}
      <li class="browser-entry loading-entry">
        <div class="loading-spinner"></div>
        Loading directory...
      </li>
    {:else if localEntries && localEntries.length > 0}
      {#each localEntries as entry}
        <li class="browser-entry" class:dir={entry.is_dir} class:file={!entry.is_dir}>
          {#if entry.is_dir}
            <button type="button" class="dir-button" on:click={() => handleDirectoryClick(entry.path)}>
              <svg class="folder-icon" viewBox="0 0 24 24" fill="currentColor">
                <path d="M10,4H4C2.89,4 2,4.89 2,6V18A2,2 0 0,0 4,20H20A2,2 0 0,0 22,18V8C22,6.89 21.1,6 20,6H12L10,4Z"/>
              </svg>
              {entry.name}/
            </button>
          {:else}
            <div class="file-entry">
              <svg class="file-icon" viewBox="0 0 24 24" fill="currentColor">
                <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"/>
              </svg>
              <span class="file-name">{entry.name}</span>
            </div>
          {/if}
        </li>
      {/each}
    {:else}
      <li class="browser-entry empty-entry">
        <svg class="empty-icon" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M12,17A5,5 0 0,1 7,12A5,5 0 0,1 12,7A5,5 0 0,1 17,12A5,5 0 0,1 12,17M12,9A3,3 0 0,0 9,12A3,3 0 0,0 12,15A3,3 0 0,0 15,12A3,3 0 0,0 12,9Z"/>
        </svg>
        No entries found
      </li>
    {/if}
  </ul>
</div>

<style>
  .file-browser {
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    overflow: hidden;
    background: white;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  }

  .browser-nav {
    display: flex;
    gap: 0.5rem;
    padding: 1rem;
    border-bottom: 1px solid #f3f4f6;
    background: linear-gradient(90deg, #f8fafc 0%, #f1f5f9 100%);
    flex-wrap: wrap;
  }

  .nav-btn {
    padding: 0.5rem 1rem;
    font-size: 0.875rem;
    background: white;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    cursor: pointer;
    color: #374151;
    font-weight: 500;
    transition: all 0.2s ease;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  }

  .nav-btn:hover:not(:disabled) {
    background: #f9fafb;
    border-color: #9ca3af;
    transform: translateY(-1px);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  }

  .nav-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    transform: none;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  }

  .browser-path {
    padding: 0.75rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: #ffffff;
    border-bottom: 1px solid #e5e7eb;
    font-size: 0.9rem;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .select-btn {
    padding: 0.4rem 0.8rem;
    font-size: 0.85rem;
    background: #3498db;
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    transition: background-color 0.2s ease;
  }

  .select-btn:hover:not(:disabled) {
    background: #2980b9;
  }

  .select-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .browser-options {
    padding: 0.5rem 0.75rem;
    background: #ffffff;
    border-bottom: 1px solid #e5e7eb;
    display: flex;
    gap: 1rem;
    align-items: center;
    font-size: 0.85rem;
    flex-wrap: wrap;
  }

  .checkbox-label {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    font-size: 0.85rem;
    color: #6c757d;
    margin: 0;
    cursor: pointer;
  }

  .checkbox-label input[type="checkbox"] {
    margin: 0;
    cursor: pointer;
  }

  .limit-info {
    color: #6c757d;
    font-size: 0.8rem;
    margin-left: auto;
  }

  .browser-error {
    padding: 0.75rem;
    background: #fef2f2;
    color: #dc2626;
    border-bottom: 1px solid #fecaca;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.9rem;
  }

  .retry-btn {
    padding: 0.25rem 0.5rem;
    background: #dc2626;
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.8rem;
    transition: background-color 0.2s ease;
  }

  .retry-btn:hover {
    background: #b91c1c;
  }

  .browser-list {
    max-height: 300px;
    overflow-y: auto;
    margin: 0;
    padding: 0;
    list-style: none;
    background: white;
  }

  .browser-entry {
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid #f3f4f6;
    transition: background-color 0.2s ease;
  }

  .browser-entry:last-child {
    border-bottom: none;
  }

  .browser-entry.dir {
    background: #f8fafc;
  }

  .browser-entry.file {
    background: #ffffff;
    color: #6c757d;
  }

  .browser-entry:hover {
    background: #f1f5f9;
  }

  .dir-button {
    background: none;
    border: none;
    color: #3498db;
    cursor: pointer;
    font-size: 0.9rem;
    padding: 0;
    text-align: left;
    width: 100%;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    transition: color 0.2s ease;
  }

  .dir-button:hover {
    color: #2980b9;
  }

  .file-entry {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: #6c757d;
  }

  .folder-icon, .file-icon, .empty-icon {
    width: 16px;
    height: 16px;
    flex-shrink: 0;
  }

  .folder-icon {
    color: #f59e0b;
  }

  .file-icon {
    color: #6b7280;
  }

  .empty-icon {
    color: #9ca3af;
  }

  .file-name {
    font-size: 0.9rem;
  }

  .loading-entry {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    color: #6c757d;
    font-style: italic;
  }

  .loading-spinner {
    width: 16px;
    height: 16px;
    border: 2px solid #f3f4f6;
    border-top: 2px solid #3498db;
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  .empty-entry {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: #9ca3af;
    font-style: italic;
    justify-content: center;
    padding: 1.5rem 0.75rem;
  }

  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }

  /* Mobile responsive improvements */
  @media (max-width: 768px) {
    .browser-nav {
      padding: 0.5rem;
      flex-wrap: wrap;
      gap: 0.375rem;
    }

    .nav-btn {
      padding: 0.375rem 0.625rem;
      font-size: 0.8rem;
    }

    .browser-path {
      padding: 0.625rem;
      flex-direction: column;
      align-items: flex-start;
      gap: 0.5rem;
    }

    .select-btn {
      align-self: stretch;
      text-align: center;
    }

    .browser-options {
      flex-direction: column;
      align-items: flex-start;
      gap: 0.5rem;
    }

    .limit-info {
      margin-left: 0;
    }

    .browser-list {
      max-height: 200px;
    }

    .browser-entry {
      padding: 0.625rem 0.5rem;
    }
  }

  /* Improved scrollbar for browser list */
  .browser-list::-webkit-scrollbar {
    width: 6px;
  }

  .browser-list::-webkit-scrollbar-track {
    background: transparent;
  }

  .browser-list::-webkit-scrollbar-thumb {
    background: rgba(156, 163, 175, 0.4);
    border-radius: 3px;
  }

  .browser-list::-webkit-scrollbar-thumb:hover {
    background: rgba(156, 163, 175, 0.6);
  }
</style>