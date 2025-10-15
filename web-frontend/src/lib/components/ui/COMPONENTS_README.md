# UI Component System - Usage Guide

This document describes the unified overlay component system for ssync. All components provide consistent keyboard navigation, focus management, and accessibility features.

## Base Components

### Overlay

The foundational component for all overlays. Provides backdrop, focus trap, and keyboard navigation.

```svelte
<script>
  import { Overlay } from '$lib/components/ui';
  let isOpen = true;
</script>

<Overlay
  open={isOpen}
  on:close={() => isOpen = false}
  closeOnBackdropClick={true}
  closeOnEscape={true}
  backdrop={true}
  zIndex={50}
  lockScroll={true}
  trapFocus={true}
>
  <div style="background: white; padding: 2rem; border-radius: 0.5rem;">
    Custom overlay content
  </div>
</Overlay>
```

**Props:**
- `open: boolean` - Whether overlay is visible
- `closeOnBackdropClick?: boolean` - Close when clicking backdrop (default: true)
- `closeOnEscape?: boolean` - Close with Escape key (default: true)
- `backdrop?: boolean` - Show backdrop (default: true)
- `backdropClass?: string` - Custom backdrop classes
- `zIndex?: number` - Z-index value (default: 50)
- `lockScroll?: boolean` - Lock body scroll (default: true)
- `trapFocus?: boolean` - Trap focus within overlay (default: true)

**Events:**
- `on:close` - Fired when overlay should close

---

### Dialog

Centered modal dialog with header, content, and footer sections.

```svelte
<script>
  import { Dialog, Button } from '$lib/components/ui';
  let showDialog = false;
  let name = '';

  function handleSave() {
    console.log('Saving:', name);
    showDialog = false;
  }
</script>

<button on:click={() => showDialog = true}>Open Dialog</button>

<Dialog
  bind:open={showDialog}
  title="Create New Template"
  description="Enter a name for your new template"
  size="md"
>
  <div class="space-y-4">
    <input
      type="text"
      bind:value={name}
      placeholder="Template name"
      class="w-full px-3 py-2 border rounded"
    />
  </div>

  <div slot="footer">
    <Button variant="outline" on:click={() => showDialog = false}>
      Cancel
    </Button>
    <Button on:click={handleSave} disabled={!name.trim()}>
      Save
    </Button>
  </div>
</Dialog>
```

**Props:** (All Overlay props, plus:)
- `title?: string` - Dialog title
- `description?: string` - Dialog description
- `size?: 'sm' | 'md' | 'lg' | 'xl' | 'full'` - Dialog size (default: 'md')
- `showCloseButton?: boolean` - Show X button (default: true)
- `headerClass?: string` - Custom header classes
- `contentClass?: string` - Custom content classes
- `footerClass?: string` - Custom footer classes

**Slots:**
- `header` - Custom header content (overrides title/description)
- `default` - Main content
- `footer` - Footer buttons/actions

**Mobile:** Full screen on small devices

---

### Sidebar

Slide-in panel from any edge of the screen.

```svelte
<script>
  import { Sidebar, Button } from '$lib/components/ui';
  let showSidebar = false;
</script>

<button on:click={() => showSidebar = true}>Open Sidebar</button>

<Sidebar
  bind:open={showSidebar}
  position="right"
  size="400px"
  title="Templates"
>
  <div slot="header">
    <h3>My Templates</h3>
    <Button size="sm" on:click={createNew}>New</Button>
  </div>

  <!-- Sidebar content -->
  <div class="space-y-2">
    {#each templates as template}
      <div class="p-3 border rounded">{template.name}</div>
    {/each}
  </div>
</Sidebar>
```

**Props:** (All Overlay props, plus:)
- `position?: 'left' | 'right' | 'top' | 'bottom'` - Slide direction (default: 'right')
- `size?: string` - Width/height ('300px', '40%', 'full')
- `title?: string` - Sidebar title
- `showCloseButton?: boolean` - Show X button (default: true)
- `headerClass?: string` - Custom header classes
- `contentClass?: string` - Custom content classes

**Slots:**
- `header` - Custom header content
- `default` - Main content

**Mobile:** Full screen on small devices

---

### Dropdown

Contextual menu positioned relative to a trigger element.

