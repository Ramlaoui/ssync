<script lang="ts">
  interface Props {
    label?: string;
    children?: import('svelte').Snippet;
  }

  let { label = '', children }: Props = $props();
</script>

<div class="dropdown-label" role="presentation">
  {#if children}{@render children()}{:else}{label}{/if}
</div>

<style>
  .dropdown-label {
    padding: 0.5rem 1rem 0.25rem;
    font-size: 0.75rem;
    font-weight: 600;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
</style>