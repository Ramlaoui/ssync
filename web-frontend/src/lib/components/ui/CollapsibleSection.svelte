<!-- @migration-task Error while migrating Svelte code: This migration would change the name of a slot (header-actions to header_actions) making the component unusable -->
<script lang="ts">
  import { ChevronDown, ChevronRight } from 'lucide-svelte';
  import { onMount } from 'svelte';
  import { slide } from 'svelte/transition';

  export let title: string;
  export let subtitle: string = '';
  export let badge: string = '';
  export let defaultExpanded: boolean = true;
  export let storageKey: string = '';
  export let onToggle: ((expanded: boolean) => void) | null = null;

  let expanded = defaultExpanded;

  // Load state from sessionStorage if key provided
  onMount(() => {
    if (storageKey && typeof window !== 'undefined') {
      const stored = sessionStorage.getItem(storageKey);
      if (stored !== null) {
        expanded = stored === 'true';
      }
    }
  });

  function toggle() {
    expanded = !expanded;

    // Save to sessionStorage if key provided
    if (storageKey && typeof window !== 'undefined') {
      sessionStorage.setItem(storageKey, String(expanded));
    }

    // Call callback if provided
    if (onToggle) {
      onToggle(expanded);
    }
  }

  // Allow external control via defaultExpanded changes
  $: if (defaultExpanded !== undefined) {
    expanded = defaultExpanded;
  }
</script>

<div class="collapsible-section">
  <button
    class="section-header"
    on:click={toggle}
    aria-expanded={expanded}
    aria-label="{expanded ? 'Collapse' : 'Expand'} {title}"
  >
    <div class="header-left">
      <div class="chevron" class:expanded>
        {#if expanded}
          <ChevronDown size={18} />
        {:else}
          <ChevronRight size={18} />
        {/if}
      </div>
      <h4 class="title">{title}</h4>
      {#if badge}
        <span class="badge">{badge}</span>
      {/if}
    </div>

    {#if subtitle}
      <span class="subtitle">{subtitle}</span>
    {/if}

    <!-- Allow custom header content via slot -->
    <slot name="header-actions" />
  </button>

  {#if expanded}
    <div class="section-content" transition:slide="{{ duration: 200 }}">
      <slot />
    </div>
  {/if}
</div>

<style>
  .collapsible-section {
    margin-bottom: 16px;
  }

  .section-header {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.2s ease;
    text-align: left;
  }

  .section-header:hover {
    background: #f3f4f6;
    border-color: #d1d5db;
  }

  .section-header:active {
    transform: scale(0.99);
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;
  }

  .chevron {
    color: #6b7280;
    display: flex;
    align-items: center;
    transition: transform 0.2s ease;
  }

  .chevron.expanded {
    transform: rotate(0deg);
  }

  .title {
    margin: 0;
    font-size: 14px;
    font-weight: 600;
    color: #374151;
  }

  .badge {
    padding: 2px 8px;
    background: #e5e7eb;
    color: #6b7280;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 500;
  }

  .subtitle {
    font-size: 12px;
    color: #9ca3af;
    margin-right: 8px;
  }

  .section-content {
    padding: 12px 0;
  }

  /* Mobile responsive */
  @media (max-width: 640px) {
    .section-header {
      padding: 10px 12px;
    }

    .title {
      font-size: 13px;
    }

    .subtitle {
      display: none;
    }
  }
</style>
