<script lang="ts">
  import type { Snippet } from 'svelte';
  let { label, onclick, disabled = false, children, class: className = '' }: {
    label: string;
    onclick: () => void;
    disabled?: boolean;
    children: Snippet;
    class?: string;
  } = $props();
</script>

<button type="button" class="relay-icon-button {className}" aria-label={label} title={label} {onclick} {disabled}>
  {@render children()}
</button>
