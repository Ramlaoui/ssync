<script lang="ts" generics="T">
  import Dialog from './Dialog.svelte';
  import { createEventDispatcher } from 'svelte';

  const dispatch = createEventDispatcher<{
    select: T | T[] | null;
    cancel: void;
  }>();

  interface Props {
    // All Dialog props
    open?: boolean;
    title?: string;
    description?: string;
    size?: 'sm' | 'md' | 'lg' | 'xl' | 'full';
    closeOnBackdropClick?: boolean;
    closeOnEscape?: boolean;
    // Selection-specific props
    items?: T[];
    selected?: T | T[] | null;
    multiSelect?: boolean;
    searchable?: boolean;
    searchPlaceholder?: string;
    emptyMessage?: string;
    confirmText?: string;
    cancelText?: string;
    // Item rendering functions
    getItemId?: (item: T) => string | number;
    getItemLabel?: (item: T) => string;
    getItemDescription?: ((item: T) => string | null) | null;
    renderItem?: ((item: T) => any) | null;
  }

  let {
    open = $bindable(false),
    title = 'Select Items',
    description = '',
    size = 'md',
    closeOnBackdropClick = true,
    closeOnEscape = true,
    items = [],
    selected = null,
    multiSelect = false,
    searchable = false,
    searchPlaceholder = 'Search...',
    emptyMessage = 'No items available',
    confirmText = 'Select',
    cancelText = 'Cancel',
    getItemId = (item: any) => item.id ?? item,
    getItemLabel = (item: any) => item.label ?? item.name ?? String(item),
    getItemDescription = null,
    renderItem = null
  }: Props = $props();

  // Internal state
  let searchQuery = $state('');
  let internalSelected: Set<string | number> = $state(new Set());

  // Initialize internal selection state
  $effect(() => {
    internalSelected = new Set();
    if (selected) {
      if (Array.isArray(selected)) {
        selected.forEach(item => internalSelected.add(getItemId(item)));
      } else {
        internalSelected.add(getItemId(selected));
      }
    }
  });

  // Filter items based on search
  let filteredItems = $derived(searchable && searchQuery.trim()
    ? items.filter(item => {
        const label = getItemLabel(item).toLowerCase();
        const description = getItemDescription?.(item)?.toLowerCase() ?? '';
        const query = searchQuery.toLowerCase();
        return label.includes(query) || description.includes(query);
      })
    : items);

  function handleClose() {
    open = false;
    dispatch('cancel');
  }

  function toggleItem(item: T) {
    const itemId = getItemId(item);

    if (multiSelect) {
      if (internalSelected.has(itemId)) {
        internalSelected.delete(itemId);
      } else {
        internalSelected.add(itemId);
      }
      internalSelected = new Set(internalSelected); // Trigger reactivity
    } else {
      internalSelected = new Set([itemId]);
    }
  }

  function isSelected(item: T): boolean {
    return internalSelected.has(getItemId(item));
  }

  function handleConfirm() {
    const selectedItems = items.filter(item => internalSelected.has(getItemId(item)));

    if (multiSelect) {
      dispatch('select', selectedItems);
    } else {
      dispatch('select', selectedItems[0] ?? null);
    }

    open = false;
  }

  function handleItemClick(item: T) {
    toggleItem(item);

    // In single-select mode, auto-confirm on selection
    if (!multiSelect) {
      handleConfirm();
    }
  }
</script>

