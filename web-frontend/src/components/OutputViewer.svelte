<script lang="ts">
  import { run } from 'svelte/legacy';
  import { untrack } from 'svelte';

  import { onMount, onDestroy } from 'svelte';
  import LoadingSpinner from './LoadingSpinner.svelte';
  import { Settings, Type, Hash, WrapText, RefreshCw } from 'lucide-svelte';
  
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
    refreshing = false
  }: Props = $props();

  let outputElement: HTMLPreElement = $state();
  let lineNumbersElement: HTMLDivElement = $state();
  let searchQuery: string = $state('');
  let searchResults: number[] = $state([]);
  let currentSearchIndex: number = $state(-1);
  let showLineNumbers: boolean = $state(true);
  let autoScroll: boolean = true;
  let isAtBottom: boolean = $state(true);
  let highlightedContent: string = $state('');
  let showSettingsMenu: boolean = $state(false);
  let fontSize: 'small' | 'medium' | 'large' = $state('medium');
  let wordWrap: boolean = $state(true);

  // Progressive loading constants
  const MAX_INITIAL_SIZE = 2 * 1024 * 1024; // 2MB initial load
  const CHUNK_SIZE = 500 * 1024; // 500KB per chunk
  const WINDOW_SIZE = 3 * 1024 * 1024; // 3MB window in DOM
  const BUFFER_SIZE = 500 * 1024; // 500KB buffer before/after viewport
  const LARGE_FILE_THRESHOLD = 5 * 1024 * 1024; // 5MB for warnings
  const DISABLE_HIGHLIGHTING_THRESHOLD = 1 * 1024 * 1024; // 1MB

  // Progressive loading state
  let renderedContent: string = $state('');
  let windowStart: number = $state(0); // Start of the rendered window
  let windowEnd: number = $state(0); // End of the rendered window
  let totalContentSize: number = $state(0);
  let isLargeFile: boolean = $state(false);
  let loadingMore: boolean = $state(false);
  let disableHighlighting: boolean = $state(false);
  let showSizeWarning: boolean = $state(false);
  let warningDismissTimer: NodeJS.Timeout | null = null;
  let userInteractionCount: number = $state(0);
  let virtualScrollOffset: number = 0; // Virtual scroll position
  let scrollPlaceholder: HTMLDivElement; // Placeholder to maintain scroll height
  
  // Line processing
  let lines: string[] = $state([]);
  let filteredLines: { lineNumber: number; content: string; matches: number[] }[] = [];


  function initializeContent() {
    totalContentSize = content.length;
    isLargeFile = totalContentSize > LARGE_FILE_THRESHOLD;
    showSizeWarning = totalContentSize > LARGE_FILE_THRESHOLD;
    disableHighlighting = totalContentSize > DISABLE_HIGHLIGHTING_THRESHOLD;
    userInteractionCount = 0;

    // Auto-dismiss warning after 8 seconds
    if (showSizeWarning) {
      if (warningDismissTimer) clearTimeout(warningDismissTimer);
      warningDismissTimer = setTimeout(() => {
        showSizeWarning = false;
      }, 8000);
    }

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
      updateFilteredLines();

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
    // Dismiss warning on search (shows user is actively working)
    // Use untrack to prevent infinite loop from reading/writing showSizeWarning
    if (searchQuery) {
      untrack(() => {
        if (showSizeWarning) {
          dismissWarning();
        }
      });
    }

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
      
      // Auto-scroll to first result
      if (searchResults.length > 0 && currentSearchIndex === -1) {
        currentSearchIndex = 0;
        scrollToSearchResult(0);
      }
    } catch (error) {
      // Fallback to escaped content if regex fails
      console.warn('Search highlighting failed:', error);
      highlightedContent = escapeHtml(renderedContent);
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
    if (!outputElement || loadingMore) return;

    const { scrollTop, scrollHeight, clientHeight } = outputElement;
    isAtBottom = scrollTop + clientHeight >= scrollHeight - 5;

    // Track user interaction for auto-dismissing warning
    if (showSizeWarning && scrollTop > 100) {
      userInteractionCount++;
      if (userInteractionCount >= 3) {
        dismissWarning();
      }
    }

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

    // Calculate actual boundaries
    const newStart = Math.max(0, start - BUFFER_SIZE);
    const newEnd = Math.min(totalContentSize, end + BUFFER_SIZE);

    // Ensure window doesn't exceed maximum size
    if (newEnd - newStart > WINDOW_SIZE) {
      if (preserveScrollTop > outputElement.scrollHeight / 2) {
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
    virtualScrollOffset = windowStart;

    // Update display
    await updateRenderedContent();

    // Restore approximate scroll position
    if (outputElement) {
      // Calculate where we should be in the new content
      const contentProgress = (preserveScrollTop / outputElement.scrollHeight);
      outputElement.scrollTop = contentProgress * outputElement.scrollHeight;
    }

    loadingMore = false;
  }

  function dismissWarning() {
    showSizeWarning = false;
    if (warningDismissTimer) {
      clearTimeout(warningDismissTimer);
      warningDismissTimer = null;
    }
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
      virtualScrollOffset = windowStart;
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
    if (warningDismissTimer) {
      clearTimeout(warningDismissTimer);
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
    if (currentContent) {
      // Use untrack to prevent tracking nested state reads in initializeContent
      // This prevents circular dependencies with searchQuery, showSizeWarning, etc.
      untrack(() => initializeContent());
    }
  });

  // React to search query changes
  run(() => {
    const query = searchQuery; // Track only searchQuery
    if (query) {
      // Use untrack to prevent tracking any state reads inside highlightSearchResults
      // This prevents the effect from tracking renderedContent, showSizeWarning, etc.
      untrack(() => highlightSearchResults());
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

<div class="enhanced-output-viewer" onclick={handleClickOutside} role="presentation">
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
            onclick={prevSearchResult}
            disabled={searchResults.length === 0}
            title="Previous result"
          >
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M15.41,16.58L10.83,12L15.41,7.41L14,6L8,12L14,18L15.41,16.58Z"/>
            </svg>
          </button>
          <button 
            class="search-nav-btn" 
            onclick={nextSearchResult}
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
          onclick={onRefresh}
          disabled={refreshing}
          title="Refresh {type}"
        >
          <RefreshCw class="w-3.5 h-3.5 {refreshing ? 'animate-spin' : ''}" />
        </button>
      {/if}

      <!-- Scroll Controls -->
      <button class="control-btn" onclick={handleScrollToTop} title="Scroll to top">
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M7.41,15.41L12,10.83L16.59,15.41L18,14L12,8L6,14L7.41,15.41Z"/>
        </svg>
      </button>

      <button class="control-btn" onclick={handleScrollToBottom} title="Scroll to bottom">
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M7.41,8.59L12,13.17L16.59,8.59L18,10L12,16L6,10L7.41,8.59Z"/>
        </svg>
      </button>

      <!-- Settings Menu -->
      <div class="settings-dropdown relative">
        <button class="control-btn" onclick={() => showSettingsMenu = !showSettingsMenu} title="View settings">
          <Settings class="w-3.5 h-3.5" />
        </button>

        {#if showSettingsMenu}
          <div class="settings-menu absolute right-0 top-full mt-2 w-48 bg-popover rounded-md shadow-lg border border-border z-50">
            <div class="py-1">
              <!-- Text Size -->
              <div class="px-4 py-2 text-xs font-medium text-muted-foreground uppercase tracking-wider">Text Size</div>
              <button
                class="flex items-center gap-2 w-full px-4 py-2 text-sm hover:bg-secondary {fontSize === 'small' ? 'text-accent bg-accent/10' : 'text-foreground'}"
                onclick={() => setFontSize('small')}
              >
                <Type class="w-3 h-3" />
                Small
              </button>
              <button
                class="flex items-center gap-2 w-full px-4 py-2 text-sm hover:bg-secondary {fontSize === 'medium' ? 'text-accent bg-accent/10' : 'text-foreground'}"
                onclick={() => setFontSize('medium')}
              >
                <Type class="w-4 h-4" />
                Medium
              </button>
              <button
                class="flex items-center gap-2 w-full px-4 py-2 text-sm hover:bg-secondary {fontSize === 'large' ? 'text-accent bg-accent/10' : 'text-foreground'}"
                onclick={() => setFontSize('large')}
              >
                <Type class="w-5 h-5" />
                Large
              </button>

              <div class="border-t border-border my-1"></div>

              <!-- Display Options -->
              <button
                class="flex items-center gap-2 w-full px-4 py-2 text-sm hover:bg-secondary {showLineNumbers ? 'text-accent bg-accent/10' : 'text-foreground'}"
                onclick={toggleLineNumbers}
              >
                <Hash class="w-4 h-4" />
                {showLineNumbers ? 'Hide' : 'Show'} Line Numbers
              </button>
              <button
                class="flex items-center gap-2 w-full px-4 py-2 text-sm hover:bg-secondary {wordWrap ? 'text-accent bg-accent/10' : 'text-foreground'}"
                onclick={toggleWordWrap}
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
  
  <!-- Floating Size Warning -->
  {#if showSizeWarning && !isLoading}
    <div class="size-warning-floating" class:fade-out={userInteractionCount > 1}>
      <div class="warning-inner">
        <svg class="warning-icon" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>
        </svg>
        <div class="warning-content">
          <span class="warning-text">
            Large file: {formatBytes(totalContentSize)}
            {#if disableHighlighting}
              • Highlighting disabled
            {/if}
          </span>
          {#if windowEnd < totalContentSize}
            <span class="warning-subtext">
              Loading progressively as you scroll
            </span>
          {/if}
        </div>
        <button
          class="dismiss-btn"
          onclick={dismissWarning}
          title="Dismiss"
        >
          <svg viewBox="0 0 20 20" fill="currentColor">
            <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z"/>
          </svg>
        </button>
      </div>
      <div class="warning-progress" style="width: {Math.min(100, (windowEnd / totalContentSize) * 100)}%"></div>
    </div>
  {/if}

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

    {#if isLoading && !renderedContent}
      <div class="loading-state">
        <LoadingSpinner message="Loading {type}..." />
      </div>
    {:else if renderedContent}
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
  
  <!-- Bottom Status Bar -->
  <div class="status-bar">
    <div class="status-info">
      {#if renderedContent}
        <span class="line-count">{lines.length} lines</span>
        {#if totalContentSize > 0}
          <span class="size-info">{formatBytes(Math.min(windowEnd, totalContentSize))} / {formatBytes(totalContentSize)}</span>
        {/if}
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
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
  }

  .viewer-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 1rem;
    background: var(--secondary);
    border-bottom: 1px solid var(--border);
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
    border: 1px solid var(--border);
    border-radius: 8px;
    font-size: 0.875rem;
    background: var(--input);
    color: var(--foreground);
    transition: border-color 0.2s;
  }

  .search-input:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  .search-results-info {
    position: absolute;
    right: 0.75rem;
    font-size: 0.75rem;
    color: var(--muted-foreground);
    background: var(--card);
    padding: 0.125rem 0.5rem;
    border-radius: 4px;
    border: 1px solid var(--border);
  }

  .search-navigation {
    display: flex;
    gap: 0.25rem;
  }

  .search-nav-btn {
    width: 32px;
    height: 32px;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--card);
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--muted-foreground);
    transition: all 0.2s;
  }

  .search-nav-btn:hover:not(:disabled) {
    background: var(--secondary);
    border-color: var(--muted);
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
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--card);
    font-size: 0.75rem;
    color: var(--muted-foreground);
    transition: all 0.2s;
  }

  .control-btn:hover {
    background: var(--secondary);
    border-color: var(--muted);
  }

  .control-btn.active {
    background: var(--accent);
    border-color: var(--accent);
    color: var(--accent-foreground);
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
    background: var(--card);
  }

  .output-wrapper.error-type {
    background: #fef2f2;
  }

  .output-wrapper.with-line-numbers {
    background: linear-gradient(to right, var(--secondary) 60px, var(--card) 60px);
  }

  .output-wrapper.with-line-numbers.error-type {
    background: linear-gradient(to right, var(--secondary) 60px, #fef2f2 60px);
  }

  .line-numbers {
    width: 60px;
    background: var(--secondary);
    border-right: 1px solid var(--border);
    padding: 1rem 0.75rem;
    overflow-y: hidden;
    overflow-x: hidden;
    font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
    font-size: 0.75rem;
    line-height: 1.5;
    color: var(--muted-foreground);
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
    color: var(--foreground);
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
    background: var(--secondary);
    border-top: 1px solid var(--border);
    font-size: 0.875rem;
    color: var(--muted-foreground);
  }

  .load-more-indicator {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 1rem;
    background: #f0f9ff;
    border-top: 1px solid #bae6fd;
    font-size: 0.875rem;
  }

  .indicator-text {
    color: #0369a1;
    font-weight: 500;
  }

  .indicator-subtext {
    color: #0c4a6e;
    font-size: 0.75rem;
    margin-top: 0.25rem;
  }

  .size-warning-floating {
    position: fixed;
    top: 1rem;
    right: 1rem;
    z-index: 100;
    background: var(--card);
    border-radius: 12px;
    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1), 0 6px 10px rgba(0, 0, 0, 0.08);
    overflow: hidden;
    animation: slideIn 0.3s ease-out;
    transition: all 0.3s ease;
    max-width: 320px;
  }

  .size-warning-floating.fade-out {
    opacity: 0.7;
    transform: scale(0.95);
  }

  @keyframes slideIn {
    from {
      transform: translateY(-100%);
      opacity: 0;
    }
    to {
      transform: translateY(0);
      opacity: 1;
    }
  }

  .warning-inner {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.875rem 1rem;
    background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
  }

  .warning-icon {
    width: 20px;
    height: 20px;
    color: #d97706;
    flex-shrink: 0;
  }

  .warning-content {
    display: flex;
    flex-direction: column;
    flex: 1;
    gap: 0.125rem;
  }

  .warning-text {
    color: #92400e;
    font-weight: 600;
    font-size: 0.8125rem;
    line-height: 1.2;
  }

  .warning-subtext {
    color: #78350f;
    font-size: 0.6875rem;
    opacity: 0.9;
  }

  .dismiss-btn {
    padding: 0.125rem;
    background: transparent;
    border: none;
    cursor: pointer;
    color: #92400e;
    transition: all 0.2s;
    border-radius: 4px;
    opacity: 0.6;
  }

  .dismiss-btn:hover {
    opacity: 1;
    background: rgba(217, 119, 6, 0.1);
  }

  .dismiss-btn svg {
    width: 14px;
    height: 14px;
  }

  .warning-progress {
    position: absolute;
    bottom: 0;
    left: 0;
    height: 2px;
    background: linear-gradient(90deg, #f59e0b 0%, #d97706 100%);
    transition: width 0.3s ease;
  }

  .size-info {
    background: #e0f2fe;
    color: #0369a1;
    padding: 0.125rem 0.5rem;
    border-radius: 4px;
    font-weight: 500;
  }

  .content-indicator {
    position: absolute;
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.25rem 0.625rem;
    background: rgba(255, 255, 255, 0.95);
    backdrop-filter: blur(8px);
    border: 1px solid rgba(229, 231, 235, 0.8);
    border-radius: 9999px;
    font-size: 0.6875rem;
    font-weight: 500;
    color: #6b7280;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
    z-index: 10;
    transition: all 0.2s ease;
    opacity: 0.8;
  }

  .content-indicator:hover {
    opacity: 1;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
  }

  .top-indicator {
    top: 0.5rem;
  }

  .bottom-indicator {
    bottom: 0.5rem;
  }

  .indicator-dots {
    display: flex;
    gap: 2px;
    align-items: center;
  }

  .dot {
    width: 3px;
    height: 3px;
    background: #9ca3af;
    border-radius: 50%;
    animation: pulse 1.5s ease-in-out infinite;
  }

  .dot:nth-child(1) {
    animation-delay: 0s;
  }

  .dot:nth-child(2) {
    animation-delay: 0.2s;
  }

  .dot:nth-child(3) {
    animation-delay: 0.4s;
  }

  @keyframes pulse {
    0%, 80%, 100% {
      opacity: 0.3;
    }
    40% {
      opacity: 1;
    }
  }

  .indicator-text {
    color: #6b7280;
    white-space: nowrap;
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
    background: var(--secondary);
    border-top: 1px solid var(--border);
    font-size: 0.75rem;
    color: var(--muted-foreground);
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
    .size-warning-floating {
      top: 0.5rem;
      right: 0.5rem;
      left: 0.5rem;
      max-width: none;
    }

    .warning-inner {
      padding: 0.625rem 0.75rem;
    }

    .warning-text {
      font-size: 0.75rem;
    }

    .warning-subtext {
      font-size: 0.625rem;
    }

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