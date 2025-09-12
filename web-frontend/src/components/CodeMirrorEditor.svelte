<script lang="ts">
  import { onMount, onDestroy, createEventDispatcher } from 'svelte';
  import { EditorView, keymap, drawSelection, dropCursor, rectangularSelection, crosshairCursor, lineNumbers, gutter } from '@codemirror/view';
  import { EditorState, Compartment } from '@codemirror/state';
  import type { Extension } from '@codemirror/state';
  import { vim } from '@replit/codemirror-vim';
  import { shell } from '@codemirror/legacy-modes/mode/shell';
  import { StreamLanguage, indentOnInput, bracketMatching, foldGutter, foldKeymap } from '@codemirror/language';
  import { defaultKeymap, history, historyKeymap } from '@codemirror/commands';
  import { searchKeymap, highlightSelectionMatches } from '@codemirror/search';
  import { autocompletion, completionKeymap, closeBrackets, closeBracketsKeymap } from '@codemirror/autocomplete';
  import { lintKeymap } from '@codemirror/lint';

  const dispatch = createEventDispatcher<{
    change: { content: string };
    toggleVim: void;
  }>();

  export let value = '';
  export let placeholder = '';
  export let disabled = false;
  export let vimMode = true;

  let editorElement: HTMLDivElement;
  let editorView: EditorView | null = null;
  let previousValue = '';
  let previousDisabled = disabled;
  let previousVimMode = vimMode;
  let isInternalChange = false;
  let isMobile = false;
  
  // Create compartments for dynamic configuration
  const readOnlyCompartment = new Compartment();
  const vimCompartment = new Compartment();

  // Create the bash language support using legacy modes
  const bashLanguage = StreamLanguage.define(shell);

  function createEditorState(initialDoc: string) {
    const extensions = [
      // Basic editor functionality
      EditorView.lineWrapping,
      lineNumbers(),
      foldGutter(),
      history(),
      drawSelection(),
      dropCursor(),
      EditorState.allowMultipleSelections.of(true),
      indentOnInput(),
      bracketMatching(),
      closeBrackets(),
      autocompletion(),
      rectangularSelection(),
      crosshairCursor(),
      highlightSelectionMatches(),
      keymap.of([
        ...closeBracketsKeymap,
        ...defaultKeymap,
        ...searchKeymap,
        ...historyKeymap,
        ...foldKeymap,
        ...completionKeymap,
        ...lintKeymap,
      ]),
      
      // Language and theme
      bashLanguage,
      EditorView.theme({
        '&': {
          height: '100%',
          fontSize: isMobile ? '1.1rem' : '0.85rem',
          fontFamily: isMobile ? '"SF Mono", "Monaco", "Courier New", monospace' : '"JetBrains Mono", "Monaco", "Menlo", "Ubuntu Mono", monospace',
          backgroundColor: '#1a1f2e',
          color: '#e2e8f0',
        },
        '.cm-content': {
          padding: isMobile ? '1rem' : '1.5rem',
          paddingTop: isMobile ? '4.5rem' : '1.5rem',
          paddingBottom: isMobile ? '8rem' : '1.5rem',
          minHeight: '100%',
          backgroundColor: 'transparent',
          color: '#e2e8f0',
          caretColor: '#10b981',
          lineHeight: isMobile ? '2' : '1.6',
        },
        '.cm-focused': {
          outline: 'none',
        },
        '.cm-editor': {
          height: '100%',
          backgroundColor: 'transparent',
        },
        '.cm-scroller': {
          fontFamily: '"JetBrains Mono", "Monaco", "Menlo", "Ubuntu Mono", monospace',
          lineHeight: '1.6',
        },
        '.cm-cursor': {
          borderColor: '#10b981',
        },
        '.cm-selectionBackground': {
          backgroundColor: 'rgba(16, 185, 129, 0.2)',
        },
        '.cm-activeLine': {
          backgroundColor: 'rgba(255, 255, 255, 0.02)',
        },
        '.cm-activeLineGutter': {
          backgroundColor: 'rgba(255, 255, 255, 0.05)',
        },
        '.cm-gutters': {
          backgroundColor: 'rgba(0, 0, 0, 0.2)',
          color: 'rgba(255, 255, 255, 0.4)',
          border: 'none',
          borderRight: '1px solid rgba(255, 255, 255, 0.1)',
        },
        '.cm-lineNumbers': {
          color: 'rgba(255, 255, 255, 0.4)',
          paddingRight: '0.5rem',
          paddingLeft: '0.5rem',
          minWidth: '3rem',
        },
        '.cm-foldGutter': {
          color: 'rgba(255, 255, 255, 0.4)',
        },
        '.cm-placeholder': {
          color: 'rgba(255, 255, 255, 0.4)',
          fontStyle: 'italic',
        },
        // Syntax highlighting
        '.cm-keyword': { color: '#c678dd' },
        '.cm-string': { color: '#98c379' },
        '.cm-comment': { color: '#5c6370', fontStyle: 'italic' },
        '.cm-number': { color: '#d19a66' },
        '.cm-variable': { color: '#e06c75' },
        '.cm-punctuation': { color: '#abb2bf' },
        '.cm-operator': { color: '#56b6c2' },
        '.cm-builtin': { color: '#e5c07b' },
      }, { dark: true }),
      readOnlyCompartment.of(disabled ? EditorState.readOnly.of(true) : []),
      vimCompartment.of(vimMode ? vim() : []),
      EditorView.updateListener.of((update) => {
        if (update.docChanged && !isInternalChange) {
          const newContent = update.state.doc.toString();
          if (newContent !== previousValue) {
            previousValue = newContent;
            // Don't directly update value prop, just dispatch the change event
            dispatch('change', { content: newContent });
          }
        }
        
      }),
    ];

    // Add placeholder if provided
    if (placeholder) {
      extensions.push(
        EditorView.contentAttributes.of({
          'data-placeholder': placeholder,
        })
      );
    }

    return EditorState.create({
      doc: initialDoc,
      extensions,
    });
  }

  function createEditor() {
    if (!editorElement) return;

    const state = createEditorState(value);
    editorView = new EditorView({
      state,
      parent: editorElement,
    });

    previousValue = value;
    previousDisabled = disabled;
    previousVimMode = vimMode;
  }

  function updateEditorContent(newValue: string) {
    if (!editorView || newValue === previousValue) return;

    const currentContent = editorView.state.doc.toString();
    if (currentContent !== newValue) {
      isInternalChange = true;
      
      // Store cursor position
      const selection = editorView.state.selection;
      
      editorView.dispatch({
        changes: {
          from: 0,
          to: editorView.state.doc.length,
          insert: newValue,
        },
        selection: selection, // Restore cursor position
      });
      
      previousValue = newValue;
      isInternalChange = false;
    }
  }

  // Reactive updates
  $: if (editorView && value !== previousValue) {
    updateEditorContent(value);
  }

  $: if (editorView && (disabled !== previousDisabled || vimMode !== previousVimMode)) {
    const effects = [];
    
    if (disabled !== previousDisabled) {
      effects.push(readOnlyCompartment.reconfigure(disabled ? EditorState.readOnly.of(true) : []));
      previousDisabled = disabled;
    }
    
    if (vimMode !== previousVimMode) {
      effects.push(vimCompartment.reconfigure(vimMode ? vim() : []));
      previousVimMode = vimMode;
    }
    
    if (effects.length > 0) {
      editorView.dispatch({ effects });
    }
  }

  onMount(() => {
    // Detect if we're on a mobile device
    isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent) || 
                ('ontouchstart' in window) ||
                (window.matchMedia && window.matchMedia('(max-width: 768px)').matches) ||
                (window.matchMedia && window.matchMedia('(pointer: coarse)').matches);
    
    createEditor();
  });

  onDestroy(() => {
    if (editorView) {
      editorView.destroy();
      editorView = null;
    }
  });

  // Public methods
  export function focus() {
    if (editorView) {
      editorView.focus();
    }
  }

  export function getContent(): string {
    return editorView ? editorView.state.doc.toString() : value;
  }

  export function setContent(content: string) {
    if (editorView) {
      isInternalChange = true;
      editorView.dispatch({
        changes: {
          from: 0,
          to: editorView.state.doc.length,
          insert: content,
        },
      });
      previousValue = content;
      isInternalChange = false;
    }
    // Don't set value directly when using bind:value
  }

  export function toggleVimMode() {
    // Don't modify the bound prop directly, dispatch an event instead
    dispatch('toggleVim');
  }

  function sendEscKey() {
    if (editorView && vimMode) {
      // Dispatch ESC key event to CodeMirror
      const escEvent = new KeyboardEvent('keydown', {
        key: 'Escape',
        code: 'Escape',
        keyCode: 27,
        which: 27,
        bubbles: true,
        cancelable: true
      });
      editorView.contentDOM.dispatchEvent(escEvent);
      editorView.focus();
    }
  }
