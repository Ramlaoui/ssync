<script lang="ts">
  import { onMount, createEventDispatcher } from 'svelte';
  import { fade } from 'svelte/transition';
  
  export let script: string = '';
  export let readOnly: boolean = false;
  export let mode: 'normal' | 'vim' = 'normal';
  
  const dispatch = createEventDispatcher<{
    update: { script: string };
    close: void;
  }>();
  
  let textarea: HTMLTextAreaElement;
  let cursorPosition = 0;
  let vimMode: 'normal' | 'insert' | 'visual' = 'normal';
  let commandBuffer = '';
  let selectedRange = { start: 0, end: 0 };
  let showLineNumbers = true;
  let lines: string[] = [];
  
  $: lines = script.split('\n');
  $: lineNumbers = lines.map((_, i) => i + 1).join('\n');
  
  function handleKeydown(e: KeyboardEvent) {
    if (mode !== 'vim' || vimMode === 'insert') return;
    
    switch (e.key) {
      case 'i':
        e.preventDefault();
        vimMode = 'insert';
        break;
      case 'Escape':
        e.preventDefault();
        vimMode = 'normal';
        commandBuffer = '';
        break;
      case 'v':
        e.preventDefault();
        vimMode = 'visual';
        selectedRange.start = textarea.selectionStart;
        break;
      case 'h':
        e.preventDefault();
        moveCursor(-1);
        break;
      case 'l':
        e.preventDefault();
        moveCursor(1);
        break;
      case 'j':
        e.preventDefault();
        moveLineDown();
        break;
      case 'k':
        e.preventDefault();
        moveLineUp();
        break;
      case 'w':
        e.preventDefault();
        moveWord(1);
        break;
      case 'b':
        e.preventDefault();
        moveWord(-1);
        break;
      case '0':
        e.preventDefault();
        moveToLineStart();
        break;
      case '$':
        e.preventDefault();
        moveToLineEnd();
        break;
      case 'G':
        e.preventDefault();
        if (e.shiftKey) {
          moveToEnd();
        }
        break;
      case 'g':
        if (commandBuffer === 'g') {
          e.preventDefault();
          moveToStart();
          commandBuffer = '';
        } else {
          commandBuffer = 'g';
        }
        break;
      case 'd':
        if (commandBuffer === 'd') {
          e.preventDefault();
          deleteLine();
          commandBuffer = '';
        } else {
          commandBuffer = 'd';
        }
        break;
      case 'y':
        if (commandBuffer === 'y') {
          e.preventDefault();
          yankLine();
          commandBuffer = '';
        } else {
          commandBuffer = 'y';
        }
        break;
      case 'p':
        e.preventDefault();
        paste();
        break;
      case 'u':
        e.preventDefault();
        undo();
        break;
      case '/':
        e.preventDefault();
        // Start search mode
        break;
    }
  }
  
  function moveCursor(offset: number) {
    const newPos = Math.max(0, Math.min(script.length, textarea.selectionStart + offset));
    textarea.selectionStart = textarea.selectionEnd = newPos;
  }
  
  function moveLineUp() {
    const currentLine = script.substring(0, textarea.selectionStart).split('\n').length - 1;
    if (currentLine > 0) {
      const lines = script.split('\n');
      let newPos = 0;
      for (let i = 0; i < currentLine - 1; i++) {
        newPos += lines[i].length + 1;
      }
      const colPos = textarea.selectionStart - script.lastIndexOf('\n', textarea.selectionStart - 1) - 1;
      newPos += Math.min(colPos, lines[currentLine - 1].length);
      textarea.selectionStart = textarea.selectionEnd = newPos;
    }
  }
  
  function moveLineDown() {
    const lines = script.split('\n');
    const currentLine = script.substring(0, textarea.selectionStart).split('\n').length - 1;
    if (currentLine < lines.length - 1) {
      let newPos = 0;
      for (let i = 0; i <= currentLine + 1; i++) {
        if (i > 0) newPos += 1;
        if (i <= currentLine) {
          newPos += lines[i].length;
        } else {
          const colPos = textarea.selectionStart - script.lastIndexOf('\n', textarea.selectionStart - 1) - 1;
          newPos += Math.min(colPos, lines[i].length);
        }
      }
      textarea.selectionStart = textarea.selectionEnd = newPos;
    }
  }
  
  function moveWord(direction: number) {
    const text = script;
    let pos = textarea.selectionStart;
    if (direction === 1) {
      const match = text.substring(pos).match(/\W*\w+/);
      if (match) pos += match[0].length;
    } else {
      const before = text.substring(0, pos);
      const match = before.match(/\w+\W*$/);
      if (match) pos -= match[0].length;
    }
    textarea.selectionStart = textarea.selectionEnd = pos;
  }
  
  function moveToLineStart() {
    const pos = script.lastIndexOf('\n', textarea.selectionStart - 1) + 1;
    textarea.selectionStart = textarea.selectionEnd = pos;
  }
  
  function moveToLineEnd() {
    let pos = script.indexOf('\n', textarea.selectionStart);
    if (pos === -1) pos = script.length;
    textarea.selectionStart = textarea.selectionEnd = pos;
  }
  
  function moveToStart() {
    textarea.selectionStart = textarea.selectionEnd = 0;
  }
  
  function moveToEnd() {
    textarea.selectionStart = textarea.selectionEnd = script.length;
  }
  
  let clipboard = '';
  
  function deleteLine() {
    const start = script.lastIndexOf('\n', textarea.selectionStart - 1) + 1;
    let end = script.indexOf('\n', textarea.selectionStart);
    if (end === -1) end = script.length;
    else end += 1;
    clipboard = script.substring(start, end);
    script = script.substring(0, start) + script.substring(end);
    textarea.selectionStart = textarea.selectionEnd = start;
    dispatch('update', { script });
  }
  
  function yankLine() {
    const start = script.lastIndexOf('\n', textarea.selectionStart - 1) + 1;
    let end = script.indexOf('\n', textarea.selectionStart);
    if (end === -1) end = script.length;
    clipboard = script.substring(start, end) + '\n';
  }
  
  function paste() {
    const pos = textarea.selectionStart;
    script = script.substring(0, pos) + clipboard + script.substring(pos);
    textarea.selectionStart = textarea.selectionEnd = pos + clipboard.length;
    dispatch('update', { script });
  }
  
  let history: string[] = [];
  let historyIndex = -1;
  
  function undo() {
    if (historyIndex > 0) {
      historyIndex--;
      script = history[historyIndex];
      dispatch('update', { script });
    }
  }
  
  function recordHistory() {
    history = history.slice(0, historyIndex + 1);
    history.push(script);
    historyIndex = history.length - 1;
  }
  
  function handleInput() {
    recordHistory();
    dispatch('update', { script });
  }
  
  function insertTemplate(template: string) {
    script = template;
    recordHistory();
    dispatch('update', { script });
  }
  
  onMount(() => {
    if (textarea && !readOnly) {
      textarea.focus();
    }
    recordHistory();
  });
  
  // Common templates
  const templates = [
    {
      name: 'Basic Job',
      script: `#!/bin/bash
#SBATCH --job-name=my_job
#SBATCH --time=01:00:00
#SBATCH --mem=4G
#SBATCH --cpus-per-task=1

echo "Job started"
# Your commands here
echo "Job completed"`
    },
    {
      name: 'GPU Job',
      script: `#!/bin/bash
#SBATCH --job-name=gpu_job
#SBATCH --time=04:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --partition=gpu

module load cuda
python train.py`
    },
    {
      name: 'Array Job',
      script: `#!/bin/bash
#SBATCH --job-name=array_job
#SBATCH --time=00:30:00
#SBATCH --mem=2G
#SBATCH --array=1-10

echo "Task ID: $SLURM_ARRAY_TASK_ID"
python script.py --task $SLURM_ARRAY_TASK_ID`
    }
  ];
  
  let showTemplates = false;
  let searchQuery = '';
  
  $: filteredLines = lines.map((line, i) => {
    const matches = searchQuery && line.toLowerCase().includes(searchQuery.toLowerCase());
    return { line, lineNumber: i + 1, matches };
  });
