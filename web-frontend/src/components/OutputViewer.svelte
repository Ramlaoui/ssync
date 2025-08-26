<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  
  export let content: string | null = null;
  export let loading = false;
  export let error: string | null = null;
  export let emptyMessage = "No output available";
  export let title = "";
  export let fileSize: number | null = null;
  export let modifiedDate: string | null = null;
  export let downloadUrl: string | null = null;
  export let fileName = "output.txt";
  export let syntaxHighlight: 'none' | 'bash' | 'python' | 'auto' = 'none';
  export let wrapLines = false;
  export let maxHeight = "600px";
  
  let outputElement: HTMLElement;
  let viewerContentElement: HTMLElement;
  let searchTerm = "";
  let showSearch = false;
  let currentMatch = 0;
  let totalMatches = 0;
  let highlightedContent = "";
  let copySuccess = false;
  let autoScroll = true;
  let fontSize = 14;
  let hasScrollableContent = false;
  let isAtTop = true;
  let isAtBottom = false;
  
  // Format file size
  function formatBytes(bytes: number): string {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }
  
  // Copy content to clipboard
  async function copyToClipboard() {
    if (!content) return;
    try {
      await navigator.clipboard.writeText(content);
      copySuccess = true;
      setTimeout(() => copySuccess = false, 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  }
  
  // Download content as file
  function downloadContent() {
    if (!content) return;
    
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = fileName;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }
  
  // Toggle line wrap
  function toggleWrap() {
    wrapLines = !wrapLines;
  }
  
  // Toggle search
  function toggleSearch() {
    showSearch = !showSearch;
    if (!showSearch) {
      searchTerm = "";
      highlightedContent = "";
    }
  }
  
  // Handle search
  function handleSearch() {
    if (!content || !searchTerm) {
      highlightedContent = "";
      totalMatches = 0;
      return;
    }
    
    const regex = new RegExp(`(${escapeRegex(searchTerm)})`, 'gi');
    const matches = content.match(regex);
    totalMatches = matches ? matches.length : 0;
    
    if (totalMatches > 0) {
      highlightedContent = content.replace(regex, '<mark>$1</mark>');
    } else {
      highlightedContent = "";
    }
  }
  
  // Escape regex special characters
  function escapeRegex(str: string): string {
    return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }
  
  // Keyboard shortcuts
  function handleKeydown(event: KeyboardEvent) {
    if (event.ctrlKey || event.metaKey) {
      if (event.key === 'f') {
        event.preventDefault();
        toggleSearch();
      } else if (event.key === 'c' && content) {
        // Browser handles copy automatically
      }
    }
    
    if (event.key === 'Escape' && showSearch) {
      toggleSearch();
    }
  }
  
  // Auto-scroll to bottom for live logs
  function scrollToBottom() {
    if (viewerContentElement && autoScroll) {
      viewerContentElement.scrollTop = viewerContentElement.scrollHeight;
    }
  }
  
  // Manual scroll to bottom
  function scrollToBottomManual() {
    if (viewerContentElement) {
      viewerContentElement.scrollTop = viewerContentElement.scrollHeight;
      autoScroll = true;
    }
  }
  
  // Scroll to top
  function scrollToTop() {
    if (viewerContentElement) {
      viewerContentElement.scrollTop = 0;
      autoScroll = false;
    }
  }
  
  // Detect if user manually scrolled
  function handleScroll() {
    if (viewerContentElement) {
      const scrollTop = viewerContentElement.scrollTop;
      const scrollHeight = viewerContentElement.scrollHeight;
      const clientHeight = viewerContentElement.clientHeight;
      
      // Use small threshold for better detection
      isAtTop = scrollTop <= 1;
      isAtBottom = scrollHeight - scrollTop - clientHeight <= 1;
      autoScroll = isAtBottom;
      hasScrollableContent = scrollHeight > clientHeight + 10; // Add buffer to avoid edge cases
    }
  }
  
  // Check scrollable content on mount and content change
  function checkScrollable() {
    if (viewerContentElement) {
      const scrollHeight = viewerContentElement.scrollHeight;
      const clientHeight = viewerContentElement.clientHeight;
      hasScrollableContent = scrollHeight > clientHeight + 10;
      handleScroll();
    }
  }
  
  // Process content with line numbers and highlighting
  function processContent(text: string): string {
    if (!text) return "";
    
    const lines = text.split('\n');
    const processedLines = lines.map((line, index) => {
      const lineNum = (index + 1).toString().padStart(lines.length.toString().length, ' ');
      
      // Apply search highlighting if there's a search term
      let processedLine = escapeHtml(line);
      if (searchTerm) {
        const regex = new RegExp(`(${escapeRegex(searchTerm)})`, 'gi');
        processedLine = processedLine.replace(regex, '<mark>$1</mark>');
      }
      
      return `<span class="line-number">${lineNum}</span><span class="line-content">${processedLine}</span>`;
    });
    
    return processedLines.join('\n');
  }
  
  // Escape HTML to prevent XSS
  function escapeHtml(text: string): string {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
  
  // Watch for content changes
  $: if (content) {
    scrollToBottom();
    // Check scrollable after DOM update
    setTimeout(() => {
      checkScrollable();
    }, 100);
  }
  
  onMount(() => {
    window.addEventListener('keydown', handleKeydown);
    // Check scrollable state after mount
    setTimeout(() => {
      checkScrollable();
    }, 100);
  });
  
  onDestroy(() => {
    window.removeEventListener('keydown', handleKeydown);
  });
</script>

<div class="output-viewer">
  <!-- Toolbar -->
  <div class="viewer-toolbar">
    <div class="toolbar-left">
      {#if title}
        <h3 class="viewer-title">{title}</h3>
      {/if}
      {#if fileSize !== null || modifiedDate}
        <div class="file-info">
          {#if fileSize !== null}
            <span class="info-item">
              <svg class="info-icon" viewBox="0 0 24 24" fill="currentColor">
                <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"/>
              </svg>
              {formatBytes(fileSize)}
            </span>
          {/if}
          {#if modifiedDate}
            <span class="info-item">
              <svg class="info-icon" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M16.2,16.2L11,13V7H12.5V12.2L17,14.9L16.2,16.2Z"/>
              </svg>
              {modifiedDate}
            </span>
          {/if}
        </div>
      {/if}
    </div>
    
    <div class="toolbar-right">
      <!-- Search -->
      {#if showSearch}
        <div class="search-box">
          <input
            type="text"
            bind:value={searchTerm}
            on:input={handleSearch}
            placeholder="Search..."
            class="search-input"
            autofocus
          />
          {#if totalMatches > 0}
            <span class="match-count">{totalMatches} matches</span>
          {/if}
        </div>
      {/if}
      
      <!-- Font size controls -->
      <div class="font-controls">
        <button
          class="toolbar-btn"
          on:click={() => fontSize = Math.max(10, fontSize - 2)}
          title="Decrease font size"
        >
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M12,20C7.59,20 4,16.41 4,12C4,7.59 7.59,4 12,4C16.41,4 20,7.59 20,12C20,16.41 16.41,20 12,20M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M7,13H17V11H7V13Z"/>
          </svg>
        </button>
        <span class="font-size">{fontSize}px</span>
        <button
          class="toolbar-btn"
          on:click={() => fontSize = Math.min(24, fontSize + 2)}
          title="Increase font size"
        >
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M12,20C7.59,20 4,16.41 4,12C4,7.59 7.59,4 12,4C16.41,4 20,7.59 20,12C20,16.41 16.41,20 12,20M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M13,7H11V11H7V13H11V17H13V13H17V11H13V7Z"/>
          </svg>
        </button>
      </div>
      
      <!-- Scroll buttons -->
      <button
        class="toolbar-btn scroll-btn"
        on:click={scrollToTop}
        title="Scroll to top"
      >
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M13,20H11V8L5.5,13.5L4.08,12.08L12,4.16L19.92,12.08L18.5,13.5L13,8V20Z"/>
        </svg>
      </button>
      <button
        class="toolbar-btn scroll-btn"
        on:click={scrollToBottomManual}
        title="Scroll to bottom"
      >
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M11,4H13V16L18.5,10.5L19.92,11.92L12,19.84L4.08,11.92L5.5,10.5L11,16V4Z"/>
        </svg>
      </button>
      
      <!-- Action buttons -->
      <button
        class="toolbar-btn"
        on:click={toggleSearch}
        title="Search (Ctrl+F)"
        class:active={showSearch}
      >
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M9.5,3A6.5,6.5 0 0,1 16,9.5C16,11.11 15.41,12.59 14.44,13.73L14.71,14H15.5L20.5,19L19,20.5L14,15.5V14.71L13.73,14.44C12.59,15.41 11.11,16 9.5,16A6.5,6.5 0 0,1 3,9.5A6.5,6.5 0 0,1 9.5,3M9.5,5C7,5 5,7 5,9.5C5,12 7,14 9.5,14C12,14 14,12 14,9.5C14,7 12,5 9.5,5Z"/>
        </svg>
      </button>
      
      <button
        class="toolbar-btn"
        on:click={toggleWrap}
        title="Toggle line wrap"
        class:active={wrapLines}
      >
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M7,7L17,7V10L21,6L17,2V5L5,5V11L7,11V7M17,17L7,17V14L3,18L7,22V19L19,19V13L17,13V17Z"/>
        </svg>
      </button>
      
      
      {#if content}
        <button
          class="toolbar-btn"
          on:click={copyToClipboard}
          title="Copy to clipboard"
        >
          {#if copySuccess}
            <svg viewBox="0 0 24 24" fill="currentColor" class="success">
              <path d="M21,7L9,19L3.5,13.5L4.91,12.09L9,16.17L19.59,5.59L21,7Z"/>
            </svg>
          {:else}
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M19,21H8V7H19M19,5H8A2,2 0 0,0 6,7V21A2,2 0 0,0 8,23H19A2,2 0 0,0 21,21V7A2,2 0 0,0 19,5M16,1H4A2,2 0 0,0 2,3V17H4V3H16V1Z"/>
            </svg>
          {/if}
        </button>
      {/if}
      
      {#if content}
        <button 
          class="toolbar-btn" 
          on:click={downloadContent}
          title="Download"
        >
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M5,20H19V18H5M19,9H15V3H9V9H5L12,16L19,9Z"/>
          </svg>
        </button>
      {/if}
    </div>
  </div>
  
  <!-- Content area -->
  <div class="viewer-content" style="max-height: {maxHeight}; font-size: {fontSize}px;" bind:this={viewerContentElement} on:scroll={handleScroll}>
    {#if loading}
      <div class="loading-state">
        <div class="loading-spinner"></div>
        <p>Loading content...</p>
      </div>
    {:else if error}
      <div class="error-state">
        <svg class="error-icon" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12,2C17.53,2 22,6.47 22,12C22,17.53 17.53,22 12,22C6.47,22 2,17.53 2,12C2,6.47 6.47,2 12,2M15.59,7L12,10.59L8.41,7L7,8.41L10.59,12L7,15.59L8.41,17L12,13.41L15.59,17L17,15.59L13.41,12L17,8.41L15.59,7Z"/>
        </svg>
        <p>{error}</p>
      </div>
    {:else if content}
      <pre 
        class="output-content line-numbers"
        class:wrap={wrapLines}
        bind:this={outputElement}
      >{@html processContent(content)}</pre>
    {:else}
      <div class="empty-state">
        <svg class="empty-icon" viewBox="0 0 24 24" fill="currentColor">
          <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20M9,13V19H7V13H9M13,13V19H11V13H13M17,13V19H15V13H17Z"/>
        </svg>
        <p>{emptyMessage}</p>
      </div>
    {/if}
  </div>
</div>

<style>
  .output-viewer {
    display: flex;
    flex-direction: column;
    background: white;
    border-radius: 8px;
    border: 1px solid #e5e7eb;
    overflow: hidden;
    height: 100%;
  }
  
  .viewer-toolbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.75rem 1rem;
    background: linear-gradient(to bottom, #f9fafb, #f3f4f6);
    border-bottom: 1px solid #e5e7eb;
    gap: 1rem;
    flex-wrap: wrap;
  }
  
  .toolbar-left {
    display: flex;
    align-items: center;
    gap: 1rem;
    flex: 1;
  }
  
  .viewer-title {
    margin: 0;
    font-size: 0.95rem;
    font-weight: 600;
    color: #374151;
  }
  
  .file-info {
    display: flex;
    gap: 1rem;
    align-items: center;
    font-size: 0.85rem;
    color: #6b7280;
  }
  
  .info-item {
    display: flex;
    align-items: center;
    gap: 0.25rem;
  }
  
  .info-icon {
    width: 14px;
    height: 14px;
    opacity: 0.6;
  }
  
  .toolbar-right {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  
  .search-box {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: white;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    padding: 0.25rem 0.5rem;
  }
  
  .search-input {
    border: none;
    outline: none;
    padding: 0.25rem;
    font-size: 0.85rem;
    width: 150px;
  }
  
  .match-count {
    font-size: 0.8rem;
    color: #6b7280;
    white-space: nowrap;
  }
  
  .font-controls {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0 0.5rem;
    border-left: 1px solid #e5e7eb;
    border-right: 1px solid #e5e7eb;
  }
  
  .font-size {
    font-size: 0.8rem;
    color: #6b7280;
    min-width: 35px;
    text-align: center;
  }
  
  .toolbar-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    background: white;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s;
    color: #6b7280;
  }
  
  .toolbar-btn:hover {
    background: #f3f4f6;
    border-color: #9ca3af;
    color: #374151;
  }
  
  .toolbar-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
  
  .toolbar-btn:disabled:hover {
    background: transparent;
    border-color: #e5e7eb;
    color: #6b7280;
  }
  
  /* Highlight scroll buttons when useful */
  .scroll-btn.highlight {
    background: #dbeafe;
    border-color: #3b82f6;
    color: #1d4ed8;
  }
  
  .scroll-btn.highlight:hover {
    background: #bfdbfe;
    border-color: #2563eb;
    color: #1e40af;
  }
  
  .toolbar-btn.active {
    background: #3b82f6;
    border-color: #3b82f6;
    color: white;
  }
  
  .toolbar-btn svg {
    width: 18px;
    height: 18px;
  }
  
  .toolbar-btn svg.success {
    color: #10b981;
  }
  
  
  .viewer-content {
    flex: 1;
    overflow: auto;
    background: #fafbfc;
  }
  
  .output-content {
    margin: 0;
    padding: 1rem;
    font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
    font-size: inherit;
    line-height: 1.5;
    color: #1f2937;
    white-space: pre;
    overflow-x: auto;
    background: white;
    min-height: 100%;
  }
  
  .output-content.wrap {
    white-space: pre-wrap;
    word-break: break-all;
  }
  
  .output-content.line-numbers {
    counter-reset: line-number;
    padding-left: 3.5rem;
    position: relative;
  }
  
  :global(.line-number) {
    position: absolute;
    left: 0.5rem;
    color: #9ca3af;
    user-select: none;
    font-size: 0.85em;
    min-width: 2.5rem;
    text-align: right;
    padding-right: 0.5rem;
  }
  
  :global(.line-content) {
    display: inline-block;
    width: 100%;
  }
  
  :global(mark) {
    background: #fef08a;
    color: inherit;
    padding: 0.1em 0;
    border-radius: 2px;
  }
  
  .loading-state,
  .error-state,
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 3rem;
    color: #6b7280;
    min-height: 300px;
  }
  
  .loading-spinner {
    width: 40px;
    height: 40px;
    border: 3px solid #e5e7eb;
    border-top-color: #3b82f6;
    border-radius: 50%;
    animation: spin 1s linear infinite;
    margin-bottom: 1rem;
  }
  
  .error-icon {
    width: 48px;
    height: 48px;
    color: #ef4444;
    margin-bottom: 1rem;
  }
  
  .empty-icon {
    width: 48px;
    height: 48px;
    color: #d1d5db;
    margin-bottom: 1rem;
  }
  
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  
  /* Scrollbar styling */
  .viewer-content::-webkit-scrollbar,
  .output-content::-webkit-scrollbar {
    width: 8px;
    height: 8px;
  }
  
  .viewer-content::-webkit-scrollbar-track,
  .output-content::-webkit-scrollbar-track {
    background: #f3f4f6;
  }
  
  .viewer-content::-webkit-scrollbar-thumb,
  .output-content::-webkit-scrollbar-thumb {
    background: #cbd5e1;
    border-radius: 4px;
  }
  
  .viewer-content::-webkit-scrollbar-thumb:hover,
  .output-content::-webkit-scrollbar-thumb:hover {
    background: #94a3b8;
  }
  
  /* Mobile responsive */
  @media (max-width: 768px) {
    .viewer-toolbar {
      padding: 0.5rem;
    }
    
    .toolbar-left {
      flex-direction: column;
      align-items: flex-start;
      gap: 0.5rem;
      width: 100%;
    }
    
    .toolbar-right {
      width: 100%;
      justify-content: flex-end;
    }
    
    .search-box {
      flex: 1;
    }
    
    .search-input {
      width: 100%;
    }
    
    .font-controls {
      display: none;
    }
    
    .output-content {
      padding: 0.5rem;
      font-size: 12px !important;
    }
  }
</style>