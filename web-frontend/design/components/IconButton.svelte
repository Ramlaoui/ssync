<script lang="ts">
  import Icon from './Icon.svelte';
  let { icon, label, onclick, size = 18, disabled = false }:
    { icon: string; label: string; onclick: () => void; size?: number; disabled?: boolean } = $props();
</script>

<button type="button" class="icon-button" aria-label={label} title={label} {onclick} {disabled}>
  <Icon name={icon} {size} />
</button>
