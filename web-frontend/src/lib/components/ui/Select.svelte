<script lang="ts">
  import { cn } from "../../cn";
  import type { HTMLSelectAttributes } from "svelte/elements";
  
  type $$Props = HTMLSelectAttributes & {
    class?: string;
  };
  
  let className: string = "";
  export { className as class };
  export let value: $$Props["value"] = "";
</script>

<select
  {...$$restProps}
  bind:value
  class={cn(
    "flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
    className
  )}
  on:change
  on:focus
  on:blur
>
  <slot />
</select>