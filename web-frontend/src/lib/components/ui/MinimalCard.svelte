<script lang="ts">
  import { cn } from "../../utils";
  
  
  interface Props {
    class?: string;
    hover?: boolean;
    noPadding?: boolean;
    children?: import('svelte').Snippet;
    [key: string]: any
  }

  let {
    class: className = "",
    hover = false,
    noPadding = false,
    children,
    ...rest
  }: Props = $props();
</script>

<div
  class={cn(
    "bg-white rounded-md border border-gray-200",
    {
      'hover:border-gray-300 transition-colors duration-150 cursor-pointer': hover,
      'p-4': !noPadding,
    },
    className
  )}
  {...rest}
>
  {@render children?.()}
</div>