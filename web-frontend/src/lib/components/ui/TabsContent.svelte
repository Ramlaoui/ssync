<script lang="ts">
  import { cn } from "../../utils";
  import { getContext } from "svelte";
  
  export let value: string;
  export let className: string = "";
  export { className as class };
  
  const activeValue = getContext<string>("activeTab");
</script>

{#if activeValue === value}
  <div
    class={cn(
      "mt-2 ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
      className
    )}
    {...$$restProps}
  >
    <slot />
  </div>
{/if}