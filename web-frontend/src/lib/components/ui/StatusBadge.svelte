<script lang="ts">
  import { cn } from "../../utils";
  import Badge from "./Badge.svelte";
  
  export let status: string;
  export let className: string = "";
  export { className as class };
  
  const statusConfig: Record<string, { label: string; variant: string; icon: string; pulse: boolean }> = {
    'R': { label: 'Running', variant: 'success', icon: '●', pulse: true },
    'PD': { label: 'Pending', variant: 'warning', icon: '◐', pulse: false },
    'CD': { label: 'Completed', variant: 'default', icon: '✓', pulse: false },
    'F': { label: 'Failed', variant: 'destructive', icon: '✕', pulse: false },
    'CA': { label: 'Cancelled', variant: 'secondary', icon: '⊘', pulse: false },
    'TO': { label: 'Timeout', variant: 'destructive', icon: '⏱', pulse: false },
  };
  
  $: config = statusConfig[status] || { label: status, variant: 'default', icon: '?', pulse: false };
</script>

<Badge 
  variant={config.variant}
  class={cn(
    "inline-flex items-center gap-1.5 font-medium",
    config.pulse && "animate-pulse",
    className
  )}
>
  <span class={cn(
    "text-xs",
    config.pulse && "animate-pulse"
  )}>
    {config.icon}
  </span>
  {config.label}
</Badge>