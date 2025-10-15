<script lang="ts">
  import { run } from 'svelte/legacy';

  import { onMount } from 'svelte';
  
  interface Props {
    script?: string;
    highlightLine?: number | null;
    showLineNumbers?: boolean;
    collapsible?: boolean;
    maxHeight?: string;
  }

  let {
    script = '',
    highlightLine = null,
    showLineNumbers = true,
    collapsible = true,
    maxHeight = '400px'
  }: Props = $props();
  
  let container: HTMLDivElement = $state();
  let isCollapsed = $state(collapsible);
  let lines: string[] = $state([]);
  let searchTerm = $state('');
  let searchVisible = $state(false);
  let matchedLines: Set<number> = $state(new Set());
  
  run(() => {
    lines = script.split('\n');
  });
  
  run(() => {
    if (searchTerm) {
      matchedLines = new Set();
      lines.forEach((line, index) => {
        if (line.toLowerCase().includes(searchTerm.toLowerCase())) {
          matchedLines.add(index);
        }
      });
    } else {
      matchedLines = new Set();
    }
  });
  
  function toggleCollapse() {
    isCollapsed = !isCollapsed;
  }
  
  function copyToClipboard() {
    navigator.clipboard.writeText(script);
    // Show toast or feedback
  }
  
  function highlightSyntax(line: string): string {
    // Basic syntax highlighting
    let highlighted = line;
    
    // SBATCH directives
    highlighted = highlighted.replace(/(#SBATCH\s+)(--?\S+)(=?)(\S*)/g, 
      '<span class="directive">$1</span><span class="flag">$2</span><span class="operator">$3</span><span class="value">$4</span>');
    
    // Comments
    if (line.startsWith('#') && !line.startsWith('#SBATCH')) {
      highlighted = `<span class="comment">${highlighted}</span>`;
    }
    
    // Environment variables
    highlighted = highlighted.replace(/\$\w+/g, '<span class="variable">$&</span>');
    
    // Strings
    highlighted = highlighted.replace(/"([^"]*)"/g, '<span class="string">"$1"</span>');
    highlighted = highlighted.replace(/'([^']*)'/g, '<span class="string">\'$1\'</span>');
    
    // Numbers
    highlighted = highlighted.replace(/\b\d+\b/g, '<span class="number">$&</span>');
    
    // Keywords
    const keywords = ['if', 'then', 'else', 'fi', 'for', 'do', 'done', 'while', 'module', 'load', 'conda', 'activate', 'python', 'echo', 'export'];
    keywords.forEach(keyword => {
      const regex = new RegExp(`\\b${keyword}\\b`, 'g');
      highlighted = highlighted.replace(regex, `<span class="keyword">${keyword}</span>`);
    });
    
    return highlighted;
  }
  
  function scrollToLine(lineNumber: number) {
    const lineElement = container?.querySelector(`[data-line="${lineNumber}"]`);
    if (lineElement) {
      lineElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }
  
  onMount(() => {
    if (highlightLine !== null) {
      scrollToLine(highlightLine);
    }
  });
</script>

<div class="script-viewer">
  <div class="viewer-header">
    <button class="expand-btn" onclick={toggleCollapse} aria-label="Toggle expand">
      <svg class="expand-icon" class:rotated={!isCollapsed} viewBox="0 0 24 24">
        <path d="M7.41,8.58L12,13.17L16.59,8.58L18,10L12,16L6,10L7.41,8.58Z" />
      </svg>
      <span>{isCollapsed ? 'Show' : 'Hide'} Script ({lines.length} lines)</span>
    </button>
    
    <div class="viewer-actions">
      <button class="action-btn" onclick={() => searchVisible = !searchVisible} aria-label="Search">
        <svg viewBox="0 0 24 24">
          <path d="M9.5,3A6.5,6.5 0 0,1 16,9.5C16,11.11 15.41,12.59 14.44,13.73L14.71,14H15.5L20.5,19L19,20.5L14,15.5V14.71L13.73,14.44C12.59,15.41 11.11,16 9.5,16A6.5,6.5 0 0,1 3,9.5A6.5,6.5 0 0,1 9.5,3M9.5,5C7,5 5,7 5,9.5C5,12 7,14 9.5,14C12,14 14,12 14,9.5C14,7 12,5 9.5,5Z" />
        </svg>
      </button>
      
      <button class="action-btn" onclick={copyToClipboard} aria-label="Copy">
        <svg viewBox="0 0 24 24">
          <path d="M19,21H8V7H19M19,5H8A2,2 0 0,0 6,7V21A2,2 0 0,0 8,23H19A2,2 0 0,0 21,21V7A2,2 0 0,0 19,5M16,1H4A2,2 0 0,0 2,3V17H4V3H16V1Z" />
        </svg>
      </button>
    </div>
  </div>
  
  {#if searchVisible}
    <div class="search-bar">
      <input 
        type="search" 
        bind:value={searchTerm} 
        placeholder="Search in script..."
        class="search-input"
      />
      <span class="search-count">
        {matchedLines.size} matches
      </span>
    </div>
  {/if}
  
  {#if !isCollapsed}
    <div 
      class="script-content" 
      bind:this={container}
      style="max-height: {maxHeight};"
    >
      <div class="script-lines">
        {#each lines as line, index}
          <div 
            class="script-line"
            class:highlighted={highlightLine === index + 1}
            class:matched={matchedLines.has(index)}
            data-line={index + 1}
          >
            {#if showLineNumbers}
              <span class="line-number">{index + 1}</span>
            {/if}
            <span class="line-content">
              {@html highlightSyntax(line) || '<span class="empty-line">&nbsp;</span>'}
            </span>
          </div>
        {/each}
      </div>
    </div>
  {/if}
</div>

<style>
  .script-viewer {
    background: #1a1f2e;
    border-radius: 12px;
    overflow: hidden;
    border: 1px solid #2a3142;
  }
  
  .viewer-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.75rem 1rem;
    background: #141925;
    border-bottom: 1px solid #2a3142;
  }
  
  .expand-btn {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: none;
    border: none;
    color: #e4e8f1;
    font-size: 0.9rem;
    font-weight: 500;
    cursor: pointer;
    padding: 0.5rem;
    margin: -0.5rem;
    -webkit-tap-highlight-color: transparent;
  }
  
  .expand-icon {
    width: 20px;
    height: 20px;
    transition: transform 0.2s;
  }
  
  .expand-icon.rotated {
    transform: rotate(180deg);
  }
  
  .viewer-actions {
    display: flex;
    gap: 0.5rem;
  }
  
  .action-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    background: #1e2433;
    border: 1px solid #2a3142;
    border-radius: 8px;
    color: #9ca3af;
    cursor: pointer;
    transition: all 0.2s;
    -webkit-tap-highlight-color: transparent;
  }
  
  .action-btn:active {
    background: #2a3142;
    transform: scale(0.95);
  }
  
  .action-btn svg {
    width: 18px;
    height: 18px;
  }
  
  .search-bar {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.75rem 1rem;
    background: #141925;
    border-bottom: 1px solid #2a3142;
  }
  
  .search-input {
    flex: 1;
    padding: 0.5rem 0.75rem;
    background: #1e2433;
    border: 1px solid #2a3142;
    border-radius: 6px;
    color: #e4e8f1;
    font-size: 0.9rem;
    outline: none;
  }
  
  .search-input:focus {
    border-color: #3b82f6;
  }
  
  .search-count {
    color: #9ca3af;
    font-size: 0.8rem;
  }
  
  .script-content {
    overflow: auto;
    -webkit-overflow-scrolling: touch;
    background: #0f1419;
  }
  
  .script-lines {
    font-family: 'SF Mono', Monaco, 'Courier New', monospace;
    font-size: 0.9rem;
    line-height: 1.6;
  }
  
  .script-line {
    display: flex;
    min-height: 1.6rem;
    transition: background 0.2s;
  }
  
  .script-line.highlighted {
    background: rgba(59, 130, 246, 0.1);
    border-left: 3px solid #3b82f6;
  }
  
  .script-line.matched {
    background: rgba(251, 191, 36, 0.1);
  }
  
  .line-number {
    width: 3.5rem;
    padding: 0 0.75rem;
    color: #6b7280;
    text-align: right;
    user-select: none;
    flex-shrink: 0;
    background: #0a0e1a;
    border-right: 1px solid #1e2433;
  }
  
  .line-content {
    flex: 1;
    padding: 0 1rem;
    white-space: pre;
    overflow-x: auto;
    color: #e4e8f1;
  }
  
  .empty-line {
    display: inline-block;
    min-height: 1.6rem;
  }
  
  /* Syntax highlighting */
  :global(.directive) { color: #c678dd; font-weight: 600; }
  :global(.flag) { color: #61afef; }
  :global(.operator) { color: #56b6c2; }
  :global(.value) { color: #98c379; }
  :global(.comment) { color: #7f848e; font-style: italic; }
  :global(.variable) { color: #e06c75; }
  :global(.string) { color: #98c379; }
  :global(.number) { color: #d19a66; }
  :global(.keyword) { color: #c678dd; }
  
  @media (max-width: 640px) {
    .script-lines {
      font-size: 0.85rem;
    }
    
    .line-number {
      width: 3rem;
      padding: 0 0.5rem;
      font-size: 0.75rem;
    }
  }
</style>