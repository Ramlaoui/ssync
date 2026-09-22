<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  let { value = '' }: { value?: string } = $props();
  const dispatch = createEventDispatcher();
</script>
<textarea aria-label="Batch script" {value} oninput={event => dispatch('change', { content: event.currentTarget.value })}></textarea>
