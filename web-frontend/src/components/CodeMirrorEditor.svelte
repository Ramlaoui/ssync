<script lang="ts">
  import { run } from 'svelte/legacy';

  import { onMount, onDestroy, createEventDispatcher } from 'svelte';
  import { EditorView, keymap, drawSelection, dropCursor, rectangularSelection, crosshairCursor, lineNumbers as lineNumbersGutter, gutter } from '@codemirror/view';
  import { EditorState, Compartment } from '@codemirror/state';
  import type { Extension } from '@codemirror/state';
  import { vim, Vim } from '@replit/codemirror-vim';
  import { shell } from '@codemirror/legacy-modes/mode/shell';
  import { StreamLanguage, indentOnInput, bracketMatching, foldGutter, foldKeymap, indentUnit } from '@codemirror/language';
  import { defaultKeymap, history, historyKeymap, insertTab } from '@codemirror/commands';
  import { searchKeymap, highlightSelectionMatches } from '@codemirror/search';
  import { autocompletion, completionKeymap, closeBrackets, closeBracketsKeymap } from '@codemirror/autocomplete';
  import { lintKeymap } from '@codemirror/lint';

  const dispatch = createEventDispatcher<{
    change: { content: string };
    toggleVim: void;
  }>();

  interface Props {
    value?: string;
    placeholder?: string;
    disabled?: boolean;
    vimMode?: boolean;
    theme?: string;
    fontSize?: number;
    lineNumbers?: boolean;
    wordWrap?: boolean;
    tabSize?: number;
    autoIndent?: boolean;
  }

  let {
    value = '',
    placeholder = '',
    disabled = false,
    vimMode = true,
    theme = 'dark',
    fontSize = 14,
    lineNumbers = true,
    wordWrap = false,
    tabSize = 2,
    autoIndent = true
  }: Props = $props();

  let editorElement: HTMLDivElement | undefined = $state();
  let editorView: EditorView | null = $state(null);
  let previousValue = $state('');
  let previousDisabled = $state(disabled);
  let previousVimMode = $state(vimMode);
  let previousTheme = $state(theme);
  let previousLineNumbers = $state(lineNumbers);
  let previousWordWrap = $state(wordWrap);
  let previousTabSize = $state(tabSize);
  let previousAutoIndent = $state(autoIndent);
  let previousFontSize = $state(fontSize);
  let isInternalChange = false;
  let isMobile = false;
  
  // Create compartments for dynamic configuration
  const readOnlyCompartment = new Compartment();
  const vimCompartment = new Compartment();
  const themeCompartment = new Compartment();
  const lineNumbersCompartment = new Compartment();
  const wrapCompartment = new Compartment();

  // Create the bash language support using legacy modes
  const bashLanguage = StreamLanguage.define(shell);

  function getThemeExtension() {
    const isDark = theme === 'dark' || theme === 'dracula';
    // Softer, more consistent colors with the page theme
    const backgroundColor = theme === 'dracula' ? '#282a36' : (isDark ? '#1a1f2e' : (isMobile ? '#fafbfc' : '#fafbfc'));
    const foregroundColor = theme === 'dracula' ? '#f8f8f2' : (isDark ? '#e2e8f0' : '#374151');
    const mobileFont = '"SF Mono", "Monaco", "Menlo", "Consolas", "Courier New", monospace';
    const desktopFont = '"JetBrains Mono", "Monaco", "Menlo", "Ubuntu Mono", monospace';

    // Unified font metrics for perfect alignment
    const fontFamily = isMobile ? mobileFont : desktopFont;
    const lineHeight = 1.5;
    const baseFontSize = `${fontSize}px`;

    return EditorView.theme({
      '&': {
        height: '100%',
        fontSize: baseFontSize,
        fontFamily: fontFamily,
        backgroundColor,
        color: foregroundColor,
        lineHeight: lineHeight,
      },
      '.cm-content': {
        padding: isMobile ? '0.75rem' : '1.5rem',
        paddingTop: isMobile ? '1rem' : '1.5rem',
        paddingBottom: isMobile ? '1rem' : '1.5rem',
        minHeight: '100%',
        backgroundColor: 'transparent',
        color: foregroundColor,
        fontSize: baseFontSize,
        fontFamily: fontFamily,
        caretColor: theme === 'dracula' ? '#ff79c6' : (isMobile ? '#6366f1' : '#10b981'),
        lineHeight: lineHeight,
        letterSpacing: isMobile ? '0.01em' : 'normal',
      },
      '.cm-focused': {
        outline: 'none',
      },
      '.cm-editor': {
        height: '100%',
        backgroundColor: 'transparent',
      },
      '.cm-scroller': {
        fontFamily: fontFamily,
        fontSize: baseFontSize,
        lineHeight: lineHeight,
      },
      '.cm-cursor': {
        borderColor: theme === 'dracula' ? '#ff79c6' : (isMobile ? '#6366f1' : '#10b981'),
        borderWidth: isMobile ? '2px' : '1px',
      },
      '.cm-selectionBackground': {
        backgroundColor: theme === 'dracula' ? 'rgba(255, 121, 198, 0.2)' : 'rgba(16, 185, 129, 0.2)',
      },
      '.cm-activeLine': {
        backgroundColor: isDark ? 'rgba(255, 255, 255, 0.02)' : 'rgba(0, 0, 0, 0.02)',
      },
      '.cm-activeLineGutter': {
        backgroundColor: isDark ? 'rgba(255, 255, 255, 0.05)' : 'rgba(0, 0, 0, 0.05)',
      },
      '.cm-gutters': {
        backgroundColor: isDark ? 'rgba(0, 0, 0, 0.1)' : 'transparent',
        color: isDark ? 'rgba(255, 255, 255, 0.3)' : 'rgba(156, 163, 175, 0.8)',
        border: 'none',
        fontSize: baseFontSize,
        fontFamily: fontFamily,
        borderRight: isDark ? '1px solid rgba(255, 255, 255, 0.05)' : 'none',
        minWidth: isMobile ? '2.5rem' : '3rem',
        lineHeight: lineHeight,
        paddingTop: isMobile ? '1rem' : '1.5rem',
      },
      '.cm-lineNumbers': {
        color: isDark ? 'rgba(255, 255, 255, 0.4)' : (isMobile ? 'rgba(0, 0, 0, 0.5)' : 'rgba(0, 0, 0, 0.4)'),
        paddingRight: isMobile ? '0.75rem' : '1rem',
        paddingLeft: isMobile ? '0.5rem' : '0.75rem',
        fontSize: baseFontSize,
        fontFamily: fontFamily,
        lineHeight: lineHeight,
        textAlign: 'right',
      },
      '.cm-foldGutter': {
        color: isDark ? 'rgba(255, 255, 255, 0.4)' : 'rgba(0, 0, 0, 0.4)',
      },
      '.cm-placeholder': {
        color: isDark ? 'rgba(255, 255, 255, 0.4)' : 'rgba(0, 0, 0, 0.4)',
        fontStyle: 'italic',
      },
      '.cm-line': {
        fontSize: baseFontSize,
        fontFamily: fontFamily,
        lineHeight: lineHeight,
      },
      // Syntax highlighting with mobile-optimized colors
      '.cm-keyword': {
        color: theme === 'dracula' ? '#8be9fd' : (isDark ? '#c678dd' : (isMobile ? '#7c3aed' : '#d73a49')),
        fontWeight: isMobile ? '500' : 'normal'
      },
      '.cm-string': {
        color: theme === 'dracula' ? '#f1fa8c' : (isDark ? '#98c379' : (isMobile ? '#059669' : '#032f62'))
      },
      '.cm-comment': {
        color: theme === 'dracula' ? '#6272a4' : (isDark ? '#5c6370' : (isMobile ? '#6b7280' : '#6a737d')),
        fontStyle: 'italic',
        opacity: isMobile ? '0.8' : '1'
      },
      '.cm-number': {
        color: theme === 'dracula' ? '#bd93f9' : (isDark ? '#d19a66' : (isMobile ? '#2563eb' : '#005cc5'))
      },
      '.cm-variable': {
        color: theme === 'dracula' ? '#ff79c6' : (isDark ? '#e06c75' : (isMobile ? '#dc2626' : '#e36209'))
      },
      '.cm-punctuation': {
        color: theme === 'dracula' ? '#f8f8f2' : (isDark ? '#abb2bf' : (isMobile ? '#4b5563' : '#24292e'))
      },
      '.cm-operator': {
        color: theme === 'dracula' ? '#ff79c6' : (isDark ? '#56b6c2' : (isMobile ? '#7c3aed' : '#d73a49'))
      },
      '.cm-builtin': {
        color: theme === 'dracula' ? '#50fa7b' : (isDark ? '#e5c07b' : (isMobile ? '#0891b2' : '#005cc5'))
      },
    }, { dark: isDark });
  }

  function createEditorState(initialDoc: string) {
    const extensions = [
      // Basic editor functionality
      wrapCompartment.of(wordWrap ? EditorView.lineWrapping : []),
      lineNumbersCompartment.of(lineNumbers ? lineNumbersGutter() : []),
      foldGutter(),
      history(),
      drawSelection(),
      dropCursor(),
      EditorState.allowMultipleSelections.of(true),
      autoIndent ? indentOnInput() : [],
      bracketMatching(),
      closeBrackets(),
      autocompletion(),
      rectangularSelection(),
      crosshairCursor(),
      highlightSelectionMatches(),
      indentUnit.of(' '.repeat(tabSize)),
      keymap.of([
        // Custom tab handling to prevent tab from leaving editor
        { key: 'Tab', run: insertTab, shift: insertTab },
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
      themeCompartment.of(getThemeExtension()),
      readOnlyCompartment.of(disabled ? EditorState.readOnly.of(true) : []),
      vimCompartment.of(vimMode ? [vim(), getVimKeymaps()] : []),
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
    if (!editorView) return;

    const currentContent = editorView.state.doc.toString();

    // Skip update if content is already the same
    if (currentContent === newValue) {
      previousValue = newValue;
      return;
    }

    isInternalChange = true;

    // Store scroll position before update
    const scrollTop = editorView.scrollDOM.scrollTop;
    const scrollLeft = editorView.scrollDOM.scrollLeft;

    // Store cursor position and clamp it to the new document length
    const selection = editorView.state.selection;
    const newDocLength = newValue.length;

    // Create a safe selection that won't exceed the new document bounds
    const safeSelection = {
      anchor: Math.min(selection.main.anchor, newDocLength),
      head: Math.min(selection.main.head, newDocLength)
    };

    editorView.dispatch({
      changes: {
        from: 0,
        to: editorView.state.doc.length,
        insert: newValue,
      },
      selection: { anchor: safeSelection.anchor, head: safeSelection.head },
      scrollIntoView: false,  // Prevent automatic scrolling
    });

    // Restore scroll position after the update
    // Use requestAnimationFrame to ensure DOM has updated
    requestAnimationFrame(() => {
      if (editorView) {
        editorView.scrollDOM.scrollTop = scrollTop;
        editorView.scrollDOM.scrollLeft = scrollLeft;
      }
    });

    previousValue = newValue;
    isInternalChange = false;
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

  function getVimKeymaps() {
    // Configure vim key mappings using the vim API
    if (typeof Vim !== 'undefined') {
      // Map 'jk' to escape in insert mode
      Vim.map('jk', '<Esc>', 'insert');
      // Alternative mapping 'jj'
      Vim.map('jj', '<Esc>', 'insert');
    }
    return [];
  }

  // Reactive updates
  run(() => {
    if (editorView && value !== previousValue) {
      updateEditorContent(value);
    }
  });
  run(() => {
    if (editorView && (disabled !== previousDisabled || vimMode !== previousVimMode)) {
      const effects = [];
      
      if (disabled !== previousDisabled) {
        effects.push(readOnlyCompartment.reconfigure(disabled ? EditorState.readOnly.of(true) : []));
        previousDisabled = disabled;
      }
      
      if (vimMode !== previousVimMode) {
        effects.push(vimCompartment.reconfigure(vimMode ? [vim(), getVimKeymaps()] : []));
        previousVimMode = vimMode;
      }
      
      if (effects.length > 0) {
        editorView.dispatch({ effects });
      }
    }
  });
  // Reactive updates for editor options
  run(() => {
    if (editorView) {
      const effects = [];
      let needsRecreate = false;

      if (vimMode !== previousVimMode) {
        effects.push(vimCompartment.reconfigure(vimMode ? [vim(), getVimKeymaps()] : []));
        previousVimMode = vimMode;
      }

      if (theme !== previousTheme || fontSize !== previousFontSize) {
        effects.push(themeCompartment.reconfigure(getThemeExtension()));
        previousTheme = theme;
        previousFontSize = fontSize;
      }

      if (lineNumbers !== previousLineNumbers) {
        effects.push(lineNumbersCompartment.reconfigure(lineNumbers ? lineNumbersGutter() : []));
        previousLineNumbers = lineNumbers;
      }

      if (wordWrap !== previousWordWrap) {
        effects.push(wrapCompartment.reconfigure(wordWrap ? EditorView.lineWrapping : []));
        previousWordWrap = wordWrap;
      }

      if (disabled !== previousDisabled) {
        effects.push(readOnlyCompartment.reconfigure(disabled ? EditorState.readOnly.of(true) : []));
        previousDisabled = disabled;
      }

      // Tab size and autoIndent require recreating some extensions
      if (tabSize !== previousTabSize || autoIndent !== previousAutoIndent) {
        needsRecreate = true;
        previousTabSize = tabSize;
        previousAutoIndent = autoIndent;
      }

      if (needsRecreate) {
        // For tabSize and autoIndent changes, we need to recreate the editor
        const currentValue = editorView.state.doc.toString();
        const currentSelection = editorView.state.selection;
        createEditor();
        if (editorView) {
          editorView.dispatch({
            changes: { from: 0, to: editorView.state.doc.length, insert: currentValue },
            selection: currentSelection
          });
        }
      } else if (effects.length > 0) {
        editorView.dispatch({ effects });
      }
    }
  });
</script>

<div class="codemirror-container">
  <div class="codemirror-editor" bind:this={editorElement}></div>
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

  /* Removed vim toggle styles - now handled by parent component */

  /* Vim escape hint for mobile users */
  .codemirror-container::after {
    content: 'Tip: Type "jk" or "jj" quickly to exit insert mode';
    position: absolute;
    bottom: 0.5rem;
    right: 0.5rem;
    font-size: 0.75rem;
    color: rgba(255, 255, 255, 0.6);
    background: rgba(0, 0, 0, 0.5);
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.3s ease;
    z-index: 10;
  }

  @media (max-width: 768px) {
    .codemirror-container:hover::after {
      opacity: 1;
    }
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

    :global(.cm-scroller) {
      font-family: "SF Mono", "Monaco", "Courier New", monospace !important;
      font-size: 14px !important;
      line-height: 1.5 !important;
    }
  }
</style>