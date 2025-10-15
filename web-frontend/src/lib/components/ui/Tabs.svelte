<script lang="ts">
  import { cn } from "../../utils";
  import { createEventDispatcher } from "svelte";
  
  interface Props {
    value: string;
    class?: string;
    children?: import('svelte').Snippet<[any]>;
    [key: string]: any
  }

  let { value = $bindable(), class: className = "", children, ...rest }: Props = $props();
  
  
  const dispatch = createEventDispatcher();
  
  export function changeTab(newValue: string) {
    value = newValue;
    dispatch("change", newValue);
  }
</script>

<div
  class={cn("w-full", className)}
  {...rest}
>
  {@render children?.({ value, changeTab, })}
</div>