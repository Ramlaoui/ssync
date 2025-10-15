<script lang="ts">
  import { cn } from "../../utils";
  
  interface Props {
    class?: string;
    children?: import('svelte').Snippet;
    [key: string]: any
  }

  let { class: className = "", children, ...rest }: Props = $props();
  
</script>

<div class={cn("relative overflow-hidden", className)} {...rest}>
  <div class="h-full w-full rounded-[inherit] overflow-auto scrollbar-thin scrollbar-track-transparent scrollbar-thumb-border hover:scrollbar-thumb-border/80">
    {@render children?.()}
  </div>
</div>