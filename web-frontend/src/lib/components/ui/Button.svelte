<script lang="ts">
  import { createBubbler } from 'svelte/legacy';

  const bubble = createBubbler();
  import { cn } from "../../cn";
  import type { HTMLButtonAttributes } from "svelte/elements";
  
  type $$Props = HTMLButtonAttributes & {
    variant?: "default" | "destructive" | "outline" | "secondary" | "ghost" | "link" | "gradient" | "glass";
    size?: "default" | "sm" | "lg" | "icon";
    class?: string;
    loading?: boolean;
  };
  
  interface Props {
    variant?: $$Props["variant"];
    size?: $$Props["size"];
    loading?: boolean;
    class?: string;
    children?: import('svelte').Snippet;
    [key: string]: any
  }

  let {
    variant = "default",
    size = "default",
    loading = false,
    class: className = "",
    children,
    ...rest
  }: Props = $props();
  
  
  const variants = {
    default: "bg-black text-white hover:bg-gray-800",
    destructive: "bg-red-500 text-white hover:bg-red-600",
    outline: "border border-gray-300 bg-white text-black hover:bg-gray-50",
    secondary: "bg-gray-100 text-black hover:bg-gray-200",
    ghost: "hover:bg-gray-100 text-gray-600 hover:text-black",
    link: "text-black underline-offset-4 hover:underline",
    gradient: "bg-gradient-to-r from-blue-500 to-purple-600 text-white hover:from-blue-600 hover:to-purple-700",
    glass: "bg-white/10 backdrop-blur-md border border-gray-200 text-black hover:bg-white/20",
  };
  
  const sizes = {
    default: "h-10 px-4 py-2",
    sm: "h-9 rounded-md px-3",
    lg: "h-11 rounded-md px-8",
    icon: "h-10 w-10",
  };
</script>

<button
  {...rest}
  class={cn(
    "inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-black disabled:pointer-events-none disabled:opacity-40",
    variant ? variants[variant] : '',
    size ? sizes[size] : '',
    loading && "cursor-wait opacity-70",
    className
  )}
  disabled={loading || rest.disabled}
  onclick={bubble('click')}
  onmouseenter={bubble('mouseenter')}
  onmouseleave={bubble('mouseleave')}
  onfocus={bubble('focus')}
  onblur={bubble('blur')}
>
  {#if loading}
    <svg class="animate-spin -ml-1 mr-2 h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
    </svg>
  {/if}
  {@render children?.()}
</button>