{#snippet selectionFooter()}
  {#if multiSelect}
    <div class="selection-footer">
      <div class="selection-count">
        {internalSelected.size} selected
      </div>
      <div class="actions">
        <button
          type="button"
          class="action-btn secondary"
          onclick={handleClose}
        >
          {cancelText}
        </button>
        <button
          type="button"
          class="action-btn primary"
          onclick={handleConfirm}
          disabled={internalSelected.size === 0}
        >
          {confirmText}
        </button>
      </div>
    </div>
  {/if}
{/snippet}

<Dialog
  bind:open
  {title}
  {description}
  {size}
  {closeOnBackdropClick}
  {closeOnEscape}
  on:close={handleClose}
  footer={selectionFooter}
>
  {#if searchable}
    <div class="search-container">
      <svg class="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
        <circle cx="11" cy="11" r="8" stroke-width="2" />
        <path d="m21 21-4.35-4.35" stroke-width="2" stroke-linecap="round" />
      </svg>
      <input
        type="text"
        class="search-input"
        placeholder={searchPlaceholder}
        bind:value={searchQuery}
      />
      {#if searchQuery}
        <button
          class="clear-button"
          onclick={() => searchQuery = ''}
          aria-label="Clear search"
        >
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z" />
          </svg>
        </button>
      {/if}
    </div>
  {/if}

  <div class="items-container">
    {#if filteredItems.length === 0}
      <div class="empty-state">
        <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
          <circle cx="12" cy="12" r="10" stroke-width="2" />
          <path d="M12 8v4m0 4h.01" stroke-width="2" stroke-linecap="round" />
        </svg>
        <p>{searchQuery ? 'No items match your search' : emptyMessage}</p>
      </div>
    {:else}
      {#each filteredItems as item (getItemId(item))}
        <button
          class="item"
          class:selected={isSelected(item)}
          onclick={() => handleItemClick(item)}
        >
          {#if multiSelect}
            <div class="checkbox" class:checked={isSelected(item)}>
              {#if isSelected(item)}
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z" />
                </svg>
              {/if}
            </div>
          {/if}

          <div class="item-content">
            {#if renderItem}
              {@html renderItem(item)}
            {:else}
              <div class="item-label">{getItemLabel(item)}</div>
              {#if getItemDescription}
                {@const desc = getItemDescription(item)}
                {#if desc}
                  <div class="item-description">{desc}</div>
                {/if}
              {/if}
            {/if}
          </div>

          {#if !multiSelect && isSelected(item)}
            <svg class="check-icon" viewBox="0 0 24 24" fill="currentColor">
              <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z" />
            </svg>
          {/if}
        </button>
      {/each}
    {/if}
  </div>
</Dialog>

<style>
  .search-container {
    position: relative;
    margin-bottom: 1rem;
  }

  .search-icon {
    position: absolute;
    left: 0.75rem;
    top: 50%;
    transform: translateY(-50%);
    width: 18px;
    height: 18px;
    color: #9ca3af;
    pointer-events: none;
  }

  .search-input {
    width: 100%;
    padding: 0.625rem 2.5rem 0.625rem 2.5rem;
    border: 1px solid #d1d5db;
    border-radius: 8px;
    font-size: 0.875rem;
    transition: all 0.2s ease;
  }

  .search-input:focus {
    outline: none;
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  .clear-button {
    position: absolute;
    right: 0.5rem;
    top: 50%;
    transform: translateY(-50%);
    padding: 0.25rem;
    border: none;
    background: transparent;
    border-radius: 4px;
    color: #9ca3af;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;
  }

  .clear-button:hover {
    background: #f3f4f6;
    color: #6b7280;
  }

  .clear-button svg {
    width: 16px;
    height: 16px;
  }

  .items-container {
    max-height: 400px;
    overflow-y: auto;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
  }

  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 3rem 1rem;
    color: #9ca3af;
  }

  .empty-icon {
    width: 48px;
    height: 48px;
    margin-bottom: 0.75rem;
  }

  .empty-state p {
    margin: 0;
    font-size: 0.875rem;
  }

  .item {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    width: 100%;
    padding: 0.75rem 1rem;
    border: none;
    border-bottom: 1px solid #e5e7eb;
    background: white;
    cursor: pointer;
    text-align: left;
    transition: all 0.15s ease;
  }

  .item:last-child {
    border-bottom: none;
  }

  .item:hover {
    background: #f9fafb;
  }

  .item.selected {
    background: #eff6ff;
  }

  .checkbox {
    flex-shrink: 0;
    width: 20px;
    height: 20px;
    border: 2px solid #d1d5db;
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.15s ease;
  }

  .checkbox.checked {
    background: #3b82f6;
    border-color: #3b82f6;
    color: white;
  }

  .checkbox svg {
    width: 14px;
    height: 14px;
  }

  .item-content {
    flex: 1;
    min-width: 0;
  }

  .item-label {
    font-size: 0.875rem;
    font-weight: 500;
    color: #374151;
  }

  .item-description {
    font-size: 0.75rem;
    color: #6b7280;
    margin-top: 0.125rem;
  }

  .check-icon {
    flex-shrink: 0;
    width: 20px;
    height: 20px;
    color: #3b82f6;
  }

  .selection-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
  }

  .selection-count {
    font-size: 0.875rem;
    color: #6b7280;
    font-weight: 500;
  }

  .actions {
    display: flex;
    gap: 0.75rem;
  }

  .action-btn {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.625rem 1.25rem;
    border-radius: 8px;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
    border: none;
    min-width: 80px;
    justify-content: center;
  }

  .action-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .action-btn.secondary {
    background: #f3f4f6;
    color: #374151;
    border: 1px solid #d1d5db;
  }

  .action-btn.secondary:hover:not(:disabled) {
    background: #e5e7eb;
    transform: translateY(-1px);
  }

  .action-btn.primary {
    background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
    color: white;
    box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3);
  }

  .action-btn.primary:hover:not(:disabled) {
    background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
    transform: translateY(-1px);
    box-shadow: 0 4px 16px rgba(59, 130, 246, 0.4);
  }

  /* Mobile responsive */
  @media (max-width: 640px) {
    .items-container {
      max-height: 300px;
    }

    .selection-footer {
      flex-direction: column;
      align-items: stretch;
    }

    .actions {
      flex-direction: column;
    }

    .action-btn {
      width: 100%;
    }
  }
</style>