</script>

<div class="editor-container">
  <!-- Editor Header -->
  <div class="editor-header">
    <div class="editor-title">
      <h3>Script Editor</h3>
      {#if mode === 'vim'}
        <span class="vim-mode" class:insert={vimMode === 'insert'} class:visual={vimMode === 'visual'}>
          {vimMode.toUpperCase()}
        </span>
      {/if}
    </div>
    
    <div class="editor-actions">
      <button 
        class="icon-btn"
        on:click={() => showTemplates = !showTemplates}
        title="Templates"
      >
        <svg viewBox="0 0 24 24">
          <path d="M19,19H5V5H19M19,3H5A2,2 0 0,0 3,5V19A2,2 0 0,0 5,21H19A2,2 0 0,0 21,19V5A2,2 0 0,0 19,3M13.96,12.29L11.21,15.83L9.25,13.47L6.5,17H17.5L13.96,12.29Z" />
        </svg>
      </button>
      
      <button 
        class="icon-btn"
        on:click={() => showLineNumbers = !showLineNumbers}
        title="Toggle line numbers"
      >
        <svg viewBox="0 0 24 24">
          <path d="M2,6H8V8H4V10H7V12H4V14H8V16H2V6M9,6H11V16H9V6M11.5,6H13V16H11.5V6M14,6H22V8H18V10H21V12H18V14H22V16H14V6Z" />
        </svg>
      </button>
      
      <button 
        class="icon-btn"
        on:click={() => mode = mode === 'vim' ? 'normal' : 'vim'}
        title="Toggle Vim mode"
      >
        <svg viewBox="0 0 24 24">
          <path d="M9,7V17H11V13H13V17H15V7H13V11H11V7H9M12,2A10,10 0 0,1 22,12A10,10 0 0,1 12,22A10,10 0 0,1 2,12A10,10 0 0,1 12,2Z" />
        </svg>
      </button>
      
      <button 
        class="icon-btn close"
        on:click={() => dispatch('close')}
        title="Close"
      >
        <svg viewBox="0 0 24 24">
          <path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z" />
        </svg>
      </button>
    </div>
  </div>
  
  <!-- Templates Panel -->
  {#if showTemplates}
    <div class="templates-panel" transition:fade={{ duration: 200 }}>
      <div class="templates-header">
        <h4>Quick Templates</h4>
        <button class="close-btn" on:click={() => showTemplates = false}>×</button>
      </div>
      <div class="templates-list">
        {#each templates as template}
          <button 
            class="template-item"
            on:click={() => {
              insertTemplate(template.script);
              showTemplates = false;
            }}
          >
            <strong>{template.name}</strong>
            <span>{template.script.split('\n')[1]?.replace('#SBATCH ', '') || ''}</span>
          </button>
        {/each}
      </div>
    </div>
  {/if}
  
  <!-- Search Bar -->
  <div class="search-bar">
    <svg viewBox="0 0 24 24">
      <path d="M9.5,3A6.5,6.5 0 0,1 16,9.5C16,11.11 15.41,12.59 14.44,13.73L14.71,14H15.5L20.5,19L19,20.5L14,15.5V14.71L13.73,14.44C12.59,15.41 11.11,16 9.5,16A6.5,6.5 0 0,1 3,9.5A6.5,6.5 0 0,1 9.5,3M9.5,5C7,5 5,7 5,9.5C5,12 7,14 9.5,14C12,14 14,12 14,9.5C14,7 12,5 9.5,5Z" />
    </svg>
    <input 
      type="search"
      bind:value={searchQuery}
      placeholder="Search in script..."
      class="search-input"
    />
  </div>
  
  <!-- Editor Area -->
  <div class="editor-wrapper">
    {#if showLineNumbers}
      <div class="line-numbers">
        {#each lines as _, i}
          <div class="line-number" class:highlighted={filteredLines[i]?.matches}>
            {i + 1}
          </div>
        {/each}
      </div>
    {/if}
    
    <textarea
      bind:this={textarea}
      bind:value={script}
      on:input={handleInput}
      on:keydown={handleKeydown}
      class="editor-textarea"
      class:vim={mode === 'vim'}
      class:insert={vimMode === 'insert'}
      {readOnly}
      placeholder="Enter your SLURM script here..."
      spellcheck="false"
      autocomplete="off"
      autocorrect="off"
      autocapitalize="off"
    />
  </div>
  
  <!-- Editor Footer -->
  <div class="editor-footer">
    <div class="stats">
      {lines.length} lines • {script.length} chars
    </div>
    {#if mode === 'vim' && commandBuffer}
      <div class="command-buffer">{commandBuffer}</div>
    {/if}
  </div>
</div>

<style>
  .editor-container {
    display: flex;
    flex-direction: column;
    height: 100%;
    background: #ffffff;
    border-radius: 12px;
    overflow: hidden;
  }
  
  .editor-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.75rem 1rem;
    background: #f8fafc;
    border-bottom: 1px solid #e2e8f0;
  }
  
  .editor-title {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }
  
  .editor-title h3 {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
    color: #1e293b;
  }
  
  .vim-mode {
    padding: 0.25rem 0.5rem;
    background: #e2e8f0;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 600;
    color: #64748b;
  }
  
  .vim-mode.insert {
    background: #dbeafe;
    color: #3b82f6;
  }
  
  .vim-mode.visual {
    background: #fce7f3;
    color: #ec4899;
  }
  
  .editor-actions {
    display: flex;
    gap: 0.5rem;
  }
  
  .icon-btn {
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: none;
    border-radius: 6px;
    color: #64748b;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .icon-btn:active {
    background: #e2e8f0;
    transform: scale(0.95);
  }
  
  .icon-btn.close {
    color: #ef4444;
  }
  
  .icon-btn svg {
    width: 18px;
    height: 18px;
  }
  
  .templates-panel {
    background: #f8fafc;
    border-bottom: 1px solid #e2e8f0;
    padding: 1rem;
  }
  
  .templates-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.75rem;
  }
  
  .templates-header h4 {
    margin: 0;
    font-size: 0.875rem;
    font-weight: 600;
    color: #1e293b;
  }
  
  .close-btn {
    width: 24px;
    height: 24px;
    background: transparent;
    border: none;
    font-size: 1.25rem;
    color: #64748b;
    cursor: pointer;
  }
  
  .templates-list {
    display: flex;
    gap: 0.5rem;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  
  .template-item {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    padding: 0.75rem;
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    min-width: 150px;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .template-item:active {
    background: #f1f5f9;
    transform: scale(0.98);
  }
  
  .template-item strong {
    font-size: 0.875rem;
    color: #1e293b;
    margin-bottom: 0.25rem;
  }
  
  .template-item span {
    font-size: 0.75rem;
    color: #64748b;
  }
  
  .search-bar {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1rem;
    background: #f8fafc;
    border-bottom: 1px solid #e2e8f0;
  }
  
  .search-bar svg {
    width: 18px;
    height: 18px;
    fill: #94a3b8;
  }
  
  .search-input {
    flex: 1;
    background: transparent;
    border: none;
    color: #1e293b;
    font-size: 0.875rem;
    outline: none;
  }
  
  .search-input::placeholder {
    color: #94a3b8;
  }
  
  .editor-wrapper {
    flex: 1;
    display: flex;
    overflow: hidden;
  }
  
  .line-numbers {
    background: #f8fafc;
    border-right: 1px solid #e2e8f0;
    padding: 1rem 0;
    min-width: 3rem;
    overflow-y: auto;
  }
  
  .line-number {
    padding: 0 0.75rem;
    text-align: right;
    color: #94a3b8;
    font-size: 0.875rem;
    font-family: 'SF Mono', Monaco, monospace;
    line-height: 1.5rem;
  }
  
  .line-number.highlighted {
    background: #fef3c7;
    color: #a16207;
  }
  
  .editor-textarea {
    flex: 1;
    padding: 1rem;
    background: transparent;
    border: none;
    color: #1e293b;
    font-family: 'SF Mono', Monaco, monospace;
    font-size: 0.875rem;
    line-height: 1.5rem;
    resize: none;
    outline: none;
  }
  
  .editor-textarea::placeholder {
    color: #cbd5e1;
  }
  
  .editor-textarea.vim {
    caret-color: #1e293b;
  }
  
  .editor-textarea.vim:not(.insert) {
    caret-shape: block;
  }
  
  .editor-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.5rem 1rem;
    background: #f8fafc;
    border-top: 1px solid #e2e8f0;
  }
  
  .stats {
    font-size: 0.75rem;
    color: #64748b;
  }
  
  .command-buffer {
    padding: 0.25rem 0.5rem;
    background: #1e293b;
    color: #e2e8f0;
    border-radius: 4px;
    font-size: 0.75rem;
    font-family: 'SF Mono', Monaco, monospace;
  }
</style>