<script lang="ts">
  import { cn } from "../../utils";
  
  export let className: string = "";
  export { className as class };
  export let hover: boolean = false;
  export let noPadding: boolean = false;
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
  {...$$restProps}
>
  <slot />
</div>