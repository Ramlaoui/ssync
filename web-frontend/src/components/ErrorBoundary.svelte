<script lang="ts">
  import { onMount, onDestroy } from 'svelte';

  interface Props {
    resetError?: () => void;
    children?: import('svelte').Snippet;
  }

  let { resetError = () => {}, children }: Props = $props();
  
  let hasError = $state(false);
  let errorMessage = $state('');
  let errorInfo = $state('');
  let errorCount = 0;
  let lastErrorTime = 0;
  
  // Set up error handler
  onMount(() => {
    const originalOnError = window.onerror;
    
    window.onerror = (message: string | Event, source?: string, line?: number, column?: number, error?: Error) => {
      // Prevent error loops
      const now = Date.now();
      if (now - lastErrorTime < 100) {
        errorCount++;
        if (errorCount > 10) {
          console.error('Too many errors in succession, stopping error handling');
          return true;
        }
      } else {
        errorCount = 0;
      }
      lastErrorTime = now;
      
      hasError = true;
      errorMessage = typeof message === 'string' ? message : 'An unknown error occurred';
      
      // Better error info formatting
      if (error?.stack) {
        errorInfo = error.stack;
      } else if (source && line) {
        errorInfo = `at ${source}:${line}:${column || 0}`;
      }
      
      // Log to console for debugging
      console.error('ErrorBoundary caught:', { message, source, line, column, error });
      
      if (originalOnError) {
        return originalOnError(message, source, line, column, error);
      }
      
      return true; // Prevent default error handling
    };
    
    // Also handle unhandled promise rejections
    const onUnhandledRejection = (event: PromiseRejectionEvent) => {
      hasError = true;
      errorMessage = event.reason?.message || 'Unhandled Promise Rejection';
      errorInfo = event.reason?.stack || '';
    };
    
    window.addEventListener('unhandledrejection', onUnhandledRejection);
    
    return () => {
      window.onerror = originalOnError;
      window.removeEventListener('unhandledrejection', onUnhandledRejection);
    };
  });
  
  function handleReload() {
    hasError = false;
    window.location.reload();
  }
  
  function handleReset() {
    hasError = false;
    resetError();
  }
</script>

{#if hasError}
  <div class="error-boundary">
    <div class="error-container">
      <svg class="error-icon" viewBox="0 0 24 24" fill="currentColor">
        <path d="M11,15H13V17H11V15M11,7H13V13H11V7M12,2C6.47,2 2,6.5 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M12,20A8,8 0 0,1 4,12A8,8 0 0,1 12,4A8,8 0 0,1 20,12A8,8 0 0,1 12,20Z"/>
      </svg>
      <h2>Oops! Something went wrong</h2>
      <p class="error-message">{errorMessage}</p>
      {#if errorInfo}
        <pre class="error-stack">{errorInfo}</pre>
      {/if}
      <div class="action-buttons">
        <button class="reset-button" onclick={handleReset}>Try Again</button>
        <button class="reload-button" onclick={handleReload}>Reload App</button>
      </div>
    </div>
  </div>
{:else}
  {@render children?.()}
{/if}

<style>
  .error-boundary {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background-color: rgba(0, 0, 0, 0.1);
    backdrop-filter: blur(4px);
    display: flex;
    justify-content: center;
    align-items: center;
    padding: 1rem;
    z-index: 9999;
  }
  
  .error-container {
    background-color: white;
    border-radius: 0.5rem;
    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.2);
    padding: 2rem;
    max-width: 600px;
    width: 100%;
    text-align: center;
    animation: slide-up 0.3s ease-out;
  }
  
  @keyframes slide-up {
    from { transform: translateY(30px); opacity: 0; }
    to { transform: translateY(0); opacity: 1; }
  }
  
  .error-icon {
    width: 64px;
    height: 64px;
    color: #dc3545;
    margin-bottom: 1rem;
  }
  
  h2 {
    margin: 0 0 1rem 0;
    color: #495057;
  }
  
  .error-message {
    margin-bottom: 1rem;
    color: #721c24;
  }
  
  .error-stack {
    background-color: #f8f9fa;
    border-radius: 0.25rem;
    padding: 1rem;
    font-size: 0.8rem;
    overflow-x: auto;
    color: #6c757d;
    text-align: left;
    margin-bottom: 1.5rem;
    max-height: 150px;
  }
  
  .action-buttons {
    display: flex;
    gap: 1rem;
    justify-content: center;
  }
  
  .reset-button, .reload-button {
    padding: 0.5rem 1.5rem;
    border: none;
    border-radius: 0.25rem;
    cursor: pointer;
    font-weight: 600;
    transition: all 0.2s;
  }
  
  .reset-button {
    background-color: #6c757d;
    color: white;
  }
  
  .reset-button:hover {
    background-color: #5a6268;
  }
  
  .reload-button {
    background-color: #007bff;
    color: white;
  }
  
  .reload-button:hover {
    background-color: #0069d9;
  }
</style>
