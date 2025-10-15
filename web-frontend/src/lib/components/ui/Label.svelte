<script lang="ts">
  import { cn } from "../../utils";
  import type { HTMLLabelAttributes } from "svelte/elements";
  
  type $$Props = HTMLLabelAttributes & {
    class?: string;
  };
  
  interface Props {
    class?: string;
    children?: import('svelte').Snippet;
    [key: string]: any
  }

  let { class: className = "", children, ...rest }: Props = $props();
  
</script>

<label
  {...rest}
  class={cn(
    "text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70",
    className
  )}
>
  {@render children?.()}
</label>