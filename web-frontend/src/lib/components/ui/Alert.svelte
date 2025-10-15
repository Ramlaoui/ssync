<script lang="ts">
  import { cn } from "../../utils";
  
  interface Props {
    variant?: "default" | "destructive";
    class?: string;
    children?: import('svelte').Snippet;
    [key: string]: any
  }

  let { variant = "default", class: className = "", children, ...rest }: Props = $props();
  
  
  const variants = {
    default: "bg-background text-foreground border-border",
    destructive: "border-destructive/50 text-destructive dark:border-destructive [&>svg]:text-destructive"
  };
</script>

<div
  class={cn(
    "relative w-full rounded-lg border p-4 [&>svg~*]:pl-7 [&>svg+div]:translate-y-[-3px] [&>svg]:absolute [&>svg]:left-4 [&>svg]:top-4 [&>svg]:text-foreground",
    variants[variant],
    className
  )}
  role="alert"
  {...rest}
>
  {@render children?.()}
</div>