```svelte
<script>
  import { Dropdown, DropdownItem, DropdownDivider, DropdownLabel } from '$lib/components/ui';
  import { Server, Settings, Trash } from 'lucide-svelte';

  let triggerRef: HTMLElement;
  let dropdownOpen = false;

  function selectHost(host) {
    console.log('Selected:', host);
  }
</script>

<button
  bind:this={triggerRef}
  on:click={() => dropdownOpen = !dropdownOpen}
>
  Select Host
</button>

<Dropdown
  open={dropdownOpen}
  onClose={() => dropdownOpen = false}
  {triggerRef}
  placement="bottom"
  align="start"
  width="200px"
>
  <DropdownLabel>Available Hosts</DropdownLabel>

  <DropdownItem on:click={() => selectHost('host1')}>
    <Server />
    <span>Host 1</span>
  </DropdownItem>

  <DropdownItem on:click={() => selectHost('host2')}>
    <Server />
    <span>Host 2</span>
  </DropdownItem>

  <DropdownDivider />

  <DropdownItem on:click={openSettings}>
    <Settings />
    <span>Settings</span>
  </DropdownItem>

  <DropdownItem danger on:click={deleteHost}>
    <Trash />
    <span>Delete</span>
  </DropdownItem>
</Dropdown>
```

**Props:**
- `open: boolean` - Whether dropdown is visible
- `triggerRef: HTMLElement | null` - Reference to trigger button
- `placement?: 'bottom' | 'top' | 'left' | 'right' | 'auto'` - Position (default: 'auto')
- `align?: 'start' | 'center' | 'end'` - Alignment (default: 'start')
- `offset?: number` - Distance from trigger in pixels (default: 8)
- `width?: string` - Width ('auto', '200px', 'trigger')
- `maxHeight?: string` - Max height (default: '300px')
- `closeOnSelect?: boolean` - Close when item selected (default: true)

**Events:**
- `on:close` - Fired when dropdown should close
- `on:select` - Fired when item is selected

**Mobile:** Works as bottom sheet on small screens (can be enhanced)

---

### DropdownItem

Individual item within a dropdown menu.

```svelte
<DropdownItem
  on:click={handleClick}
  disabled={false}
  danger={false}
  active={false}
>
  <Icon />
  <span>Item Label</span>
</DropdownItem>
```

**Props:**
- `disabled?: boolean` - Item is disabled (default: false)
- `danger?: boolean` - Red color variant (default: false)
- `active?: boolean` - Active/selected state (default: false)
- `href?: string` - Optional link (renders as `<a>`)

**Events:**
- `on:click` - Fired when item is clicked

**Keyboard:** Enter and Space trigger click

---

### DropdownDivider

Visual separator between dropdown items.

```svelte
<DropdownDivider />
```

---

### DropdownLabel

Section label for dropdown items.

```svelte
<DropdownLabel label="Recent Items" />

<!-- Or with slot -->
<DropdownLabel>
  <span>Custom Label</span>
</DropdownLabel>
```

---

## Examples

### Confirmation Dialog

```svelte
<script>
  import { Dialog, Button } from '$lib/components/ui';

  export let open = false;
  export let title = 'Confirm Action';
  export let message = 'Are you sure?';
  export let onConfirm: () => void;
  export let onCancel: () => void;
</script>

<Dialog
  {open}
  on:close={onCancel}
  {title}
  size="sm"
>
  <p>{message}</p>

  <div slot="footer">
    <Button variant="outline" on:click={onCancel}>Cancel</Button>
    <Button variant="primary" on:click={onConfirm}>Confirm</Button>
  </div>
</Dialog>
```

### Form Dialog

```svelte
<script>
  import { Dialog, Button, Input } from '$lib/components/ui';

  let open = false;
  let formData = { name: '', email: '' };

  async function handleSubmit() {
    await api.save(formData);
    open = false;
  }
</script>

<Dialog
  bind:open
  title="User Information"
  description="Enter your details below"
  size="md"
>
  <form on:submit|preventDefault={handleSubmit} class="space-y-4">
    <div>
      <label for="name">Name</label>
      <Input id="name" bind:value={formData.name} required />
    </div>

    <div>
      <label for="email">Email</label>
      <Input id="email" type="email" bind:value={formData.email} required />
    </div>
  </form>

  <div slot="footer">
    <Button variant="outline" on:click={() => open = false}>Cancel</Button>
    <Button on:click={handleSubmit}>Save</Button>
  </div>
</Dialog>
```

### Settings Sidebar

```svelte
<script>
  import { Sidebar, Button } from '$lib/components/ui';

  let showSettings = false;
  let settings = { theme: 'light', notifications: true };
</script>

<Sidebar
  bind:open={showSettings}
  position="right"
  size="500px"
  title="Settings"
>
  <div class="space-y-6">
    <div>
      <h4 class="font-medium mb-2">Appearance</h4>
      <select bind:value={settings.theme} class="w-full">
        <option value="light">Light</option>
        <option value="dark">Dark</option>
      </select>
    </div>

    <div>
      <h4 class="font-medium mb-2">Notifications</h4>
      <label class="flex items-center gap-2">
        <input type="checkbox" bind:checked={settings.notifications} />
        <span>Enable notifications</span>
      </label>
    </div>
  </div>

  <div slot="footer" class="border-t pt-4">
    <Button on:click={saveSettings}>Save Changes</Button>
  </div>
</Sidebar>
```

