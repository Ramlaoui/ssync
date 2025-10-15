/**
 * Focus trap action for Svelte components
 * Traps focus within an element, useful for modals and dialogs
 */

const FOCUSABLE_ELEMENTS = [
  'a[href]',
  'area[href]',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  'button:not([disabled])',
  'iframe',
  'object',
  'embed',
  '[contenteditable]',
  '[tabindex]:not([tabindex="-1"])'
].join(',');

export interface FocusTrapOptions {
  /** Whether the focus trap is enabled */
  enabled?: boolean;
  /** Whether to focus the first element on mount */
  autoFocus?: boolean;
  /** Element to focus initially (overrides autoFocus) */
  initialFocus?: HTMLElement | null;
  /** Element to restore focus to when trap is disabled */
  restoreFocus?: HTMLElement | null;
}

/**
 * Gets all focusable elements within a container
 */
function getFocusableElements(container: HTMLElement): HTMLElement[] {
  const elements = container.querySelectorAll<HTMLElement>(FOCUSABLE_ELEMENTS);
  const elementsArray: HTMLElement[] = [];

  for (let i = 0; i < elements.length; i++) {
    const el = elements[i];
    // Check if element is visible and not hidden
    if (el.offsetParent !== null && window.getComputedStyle(el).visibility !== 'hidden') {
      elementsArray.push(el);
    }
  }

  return elementsArray;
}

/**
 * Svelte action that traps focus within an element
 *
 * @example
 * ```svelte
 * <div use:focusTrap={{ enabled: isOpen, autoFocus: true }}>
 *   <input type="text" />
 *   <button>Submit</button>
 * </div>
 * ```
 */
export function focusTrap(node: HTMLElement, options: FocusTrapOptions = {}) {
  const {
    enabled = true,
    autoFocus = true,
    initialFocus = null,
    restoreFocus = null
  } = options;

  let currentEnabled = enabled;
  let previousActiveElement: Element | null = null;

  const handleKeyDown = (event: KeyboardEvent) => {
    if (!currentEnabled || event.key !== 'Tab') return;

    const focusableElements = getFocusableElements(node);
    if (focusableElements.length === 0) return;

    const firstElement = focusableElements[0];
    const lastElement = focusableElements[focusableElements.length - 1];

    // Shift + Tab
    if (event.shiftKey) {
      if (document.activeElement === firstElement) {
        event.preventDefault();
        lastElement.focus();
      }
    }
    // Tab
    else {
      if (document.activeElement === lastElement) {
        event.preventDefault();
        firstElement.focus();
      }
    }
  };

  function activate() {
    if (!currentEnabled) return;

    // Store the currently focused element
    previousActiveElement = document.activeElement;

    // Focus initial element
    if (initialFocus && initialFocus.focus) {
      initialFocus.focus();
    } else if (autoFocus) {
      const focusableElements = getFocusableElements(node);
      if (focusableElements.length > 0) {
        // Small delay to ensure element is mounted
        setTimeout(() => {
          focusableElements[0].focus();
        }, 0);
      }
    }

    // Add keyboard listener
    node.addEventListener('keydown', handleKeyDown);
  }

  function deactivate() {
    // Remove keyboard listener
    node.removeEventListener('keydown', handleKeyDown);

    // Restore focus to previous element
    const elementToRestore = restoreFocus || previousActiveElement;
    if (elementToRestore && elementToRestore instanceof HTMLElement && elementToRestore.focus) {
      // Small delay to ensure the element is still in the DOM
      setTimeout(() => {
        elementToRestore.focus();
      }, 0);
    }
  }

  // Activate on mount if enabled
  if (currentEnabled) {
    activate();
  }

  return {
    update(newOptions: FocusTrapOptions) {
      const wasEnabled = currentEnabled;
      currentEnabled = newOptions.enabled ?? true;

      // Enable/disable based on state change
      if (currentEnabled && !wasEnabled) {
        activate();
      } else if (!currentEnabled && wasEnabled) {
        deactivate();
      }
    },
    destroy() {
      if (currentEnabled) {
        deactivate();
      }
    }
  };
}