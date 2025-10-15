/**
 * Enhanced click outside action for Svelte components
 * Detects clicks outside an element and triggers a callback
 */

export interface ClickOutsideOptions {
  /** Whether the action is enabled */
  enabled?: boolean;
  /** Callback function when click outside is detected */
  callback?: (event: MouseEvent) => void;
  /** CSS selector for elements to exclude from outside check */
  excludeSelector?: string;
}

/**
 * Svelte action that detects clicks outside an element
 *
 * @example
 * ```svelte
 * <div use:clickOutside={{ enabled: isOpen, callback: () => isOpen = false }}>
 *   Content
 * </div>
 * ```
 */
export function clickOutside(node: HTMLElement, options: ClickOutsideOptions = {}) {
  const { enabled = true, callback, excludeSelector } = options;

  let currentEnabled = enabled;
  let currentCallback = callback;
  let currentExcludeSelector = excludeSelector;

  const handleClick = (event: MouseEvent) => {
    if (!currentEnabled) return;

    const target = event.target as Node;

    // Check if click is inside the element
    if (node.contains(target)) return;

    // Check if event was already handled
    if (event.defaultPrevented) return;

    // Check if click is on an excluded element
    if (currentExcludeSelector && target instanceof Element) {
      const excludedElement = target.closest(currentExcludeSelector);
      if (excludedElement) return;
    }

    // Trigger callback if provided
    if (currentCallback) {
      currentCallback(event);
    }

    // Dispatch custom event for backward compatibility
    node.dispatchEvent(
      new CustomEvent('click_outside', { detail: event })
    );
  };

  // Use capture phase to catch events before they bubble
  document.addEventListener('click', handleClick, true);

  return {
    update(newOptions: ClickOutsideOptions) {
      currentEnabled = newOptions.enabled ?? true;
      currentCallback = newOptions.callback;
      currentExcludeSelector = newOptions.excludeSelector;
    },
    destroy() {
      document.removeEventListener('click', handleClick, true);
    }
  };
}