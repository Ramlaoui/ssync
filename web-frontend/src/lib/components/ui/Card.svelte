<script lang="ts">
  import { cn } from "../../cn";
  
  
  interface Props {
    class?: string;
    variant?: 'default' | 'glass' | 'gradient' | 'bordered' | 'elevated';
    hover?: boolean;
    noPadding?: boolean;
    children?: import('svelte').Snippet;
    [key: string]: any
  }

  let {
    class: className = "",
    variant = 'default',
    hover = false,
    noPadding = false,
    children,
    ...rest
  }: Props = $props();
  
  const variants = {
    default: "bg-[var(--card)] border border-[var(--border)]",
    glass: "bg-[var(--card)]/80 backdrop-blur-sm border border-[var(--border)]",
    gradient: "bg-gradient-to-br from-[var(--card)] to-[var(--secondary)] border border-[var(--border)]",
    bordered: "bg-transparent border border-[var(--border)]",
    elevated: "bg-[var(--card)] shadow-sm hover:shadow-md"
  };
</script>

<div
  class={cn(
    "rounded-lg transition-shadow duration-200",
    variants[variant],
    {
      'hover:shadow-md cursor-pointer': hover,
      'p-4': !noPadding,
    },
    className
  )}
  {...rest}
>
  {@render children?.()}
</div>