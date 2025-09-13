<script lang="ts">
  import { cn } from "../../utils";
  
  export let orientation: "horizontal" | "vertical" = "horizontal";
  export let className: string = "";
  export { className as class };
</script>

<div
  class={cn(
    "shrink-0 bg-border",
    orientation === "horizontal" ? "h-[1px] w-full" : "h-full w-[1px]",
    className
  )}
  {...$$restProps}
/>