<script lang="ts">
  import { cn } from "../../utils";
  import Card from "./Card.svelte";
  
  
  interface Props {
    class?: string;
    hover?: boolean;
    noPadding?: boolean;
    blur?: 'sm' | 'md' | 'lg' | 'xl';
    children?: import('svelte').Snippet;
    [key: string]: any
  }

  let {
    class: className = "",
    hover = false,
    noPadding = false,
    blur = 'lg',
    children,
    ...rest
  }: Props = $props();
  
  const blurLevels = {
    sm: 'backdrop-blur-sm',
    md: 'backdrop-blur-md', 
    lg: 'backdrop-blur-lg',
    xl: 'backdrop-blur-xl'
  };
</script>

<div class="relative">
  <div class="absolute inset-0 bg-gradient-to-r from-blue-400/10 via-purple-400/10 to-pink-400/10 rounded-xl blur-2xl"></div>
  <Card 
    variant="glass" 
    {hover} 
    {noPadding}
    class={cn(blurLevels[blur], "relative", className)}
    {...rest}
  >
    {@render children?.()}
  </Card>
</div>