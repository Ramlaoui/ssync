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
  import WatchersPage from "./pages/WatchersPageEnhanced.svelte";
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
    '/watchers': WatchersPage,
    '/settings': ApiKeyConfig
  };

  // Derive active tab from location
  $: activeTab = $location === '/launch' ? 'launch' : 
                 $location === '/settings' ? 'settings' : 
                 $location === '/watchers' ? 'watchers' :
                 'jobs';

  onMount(async () => {
    // Try to get API key from config if not already set
    if (!$apiConfig.apiKey) {
      // Try with the known API key from the backend config
      const configuredKey = 'T_O4bkV5JYmz8T-MdMqgoCvwAFEz12GzmMPuY0_e5DA';
      if (configuredKey) {
        apiConfig.update(c => ({
          ...c,
          apiKey: configuredKey
        }));
        localStorage.setItem('ssync_api_key', configuredKey);
      }
    }
    
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
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M19,3A2,2 0 0,1 21,5V19A2,2 0 0,1 19,21H5A2,2 0 0,1 3,19V5A2,2 0 0,1 5,3H19M19,19V5H5V19H19M7,7H9V9H7V7M11,7H17V9H11V7M7,11H9V13H7V11M11,11H17V13H11V11M7,15H9V17H7V15M11,15H17V17H11V15Z"/>
            </svg>
            <span class="tab-text">Jobs</span>
          </a>
          <a
            href="/launch"
            use:link
            class="tab-button"
            class:active={activeTab === "launch"}
            class:disabled={!$apiConfig.authenticated}
          >
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M8,5.14V19.14L19,12.14L8,5.14Z"/>
            </svg>
            <span class="tab-text">Launch Job</span>
          </a>
          <a
            href="/watchers"
            use:link
            class="tab-button"
            class:active={activeTab === "watchers"}
            class:disabled={!$apiConfig.authenticated}
          >
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M12,9A3,3 0 0,0 9,12A3,3 0 0,0 12,15A3,3 0 0,0 15,12A3,3 0 0,0 12,9M12,17A5,5 0 0,1 7,12A5,5 0 0,1 12,7A5,5 0 0,1 17,12A5,5 0 0,1 12,17M12,4.5C7,4.5 2.73,7.61 1,12C2.73,16.39 7,19.5 12,19.5C17,19.5 21.27,16.39 23,12C21.27,7.61 17,4.5 12,4.5Z"/>
            </svg>
            <span class="tab-text">Watchers</span>
          </a>
          <a
            href="/settings"
            use:link
            class="tab-button"
            class:active={activeTab === "settings"}
          >
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M12,15.5A3.5,3.5 0 0,1 8.5,12A3.5,3.5 0 0,1 12,8.5A3.5,3.5 0 0,1 15.5,12A3.5,3.5 0 0,1 12,15.5M19.43,12.97C19.47,12.65 19.5,12.33 19.5,12C19.5,11.67 19.47,11.34 19.43,11L21.54,9.37C21.73,9.22 21.78,8.95 21.66,8.73L19.66,5.27C19.54,5.05 19.27,4.96 19.05,5.05L16.56,6.05C16.04,5.66 15.5,5.32 14.87,5.07L14.5,2.42C14.46,2.18 14.25,2 14,2H10C9.75,2 9.54,2.18 9.5,2.42L9.13,5.07C8.5,5.32 7.96,5.66 7.44,6.05L4.95,5.05C4.73,4.96 4.46,5.05 4.34,5.27L2.34,8.73C2.22,8.95 2.27,9.22 2.46,9.37L4.57,11C4.53,11.34 4.5,11.67 4.5,12C4.5,12.33 4.53,12.65 4.57,12.97L2.46,14.63C2.27,14.78 2.21,15.05 2.34,15.27L4.34,18.73C4.46,18.95 4.73,19.03 4.95,18.95L7.44,17.94C7.96,18.34 8.5,18.68 9.13,18.93L9.5,21.58C9.54,21.82 9.75,22 10,22H14C14.25,22 14.46,21.82 14.5,21.58L14.87,18.93C15.5,18.68 16.04,18.34 16.56,17.94L19.05,18.95C19.27,19.03 19.54,18.95 19.66,18.73L21.66,15.27C21.78,15.05 21.73,14.78 21.54,14.63L19.43,12.97Z"/>
            </svg>
            <span class="tab-text">Settings</span>
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
    user-select: none;
    -webkit-user-select: none;
    -moz-user-select: none;
    -ms-user-select: none;
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
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
  }

  .tab-button svg {
    width: 18px;
    height: 18px;
    flex-shrink: 0;
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
      padding: 0.5rem 0.75rem;
      flex-direction: row;
      gap: 0.75rem;
      position: sticky;
      top: 0;
      z-index: 100;
      backdrop-filter: blur(10px);
      min-height: auto;
    }

    .header-left {
      gap: 0.75rem;
      flex: 1;
      flex-direction: row;
      align-items: center;
      justify-content: space-between;
    }

    .app-title {
      font-size: 1.1rem;
      font-weight: 700;
      text-align: left;
      flex-shrink: 0;
    }

    .stats {
      display: none; /* Hide host count on mobile to save space */
    }

    .tab-nav {
      gap: 0.25rem;
      display: flex;
      justify-content: center;
      flex-wrap: nowrap;
      flex-shrink: 0;
    }

    .tab-button {
      font-size: 0;  /* Hide text on mobile */
      padding: 0.5rem;
      min-width: 44px;  /* Touch-friendly minimum size */
      justify-content: center;
      border-radius: 8px;
    }

    .tab-button svg {
      width: 20px;
      height: 20px;
    }

    .tab-text {
      display: none;  /* Hide text labels on mobile */
    }

    .main-content {
      flex-direction: column;
      padding: 0;
    }
  }
</style>