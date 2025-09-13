<script lang="ts">
  import { cn } from "../../utils";
  
  export let className: string = "";
  export { className as class };
</script>

<div class={cn("relative overflow-hidden", className)} {...$$restProps}>
  <div class="h-full w-full rounded-[inherit] overflow-auto scrollbar-thin scrollbar-track-transparent scrollbar-thumb-border hover:scrollbar-thumb-border/80">
    <slot />
  </div>
</div>