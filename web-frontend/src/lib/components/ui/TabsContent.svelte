<script lang="ts">
  import { cn } from "../../utils";
  import { getContext } from "svelte";
  
  interface Props {
    value: string;
    class?: string;
    children?: import('svelte').Snippet;
    [key: string]: any
  }

  let { value, class: className = "", children, ...rest }: Props = $props();
  
  
  const activeValue = getContext<string>("activeTab");
</script>

{#if activeValue === value}
  <div
    class={cn(
      "mt-2 ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
      className
    )}
    {...rest}
  >
    {@render children?.()}
  </div>
{/if}