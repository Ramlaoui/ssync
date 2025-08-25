<script lang="ts">
  import type { AxiosError } from "axios";
  import { onMount } from "svelte";
  import Router, { push, link, location } from "svelte-spa-router";
  import { wrap } from "svelte-spa-router/wrap";
  import ApiKeyConfig from "./components/ApiKeyConfig.svelte";
  import ErrorBoundary from "./components/ErrorBoundary.svelte";
  import LaunchJob from "./components/LaunchJob.svelte";
  import JobsPage from "./pages/JobsPage.svelte";
  import JobPage from "./pages/JobPage.svelte";
  import { api, apiConfig, testConnection } from "./services/api";
  import type { HostInfo } from "./types/api";

  let hosts: HostInfo[] = [];
  let hostsLoading = false;
  let error: string | null = null;
  
  // Define routes
  const routes = {
    '/': JobsPage,
    '/jobs/:id/:host': JobPage,
    '/launch': wrap({
      component: LaunchJob,
      props: { hosts }
    }),
    '/settings': ApiKeyConfig
  };

  // Derive active tab from location
  $: activeTab = $location === '/launch' ? 'launch' : 
                 $location === '/settings' ? 'settings' : 
                 'jobs';

  onMount(() => {
    // Test API connection first
    testConnection().then((connected) => {
      if (connected) {
        loadHosts();
      } else if (!$apiConfig.apiKey) {
        push('/settings');
        error = "Please configure your API key to use the application";
      }
    });
  });

  async function loadHosts(): Promise<void> {
    if (hostsLoading) return;

    hostsLoading = true;
    try {
      const response = await api.get<HostInfo[]>("/api/hosts");
      hosts = response.data;
    } catch (err: unknown) {
      const axiosError = err as AxiosError;
      if (axiosError.response?.status === 401) {
        error = "Authentication failed. Please check your API key.";
        push('/settings');
      } else {
        error = `Failed to load hosts: ${axiosError.message}`;
      }
    } finally {
      hostsLoading = false;
    }
  }
</script>

<ErrorBoundary
  resetError={() => {
    error = null;
    window.location.reload();
  }}
