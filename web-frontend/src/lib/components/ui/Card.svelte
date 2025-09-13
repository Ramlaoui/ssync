<script lang="ts">
  import { cn } from "../../utils";
  
  export let className: string = "";
  export { className as class };
</script>

<div
  class={cn(
    "rounded-lg border bg-card text-card-foreground shadow-sm",
    className
  )}
  {...$$restProps}
>
  <slot />
</div>