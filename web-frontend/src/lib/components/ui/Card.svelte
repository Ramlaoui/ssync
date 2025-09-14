<script lang="ts">
  import { cn } from "../../utils";
  
  export let className: string = "";
  export { className as class };
  export let variant: 'default' | 'glass' | 'gradient' | 'bordered' | 'elevated' = 'default';
  export let hover: boolean = false;
  export let noPadding: boolean = false;
  
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
  {...$$restProps}
>
  <slot />
</div>