<script lang="ts">
  import { cn } from "../../utils";
  
  interface Props {
    variant?: "default" | "secondary" | "destructive" | "outline" | "success" | "warning";
    class?: string;
    children?: import('svelte').Snippet;
    [key: string]: any
  }

  let { variant = "default", class: className = "", children, ...rest }: Props = $props();
  
  
  const variants = {
    default: "bg-primary text-primary-foreground hover:bg-primary/80",
    secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
    destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/80",
    outline: "text-foreground border border-input",
    success: "badge-success",
    warning: "badge-warning"
  };
</script>

<div
  class={cn(
    "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
    variants[variant],
    className
  )}
  {...rest}
>
  {@render children?.()}
</div>

<style>
  :global(.badge-success) {
    background: var(--success-bg);
    color: var(--success);
  }

  :global(.badge-warning) {
    background: var(--warning-bg);
    color: var(--warning);
  }
</style>