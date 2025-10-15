<script lang="ts">
  import { createBubbler } from 'svelte/legacy';

  const bubble = createBubbler();
  import { cn } from "../../cn";
  import type { HTMLSelectAttributes } from "svelte/elements";
  
  type $$Props = HTMLSelectAttributes & {
    class?: string;
  };
  
  
  interface Props {
    class?: string;
    value?: $$Props["value"];
    children?: import('svelte').Snippet;
    [key: string]: any
  }

  let { class: className = "", value = $bindable(""), children, ...rest }: Props = $props();
</script>

<select
  {...rest}
  bind:value
  class={cn(
    "flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
    className
  )}
  onchange={bubble('change')}
  onfocus={bubble('focus')}
  onblur={bubble('blur')}
>
  {@render children?.()}
</select>