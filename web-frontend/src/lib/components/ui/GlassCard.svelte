<script lang="ts">
  import { cn } from "../../utils";
  import Card from "./Card.svelte";
  
  export let className: string = "";
  export { className as class };
  export let hover: boolean = false;
  export let noPadding: boolean = false;
  export let blur: 'sm' | 'md' | 'lg' | 'xl' = 'lg';
  
  const blurLevels = {
    sm: 'backdrop-blur-sm',
    md: 'backdrop-blur-md', 
    lg: 'backdrop-blur-lg',
    xl: 'backdrop-blur-xl'
  };
</script>

<div class="relative">
  <div class="absolute inset-0 bg-gradient-to-r from-blue-400/10 via-purple-400/10 to-pink-400/10 rounded-xl blur-2xl" />
  <Card 
    variant="glass" 
    {hover} 
    {noPadding}
    class={cn(blurLevels[blur], "relative", className)}
    {...$$restProps}
  >
    <slot />
  </Card>
</div>