>
  <div class="app">
    <header class="header">
      <div class="header-left">
        <button
          class="app-title"
          on:click={() => push('/')}
        >
          ssync
        </button>

        <nav class="tab-nav">
          <a
            href="/"
            use:link
            class="tab-button"
            class:active={activeTab === "jobs"}
          >
            Jobs
          </a>
          <a
            href="/launch"
            use:link
            class="tab-button"
            class:active={activeTab === "launch"}
            class:disabled={!$apiConfig.authenticated}
          >
            Launch Job
          </a>
          <a
            href="/settings"
            use:link
            class="tab-button"
            class:active={activeTab === "settings"}
          >
            Settings
            {#if !$apiConfig.authenticated}
              <span class="badge">!</span>
            {/if}
          </a>
        </nav>
      </div>

      <div class="stats">
        <span class="stat">
          {hosts.length} Hosts
        </span>
      </div>
    </header>

    {#if error}
      <div class="error">
        <svg class="error-icon" viewBox="0 0 24 24" fill="currentColor">
          <path
            d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"
          />
        </svg>
        {error}
        <button on:click={() => window.location.reload()} class="retry-button">
          Retry
        </button>
      </div>
    {/if}

    <div class="main-content">
      <Router {routes} />
    </div>
  </div>
</ErrorBoundary>

<style>
  .app {
    min-height: 100vh;
    height: 100vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .header {
    background: linear-gradient(135deg, #2c3e50 0%, #34495e 100%);
    color: white;
    padding: 1rem 2rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    backdrop-filter: blur(10px);
    position: relative;
    z-index: 10;
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 2rem;
  }

  .app-title {
    margin: 0;
    font-size: 1.5rem;
    cursor: pointer;
    transition: opacity 0.2s;
    background: none;
    border: none;
    color: inherit;
    font: inherit;
    font-weight: 600;
  }

  .app-title:hover {
    opacity: 0.8;
  }

  .error-icon {
    width: 20px;
    height: 20px;
    margin-right: 0.5rem;
  }

  .stats {
    display: flex;
    gap: 0.75rem;
    align-items: center;
  }

  .stat {
    background: rgba(255, 255, 255, 0.1);
    padding: 0.25rem 0.75rem;
    border-radius: 1rem;
    font-size: 0.9rem;
    white-space: nowrap;
  }

  .error {
    background: #f8d7da;
    color: #721c24;
    padding: 1rem 2rem;
    border-bottom: 1px solid #f5c6cb;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .retry-button {
    background: #dc3545;
    color: white;
    border: none;
    padding: 0.5rem 1rem;
    border-radius: 0.25rem;
    cursor: pointer;
    transition: background-color 0.2s;
  }

  .retry-button:hover {
    background: #c82333;
  }

  .main-content {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-height: 0;
    overflow: hidden;
    width: 100%;
  }
  
  /* Ensure router content takes full space */
  .main-content :global(> *) {
    flex: 1;
    width: 100%;
  }

  .tab-nav {
    display: flex;
    gap: 0.5rem;
  }

  .tab-button {
    padding: 0.625rem 1.25rem;
    background: rgba(255, 255, 255, 0.1);
    border: none;
    border-radius: 8px;
    color: rgba(255, 255, 255, 0.8);
    cursor: pointer;
    transition: all 0.2s ease;
    font: inherit;
    font-size: 0.9rem;
    font-weight: 500;
    position: relative;
    overflow: hidden;
    text-decoration: none;
    display: inline-block;
  }

  .tab-button.disabled {
    opacity: 0.5;
    cursor: not-allowed;
    pointer-events: none;
  }

  .tab-button:hover:not(.disabled):not(.active) {
    background: rgba(255, 255, 255, 0.2);
    color: white;
    transform: translateY(-1px);
  }

  .tab-button:active:not(.disabled) {
    transform: scale(0.98);
  }

  .tab-button:focus {
    outline: 2px solid rgba(255, 255, 255, 0.5);
    outline-offset: 2px;
  }

  .tab-button:focus:not(:focus-visible) {
    outline: none;
  }

  .tab-button.active {
    background: rgba(255, 255, 255, 0.95);
    color: #2c3e50;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
    transform: translateY(-1px);
  }

  .tab-button.active:hover {
    background: rgba(255, 255, 255, 1);
  }

  .tab-button .badge {
    position: absolute;
    top: 4px;
    right: 4px;
    background: #dc3545;
    color: white;
    border-radius: 50%;
    width: 16px;
    height: 16px;
    font-size: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1;
  }

  /* Mobile styles */
  @media (max-width: 768px) {
    .header {
      padding: 1rem;
      flex-direction: column;
      gap: 1rem;
      position: sticky;
      top: 0;
      z-index: 100;
      backdrop-filter: blur(10px);
    }

    .header-left {
      gap: 0.75rem;
      width: 100%;
      flex-direction: column;
      align-items: stretch;
    }

    .app-title {
      font-size: 1.25rem;
      font-weight: 700;
      text-align: center;
    }

    .stats {
      flex-wrap: wrap;
      gap: 0.5rem;
      justify-content: center;
      width: 100%;
    }

    .stat {
      font-size: 0.8rem;
      padding: 0.2rem 0.6rem;
    }

    .tab-nav {
      gap: 0.25rem;
      display: flex;
      justify-content: center;
      flex-wrap: nowrap;
    }

    .tab-button {
      font-size: 0.75rem;
      padding: 0.4rem 0.6rem;
      white-space: nowrap;
      min-width: fit-content;
    }

    .main-content {
      flex-direction: column;
      padding: 0;
    }
  }
</style>