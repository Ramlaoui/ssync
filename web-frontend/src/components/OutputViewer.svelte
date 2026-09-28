<script lang="ts">
  import { run } from 'svelte/legacy';
  import { tick, untrack } from 'svelte';
  import type { Snippet } from 'svelte';

  import { onMount, onDestroy } from 'svelte';
  import LoadingSpinner from './LoadingSpinner.svelte';
  import { Settings, Type, Hash, WrapText, RefreshCw, Search, X } from 'lucide-svelte';
  import { debounce } from '../lib/debounce';
  import { keyboardNav } from '../lib/actions/keyboardNav';
  import {
    resolveActiveSearchIndex,
    updateActiveSearchHighlight,
  } from '../lib/searchHighlights';
  
  interface Props {
    content?: string;
    isLoading?: boolean;
    hasMoreContent?: boolean;
    onLoadMore?: (() => void) | null;
    onScrollToTop?: (() => void) | null;
    onScrollToBottom?: (() => void) | null;
    type?: 'output' | 'error';
    isStreaming?: boolean;
    onRefresh?: (() => void) | null;
    refreshing?: boolean;
    isPending?: boolean;
    pendingMessage?: string;
    toolbarStart?: Snippet;
    toolbarEnd?: Snippet;
  }

  let {
    content = '',
    isLoading = false,
    hasMoreContent = false,
    onLoadMore = null,
    onScrollToTop = null,
    onScrollToBottom = null,
    type = 'output',
    isStreaming = false,
    onRefresh = null,
    refreshing = false,
    isPending = false,
    pendingMessage = '',
    toolbarStart,
    toolbarEnd
  }: Props = $props();

  let outputElement: HTMLPreElement | null = $state(null);
  let lineNumbersElement: HTMLDivElement | null = $state(null);
  let searchInputElement: HTMLInputElement | null = $state(null);
  let searchButtonElement: HTMLButtonElement | null = $state(null);
  let settingsButtonElement: HTMLButtonElement | null = $state(null);
  let searchQuery: string = $state('');
  let searchResults: number[] = $state([]);
  let currentSearchIndex: number = $state(-1);
  let showLineNumbers: boolean = $state(true);
  let autoScroll: boolean = true;
  let isAtBottom: boolean = $state(true);
  let highlightedContent: string = $state('');
  let showSearch: boolean = $state(false);
  let showSettingsMenu: boolean = $state(false);
  let fontSize: 'small' | 'medium' | 'large' = $state('medium');
  let wordWrap: boolean = $state(true);

  // Progressive loading constants
  const MAX_INITIAL_SIZE = 2 * 1024 * 1024; // 2MB initial load
  const CHUNK_SIZE = 500 * 1024; // 500KB per chunk
  const WINDOW_SIZE = 3 * 1024 * 1024; // 3MB window in DOM
  const BUFFER_SIZE = 500 * 1024; // 500KB buffer before/after viewport
  const LARGE_FILE_THRESHOLD = 5 * 1024 * 1024; // 5MB for windowing
  const DISABLE_HIGHLIGHTING_THRESHOLD = 1 * 1024 * 1024; // 1MB

  // Progressive loading state
  let renderedContent: string = $state('');
  let windowStart: number = $state(0); // Start of the rendered window
  let windowEnd: number = $state(0); // End of the rendered window
  let totalContentSize: number = $state(0);
  let isLargeFile: boolean = $state(false);
  let loadingMore: boolean = $state(false);
  let disableHighlighting: boolean = $state(false);
  let loadingMessage = $derived(pendingMessage || `Loading ${type}...`);
  
  // Line processing
  let lines: string[] = $state([]);


  function initializeContent() {
    totalContentSize = content.length;
    isLargeFile = totalContentSize > LARGE_FILE_THRESHOLD;
    disableHighlighting = totalContentSize > DISABLE_HIGHLIGHTING_THRESHOLD;

    // Load initial chunk
    if (totalContentSize > MAX_INITIAL_SIZE) {
      windowStart = 0;
      windowEnd = MAX_INITIAL_SIZE;
      renderedContent = content.slice(windowStart, windowEnd);
    } else {
      windowStart = 0;
      windowEnd = totalContentSize;
      renderedContent = content;
    }

    updateRenderedContent();
  }

  async function updateRenderedContent() {
    lines = renderedContent.split('\n');

    // Use untrack to prevent tracking searchQuery when this is called from content effect
    untrack(() => {
      if (searchQuery) {
        highlightSearchResults();
      } else if (!disableHighlighting) {
        highlightedContent = escapeHtml(renderedContent);
      } else {
        // Skip highlighting for large files
        highlightedContent = escapeHtml(renderedContent);
      }
    });
  }
  
  function escapeHtml(unsafe: string): string {
    return unsafe
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#x27;");
  }

  function highlightSearchResults() {
    if (!searchQuery) {
      highlightedContent = escapeHtml(renderedContent);
      searchResults = [];
      currentSearchIndex = -1;
      return;
    }

    // Escape special regex characters but preserve the search term
    const escapedQuery = searchQuery.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

    try {
      const regex = new RegExp(`(${escapedQuery})`, 'gi');
      // First escape HTML, then apply search highlighting
      const escaped = escapeHtml(renderedContent);
      
      // Count matches to update searchResults
      const matches = escaped.match(regex);
      searchResults = matches ? Array.from({length: matches.length}, (_, i) => i) : [];
      
      highlightedContent = escaped.replace(regex, '<mark class="search-highlight">$1</mark>');

      if (searchResults.length === 0) {
        currentSearchIndex = -1;
        return;
      }

      const nextIndex = resolveActiveSearchIndex(
        currentSearchIndex,
        searchResults.length
      );

      currentSearchIndex = nextIndex;
      void scrollToSearchResult(nextIndex);
    } catch (error) {
      // Fallback to escaped content if regex fails
      console.warn('Search highlighting failed:', error);
      highlightedContent = escapeHtml(renderedContent);
      searchResults = [];
      currentSearchIndex = -1;
    }
  }
  
  async function scrollToSearchResult(index: number) {
    const element = outputElement;
    if (!element || searchResults.length === 0) return;

    await tick();

    const marks = element.querySelectorAll('mark.search-highlight');
    if (marks.length === 0 || !marks[index]) return;

    const mark = marks[index] as HTMLElement;
    mark.scrollIntoView({ behavior: 'smooth', block: 'center' });
    currentSearchIndex = index;
    updateActiveSearchHighlight(marks, index);
  }
  
  function nextSearchResult() {
    if (searchResults.length === 0) return;
    const nextIndex = (currentSearchIndex + 1) % searchResults.length;
    scrollToSearchResult(nextIndex);
  }
  
  function prevSearchResult() {
    if (searchResults.length === 0) return;
    const prevIndex = currentSearchIndex === 0 ? searchResults.length - 1 : currentSearchIndex - 1;
    scrollToSearchResult(prevIndex);
  }
  
  
  function checkScrollPosition() {
    if (!outputElement || loadingMore) return;

    const { scrollTop, scrollHeight, clientHeight } = outputElement;
    isAtBottom = scrollTop + clientHeight >= scrollHeight - 5;

    // Sync line numbers scroll position
    if (lineNumbersElement && showLineNumbers) {
      lineNumbersElement.scrollTop = scrollTop;
    }

    // Calculate the content position based on scroll
    const scrollRatio = scrollTop / scrollHeight;
    const estimatedPosition = Math.floor(scrollRatio * totalContentSize);

    // Check if we need to load a different window
    if (isLargeFile && totalContentSize > WINDOW_SIZE) {
      updateContentWindow(estimatedPosition, scrollTop, clientHeight);
    } else {
      // Simple progressive loading for smaller files
      const scrollPercentage = (scrollTop + clientHeight) / scrollHeight;
      if (scrollPercentage > 0.8 && windowEnd < totalContentSize) {
        loadMoreContentChunk();
      }
    }

    // Trigger external load more if available
    if (isAtBottom && hasMoreContent && onLoadMore && !isLoading) {
      loadMoreOutput();
    }
  }

  function updateContentWindow(estimatedPosition: number, scrollTop: number, clientHeight: number) {
    // Calculate the ideal window based on current viewport
    const viewportSize = clientHeight * 3; // Load 3x viewport height
    let idealStart = Math.max(0, estimatedPosition - viewportSize);
    let idealEnd = Math.min(totalContentSize, estimatedPosition + viewportSize * 2);

    // Check if we need to update the window
    const needsUpdate = idealStart < windowStart - BUFFER_SIZE ||
                       idealEnd > windowEnd + BUFFER_SIZE ||
                       idealStart > windowStart + BUFFER_SIZE ||
                       idealEnd < windowEnd - BUFFER_SIZE;

    if (needsUpdate && !loadingMore) {
      loadContentWindow(idealStart, idealEnd, scrollTop);
    }
  }

  async function loadContentWindow(start: number, end: number, preserveScrollTop: number) {
    loadingMore = true;
    const element = outputElement;

    // Calculate actual boundaries
    const newStart = Math.max(0, start - BUFFER_SIZE);
    const newEnd = Math.min(totalContentSize, end + BUFFER_SIZE);

    // Ensure window doesn't exceed maximum size
    if (newEnd - newStart > WINDOW_SIZE) {
      if (element && preserveScrollTop > element.scrollHeight / 2) {
        // User is scrolling down, prioritize content below
        start = Math.max(0, newEnd - WINDOW_SIZE);
      } else {
        // User is scrolling up, prioritize content above
        end = Math.min(totalContentSize, newStart + WINDOW_SIZE);
      }
    }

    // Update window boundaries
    windowStart = newStart;
    windowEnd = newEnd;

    // Load new content
    renderedContent = content.slice(windowStart, windowEnd);

    // Update display
    await updateRenderedContent();

    // Restore approximate scroll position
    if (element) {
      // Calculate where we should be in the new content
      const contentProgress = (preserveScrollTop / element.scrollHeight);
      element.scrollTop = contentProgress * element.scrollHeight;
    }

    loadingMore = false;
  }

  async function loadMoreContentChunk() {
    if (loadingMore || windowEnd >= totalContentSize) return;

    loadingMore = true;

    // Simulate async loading for smooth UX
    await new Promise(resolve => setTimeout(resolve, 10));

    const nextChunkEnd = Math.min(windowEnd + CHUNK_SIZE, totalContentSize);
    const nextChunk = content.slice(windowEnd, nextChunkEnd);

    // For large files, use windowing; for smaller files, just append
    if (isLargeFile && renderedContent.length + nextChunk.length > WINDOW_SIZE) {
      // Shift window down, removing content from beginning
      const removeSize = nextChunk.length;
      windowStart += removeSize;
      renderedContent = content.slice(windowStart, nextChunkEnd);
    } else {
      renderedContent += nextChunk;
    }

    windowEnd = nextChunkEnd;
    await updateRenderedContent();
    loadingMore = false;
  }
  
  function loadMoreOutput() {
    if (hasMoreContent && onLoadMore && !isLoading) {
      onLoadMore();
    }
  }
  
  function handleScrollToTop() {
    if (outputElement) {
      outputElement.scrollTop = 0;
      isAtBottom = false;
    }
    onScrollToTop?.();
  }
  
  function handleScrollToBottom() {
    if (outputElement) {
      outputElement.scrollTop = outputElement.scrollHeight;
      isAtBottom = true;
    }
    onScrollToBottom?.();
  }

  async function openSearch() {
    showSearch = true;
    await tick();
    searchInputElement?.focus();
  }

  function closeSearch() {
    showSearch = false;
    searchQuery = '';
    searchResults = [];
    currentSearchIndex = -1;
    searchButtonElement?.focus();
  }

  function dismissControls() {
    if (showSettingsMenu) {
      showSettingsMenu = false;
      settingsButtonElement?.focus();
    } else {
      closeSearch();
    }
  }
  
  
  onMount(() => {
    if (outputElement) {
      outputElement.addEventListener('scroll', checkScrollPosition);
      // Initial sync
      checkScrollPosition();
    }
  });

  onDestroy(() => {
    if (outputElement) {
      outputElement.removeEventListener('scroll', checkScrollPosition);
    }
  });

  function toggleLineNumbers() {
    showLineNumbers = !showLineNumbers;
    showSettingsMenu = false;
  }

  function toggleWordWrap() {
    wordWrap = !wordWrap;
    showSettingsMenu = false;
  }

  function setFontSize(size: 'small' | 'medium' | 'large') {
    fontSize = size;
    showSettingsMenu = false;
  }

  function handleClickOutside(event: Event) {
    if (showSettingsMenu) {
      const target = event.target as HTMLElement;
      if (!target.closest('.settings-dropdown')) {
        showSettingsMenu = false;
      }
    }
  }


  // Utility function to format bytes
  function formatBytes(bytes: number): string {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }
  // Initialize content when it changes
  run(() => {
    const currentContent = content; // Track content changes
    // Use untrack to prevent tracking nested state reads in initializeContent.
    // This prevents circular dependencies with searchQuery and other presentation state.
    untrack(() => initializeContent());
  });

  // Create debounced search handler (300ms delay)
  const debouncedHighlightSearch = debounce(() => {
    highlightSearchResults();
  }, 300);

  // React to search query changes with debouncing
  run(() => {
    const query = searchQuery; // Track only searchQuery
    if (query) {
      // Use untrack to prevent tracking any state reads inside the debounced function
      // This prevents the effect from tracking renderedContent and other presentation state.
      untrack(() => debouncedHighlightSearch());
    } else {
      // Clear search immediately when query is empty
      untrack(() => {
        highlightedContent = escapeHtml(renderedContent);
        searchResults = [];
        currentSearchIndex = -1;
      });
    }
  });

  // Auto-scroll to bottom when new content arrives (if enabled and user is at bottom)
  run(() => {
    // Track these specific states
    const shouldScroll = autoScroll && isAtBottom && renderedContent;
    const element = outputElement;

    if (shouldScroll && element) {
      // Use untrack to prevent tracking state reads inside setTimeout
      untrack(() => {
        setTimeout(() => {
          if (element && element.parentElement) {
            element.scrollTop = element.scrollHeight;
          }
        }, 10);
      });
    }
  });
  // Font size classes
  let fontSizeClass = $derived({
    small: 'text-xs',
    medium: 'text-sm',
    large: 'text-base'
  }[fontSize]);
