# Svelte Actions

This directory contains reusable Svelte actions for common UI interactions. These actions form the foundation of the unified component system for overlays, dialogs, sidebars, and dropdowns.

## Available Actions

### clickOutside

Detects clicks outside an element and triggers a callback.

**Features:**
- Enable/disable toggle
- Exclude specific elements from detection
- Callback function support
- Backward compatible event dispatch

**Usage:**
```svelte
<script>
  import { clickOutside } from '$lib/actions';

  let isOpen = true;

  function handleClickOutside() {
    isOpen = false;
  }
</script>

<div use:clickOutside={{ enabled: isOpen, callback: handleClickOutside }}>
  Modal content
</div>

<!-- With excluded elements -->
<div use:clickOutside={{
  enabled: isOpen,
  callback: handleClickOutside,
  excludeSelector: '.trigger-button'
}}>
  Modal content
</div>

<!-- Using custom event (backward compatible) -->
<div use:clickOutside on:click_outside={handleClickOutside}>
  Modal content
</div>
```

**Options:**
- `enabled?: boolean` - Whether the action is enabled (default: `true`)
- `callback?: (event: MouseEvent) => void` - Callback when click outside occurs
- `excludeSelector?: string` - CSS selector for elements to exclude

---

### focusTrap

Traps focus within an element, cycling through focusable elements with Tab/Shift+Tab.

**Features:**
- Automatic focus on first focusable element
- Tab/Shift+Tab cycling
- Custom initial focus element
- Focus restoration when disabled
- Filters hidden/disabled elements

**Usage:**
```svelte
<script>
  import { focusTrap } from '$lib/actions';

  let dialogOpen = true;
</script>

<!-- Basic usage -->
<div use:focusTrap={{ enabled: dialogOpen }}>
  <input type="text" />
  <button>Submit</button>
  <button>Cancel</button>
</div>

<!-- Custom initial focus -->
<div use:focusTrap={{ enabled: dialogOpen, initialFocus: submitButton }}>
  <input type="text" />
  <button bind:this={submitButton}>Submit</button>
</div>

<!-- Disable auto-focus -->
<div use:focusTrap={{ enabled: dialogOpen, autoFocus: false }}>
  Content
</div>
```

**Options:**
- `enabled?: boolean` - Whether focus trap is active (default: `true`)
- `autoFocus?: boolean` - Auto-focus first element on mount (default: `true`)
- `initialFocus?: HTMLElement | null` - Element to focus initially
- `restoreFocus?: HTMLElement | null` - Element to restore focus to

**Focusable Elements:**
- Links with href
- Inputs, selects, textareas (not disabled)
- Buttons (not disabled)
- Elements with contenteditable
- Elements with tabindex >= 0

---

### keyboardNav

Centralized keyboard event handling with common key bindings.

**Features:**
- Support for all common keys (Escape, Enter, Arrows, Tab, etc.)
- Optional preventDefault and stopPropagation
- Enable/disable toggle
- Backward compatible with older browsers

**Usage:**
```svelte
<script>
  import { keyboardNav } from '$lib/actions';

  let selectedIndex = 0;
  let items = ['Item 1', 'Item 2', 'Item 3'];

  function handleArrowDown(event) {
    selectedIndex = Math.min(selectedIndex + 1, items.length - 1);
  }

  function handleArrowUp(event) {
    selectedIndex = Math.max(selectedIndex - 1, 0);
  }

  function handleEnter(event) {
    selectItem(items[selectedIndex]);
  }

  function handleEscape(event) {
    closeDropdown();
  }
</script>

<!-- Dropdown with keyboard navigation -->
<div use:keyboardNav={{
  onEscape: handleEscape,
  onEnter: handleEnter,
  onArrowDown: handleArrowDown,
  onArrowUp: handleArrowUp,
  preventDefault: true
}}>
  {#each items as item, i}
    <div class:selected={i === selectedIndex}>{item}</div>
  {/each}
</div>
```

