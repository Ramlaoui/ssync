<script lang="ts">
  import { cn } from "../../utils";
  
  export let className: string = "";
  export { className as class };
</script>

<div
  class={cn("animate-pulse rounded-md bg-muted", className)}
  {...$$restProps}
/>