</script>

<div class="enhanced-output-viewer" onclick={handleClickOutside} role="presentation" use:keyboardNav={{ onEscape: showSearch || showSettingsMenu ? dismissControls : undefined, preventDefault: true, stopPropagation: true }}>
  <!-- Compact toolbar -->
  <div class="viewer-header">
    <div class="viewer-toolbar">
      {#if toolbarStart}
        <div class="toolbar-slot toolbar-start">
          {@render toolbarStart()}
        </div>
      {/if}

      <div class="viewer-controls">
        <button
          class="control-btn"
          bind:this={searchButtonElement}
          class:active={showSearch}
          onclick={() => void openSearch()}
          aria-label="Search output"
          aria-expanded={showSearch}
          title="Search output"
        >
          <Search size={15} aria-hidden="true" />
        </button>

      <!-- Refresh Button -->
      {#if onRefresh}
        <button
          class="control-btn"
          onclick={onRefresh}
          disabled={refreshing}
          aria-label="Refresh {type}"
          title="Refresh {type}"
        >
          <RefreshCw class="w-3.5 h-3.5 {refreshing ? 'animate-spin' : ''}" aria-hidden="true" />
        </button>
      {/if}

      <button class="control-btn" onclick={handleScrollToBottom} aria-label="Scroll to bottom" title="Scroll to bottom">
        <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <path d="M7.41,8.59L12,13.17L16.59,8.59L18,10L12,16L6,10L7.41,8.59Z"/>
        </svg>
      </button>

      {#if renderedContent}
        <span class="toolbar-line-count">{lines.length} lines</span>
      {/if}

      {#if isLargeFile && (windowStart > 0 || windowEnd < totalContentSize)}
        <span
          class="partial-output-badge"
          role="status"
          title={`Showing ${formatBytes(Math.min(windowEnd, totalContentSize))} of ${formatBytes(totalContentSize)}; more content loads as you scroll`}
        >
          Partial
        </span>
      {/if}

      </div>

      {#if toolbarEnd}
        <div class="toolbar-slot toolbar-end">
          {@render toolbarEnd()}
        </div>
      {/if}

      <!-- Settings Menu -->
      <div class="settings-dropdown relative">
        <button class="control-btn" bind:this={settingsButtonElement} onclick={() => showSettingsMenu = !showSettingsMenu} aria-label="Output settings" aria-expanded={showSettingsMenu} title="Output settings">
          <Settings class="w-3.5 h-3.5" aria-hidden="true" />
        </button>

        {#if showSettingsMenu}
          <div class="settings-menu absolute right-0 top-full mt-2 w-48 bg-popover rounded-md shadow-lg border border-border z-50">
            <div class="py-1">
              <button
                class="flex items-center gap-2 w-full px-4 py-2 text-sm hover:bg-secondary"
                onclick={handleScrollToTop}
              >
                <svg class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                  <path d="M7.41,15.41L12,10.83L16.59,15.41L18,14L12,8L6,14L7.41,15.41Z"/>
                </svg>
                Scroll to top
              </button>

              <div class="border-t border-border my-1"></div>

              <!-- Text Size -->
              <div class="px-4 py-2 text-xs font-medium text-muted-foreground uppercase tracking-wider">Text Size</div>
              <button
                class="flex items-center gap-2 w-full px-4 py-2 text-sm hover:bg-secondary {fontSize === 'small' ? 'text-accent bg-accent/10' : 'text-foreground'}"
                onclick={() => setFontSize('small')}
              >
                <Type class="w-3 h-3" aria-hidden="true" />
                Small
              </button>
              <button
                class="flex items-center gap-2 w-full px-4 py-2 text-sm hover:bg-secondary {fontSize === 'medium' ? 'text-accent bg-accent/10' : 'text-foreground'}"
                onclick={() => setFontSize('medium')}
              >
                <Type class="w-4 h-4" aria-hidden="true" />
                Medium
              </button>
              <button
                class="flex items-center gap-2 w-full px-4 py-2 text-sm hover:bg-secondary {fontSize === 'large' ? 'text-accent bg-accent/10' : 'text-foreground'}"
                onclick={() => setFontSize('large')}
              >
                <Type class="w-5 h-5" aria-hidden="true" />
                Large
              </button>

              <div class="border-t border-border my-1"></div>

              <!-- Display Options -->
              <button
                class="flex items-center gap-2 w-full px-4 py-2 text-sm hover:bg-secondary {showLineNumbers ? 'text-accent bg-accent/10' : 'text-foreground'}"
                onclick={toggleLineNumbers}
              >
                <Hash class="w-4 h-4" aria-hidden="true" />
                {showLineNumbers ? 'Hide' : 'Show'} Line Numbers
              </button>
              <button
                class="flex items-center gap-2 w-full px-4 py-2 text-sm hover:bg-secondary {wordWrap ? 'text-accent bg-accent/10' : 'text-foreground'}"
                onclick={toggleWordWrap}
              >
                <WrapText class="w-4 h-4" aria-hidden="true" />
                {wordWrap ? 'Disable' : 'Enable'} Word Wrap
              </button>
            </div>
          </div>
        {/if}
      </div>
      
    </div>

    {#if showSearch}
      <div class="search-row" role="search">
        <div class="search-input-group">
          <Search class="search-icon" size={15} aria-hidden="true" />
          <input
            type="text"
            placeholder="Search in output..."
            aria-label="Search in output"
            bind:this={searchInputElement}
            bind:value={searchQuery}
            class="search-input"
          />
          {#if searchQuery}
            <div class="search-results-info" aria-live="polite">
              {searchResults.length > 0 ? `${currentSearchIndex + 1} of ${searchResults.length}` : 'No matches'}
            </div>
          {/if}
        </div>

        <div class="search-navigation">
          <button
            class="search-nav-btn"
            onclick={prevSearchResult}
            disabled={searchResults.length === 0}
            aria-label="Previous search result"
            title="Previous result"
          >
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M15.41,16.58L10.83,12L15.41,7.41L14,6L8,12L14,18L15.41,16.58Z"/>
            </svg>
          </button>
          <button
            class="search-nav-btn"
            onclick={nextSearchResult}
            disabled={searchResults.length === 0}
            aria-label="Next search result"
            title="Next result"
          >
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M8.59,16.58L13.17,12L8.59,7.41L10,6L16,12L10,18L8.59,16.58Z"/>
            </svg>
          </button>
          <button class="search-nav-btn" onclick={closeSearch} aria-label="Close search" title="Close search">
            <X size={15} aria-hidden="true" />
          </button>
        </div>
      </div>

    {/if}
  </div>
  <!-- Output Content -->
  <div class="output-container">
    {#if windowStart > 0 && isLargeFile}
      <div class="content-indicator top-indicator">
        <div class="indicator-dots">
          <span class="dot"></span>
          <span class="dot"></span>
          <span class="dot"></span>
        </div>
        <span class="indicator-text">{formatBytes(windowStart)} above</span>
      </div>
    {/if}

    {#if (isLoading || isPending) && !renderedContent}
      <div class="loading-state">
        <LoadingSpinner message={loadingMessage} />
      </div>
    {:else if renderedContent}
      <div class="output-wrapper {fontSizeClass}">
        {#if showLineNumbers}
          <div class="line-numbers" bind:this={lineNumbersElement}>
            {#each lines as _, index}
              <div class="line-number">{index + 1}</div>
            {/each}
          </div>
        {/if}
        <pre
          class="output-content {fontSizeClass}"
          class:wrap={wordWrap}
          bind:this={outputElement}
          onscroll={() => checkScrollPosition()}
        >{@html highlightedContent}</pre>
      </div>

      {#if loadingMore}
        <div class="loading-more">
          <div class="loading-spinner small"></div>
          <span>Loading more content...</span>
        </div>
      {/if}

      {#if windowEnd < totalContentSize && isLargeFile}
        <div class="content-indicator bottom-indicator">
          <div class="indicator-dots">
            <span class="dot"></span>
            <span class="dot"></span>
            <span class="dot"></span>
          </div>
          <span class="indicator-text">{formatBytes(totalContentSize - windowEnd)} below</span>
        </div>
      {/if}
    {:else}
      <div class="empty-state">
        <svg class="empty-icon" viewBox="0 0 24 24" fill="currentColor">
          <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"/>
        </svg>
        <span>No {type} available</span>
      </div>
    {/if}
  </div>
  
</div>

<style>
  .enhanced-output-viewer {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
    min-width: 0;
    background: var(--card);
    overflow: hidden;
    container-type: inline-size;
  }

  .viewer-header {
    flex-shrink: 0;
    padding: 6px 8px;
    border-bottom: 1px solid var(--border);
    background: var(--card);
  }

  .viewer-toolbar,.viewer-controls,.toolbar-slot,.search-row,.search-navigation {
    display: flex;
    align-items: center;
    gap: 4px;
    min-width: 0;
  }

  .viewer-toolbar { min-height: 30px; }
  .viewer-controls { margin-left: auto; }
  .toolbar-slot { flex-shrink: 0; }
  .toolbar-start { gap: 6px; }
  .toolbar-end { gap: 2px; }

  .control-btn,.search-nav-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 30px;
    padding: 0;
    border: 0;
    border-radius: 6px;
    background: transparent;
    color: var(--muted-foreground);
    flex-shrink: 0;
  }

  .control-btn:hover,.search-nav-btn:hover:not(:disabled) {
    background: var(--hover);
    color: var(--foreground);
  }
  .control-btn.active { background: var(--accent-soft); color: var(--accent); }
  .control-btn:disabled,.search-nav-btn:disabled { opacity: .4; cursor: not-allowed; }
  .control-btn svg,.search-nav-btn svg { width: 15px; height: 15px; }
  .toolbar-line-count,.partial-output-badge { font-size: .6875rem; white-space: nowrap; color: var(--muted-foreground); }
  .toolbar-line-count { padding: 0 6px; }
  .partial-output-badge { padding: 3px 5px; background: var(--secondary); border-radius: 4px; }

  .search-row { padding-top: 6px; gap: 6px; }
  .search-input-group { display: flex; align-items: center; flex: 1; min-width: 0; position: relative; }
  .search-input-group :global(.search-icon) { position: absolute; left: 8px; color: var(--muted-foreground); pointer-events: none; }
  .search-input {
    width: 100%;
    min-width: 0;
    height: 30px;
    padding: 4px 80px 4px 29px;
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: .8125rem;
    background: var(--background);
    color: var(--foreground);
  }
  .search-input:focus { outline: 1px solid var(--accent); outline-offset: -1px; }
  .search-results-info { position: absolute; right: 6px; font-size: .6875rem; color: var(--muted-foreground); pointer-events: none; }

  .settings-dropdown { position: relative; flex-shrink: 0; }
  .settings-menu { min-width: 200px; }

  .output-container { flex: 1; min-height: 0; min-width: 0; position: relative; display: flex; flex-direction: column; overflow: hidden; }
  .output-wrapper { flex: 1; min-height: 0; min-width: 0; display: flex; overflow: hidden; }
  .output-wrapper.text-xs { font-size: .75rem; }
  .output-wrapper.text-sm { font-size: .875rem; }
  .output-wrapper.text-base { font-size: 1rem; }

  .line-numbers,.output-content {
    padding-top: 12px;
    padding-bottom: 12px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: inherit;
    line-height: 1.5;
  }
  .line-numbers {
    width: 48px;
    padding-left: 8px;
    padding-right: 8px;
    border-right: 1px solid var(--border-soft);
    color: var(--muted-foreground);
    text-align: right;
    user-select: none;
    overflow: hidden;
    flex-shrink: 0;
    pointer-events: none;
  }
  .line-number { height: 1.5em; }
  .output-content {
    flex: 1;
    min-width: 0;
    margin: 0;
    padding-left: 12px;
    padding-right: 12px;
    white-space: pre;
    overflow: auto;
    overscroll-behavior: contain;
    background: transparent;
    color: var(--foreground);
    border: 0;
  }
  .output-content.wrap { white-space: pre-wrap; word-wrap: break-word; overflow-wrap: break-word; }

  .loading-state,.empty-state { display: flex; flex: 1; flex-direction: column; align-items: center; justify-content: center; gap: 12px; color: var(--muted-foreground); }
  .empty-icon { width: 32px; height: 32px; opacity: .5; }
  .loading-more { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 6px; color: var(--muted-foreground); font-size: .75rem; }
  .loading-spinner.small { width: 14px; height: 14px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin 1s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }

  .content-indicator { position: absolute; left: 50%; transform: translateX(-50%); display: flex; align-items: center; gap: 6px; padding: 3px 8px; background: var(--card); border: 1px solid var(--border); border-radius: 20px; font-size: .6875rem; color: var(--muted-foreground); z-index: 1; }
  .top-indicator { top: 4px; }
  .bottom-indicator { bottom: 4px; }
  .indicator-dots { display: flex; gap: 2px; }
  .dot { width: 3px; height: 3px; background: currentColor; border-radius: 50%; }
  .indicator-text { white-space: nowrap; }

  :global(.search-highlight) { background: var(--warning-bg); color: var(--warning); border-radius: 2px; }
  :global(.search-highlight-active) { background: var(--warning); color: var(--background); }

  @container (max-width:600px) {
    .toolbar-line-count { display: none; }
  }
  @container (max-width:350px) {
    .viewer-header { padding-left: 6px; padding-right: 6px; }
    .toolbar-start { gap: 2px; }
    .viewer-toolbar { gap: 2px; }
    .partial-output-badge { max-width: 24px; overflow: hidden; }
  }
  @container (max-width:500px) {
    .output-wrapper.text-sm { font-size: .75rem; }
    .output-wrapper.text-base { font-size: .875rem; }
    .line-numbers { width: 38px; }
    .output-content { padding-left: 8px; padding-right: 8px; }
  }
</style>
