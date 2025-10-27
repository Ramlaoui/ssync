<script lang="ts">
  import { run } from 'svelte/legacy';

  import { onMount, onDestroy, createEventDispatcher } from 'svelte';
  import { EditorView, basicSetup } from 'codemirror';
  import { EditorState, Compartment } from '@codemirror/state';
  import { keymap, placeholder as placeholderExt } from '@codemirror/view';
  import { defaultKeymap, indentWithTab } from '@codemirror/commands';
  import { StreamLanguage } from '@codemirror/language';
  import { shell } from '@codemirror/legacy-modes/mode/shell';
  import { python } from '@codemirror/lang-python';
  
  interface Props {
    value?: string;
    language?: 'shell' | 'python';
    readOnly?: boolean;
    placeholder?: string;
    showLineNumbers?: boolean;
    height?: string;
    splitView?: boolean;
  }

  let {
    value = $bindable(''),
    language = $bindable('shell'),
    readOnly = false,
    placeholder = '',
    showLineNumbers = true,
    height = '400px',
    splitView = false
  }: Props = $props();
  
  const dispatch = createEventDispatcher();
  
  let container: HTMLDivElement = $state();
  let editor: EditorView = $state();
  let languageCompartment = new Compartment();
  let readOnlyCompartment = new Compartment();
  
  // Auto-save state
  let lastSaved = value;
  let hasUnsavedChanges = $state(false);
  let autoSaveTimer: ReturnType<typeof setTimeout>;
  
  // Split view sections
  let loginSetupContent = '';
  let mainScriptContent = '';
  
  
  function parseSplitContent(content: string) {
    const loginMatch = content.match(/#LOGIN_SETUP_BEGIN([\s\S]*?)#LOGIN_SETUP_END/);
    if (loginMatch) {
      loginSetupContent = loginMatch[1].trim();
      mainScriptContent = content.replace(/#LOGIN_SETUP_BEGIN[\s\S]*?#LOGIN_SETUP_END/, '').trim();
    } else {
      loginSetupContent = '';
      mainScriptContent = content;
    }
  }
  
  function combineSplitContent(): string {
    if (!splitView) return value;
    if (!loginSetupContent) return mainScriptContent;
    
    return `#LOGIN_SETUP_BEGIN
${loginSetupContent}
#LOGIN_SETUP_END

${mainScriptContent}`;
  }
  
  function getLanguageExtension() {
    return language === 'python' 
      ? python() 
      : StreamLanguage.define(shell);
  }
  
  function createEditorState(doc: string) {
    return EditorState.create({
      doc,
      extensions: [
        basicSetup,
        keymap.of([...defaultKeymap, indentWithTab]),
        languageCompartment.of(getLanguageExtension()),
        readOnlyCompartment.of(EditorState.readOnly.of(readOnly)),
        EditorView.theme({
          "&": {
            fontSize: "14px",
            height: height
          },
          ".cm-content": {
            minHeight: height,
            fontFamily: "'JetBrains Mono', 'Fira Code', monospace"
          },
          ".cm-focused": {
            outline: "none"
          },
          "&.cm-editor": {
            border: "1px solid var(--border)",
            borderRadius: "8px"
          },
          "&.cm-editor.cm-focused": {
            borderColor: "var(--accent)",
            boxShadow: "0 0 0 3px rgba(59, 130, 246, 0.1)"
          },
          ".cm-placeholder": {
            color: "var(--muted-foreground)",
            fontStyle: "italic"
          },
          ".cm-selectionBackground": {
            backgroundColor: "rgba(59, 130, 246, 0.2)"
          },
          ".cm-cursor": {
            borderLeftColor: "var(--accent)"
          },
          ".cm-line": {
            padding: "0 4px"
          }
        }),
        EditorView.updateListener.of((update) => {
          if (update.docChanged) {
            const newValue = update.state.doc.toString();
            value = newValue;
            hasUnsavedChanges = newValue !== lastSaved;
            dispatch('change', { value: newValue });
            
            // Auto-save after 2 seconds of inactivity
            clearTimeout(autoSaveTimer);
            autoSaveTimer = setTimeout(() => {
              saveToLocalStorage();
            }, 2000);
          }
        }),
        EditorView.lineWrapping,
        placeholder ? placeholderExt(placeholder) : []
      ]
    });
  }
  
  function saveToLocalStorage() {
    if (!hasUnsavedChanges) return;
    
    const draftKey = 'script_draft_' + Date.now();
    const drafts = JSON.parse(localStorage.getItem('script_drafts') || '[]');
    
    // Keep only last 10 drafts
    if (drafts.length >= 10) {
      const oldestKey = drafts.shift();
      localStorage.removeItem(oldestKey);
    }
    
    drafts.push(draftKey);
    localStorage.setItem('script_drafts', JSON.stringify(drafts));
    localStorage.setItem(draftKey, value);
    localStorage.setItem('last_script_draft', value);
    
    lastSaved = value;
    hasUnsavedChanges = false;
    dispatch('save', { value });
  }
  
  export function insertSnippet(snippet: string) {
    if (!editor) return;
    
    const state = editor.state;
    const selection = state.selection.main;
    
    editor.dispatch({
      changes: {
        from: selection.from,
        to: selection.to,
        insert: snippet
      },
      selection: {
        anchor: selection.from + snippet.length
      }
    });
  }
  
  export function getSelectedText(): string {
    if (!editor) return '';
    
    const state = editor.state;
    const selection = state.selection.main;
    return state.doc.sliceString(selection.from, selection.to);
  }
  
  export function replaceSelection(text: string) {
    if (!editor) return;
    
    const state = editor.state;
    const selection = state.selection.main;
    
    editor.dispatch({
      changes: {
        from: selection.from,
        to: selection.to,
        insert: text
      }
    });
  }
  
  export function formatScript() {
    // Basic formatting - could be enhanced with prettier
    if (!editor) return;
    
    let formatted = value;
    
    // Fix indentation for common patterns
    formatted = formatted.replace(/\n\s*#SBATCH/g, '\n#SBATCH');
    formatted = formatted.replace(/\n\s*module\s+/g, '\nmodule ');
    
    editor.dispatch({
      changes: {
        from: 0,
        to: editor.state.doc.length,
        insert: formatted
      }
    });
  }
  
  onMount(() => {
    // Check for draft recovery
    const lastDraft = localStorage.getItem('last_script_draft');
    if (lastDraft && !value) {
      const shouldRecover = confirm('Recover unsaved script from last session?');
      if (shouldRecover) {
        value = lastDraft;
      }
    }
    
    editor = new EditorView({
      state: createEditorState(value),
      parent: container
    });
  });
  
  onDestroy(() => {
    if (editor) {
      editor.destroy();
    }
    clearTimeout(autoSaveTimer);
  });
  
  
  
  run(() => {
    if (splitView && value) {
      parseSplitContent(value);
    }
  });
  // Handle external value changes
  run(() => {
    if (editor && value !== editor.state.doc.toString()) {
      editor.dispatch({
        changes: {
          from: 0,
          to: editor.state.doc.length,
          insert: value
        }
      });
    }
  });
  // Handle language changes
  run(() => {
    if (editor) {
      editor.dispatch({
        effects: languageCompartment.reconfigure(getLanguageExtension())
      });
    }
  });
  // Handle readonly changes
  run(() => {
    if (editor) {
      editor.dispatch({
        effects: readOnlyCompartment.reconfigure(EditorState.readOnly.of(readOnly))
      });
    }
  });
</script>

<div class="script-editor">
  {#if hasUnsavedChanges}
    <div class="unsaved-indicator">
      <span class="dot"></span>
      Unsaved changes (auto-saving...)
    </div>
  {/if}
  
  {#if splitView}
    <div class="split-view-tabs">
      <button class="tab" class:active={!splitView}>Full Script</button>
      <button class="tab" class:active={splitView}>Split View</button>
    </div>
  {/if}
  
  <div class="editor-container" bind:this={container}></div>
  
  <div class="editor-toolbar">
    <div class="toolbar-left">
      <button class="toolbar-btn" onclick={formatScript} title="Format Script">
        <svg viewBox="0 0 24 24" fill="currentColor">
          <path d="M3,3H21V5H3V3M3,7H21V9H3V7M3,11H21V13H3V11M3,15H21V17H3V15M3,19H21V21H3V19Z"/>
        </svg>
      </button>
      <div class="separator"></div>
      <span class="char-count">{value.length} chars</span>
      <span class="line-count">{value.split('\n').length} lines</span>
    </div>
    <div class="toolbar-right">
      <select bind:value={language} class="language-select">
        <option value="shell">Bash/Shell</option>
        <option value="python">Python</option>
      </select>
    </div>
  </div>
</div>

<style>
  .script-editor {
    position: relative;
    display: flex;
    flex-direction: column;
    background: var(--background);
    border-radius: 8px;
    overflow: hidden;
  }
  
  .unsaved-indicator {
    position: absolute;
    top: 0.5rem;
    right: 0.5rem;
    background: rgba(251, 191, 36, 0.1);
    color: #f59e0b;
    padding: 0.25rem 0.75rem;
    border-radius: 12px;
    font-size: 0.75rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    z-index: 10;
    animation: fadeIn 0.3s;
  }
  
  .dot {
    width: 6px;
    height: 6px;
    background: #f59e0b;
    border-radius: 50%;
    animation: pulse 2s infinite;
  }
  
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }
  
  @keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
  }
  
  .split-view-tabs {
    display: flex;
    gap: 0.5rem;
    padding: 0.5rem;
    background: var(--secondary);
    border-bottom: 1px solid var(--border);
  }
  
  .tab {
    padding: 0.375rem 0.75rem;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    color: var(--muted-foreground);
    font-size: 0.875rem;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .tab:hover {
    background: var(--background);
  }
  
  .tab.active {
    background: var(--background);
    border-color: var(--accent);
    color: var(--accent);
  }
  
  .editor-container {
    flex: 1;
    overflow: auto;
  }
  
  .editor-toolbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.5rem;
    background: var(--secondary);
    border-top: 1px solid var(--border);
    font-size: 0.75rem;
  }
  
  .toolbar-left,
  .toolbar-right {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }
  
  .toolbar-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 4px;
    color: var(--muted-foreground);
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .toolbar-btn:hover {
    background: var(--background);
    border-color: var(--accent);
    color: var(--accent);
  }
  
  .toolbar-btn svg {
    width: 16px;
    height: 16px;
  }
  
  .separator {
    width: 1px;
    height: 20px;
    background: var(--border);
  }
  
  .char-count,
  .line-count {
    color: var(--muted-foreground);
  }
  
  .language-select {
    padding: 0.25rem 0.5rem;
    background: var(--background);
    border: 1px solid var(--border);
    border-radius: 4px;
    color: var(--foreground);
    font-size: 0.75rem;
    cursor: pointer;
  }
  
  .language-select:focus {
    outline: none;
    border-color: var(--accent);
  }
  
  @media (max-width: 768px) {
    .editor-toolbar {
      flex-direction: column;
      gap: 0.5rem;
      padding: 0.75rem;
    }
    
    .toolbar-left,
    .toolbar-right {
      width: 100%;
      justify-content: center;
    }
  }
</style>