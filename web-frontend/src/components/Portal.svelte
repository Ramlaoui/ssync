<script lang="ts">
  import { onMount, onDestroy, tick } from 'svelte';
  
  let targetEl: HTMLElement;
  let contentEl: HTMLElement;
  
  onMount(async () => {
    // Create portal target
    targetEl = document.createElement('div');
    targetEl.className = 'svelte-portal';
    targetEl.style.position = 'fixed';
    targetEl.style.top = '0';
    targetEl.style.left = '0';
    targetEl.style.zIndex = '99999';
    targetEl.style.pointerEvents = 'none';
    
    document.body.appendChild(targetEl);
    
    // Wait for next tick to ensure content is ready
    await tick();
    
    // Move content to portal
    if (contentEl && targetEl) {
      targetEl.appendChild(contentEl);
      targetEl.style.pointerEvents = 'auto';
    }
  });
  
  onDestroy(() => {
    if (targetEl && targetEl.parentNode) {
      targetEl.parentNode.removeChild(targetEl);
    }
  });
</script>

<div bind:this={contentEl} style="display: contents;">
  <slot />
</div>