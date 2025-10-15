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
  const changeTab = getContext<(value: string) => void>("changeTab");
</script>

<button
  class={cn(
    "inline-flex items-center justify-center whitespace-nowrap rounded-sm px-3 py-1.5 text-sm font-medium ring-offset-background transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
    activeValue === value
      ? "bg-background text-foreground shadow-sm"
      : "text-muted-foreground hover:text-foreground",
    className
  )}
  onclick={() => changeTab(value)}
  {...rest}
>
  {@render children?.()}
</button>