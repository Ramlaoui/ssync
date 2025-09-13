<script lang="ts">
  import { cn } from "../../utils";
  import { createEventDispatcher } from "svelte";
  
  export let value: string;
  export let className: string = "";
  export { className as class };
  
  const dispatch = createEventDispatcher();
  
  export function changeTab(newValue: string) {
    value = newValue;
    dispatch("change", newValue);
  }
</script>

<div
  class={cn("w-full", className)}
  {...$$restProps}
>
  <slot {value} {changeTab} />
</div>