### Multi-level Dropdown

```svelte
<script>
  import { Dropdown, DropdownItem, DropdownDivider, DropdownLabel } from '$lib/components/ui';

  let triggerRef: HTMLElement;
  let open = false;
  let selectedHost = null;
</script>

<button bind:this={triggerRef} on:click={() => open = !open}>
  {selectedHost?.name || 'Select Host'}
</button>

<Dropdown bind:open {triggerRef} width="trigger">
  <DropdownLabel>Available Hosts</DropdownLabel>

  {#each hosts as host}
    <DropdownItem
      active={selectedHost === host}
      on:click={() => selectedHost = host}
    >
      <Server class="w-4 h-4" />
      <div class="flex-1">
        <div class="font-medium">{host.name}</div>
        <div class="text-xs text-gray-500">{host.hostname}</div>
      </div>
      {#if selectedHost === host}
        <Check class="w-4 h-4" />
      {/if}
    </DropdownItem>
  {/each}

  <DropdownDivider />

  <DropdownItem on:click={addNewHost}>
    <Plus class="w-4 h-4" />
    <span>Add New Host</span>
  </DropdownItem>
</Dropdown>
```

---

## Accessibility Features

All components include:

- ✅ **Keyboard Navigation**: Tab, Escape, Enter, Arrow keys
- ✅ **Focus Management**: Focus trap, restore focus on close
- ✅ **ARIA Attributes**: Proper roles, labels, and states
- ✅ **Screen Reader Support**: Announced state changes
- ✅ **High Contrast**: Works with system themes
- ✅ **Keyboard-only Navigation**: No mouse required

---

## Best Practices

1. **Always bind the `open` prop** for two-way state management:
   ```svelte
   <Dialog bind:open={showDialog}>
   ```

2. **Use `on:close` for cleanup**:
   ```svelte
   <Dialog on:close={() => { resetForm(); showDialog = false; }}>
   ```

3. **Provide triggerRef for dropdowns**:
   ```svelte
   <button bind:this={triggerRef}>...</button>
   <Dropdown {triggerRef} ...>
   ```

4. **Use appropriate sizes**:
   - Small dialogs: `size="sm"` for confirmations
   - Medium: `size="md"` for forms (default)
   - Large: `size="lg"` for complex content
   - Full: `size="full"` for editors

5. **Add loading states**:
   ```svelte
   <Dialog>
     {#if loading}
       <LoadingSpinner />
     {:else}
       <!-- Content -->
     {/if}
   </Dialog>
   ```

6. **Handle errors gracefully**:
   ```svelte
   <Dialog>
     {#if error}
       <Alert variant="error">{error}</Alert>
     {/if}
     <!-- Form -->
   </Dialog>
   ```

---

## Migration Guide

### From old clickOutside to new components

**Before:**
```svelte
<div use:clickOutside on:click_outside={close}>
  <div class="modal">...</div>
</div>
```

**After:**
```svelte
<Dialog bind:open={isOpen}>
  ...
</Dialog>
```

### From manual dropdowns to Dropdown component

**Before:**
```svelte
<div class="dropdown-container">
  <button on:click={() => showDropdown = !showDropdown}>Toggle</button>
  {#if showDropdown}
    <div class="dropdown" on:click|stopPropagation>
      <button on:click={select1}>Option 1</button>
      <button on:click={select2}>Option 2</button>
    </div>
  {/if}
</div>
```

**After:**
```svelte
<button bind:this={triggerRef} on:click={() => open = !open}>Toggle</button>
<Dropdown bind:open {triggerRef}>
  <DropdownItem on:click={select1}>Option 1</DropdownItem>
  <DropdownItem on:click={select2}>Option 2</DropdownItem>
</Dropdown>
```

---

## Performance Tips

1. **Lazy load dialog content**:
   ```svelte
   <Dialog bind:open>
     {#if open}
       <ExpensiveContent />
     {/if}
   </Dialog>
   ```

2. **Use transitions wisely**: Default transitions are optimized

3. **Avoid nested overlays**: Stack multiple dialogs carefully

4. **Portal to body**: Automatically handled for z-index management

---

## Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
- Mobile browsers (iOS Safari, Chrome Android)

---

## Related Documentation

- [Actions README](../../actions/README.md) - Core Svelte actions
- [plan.md](/plan.md) - Full implementation plan
- [CLAUDE.md](/CLAUDE.md) - Project overview