**Options:**
- `onEscape?: (event: KeyboardEvent) => void` - Escape key handler
- `onEnter?: (event: KeyboardEvent) => void` - Enter key handler
- `onArrowUp?: (event: KeyboardEvent) => void` - Arrow Up handler
- `onArrowDown?: (event: KeyboardEvent) => void` - Arrow Down handler
- `onArrowLeft?: (event: KeyboardEvent) => void` - Arrow Left handler
- `onArrowRight?: (event: KeyboardEvent) => void` - Arrow Right handler
- `onTab?: (event: KeyboardEvent) => void` - Tab key handler
- `onSpace?: (event: KeyboardEvent) => void` - Space key handler
- `onHome?: (event: KeyboardEvent) => void` - Home key handler
- `onEnd?: (event: KeyboardEvent) => void` - End key handler
- `preventDefault?: boolean` - Prevent default for handled keys (default: `false`)
- `stopPropagation?: boolean` - Stop event propagation (default: `false`)
- `enabled?: boolean` - Whether keyboard nav is enabled (default: `true`)

---

### portal

Moves an element to a different location in the DOM (typically `document.body`) for proper z-index stacking.

**Features:**
- Flexible target (selector or element)
- Configurable z-index
- Optional wrapper container
- Proper cleanup on destroy

**Usage:**
```svelte
<script>
  import { portal } from '$lib/actions';
</script>

<!-- Basic usage - portal to body -->
<div use:portal={{ target: 'body', zIndex: 50 }}>
  This will be moved to document.body
</div>

<!-- Portal to custom target -->
<div use:portal={{ target: '#overlay-container', zIndex: 100 }}>
  Custom target
</div>

<!-- Shorthand syntax -->
<div use:portal={'body'}>
  Shorthand portal to body
</div>

<!-- Without wrapper -->
<div use:portal={{ target: 'body', useWrapper: false }}>
  Direct portal without wrapper div
</div>

<!-- Custom class -->
<div use:portal={{ target: 'body', className: 'my-portal' }}>
  With custom class
</div>
```

**Options:**
- `target?: string | HTMLElement` - Target element or selector (default: `'body'`)
- `zIndex?: number` - z-index value (default: `9999`)
- `useWrapper?: boolean` - Whether to use wrapper div (default: `true`)
- `className?: string` - CSS class for wrapper (default: `'svelte-portal'`)

---

## Composing Actions

Actions can be combined on the same element:

```svelte
<div
  use:portal={'body'}
  use:clickOutside={{ enabled: isOpen, callback: close }}
  use:focusTrap={{ enabled: isOpen }}
  use:keyboardNav={{ onEscape: close }}
>
  Fully accessible modal with all features
</div>
```

## Best Practices

1. **Always bind `enabled` state** - Disable actions when components are not visible
2. **Use focusTrap for modals** - Essential for accessibility
3. **Combine keyboardNav with clickOutside** - Consistent UX
4. **Portal large overlays** - Prevents z-index issues
5. **Test keyboard navigation** - Ensure Tab, Escape, Enter work correctly

## Browser Compatibility

All actions support:
- Modern browsers (Chrome, Firefox, Safari, Edge)
- Older key codes (e.g., 'Esc' → 'Escape')
- ES5-compatible syntax (no Array.from, Object.assign)

## TypeScript Support

All actions have full TypeScript support with exported interfaces:

```typescript
import type {
  ClickOutsideOptions,
  FocusTrapOptions,
  KeyboardNavOptions,
  PortalOptions
} from '$lib/actions';
```

## Testing

Test keyboard and mouse interactions:

```typescript
import { render, fireEvent } from '@testing-library/svelte';

// Test click outside
const { container } = render(Component);
fireEvent.click(document.body);

// Test keyboard
fireEvent.keyDown(element, { key: 'Escape' });
fireEvent.keyDown(element, { key: 'Enter' });
```

## Related Components

These actions are used by:
- `Overlay.svelte` - Base overlay component
- `Dialog.svelte` - Modal dialogs
- `Sidebar.svelte` - Slide-in panels
- `Dropdown.svelte` - Contextual menus

See `web-frontend/src/lib/components/ui/` for component implementations.