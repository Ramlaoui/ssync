<script lang="ts">
  import { X, Loader2, CheckCircle2, XCircle } from 'lucide-svelte';

  interface Props {
    status: 'launching' | 'success' | 'error';
    message?: string;
    onDismiss: () => void;
    onNavigate?: () => void;
  }

  let { status, message = '', onDismiss, onNavigate }: Props = $props();

  const statusConfig = {
    launching: {
      icon: Loader2,
      iconClass: 'animate-spin text-blue-500',
      bgClass: 'bg-blue-50 dark:bg-blue-950/30 border-blue-200 dark:border-blue-800',
      textClass: 'text-blue-900 dark:text-blue-100',
      title: 'Launching Job...'
    },
    success: {
      icon: CheckCircle2,
      iconClass: 'text-green-500',
      bgClass: 'bg-green-50 dark:bg-green-950/30 border-green-200 dark:border-green-800',
      textClass: 'text-green-900 dark:text-green-100',
      title: 'Job Launched Successfully'
    },
    error: {
      icon: XCircle,
      iconClass: 'text-red-500',
      bgClass: 'bg-red-50 dark:bg-red-950/30 border-red-200 dark:border-red-800',
      textClass: 'text-red-900 dark:text-red-100',
      title: 'Launch Failed'
    }
  };

  const config = $derived(statusConfig[status]);
  const Icon = $derived(config.icon);
</script>

<div class="fixed top-4 left-1/2 transform -translate-x-1/2 z-50 w-full max-w-md px-4 animate-slide-down">
  <div class={`relative rounded-lg border shadow-lg p-4 ${config.bgClass}`}>
    <div class="flex items-start gap-3">
      <!-- Icon -->
      <div class="flex-shrink-0 mt-0.5">
        <Icon class={`w-5 h-5 ${config.iconClass}`} />
      </div>

      <!-- Content -->
      <div class="flex-1 min-w-0">
        <h3 class={`text-sm font-semibold ${config.textClass}`}>
          {config.title}
        </h3>
        {#if message}
          <p class={`text-xs mt-1 ${config.textClass} opacity-80`}>
            {message}
          </p>
        {/if}
        {#if status === 'launching'}
          <p class={`text-xs mt-1 ${config.textClass} opacity-70`}>
            You can navigate away - the job will continue launching in the background.
          </p>
        {/if}
        {#if status === 'success' && onNavigate}
          <button
            onclick={onNavigate}
            class="text-xs mt-2 font-medium underline hover:no-underline"
          >
            View Job
          </button>
        {/if}
      </div>

      <!-- Dismiss button -->
      <button
        onclick={onDismiss}
        class={`flex-shrink-0 ${config.textClass} opacity-50 hover:opacity-100 transition-opacity`}
        aria-label="Dismiss"
      >
        <X class="w-4 h-4" />
      </button>
    </div>
  </div>
</div>

<style>
  @keyframes slide-down {
    from {
      opacity: 0;
      transform: translate(-50%, -1rem);
    }
    to {
      opacity: 1;
      transform: translate(-50%, 0);
    }
  }

  .animate-slide-down {
    animation: slide-down 0.3s ease-out;
  }
</style>
