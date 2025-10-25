<script lang="ts">
  import { run } from 'svelte/legacy';

  import { onMount, onDestroy } from 'svelte';
  import LoadingSpinner from './LoadingSpinner.svelte';
  import { Settings, Type, Hash, WrapText } from 'lucide-svelte';
  
  interface Props {
    content?: string;
    isLoading?: boolean;
    onDownload?: (() => void) | null;
    onScrollToTop?: (() => void) | null;
    onScrollToBottom?: (() => void) | null;
    fileName?: string;
  }

  let {
    content = '',
    isLoading = false,
    onDownload = null,
    onScrollToTop = null,
    onScrollToBottom = null,
    fileName = 'script.sh'
  }: Props = $props();

  let scriptElement: HTMLPreElement = $state();
  let lineNumbersElement: HTMLDivElement = $state();
  let searchQuery: string = $state('');
  let searchResults: number[] = $state([]);
  let currentSearchIndex: number = $state(-1);
  let showLineNumbers: boolean = $state(true);
  let highlightedContent: string = $state('');
  let showSettingsMenu: boolean = $state(false);
  let fontSize: 'small' | 'medium' | 'large' = $state('medium');
  let wordWrap: boolean = $state(true);

  // Progressive loading constants
  const MAX_INITIAL_SIZE = 1 * 1024 * 1024; // 1MB initial load for scripts
  const CHUNK_SIZE = 200 * 1024; // 200KB per chunk
  const WINDOW_SIZE = 2 * 1024 * 1024; // 2MB window in DOM for scripts
  const BUFFER_SIZE = 200 * 1024; // 200KB buffer before/after viewport
  const LARGE_FILE_THRESHOLD = 2 * 1024 * 1024; // 2MB for warnings
  const DISABLE_HIGHLIGHTING_THRESHOLD = 500 * 1024; // 500KB

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
  
  // Line processing
  let lines: string[] = $state([]);


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

  function updateRenderedContent() {
    lines = renderedContent.split('\n');

    if (searchQuery) {
      highlightSearchResults();
    } else if (!disableHighlighting) {
      highlightedContent = applySyntaxHighlighting(renderedContent);
    } else {
      // Skip highlighting for large files
      highlightedContent = escapeHtml(renderedContent);
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

  function applySyntaxHighlighting(text: string): string {
    if (!text) return '';

    // Start with escaped text to prevent XSS
    let highlighted = escapeHtml(text);

    // Apply syntax highlighting patterns
    // Note: Order matters - more specific patterns first

    // Shebang line first (most specific) - handle both escaped and unescaped slashes
    highlighted = highlighted.replace(
      /(^#!.*$)/gm,
      '<span class="shebang">$1</span>'
    );

    // SLURM directives (e.g., #SBATCH)
    highlighted = highlighted.replace(
      /(^#SBATCH.*$)/gm,
      '<span class="slurm-directive">$1</span>'
    );

    // Special login setup markers
    highlighted = highlighted.replace(
      /(^#LOGIN_SETUP_(?:BEGIN|END).*$)/gm,
      '<span class="slurm-directive">$1</span>'
    );

    // Comments (but not SLURM directives, shebang, or LOGIN markers)
    highlighted = highlighted.replace(
      /(^#(?!SBATCH|!|LOGIN_SETUP_).*$)/gm,
      '<span class="comment">$1</span>'
    );
    
    // Environment variables
    highlighted = highlighted.replace(
      /(\$\{[^}]+\}|\$[A-Za-z_][A-Za-z0-9_]*)/g,
      '<span class="variable">$1</span>'
    );
    
    // Strings in double quotes (with proper escaping)
    highlighted = highlighted.replace(
      /(&quot;([^&]|&(?!quot;))*&quot;)/g,
      '<span class="string">$1</span>'
    );
    
    // Strings in single quotes (with proper escaping)
    highlighted = highlighted.replace(
      /(&#x27;([^&]|&(?!#x27;))*&#x27;)/g,
      '<span class="string">$1</span>'
    );
    
    // Keywords - need to be careful not to match inside HTML tags
    const keywords = [
      'if', 'then', 'else', 'elif', 'fi', 'for', 'while', 'do', 'done',
      'case', 'esac', 'function', 'return', 'exit', 'break', 'continue',
      'export', 'source', 'echo', 'printf', 'read', 'cd', 'pwd', 'ls',
      'cp', 'mv', 'rm', 'mkdir', 'chmod', 'chown', 'grep', 'awk', 'sed',
      'sort', 'uniq', 'head', 'tail', 'cat', 'less', 'more', 'find',
      'python', 'python3', 'pip', 'conda', 'module', 'srun', 'sbatch',
      'scancel', 'squeue', 'sinfo', 'scontrol', 'uv', 'ulimit', 'activate'
    ];
    
    keywords.forEach(keyword => {
      // Match whole words that aren't already inside a span tag
      // Use a simpler approach without lookbehind
      const regex = new RegExp(`\\b(${keyword})\\b`, 'g');
      highlighted = highlighted.replace(regex, (match, p1, offset, string) => {
        // Check if we're inside an HTML tag
        const beforeMatch = string.substring(0, offset);
        const afterMatch = string.substring(offset + match.length);

        // Simple check: if there's an unclosed tag before and a closing > after, skip
        const lastOpenTag = beforeMatch.lastIndexOf('<');
        const lastCloseTag = beforeMatch.lastIndexOf('>');
        const nextCloseTag = afterMatch.indexOf('>');

        if (lastOpenTag > lastCloseTag && nextCloseTag !== -1) {
          return match; // We're inside a tag, don't highlight
        }

        return `<span class="keyword">${p1}</span>`;
      });
    });

    // Numbers - simpler pattern
    highlighted = highlighted.replace(
      /\b(\d+\.?\d*)\b/g,
      (match, p1, offset, string) => {
        // Check if we're inside an HTML tag
        const beforeMatch = string.substring(0, offset);
        const lastOpenTag = beforeMatch.lastIndexOf('<');
        const lastCloseTag = beforeMatch.lastIndexOf('>');

        if (lastOpenTag > lastCloseTag) {
          return match; // We're inside a tag
        }

        return `<span class="number">${p1}</span>`;
      }
    );
    
    // Operators - handle escaped HTML entities
    highlighted = highlighted.replace(
      /(&lt;|&gt;|&amp;&amp;|&amp;|\||=|!|\+|-|\*|\/)/g,
      (match, p1, offset, string) => {
        // Simple check to avoid highlighting inside existing spans
        const beforeMatch = string.substring(0, offset);
        const lastOpenSpan = beforeMatch.lastIndexOf('<span');
        const lastCloseSpan = beforeMatch.lastIndexOf('</span>');

        if (lastOpenSpan > lastCloseSpan) {
          return match; // We're inside a span
        }

        return `<span class="operator">${p1}</span>`;
      }
    );
    
    return highlighted;
  }
  
  function highlightSearchResults() {
    // Dismiss warning on search (shows user is actively working)
    if (searchQuery && showSizeWarning) {
      dismissWarning();
    }

    if (!searchQuery || !renderedContent) {
      highlightedContent = applySyntaxHighlighting(renderedContent);
      searchResults = [];
      currentSearchIndex = -1;
      return;
    }

    try {
      // First apply syntax highlighting if enabled
      let highlighted = !disableHighlighting
        ? applySyntaxHighlighting(renderedContent)
        : escapeHtml(renderedContent);
      
      // Escape the search query to match against escaped content
      const escapedQuery = escapeHtml(searchQuery).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      
      // Create regex that won't match inside HTML tags
      const regex = new RegExp(`(?![^<]*>)(${escapedQuery})`, 'gi');
      
      // Count matches
      const matches = [];
      let match;
      const tempRegex = new RegExp(`(?![^<]*>)(${escapedQuery})`, 'gi');
      while ((match = tempRegex.exec(highlighted)) !== null) {
        matches.push(match);
      }
      searchResults = matches.length > 0 ? Array.from({length: matches.length}, (_, i) => i) : [];
      
      // Apply highlighting
      highlighted = highlighted.replace(regex, '<mark class="search-highlight">$1</mark>');
      
      highlightedContent = highlighted;
      
      // Auto-scroll to first result
      if (searchResults.length > 0 && currentSearchIndex === -1) {
        currentSearchIndex = 0;
        scrollToSearchResult(0);
      }
    } catch (error) {
      console.warn('Search highlighting failed:', error);
      highlightedContent = !disableHighlighting
        ? applySyntaxHighlighting(renderedContent)
        : escapeHtml(renderedContent);
      searchResults = [];
    }
  }
  
  function scrollToSearchResult(index: number) {
    if (!scriptElement || searchResults.length === 0) return;
    
    // Wait for DOM to update with highlights
    setTimeout(() => {
      const marks = scriptElement.querySelectorAll('mark.search-highlight');
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
  
  
  function handleScrollToTop() {
    if (scriptElement) {
      scriptElement.scrollTop = 0;
      // Sync line numbers
      if (lineNumbersElement) {
        lineNumbersElement.scrollTop = 0;
      }
    }
    onScrollToTop?.();
  }
  
  function handleScrollToBottom() {
    if (scriptElement) {
      scriptElement.scrollTop = scriptElement.scrollHeight;
      // Sync line numbers
      if (lineNumbersElement) {
        lineNumbersElement.scrollTop = scriptElement.scrollHeight;
      }
    }
    onScrollToBottom?.();
  }

  function onScriptScroll() {
    if (scriptElement && lineNumbersElement && showLineNumbers) {
      lineNumbersElement.scrollTop = scriptElement.scrollTop;
    }

    // Auto-load more content when scrolling near bottom
    if (scriptElement) {
      const { scrollTop, scrollHeight, clientHeight } = scriptElement;
      const scrollPercentage = (scrollTop + clientHeight) / scrollHeight;

      // Track user interaction for auto-dismissing warning
      if (showSizeWarning && scrollTop > 100) {
        userInteractionCount++;
        if (userInteractionCount >= 3) {
          dismissWarning();
        }
      }

      if (scrollPercentage > 0.8 && !loadingMore && windowEnd < totalContentSize) {
        loadMoreContentChunk();
      }
    }
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
    updateRenderedContent();
    loadingMore = false;
  }
  
  function copyToClipboard() {
    // For large files, warn before copying entire content
    if (isLargeFile && windowEnd < totalContentSize) {
      if (!confirm(`This will copy the entire script (${formatBytes(totalContentSize)}) to clipboard. Continue?`)) {
        return;
      }
    }
    navigator.clipboard.writeText(content).catch(err => {
      console.error('Failed to copy script:', err);
    });
  }

  // Initialize line numbers sync
  onMount(() => {
    if (scriptElement && lineNumbersElement) {
      scriptElement.addEventListener('scroll', onScriptScroll);
      // Initial sync
      onScriptScroll();
    }
  });

  onDestroy(() => {
    if (scriptElement) {
      scriptElement.removeEventListener('scroll', onScriptScroll);
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
    if (content) {
      initializeContent();
    }
  });
  run(() => {
    lines = renderedContent.split('\n');
    if (searchQuery) {
      highlightSearchResults();
    } else if (!disableHighlighting) {
      highlightedContent = applySyntaxHighlighting(renderedContent);
    } else {
      highlightedContent = escapeHtml(renderedContent);
    }
  });
  // Font size classes
  let fontSizeClass = $derived({
    small: 'text-xs',
    medium: 'text-sm',
    large: 'text-base'
  }[fontSize]);
</script>

<div class="enhanced-script-viewer" onclick={handleClickOutside} role="presentation">
  <!-- Header with Controls -->
  <div class="viewer-header">
    <div class="search-controls">
      <div class="search-input-group">
        <svg class="search-icon" viewBox="0 0 24 24" fill="currentColor">
          <path d="M9.5,3A6.5,6.5 0 0,1 16,9.5C16,11.11 15.41,12.59 14.44,13.73L14.71,14H15.5L20.5,19L19,20.5L14,15.5V14.71L13.73,14.44C12.59,15.41 11.11,16 9.5,16A6.5,6.5 0 0,1 3,9.5A6.5,6.5 0 0,1 9.5,3M9.5,5C7,5 5,7 5,9.5C5,12 7,14 9.5,14C12,14 14,12 14,9.5C14,7 12,5 9.5,5Z"/>
        </svg>
        <input
          type="text"
          placeholder="Search in script..."
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
      <span class="file-name">{fileName}</span>
      
      
      
      <!-- Copy to Clipboard -->
      <button class="control-btn" onclick={copyToClipboard} title="Copy script">
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M19,21H8V7H19M19,5H8A2,2 0 0,0 6,7V21A2,2 0 0,0 8,23H19A2,2 0 0,0 21,21V7A2,2 0 0,0 19,5M16,1H4A2,2 0 0,0 2,3V17H4V3H16V1Z"/>
        </svg>
      </button>
      
      <!-- Download Script -->
      {#if onDownload}
        <button class="control-btn" onclick={onDownload} title="Download script">
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M5,20H19V18H5M19,9H15V3H9V9H5L12,16L19,9Z"/>
          </svg>
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
          <div class="settings-menu absolute right-0 top-full mt-2 w-48 bg-white rounded-md shadow-lg border border-gray-200 z-50">
            <div class="py-1">
              <!-- Text Size -->
              <div class="px-4 py-2 text-xs font-medium text-gray-500 uppercase tracking-wider">Text Size</div>
              <button
                class="flex items-center gap-2 w-full px-4 py-2 text-sm hover:bg-gray-100 {fontSize === 'small' ? 'text-blue-600 bg-blue-50' : 'text-gray-700'}"
                onclick={() => setFontSize('small')}
              >
                <Type class="w-3 h-3" />
                Small
              </button>
              <button
                class="flex items-center gap-2 w-full px-4 py-2 text-sm hover:bg-gray-100 {fontSize === 'medium' ? 'text-blue-600 bg-blue-50' : 'text-gray-700'}"
                onclick={() => setFontSize('medium')}
              >
                <Type class="w-4 h-4" />
                Medium
              </button>
              <button
                class="flex items-center gap-2 w-full px-4 py-2 text-sm hover:bg-gray-100 {fontSize === 'large' ? 'text-blue-600 bg-blue-50' : 'text-gray-700'}"
                onclick={() => setFontSize('large')}
              >
                <Type class="w-5 h-5" />
                Large
              </button>

              <div class="border-t border-gray-100 my-1"></div>

              <!-- Display Options -->
              <button
                class="flex items-center gap-2 w-full px-4 py-2 text-sm hover:bg-gray-100 {showLineNumbers ? 'text-blue-600 bg-blue-50' : 'text-gray-700'}"
                onclick={toggleLineNumbers}
              >
                <Hash class="w-4 h-4" />
                {showLineNumbers ? 'Hide' : 'Show'} Line Numbers
              </button>
              <button
                class="flex items-center gap-2 w-full px-4 py-2 text-sm hover:bg-gray-100 {wordWrap ? 'text-blue-600 bg-blue-50' : 'text-gray-700'}"
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
            Large script: {formatBytes(totalContentSize)}
            {#if disableHighlighting}
              • Highlighting off
            {/if}
          </span>
          {#if windowEnd < totalContentSize}
            <span class="warning-subtext">
              Loading as you scroll
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

  <!-- Script Content -->
  <div class="script-container">
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

    {#if isLoading}
      <div class="loading-state">
        <LoadingSpinner message="Loading script..." />
      </div>
    {:else if renderedContent}
      <div class="script-content-wrapper" class:with-line-numbers={showLineNumbers}>
        {#if showLineNumbers}
          <div class="line-numbers" bind:this={lineNumbersElement}>
            {#each lines as _, index}
              <div class="line-number">{index + 1}</div>
            {/each}
          </div>
        {/if}
        <pre
          class="script-content {fontSizeClass}"
          class:wrap={wordWrap}
          bind:this={scriptElement}
          onscroll={() => onScriptScroll()}
        >{@html highlightedContent}</pre>
      </div>

      {#if loadingMore}
        <div class="loading-more">
          <div class="loading-spinner small"></div>
          <span>Loading more content...</span>
        </div>
      {:else if windowEnd < totalContentSize}
        <div class="load-more-indicator">
          <span class="indicator-text">Scroll down to load more...</span>
          <span class="indicator-subtext">{formatBytes(totalContentSize - windowEnd)} remaining</span>
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
          <path d="M9.4 16.6L4.8 12l4.6-4.6L8 6l-6 6 6 6 1.4-1.4zm5.2 0l4.6-4.6-4.6-4.6L16 6l6 6-6 6-1.4-1.4z"/>
        </svg>
        <span>No script available</span>
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
        {:else}
          <span class="char-count">{renderedContent.length} characters</span>
        {/if}
        {#if searchQuery && searchResults.length > 0}
          <span class="search-status">{searchResults.length} matches found</span>
        {/if}
      {/if}
    </div>
    
    <div class="file-info">
      <span class="file-type">Shell Script</span>
    </div>
  </div>
</div>

<style>
  .enhanced-script-viewer {
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
    background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
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

  .file-name {
    font-size: 0.875rem;
    font-weight: 600;
    color: #374151;
    background: white;
    padding: 0.375rem 0.75rem;
    border: 1px solid #d1d5db;
    border-radius: 6px;
  }

  .control-btn {
    display: flex;
    align-items: center;
    justify-content: center;
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

  .script-container {
    flex: 1;
    position: relative;
    overflow: hidden;
    height: 100%;
  }

  .script-content-wrapper {
    height: 100%;
    display: flex;
    background: #fafbfc;
  }

  .script-content-wrapper.with-line-numbers {
    background: linear-gradient(to right, #f1f5f9 60px, #fafbfc 60px);
  }

  .line-numbers {
    width: 60px;
    background: #f1f5f9;
    border-right: 1px solid #e2e8f0;
    padding: 1rem 0.75rem;
    user-select: none;
    font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
    font-size: 0.75rem;
    line-height: 1.5;
    color: #94a3b8;
    text-align: right;
    overflow-y: hidden;
    overflow-x: hidden;
    pointer-events: none;
  }

  .line-number {
    height: 1.5rem;
    display: flex;
    align-items: center;
    justify-content: flex-end;
  }

  .script-content {
    flex: 1;
    padding: 1rem;
    margin: 0;
    font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
    line-height: 1.5;
    white-space: pre;
    overflow: auto;
    background: transparent;
    color: #1f2937;
  }

  .script-content.wrap {
    white-space: pre-wrap;
    word-wrap: break-word;
    overflow-wrap: break-word;
  }

  .script-content.text-xs {
    font-size: 0.75rem;
  }

  .script-content.text-sm {
    font-size: 0.875rem;
  }

  .script-content.text-base {
    font-size: 1rem;
  }

  .settings-menu {
    min-width: 200px;
  }

  .relative {
    position: relative;
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
    background: white;
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
    background: #f9fafb;
    border-top: 1px solid #e5e7eb;
    font-size: 0.75rem;
    color: #6b7280;
  }

  .status-info {
    display: flex;
    gap: 1rem;
  }

  .file-info {
    display: flex;
    gap: 0.5rem;
  }

  .file-type {
    background: #e0f2fe;
    color: #0369a1;
    padding: 0.125rem 0.5rem;
    border-radius: 4px;
    font-weight: 500;
  }

  /* Syntax Highlighting Styles */
  :global(.slurm-directive) {
    color: #dc2626;
    font-weight: 600;
  }

  :global(.comment) {
    color: #6b7280;
    font-style: italic;
  }

  :global(.shebang) {
    color: #7c3aed;
    font-weight: 600;
  }

  :global(.variable) {
    color: #059669;
    font-weight: 500;
  }

  :global(.string) {
    color: #ea580c;
  }

  :global(.keyword) {
    color: #2563eb;
    font-weight: 600;
  }

  :global(.number) {
    color: #c2410c;
  }

  :global(.operator) {
    color: #374151;
    font-weight: 500;
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

    .file-name {
      display: none;
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

    .control-label {
      display: none;
    }

    .script-content-wrapper.with-line-numbers {
      background: linear-gradient(to right, #f1f5f9 40px, #fafbfc 40px);
    }

    .line-numbers {
      width: 40px;
      padding: 1rem 0.5rem;
    }

    .script-content.text-xs {
      font-size: 0.625rem;
    }

    .script-content.text-sm {
      font-size: 0.6875rem;
    }

    .script-content.text-base {
      font-size: 0.75rem;
    }

    .status-bar {
      flex-direction: column;
      gap: 0.5rem;
      align-items: flex-start;
    }
  }
</style>