</script>

<div class="codemirror-container">
  <div class="codemirror-editor" bind:this={editorElement}></div>
  
  <div class="editor-controls">
    <button 
      class="vim-toggle {vimMode ? 'active' : ''}" 
      on:click={toggleVimMode}
      title={vimMode ? 'Disable vim keybindings' : 'Enable vim keybindings'}
    >
      VIM
    </button>
  </div>
  
  {#if isMobile && vimMode}
    <button 
      class="mobile-esc-button"
      on:click={sendEscKey}
      title="Exit to normal mode (ESC)"
    >
      ESC
    </button>
  {/if}
</div>

<style>
  .codemirror-container {
    position: relative;
    height: 100%;
    width: 100%;
    background: linear-gradient(135deg, #1a1f2e 0%, #232937 100%);
    border-radius: 12px;
    overflow: hidden;
    box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.2);
  }

  .codemirror-editor {
    height: 100%;
    width: 100%;
  }

  .editor-controls {
    position: fixed;
    top: auto;
    bottom: 100px;
    right: 1rem;
    z-index: 10;
    display: flex;
    gap: 0.5rem;
  }

  .vim-toggle {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    font-size: 0.65rem;
    font-weight: 600;
    font-family: monospace;
    letter-spacing: 0.5px;
    border: 1px solid rgba(255, 255, 255, 0.2);
    background: rgba(0, 0, 0, 0.3);
    color: rgba(255, 255, 255, 0.6);
    cursor: pointer;
    transition: all 0.2s ease;
    backdrop-filter: blur(4px);
    min-width: 2.5rem;
  }

  .vim-toggle:hover {
    background: rgba(0, 0, 0, 0.4);
    border-color: rgba(255, 255, 255, 0.3);
    color: rgba(255, 255, 255, 0.8);
  }

  .vim-toggle.active {
    background: rgba(16, 185, 129, 0.2);
    color: #10b981;
    border-color: rgba(16, 185, 129, 0.3);
  }

  .vim-toggle.active:hover {
    background: rgba(16, 185, 129, 0.3);
    border-color: rgba(16, 185, 129, 0.4);
  }

  /* Mobile ESC button */
  .mobile-esc-button {
    position: fixed;
    bottom: 100px;
    left: 1rem;
    z-index: 11;
    
    padding: 0.75rem 1.25rem;
    min-width: 4rem;
    min-height: 48px;
    
    background: linear-gradient(135deg, rgba(239, 68, 68, 0.95) 0%, rgba(220, 38, 38, 0.95) 100%);
    color: white;
    border: 2px solid rgba(255, 255, 255, 0.3);
    border-radius: 24px;
    
    font-size: 1rem;
    font-weight: 700;
    font-family: system-ui, -apple-system, sans-serif;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    
    cursor: pointer;
    touch-action: manipulation;
    -webkit-tap-highlight-color: transparent;
    -webkit-user-select: none;
    user-select: none;
    
    backdrop-filter: blur(10px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2), 0 2px 6px rgba(239, 68, 68, 0.4);
    
    animation: slideIn 0.3s ease-out;
    transition: all 0.15s ease;
  }

  .mobile-esc-button:active {
    transform: scale(0.95);
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15), 0 1px 2px rgba(239, 68, 68, 0.3);
  }
  
  @keyframes slideIn {
    from {
      opacity: 0;
      transform: translateY(10px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
  
  @keyframes fadeIn {
    from {
      opacity: 0;
      transform: scale(0.9);
    }
    to {
      opacity: 1;
      transform: scale(1);
    }
  }


  /* Global CodeMirror styling overrides */
  :global(.cm-editor) {
    background: transparent !important;
  }

  :global(.cm-content) {
    background: transparent !important;
    caret-color: #10b981;
  }

  :global(.cm-focused .cm-cursor) {
    border-color: #10b981 !important;
  }

  :global(.cm-selectionBackground) {
    background: rgba(16, 185, 129, 0.2) !important;
  }

  :global(.cm-vim-panel) {
    background: #1a202c !important;
    border-top: 1px solid rgba(255, 255, 255, 0.1) !important;
    color: #e2e8f0 !important;
  }

  :global(.cm-vim-panel input) {
    background: transparent !important;
    border: none !important;
    color: #e2e8f0 !important;
    font-family: 'JetBrains Mono', 'Monaco', 'Menlo', monospace !important;
  }

  /* Mobile adjustments */
  @media (max-width: 768px) {
    .codemirror-container {
      border-radius: 0;
    }
    
    .editor-controls {
      position: fixed;
      bottom: 100px;
      right: 1rem;
    }

    .vim-toggle {
      font-size: 0.85rem;
      padding: 0.5rem 1rem;
      min-width: 3.5rem;
      min-height: 44px;
      border-radius: 22px;
      font-weight: 700;
      backdrop-filter: blur(10px);
      background: rgba(0, 0, 0, 0.6);
      border: 2px solid rgba(255, 255, 255, 0.3);
    }
    
    :global(.cm-content) {
      font-size: 1.1rem !important;
      line-height: 2 !important;
      -webkit-text-size-adjust: none;
      padding-top: 1rem !important;
      padding-bottom: 8rem !important;
    }
    
    :global(.cm-line) {
      padding-top: 0.25rem !important;
      padding-bottom: 0.25rem !important;
    }
    
    :global(.cm-gutters) {
      min-width: 3rem !important;
      font-size: 0.9rem !important;
    }
    
    :global(.cm-lineNumbers) {
      font-size: 0.9rem !important;
      min-width: 2.5rem !important;
      padding-right: 0.75rem !important;
    }
    
    :global(.cm-scroller) {
      font-family: "SF Mono", "Monaco", "Courier New", monospace !important;
    }
  }
</style>