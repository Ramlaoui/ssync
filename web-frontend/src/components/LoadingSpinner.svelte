<script lang="ts">
  export let size: 'sm' | 'md' | 'lg' = 'md';
  export let message: string = 'Loading...';
  export let centered: boolean = true;
  export let showMessage: boolean = true;
  export let variant: 'default' | 'primary' | 'white' | 'small' = 'default';

  $: sizeClass = {
    sm: 'w-4 h-4',
    md: 'w-8 h-8',
    lg: 'w-12 h-12'
  }[size];

  // Use consistent gray spinner like the job page
  $: colorClass = variant === 'white'
    ? 'border-white border-b-white/30'
    : variant === 'primary'
    ? 'border-blue-600 border-b-transparent'
    : variant === 'small'
    ? 'border-gray-300 border-t-blue-600'
    : 'border-gray-900 border-b-transparent';

  $: textClass = variant === 'white' ? 'text-white' : 'text-gray-500';

  $: spacingClass = {
    sm: 'mb-2',
    md: 'mb-4',
    lg: 'mb-6'
  }[size];
</script>

{#if centered}
  <div class="flex-1 flex items-center justify-center">
    <div class="text-center">
      <div
        class="rounded-full animate-spin {sizeClass} {colorClass} mx-auto {showMessage ? spacingClass : ''}"
        style="border-width: 2px;"
        aria-label={message}
      ></div>
      {#if showMessage && message}
        <p class="{textClass} {size === 'sm' ? 'text-sm' : size === 'lg' ? 'text-lg' : 'text-base'}">{message}</p>
      {/if}
    </div>
  </div>
{:else}
  <div class="flex items-center gap-3">
    <div
      class="rounded-full animate-spin {sizeClass} {colorClass}"
      style="border-width: 2px;"
      aria-label={message}
    ></div>
    {#if showMessage && message}
      <span class="{textClass} {size === 'sm' ? 'text-sm' : size === 'lg' ? 'text-lg' : 'text-base'} font-medium">
        {message}
      </span>
    {/if}
  </div>
{/if}