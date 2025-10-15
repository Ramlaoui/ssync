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
    default: "bg-white border border-gray-200",
    glass: "bg-white/80 backdrop-blur-sm border border-gray-200",
    gradient: "bg-gradient-to-br from-white to-gray-50 border border-gray-200",
    bordered: "bg-transparent border border-gray-300",
    elevated: "bg-white shadow-sm hover:shadow-md"
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