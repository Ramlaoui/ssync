<script lang="ts">
  import { cn } from "../../utils";
  
  export let variant: "default" | "secondary" | "destructive" | "outline" | "success" | "warning" = "default";
  export let className: string = "";
  export { className as class };
  
  const variants = {
    default: "bg-primary text-primary-foreground hover:bg-primary/80",
    secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
    destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/80",
    outline: "text-foreground border border-input",
    success: "bg-green-100 text-green-800 dark:bg-green-900/20 dark:text-green-400",
    warning: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-400"
  };
</script>

<div
  class={cn(
    "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
    variants[variant],
    className
  )}
  {...$$restProps}
>
  <slot />
</div>