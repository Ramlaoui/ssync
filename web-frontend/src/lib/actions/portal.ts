/**
 * Portal action for Svelte components
 * Moves an element to a different location in the DOM (typically document.body)
 * for proper z-index stacking and overlay management
 */

export interface PortalOptions {
  /** Target element or selector to portal into */
  target?: string | HTMLElement;
  /** z-index value for the portal container */
  zIndex?: number;
  /** Whether to use a wrapper div (default: true) */
  useWrapper?: boolean;
  /** Additional CSS classes for the wrapper */
  className?: string;
}

/**
 * Svelte action that portals an element to a different location in the DOM
 *
 * @example
 * ```svelte
 * <div use:portal={{ target: 'body', zIndex: 50 }}>
 *   This will be moved to document.body
 * </div>
 * ```
 */
export function portal(node: HTMLElement, options: PortalOptions | string = {}) {
  // Handle backward compatibility: if options is a string, treat it as target
  const opts = typeof options === 'string' ? { target: options } : options;

  const {
    target = 'body',
    zIndex = 9999,
    useWrapper = true,
    className = 'svelte-portal'
  } = opts;

  let portalContainer: HTMLElement | null = null;
  let targetElement: HTMLElement | null = null;

  function mount() {
    // Get target element
    if (typeof target === 'string') {
      targetElement = document.querySelector(target);
    } else {
      targetElement = target;
    }

    if (!targetElement) {
      console.error(`Portal target not found: ${target}`);
      return;
    }

    if (useWrapper) {
      // Create wrapper container
      portalContainer = document.createElement('div');
      portalContainer.className = className;
      portalContainer.style.position = 'fixed';
      portalContainer.style.zIndex = String(zIndex);
      portalContainer.style.top = '0';
      portalContainer.style.left = '0';
      portalContainer.style.pointerEvents = 'none';

      // Make portal content interactive
      node.style.pointerEvents = 'auto';

      targetElement.appendChild(portalContainer);
      portalContainer.appendChild(node);
    } else {
      // Move node directly to target
      targetElement.appendChild(node);
      node.style.position = 'fixed';
      node.style.zIndex = String(zIndex);
    }
  }

  function unmount() {
    if (portalContainer && portalContainer.parentNode) {
      // Remove node from portal
      if (portalContainer.contains(node)) {
        portalContainer.removeChild(node);
      }
      // Remove portal container
      portalContainer.parentNode.removeChild(portalContainer);
      portalContainer = null;
    } else if (targetElement && node.parentNode === targetElement) {
      // If no wrapper, just remove the node
      targetElement.removeChild(node);
    }
    targetElement = null;
  }

  // Mount on creation
  mount();

  return {
    update(newOptions: PortalOptions | string) {
      // Unmount and remount if options change
      unmount();
      const newOpts = typeof newOptions === 'string' ? { target: newOptions } : newOptions;
      // Manually copy properties instead of Object.assign
      for (const key in newOpts) {
        if (newOpts.hasOwnProperty(key)) {
          (opts as any)[key] = (newOpts as any)[key];
        }
      }
      mount();
    },
    destroy() {
      unmount();
    }
  };
}