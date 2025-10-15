<script lang="ts">
  import { cn } from "../../utils";
  
  interface Props {
    class?: string;
    [key: string]: any
  }

  let { class: className = "", ...rest }: Props = $props();
  
</script>

<div
  class={cn("animate-pulse rounded-md bg-muted", className)}
  {...rest}
></div>