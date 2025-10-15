<script lang="ts">
  import { cn } from "../../utils";
  
  interface Props {
    orientation?: "horizontal" | "vertical";
    class?: string;
    [key: string]: any
  }

  let { orientation = "horizontal", class: className = "", ...rest }: Props = $props();
  
</script>

<div
  class={cn(
    "shrink-0 bg-border",
    orientation === "horizontal" ? "h-[1px] w-full" : "h-full w-[1px]",
    className
  )}
  {...rest}
></div>