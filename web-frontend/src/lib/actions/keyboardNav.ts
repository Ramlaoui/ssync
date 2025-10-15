/**
 * Keyboard navigation action for Svelte components
 * Provides centralized keyboard event handling
 */

export interface KeyboardNavOptions {
  /** Callback for Escape key */
  onEscape?: (event: KeyboardEvent) => void;
  /** Callback for Enter key */
  onEnter?: (event: KeyboardEvent) => void;
  /** Callback for ArrowUp key */
  onArrowUp?: (event: KeyboardEvent) => void;
  /** Callback for ArrowDown key */
  onArrowDown?: (event: KeyboardEvent) => void;
  /** Callback for ArrowLeft key */
  onArrowLeft?: (event: KeyboardEvent) => void;
  /** Callback for ArrowRight key */
  onArrowRight?: (event: KeyboardEvent) => void;
  /** Callback for Tab key */
  onTab?: (event: KeyboardEvent) => void;
  /** Callback for Space key */
  onSpace?: (event: KeyboardEvent) => void;
  /** Callback for Home key */
  onHome?: (event: KeyboardEvent) => void;
  /** Callback for End key */
  onEnd?: (event: KeyboardEvent) => void;
  /** Whether to prevent default behavior for handled keys */
  preventDefault?: boolean;
  /** Whether to stop propagation for handled events */
  stopPropagation?: boolean;
  /** Whether the keyboard navigation is enabled */
  enabled?: boolean;
}

/**
 * Svelte action for centralized keyboard event handling
 *
 * @example
 * ```svelte
 * <div use:keyboardNav={{
 *   onEscape: () => close(),
 *   onEnter: () => submit(),
 *   onArrowDown: () => selectNext(),
 *   preventDefault: true
 * }}>
 *   Content
 * </div>
 * ```
 */
export function keyboardNav(node: HTMLElement, options: KeyboardNavOptions = {}) {
  const {
    onEscape,
    onEnter,
    onArrowUp,
    onArrowDown,
    onArrowLeft,
    onArrowRight,
    onTab,
    onSpace,
    onHome,
    onEnd,
    preventDefault = false,
    stopPropagation = false,
    enabled = true
  } = options;

  let currentOptions = options;
  let currentEnabled = enabled;

  const handleKeyDown = (event: KeyboardEvent) => {
    if (!currentEnabled) return;

    let handled = false;

    switch (event.key) {
      case 'Escape':
      case 'Esc': // For older browsers
        if (currentOptions.onEscape) {
          currentOptions.onEscape(event);
          handled = true;
        }
        break;

      case 'Enter':
        if (currentOptions.onEnter) {
          currentOptions.onEnter(event);
          handled = true;
        }
        break;

      case 'ArrowUp':
      case 'Up': // For older browsers
        if (currentOptions.onArrowUp) {
          currentOptions.onArrowUp(event);
          handled = true;
        }
        break;

      case 'ArrowDown':
      case 'Down': // For older browsers
        if (currentOptions.onArrowDown) {
          currentOptions.onArrowDown(event);
          handled = true;
        }
        break;

      case 'ArrowLeft':
      case 'Left': // For older browsers
        if (currentOptions.onArrowLeft) {
          currentOptions.onArrowLeft(event);
          handled = true;
        }
        break;

      case 'ArrowRight':
      case 'Right': // For older browsers
        if (currentOptions.onArrowRight) {
          currentOptions.onArrowRight(event);
          handled = true;
        }
        break;

      case 'Tab':
        if (currentOptions.onTab) {
          currentOptions.onTab(event);
          handled = true;
        }
        break;

      case ' ':
      case 'Spacebar': // For older browsers
        if (currentOptions.onSpace) {
          currentOptions.onSpace(event);
          handled = true;
        }
        break;

      case 'Home':
        if (currentOptions.onHome) {
          currentOptions.onHome(event);
          handled = true;
        }
        break;

      case 'End':
        if (currentOptions.onEnd) {
          currentOptions.onEnd(event);
          handled = true;
        }
        break;
    }

    if (handled) {
      if (currentOptions.preventDefault ?? preventDefault) {
        event.preventDefault();
      }
      if (currentOptions.stopPropagation ?? stopPropagation) {
        event.stopPropagation();
      }
    }
  };

  node.addEventListener('keydown', handleKeyDown);

  return {
    update(newOptions: KeyboardNavOptions) {
      currentOptions = newOptions;
      currentEnabled = newOptions.enabled ?? true;
    },
    destroy() {
      node.removeEventListener('keydown', handleKeyDown);
    }
  };
}