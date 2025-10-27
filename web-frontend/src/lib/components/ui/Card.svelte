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
    default: "bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700",
    glass: "bg-white/80 dark:bg-gray-800/80 backdrop-blur-sm border border-gray-200 dark:border-gray-700",
    gradient: "bg-gradient-to-br from-white to-gray-50 dark:from-gray-800 dark:to-gray-900 border border-gray-200 dark:border-gray-700",
    bordered: "bg-transparent border border-gray-300 dark:border-gray-600",
    elevated: "bg-white dark:bg-gray-800 shadow-sm hover:shadow-md"
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