<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import LoadingSpinner from './LoadingSpinner.svelte';
  import { Settings, Type, Hash, WrapText, RefreshCw } from 'lucide-svelte';
  
  export let content: string = '';
  export let isLoading: boolean = false;
  export let hasMoreContent: boolean = false;
  export let onLoadMore: (() => void) | null = null;
  export let onScrollToTop: (() => void) | null = null;
  export let onScrollToBottom: (() => void) | null = null;
  export let type: 'output' | 'error' = 'output';
  export let isStreaming: boolean = false;
  export let onRefresh: (() => void) | null = null;
  export let refreshing: boolean = false;
  
  let outputElement: HTMLPreElement;
  let lineNumbersElement: HTMLDivElement;
  let searchQuery: string = '';
  let searchResults: number[] = [];
  let currentSearchIndex: number = -1;
  let showLineNumbers: boolean = true;
  let autoScroll: boolean = true;
  let isAtBottom: boolean = true;
  let highlightedContent: string = '';
  let showSettingsMenu: boolean = false;
  let fontSize: 'small' | 'medium' | 'large' = 'medium';
  let wordWrap: boolean = true;
  
  // Line processing
  let lines: string[] = [];
  let filteredLines: { lineNumber: number; content: string; matches: number[] }[] = [];
  
  $: {
    lines = content.split('\n');
    updateFilteredLines();
  }
  
  $: {
    if (searchQuery) {
      highlightSearchResults();
    } else {
      highlightedContent = escapeHtml(content);
    }
  }
  
  function updateFilteredLines() {
    if (!searchQuery) {
      filteredLines = lines.map((line, index) => ({
        lineNumber: index + 1,
        content: line,
        matches: []
      }));
      return;
    }
    
    const query = searchQuery.toLowerCase();
    searchResults = [];
    filteredLines = [];
    
    lines.forEach((line, index) => {
      const lowerLine = line.toLowerCase();
      const matches: number[] = [];
      let pos = 0;
      
      while (pos < lowerLine.length) {
        const found = lowerLine.indexOf(query, pos);
        if (found === -1) break;
        matches.push(found);
        searchResults.push(index);
        pos = found + 1;
      }
      
      if (matches.length > 0) {
        filteredLines.push({
          lineNumber: index + 1,
          content: line,
          matches
        });
      }
    });
    
    if (searchResults.length > 0 && currentSearchIndex === -1) {
      currentSearchIndex = 0;
      scrollToSearchResult(0);
    }
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
      highlightedContent = escapeHtml(content);
      searchResults = [];
      currentSearchIndex = -1;
      return;
    }
    
    // Escape special regex characters but preserve the search term
    const escapedQuery = searchQuery.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    
    try {
      const regex = new RegExp(`(${escapedQuery})`, 'gi');
      // First escape HTML, then apply search highlighting
      const escaped = escapeHtml(content);
      
      // Count matches to update searchResults
      const matches = escaped.match(regex);
      searchResults = matches ? Array.from({length: matches.length}, (_, i) => i) : [];
      
      highlightedContent = escaped.replace(regex, '<mark class="search-highlight">$1</mark>');
      
      // Auto-scroll to first result
      if (searchResults.length > 0 && currentSearchIndex === -1) {
        currentSearchIndex = 0;
        scrollToSearchResult(0);
      }
    } catch (error) {
      // Fallback to escaped content if regex fails
      console.warn('Search highlighting failed:', error);
      highlightedContent = escapeHtml(content);
      searchResults = [];
    }
  }
  
  function scrollToSearchResult(index: number) {
    if (!outputElement || searchResults.length === 0) return;
    
    // Wait for DOM to update with highlights
    setTimeout(() => {
      const marks = outputElement.querySelectorAll('mark.search-highlight');
      if (marks.length > 0 && marks[index]) {
        const mark = marks[index] as HTMLElement;
        // Scroll the mark into view centered
        mark.scrollIntoView({ behavior: 'smooth', block: 'center' });
        currentSearchIndex = index;
        
        // Add visual emphasis to current result
        marks.forEach((m, i) => {
          if (i === index) {
            (m as HTMLElement).style.backgroundColor = '#fbbf24';
            (m as HTMLElement).style.color = '#7c2d12';
          } else {
            (m as HTMLElement).style.backgroundColor = '#fef08a';
            (m as HTMLElement).style.color = '#92400e';
          }
        });
      }
    }, 10);
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
    if (!outputElement) return;

    const { scrollTop, scrollHeight, clientHeight } = outputElement;
    isAtBottom = scrollTop + clientHeight >= scrollHeight - 5;

    // Sync line numbers scroll position - make sure it follows
    if (lineNumbersElement && showLineNumbers) {
      lineNumbersElement.scrollTop = scrollTop;
    }

    // Load more content if near bottom and more is available
    if (isAtBottom && hasMoreContent && onLoadMore && !isLoading) {
      loadMoreOutput();
    }
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
  
  // Auto-scroll to bottom when new content arrives (if enabled and user is at bottom)
  $: if (autoScroll && isAtBottom && outputElement && content) {
    setTimeout(() => {
      if (outputElement && isAtBottom) {
        outputElement.scrollTop = outputElement.scrollHeight;
      }
    }, 10);
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

  // Font size classes
  $: fontSizeClass = {
    small: 'text-xs',
    medium: 'text-sm',
    large: 'text-base'
  }[fontSize];
</script>

<div class="enhanced-output-viewer" on:click={handleClickOutside}>
  <!-- Search and Controls Header -->
  <div class="viewer-header">
    <div class="search-controls">
      <div class="search-input-group">
        <svg class="search-icon" viewBox="0 0 24 24" fill="currentColor">
          <path d="M9.5,3A6.5,6.5 0 0,1 16,9.5C16,11.11 15.41,12.59 14.44,13.73L14.71,14H15.5L20.5,19L19,20.5L14,15.5V14.71L13.73,14.44C12.59,15.41 11.11,16 9.5,16A6.5,6.5 0 0,1 3,9.5A6.5,6.5 0 0,1 9.5,3M9.5,5C7,5 5,7 5,9.5C5,12 7,14 9.5,14C12,14 14,12 14,9.5C14,7 12,5 9.5,5Z"/>
        </svg>
        <input
          type="text"
          placeholder="Search in output..."
          bind:value={searchQuery}
          class="search-input"
        />
        {#if searchQuery && searchResults.length > 0}
          <div class="search-results-info">
            {currentSearchIndex + 1} of {searchResults.length}
          </div>
        {/if}
      </div>
      
      {#if searchQuery}
        <div class="search-navigation">
          <button 
            class="search-nav-btn" 
            on:click={prevSearchResult}
            disabled={searchResults.length === 0}
            title="Previous result"
          >
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M15.41,16.58L10.83,12L15.41,7.41L14,6L8,12L14,18L15.41,16.58Z"/>
            </svg>
          </button>
          <button 
            class="search-nav-btn" 
            on:click={nextSearchResult}
            disabled={searchResults.length === 0}
            title="Next result"
          >
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M8.59,16.58L13.17,12L8.59,7.41L10,6L16,12L10,18L8.59,16.58Z"/>
            </svg>
          </button>
        </div>
      {/if}
    </div>
    
    <div class="viewer-controls">
      <!-- Streaming Indicator (removed) -->

      <!-- Refresh Button -->
      {#if onRefresh}
        <button
          class="control-btn"
          on:click={onRefresh}
          disabled={refreshing}
          title="Refresh {type}"
        >
          <RefreshCw class="w-3.5 h-3.5 {refreshing ? 'animate-spin' : ''}" />
        </button>
      {/if}

      <!-- Scroll Controls -->
      <button class="control-btn" on:click={handleScrollToTop} title="Scroll to top">
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M7.41,15.41L12,10.83L16.59,15.41L18,14L12,8L6,14L7.41,15.41Z"/>
        </svg>
      </button>

      <button class="control-btn" on:click={handleScrollToBottom} title="Scroll to bottom">
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M7.41,8.59L12,13.17L16.59,8.59L18,10L12,16L6,10L7.41,8.59Z"/>
        </svg>
      </button>

      <!-- Settings Menu -->
      <div class="settings-dropdown relative">
        <button class="control-btn" on:click={() => showSettingsMenu = !showSettingsMenu} title="View settings">
          <Settings class="w-3.5 h-3.5" />
        </button>

        {#if showSettingsMenu}
          <div class="settings-menu absolute right-0 top-full mt-2 w-48 bg-white rounded-md shadow-lg border border-gray-200 z-50">
            <div class="py-1">
              <!-- Text Size -->
              <div class="px-4 py-2 text-xs font-medium text-gray-500 uppercase tracking-wider">Text Size</div>
              <button
                class="flex items-center gap-2 w-full px-4 py-2 text-sm hover:bg-gray-100 {fontSize === 'small' ? 'text-blue-600 bg-blue-50' : 'text-gray-700'}"
                on:click={() => setFontSize('small')}
              >
                <Type class="w-3 h-3" />
                Small
              </button>
              <button
                class="flex items-center gap-2 w-full px-4 py-2 text-sm hover:bg-gray-100 {fontSize === 'medium' ? 'text-blue-600 bg-blue-50' : 'text-gray-700'}"
                on:click={() => setFontSize('medium')}
              >
                <Type class="w-4 h-4" />
                Medium
              </button>
              <button
                class="flex items-center gap-2 w-full px-4 py-2 text-sm hover:bg-gray-100 {fontSize === 'large' ? 'text-blue-600 bg-blue-50' : 'text-gray-700'}"
                on:click={() => setFontSize('large')}
              >
                <Type class="w-5 h-5" />
                Large
              </button>

              <div class="border-t border-gray-100 my-1"></div>

              <!-- Display Options -->
              <button
                class="flex items-center gap-2 w-full px-4 py-2 text-sm hover:bg-gray-100 {showLineNumbers ? 'text-blue-600 bg-blue-50' : 'text-gray-700'}"
                on:click={toggleLineNumbers}
              >
                <Hash class="w-4 h-4" />
                {showLineNumbers ? 'Hide' : 'Show'} Line Numbers
              </button>
              <button
                class="flex items-center gap-2 w-full px-4 py-2 text-sm hover:bg-gray-100 {wordWrap ? 'text-blue-600 bg-blue-50' : 'text-gray-700'}"
                on:click={toggleWordWrap}
              >
                <WrapText class="w-4 h-4" />
                {wordWrap ? 'Disable' : 'Enable'} Word Wrap
              </button>
            </div>
          </div>
        {/if}
      </div>
      
    </div>
  </div>
  
  <!-- Output Content -->
  <div class="output-container">
    {#if isLoading && !content}
      <div class="loading-state">
        <LoadingSpinner message="Loading {type}..." />
      </div>
    {:else if content}
      <div class="output-wrapper" class:with-line-numbers={showLineNumbers} class:error-type={type === 'error'}>
        {#if showLineNumbers}
          <div class="line-numbers" bind:this={lineNumbersElement}>
            {#each lines as _, index}
              <div class="line-number">{index + 1}</div>
            {/each}
          </div>
        {/if}
        <pre
          class="output-content {fontSizeClass}"
          class:error-type={type === 'error'}
          class:wrap={wordWrap}
          bind:this={outputElement}
          on:scroll={() => checkScrollPosition()}
        >{@html highlightedContent}</pre>
      </div>
      
      {#if isLoading && hasMoreContent}
        <div class="loading-more">
          <div class="loading-spinner small"></div>
          <span>Loading more {type}...</span>
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
  
  <!-- Bottom Status Bar -->
  <div class="status-bar">
    <div class="status-info">
      {#if content}
        <span class="line-count">{lines.length} lines</span>
        {#if searchQuery && searchResults.length > 0}
          <span class="search-status">{searchResults.length} matches found</span>
        {/if}
      {/if}
    </div>

    <div class="status-controls">
      <!-- Removed scroll-to-bottom button as requested -->
    </div>
  </div>
</div>

<style>
  .enhanced-output-viewer {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    overflow: hidden;
  }

  .viewer-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 1rem;
    background: #f9fafb;
    border-bottom: 1px solid #e5e7eb;
    gap: 1rem;
  }

  .search-controls {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex: 1;
    max-width: 400px;
  }

  .search-input-group {
    position: relative;
    flex: 1;
    display: flex;
    align-items: center;
  }

  .search-icon {
    position: absolute;
    left: 0.75rem;
    width: 16px;
    height: 16px;
    color: #6b7280;
    z-index: 1;
  }

  .search-input {
    width: 100%;
    padding: 0.5rem 0.75rem 0.5rem 2.5rem;
    border: 1px solid #d1d5db;
    border-radius: 8px;
    font-size: 0.875rem;
    background: white;
    transition: border-color 0.2s;
  }

  .search-input:focus {
    outline: none;
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  .search-results-info {
    position: absolute;
    right: 0.75rem;
    font-size: 0.75rem;
    color: #6b7280;
    background: white;
    padding: 0.125rem 0.5rem;
    border-radius: 4px;
    border: 1px solid #e5e7eb;
  }

  .search-navigation {
    display: flex;
    gap: 0.25rem;
  }

  .search-nav-btn {
    width: 32px;
    height: 32px;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    background: white;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #6b7280;
    transition: all 0.2s;
  }

  .search-nav-btn:hover:not(:disabled) {
    background: #f3f4f6;
    border-color: #9ca3af;
  }

  .search-nav-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .search-nav-btn svg {
    width: 16px;
    height: 16px;
  }

  .viewer-controls {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  /* Streaming indicator styles removed */
  /* .streaming-indicator {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.375rem 0.75rem;
    background: #fef3c7;
    border: 1px solid #f59e0b;
    border-radius: 6px;
    font-size: 0.75rem;
    font-weight: 500;
    color: #92400e;
  }

  .streaming-dot {
    width: 8px;
    height: 8px;
    background: #f59e0b;
    border-radius: 50%;
    animation: pulse 2s infinite;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  } */

  .control-btn {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.375rem 0.5rem;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    background: white;
    font-size: 0.75rem;
    color: #6b7280;
    transition: all 0.2s;
  }

  .control-btn:hover {
    background: #f3f4f6;
    border-color: #9ca3af;
  }

  .control-btn.active {
    background: #3b82f6;
    border-color: #3b82f6;
    color: white;
  }

  .control-btn svg {
    width: 14px;
    height: 14px;
  }

  .control-label {
    font-weight: 500;
  }

  .output-container {
    flex: 1;
    position: relative;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  .output-wrapper {
    flex: 1;
    display: flex;
    overflow: hidden;
    background: white;
  }

  .output-wrapper.error-type {
    background: #fef2f2;
  }

  .output-wrapper.with-line-numbers {
    background: linear-gradient(to right, #f9fafb 60px, white 60px);
  }

  .output-wrapper.with-line-numbers.error-type {
    background: linear-gradient(to right, #f9fafb 60px, #fef2f2 60px);
  }

  .line-numbers {
    width: 60px;
    background: #f9fafb;
    border-right: 1px solid #e5e7eb;
    padding: 1rem 0.75rem;
    overflow-y: hidden;
    overflow-x: hidden;
    font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
    font-size: 0.75rem;
    line-height: 1.5;
    color: #9ca3af;
    text-align: right;
    user-select: none;
    flex-shrink: 0;
    pointer-events: none;
  }

  .line-number {
    height: 1.5rem;
    display: flex;
    align-items: center;
    justify-content: flex-end;
  }

  .output-content {
    flex: 1;
    padding: 1rem;
    margin: 0;
    font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
    line-height: 1.5;
    white-space: pre;
    overflow: auto;
    background: transparent;
    color: #1f2937;
    border: none;
    outline: none;
  }

  .output-content.wrap {
    white-space: pre-wrap;
    word-wrap: break-word;
    overflow-wrap: break-word;
  }

  .output-content.text-xs {
    font-size: 0.75rem;
  }

  .output-content.text-sm {
    font-size: 0.875rem;
  }

  .output-content.text-base {
    font-size: 1rem;
  }

  .settings-menu {
    min-width: 200px;
  }

  .relative {
    position: relative;
  }

  .output-content.error-type {
    color: #7f1d1d;
  }

  .loading-state,
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: #6b7280;
    gap: 1rem;
  }

  .loading-spinner.small {
    width: 16px;
    height: 16px;
    border-width: 2px;
    border: 2px solid #e5e7eb;
    border-top-color: #3b82f6;
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .loading-more {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    padding: 1rem;
    background: #f9fafb;
    border-top: 1px solid #e5e7eb;
    font-size: 0.875rem;
    color: #6b7280;
  }

  .empty-icon {
    width: 48px;
    height: 48px;
    opacity: 0.5;
  }

  .status-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.5rem 1rem;
    background: #f9fafb;
    border-top: 1px solid #e5e7eb;
    font-size: 0.75rem;
    color: #6b7280;
  }

  .status-info {
    display: flex;
    gap: 1rem;
  }

  .status-controls {
    display: flex;
    gap: 0.5rem;
  }

  :global(.search-highlight) {
    background: #fef08a;
    color: #92400e;
    padding: 0.125rem 0.25rem;
    border-radius: 3px;
    font-weight: 600;
  }

  @media (max-width: 768px) {
    .viewer-header {
      padding: 0.5rem;
      gap: 0.5rem;
    }

    .search-controls {
      max-width: none;
      flex: 1;
    }

    .search-input-group {
      min-width: 0;
    }

    .search-input {
      padding: 0.375rem 0.5rem 0.375rem 2rem;
      font-size: 0.75rem;
    }

    .search-icon {
      left: 0.5rem;
      width: 14px;
      height: 14px;
    }

    .search-results-info {
      display: none;
    }

    .search-navigation {
      /* Keep visible on mobile when searching */
      display: flex;
    }

    .search-nav-btn {
      width: 28px;
      height: 28px;
    }

    .search-nav-btn svg {
      width: 14px;
      height: 14px;
    }

    .viewer-controls {
      gap: 0.25rem;
    }

    .control-btn {
      padding: 0.25rem;
      border-radius: 4px;
      display: flex;
      align-items: center;
      justify-content: center;
      width: 26px;
      height: 26px;
    }

    .control-btn svg {
      width: 14px;
      height: 14px;
    }

    /* .streaming-indicator {
      display: none;
    } */

    .control-label {
      display: none;
    }

    .status-bar {
      flex-direction: column;
      gap: 0.5rem;
      align-items: flex-start;
    }

    .output-content.text-xs {
      font-size: 0.625rem;
    }

    .output-content.text-sm {
      font-size: 0.6875rem;
    }

    .output-content.text-base {
      font-size: 0.75rem;
    }
  }
</style>