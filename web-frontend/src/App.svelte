<script lang="ts">
  import type { AxiosError } from "axios";
  import { onMount } from "svelte";
  import Router, { push, link, location } from "svelte-spa-router";
  import { wrap } from "svelte-spa-router/wrap";
  import ErrorBoundary from "./components/ErrorBoundary.svelte";
  import LaunchJob from "./components/LaunchJob.svelte";
  import PerformanceMonitor from "./components/PerformanceMonitor.svelte";
  import DashboardPage from "./pages/DashboardPage.svelte";
  import JobsPage from "./pages/JobsPage.svelte";
  import JobPage from "./pages/JobPage.svelte";
  import WatchersPage from "./pages/WatchersPage.svelte";
  import SettingsPage from "./pages/SettingsPage.svelte";
  import { api, apiConfig, testConnection } from "./services/api";
  import type { HostInfo } from "./types/api";
  import { 
    Home,
    Play,
    Eye,
    Settings,
    AlertCircle,
    RefreshCw
  } from 'lucide-svelte';

  let hosts: HostInfo[] = [];
  let hostsLoading = false;
  let error: string | null = null;

  // Mobile detection
  let isMobile = typeof window !== 'undefined' && window.innerWidth < 768;
  
  // Define routes - on mobile, home redirects to jobs
  const routes = {
    '/': isMobile ? JobsPage : DashboardPage,
    '/jobs': JobsPage,
    '/jobs/:id/:host': JobPage,
    '/launch': wrap({
      component: LaunchJob,
      props: { hosts }
    }),
    '/watchers': WatchersPage,
    '/settings': SettingsPage
  };

  // Derive active tab from location
  $: activeTab = $location === '/launch' ? 'launch' :
                 $location === '/settings' ? 'settings' :
                 $location === '/watchers' ? 'watchers' :
                 $location === '/jobs' || $location.startsWith('/jobs/') ? 'jobs' :
                 'home';

  function checkMobile() {
    isMobile = window.innerWidth < 768;
  }

  onMount(async () => {
    checkMobile();
    window.addEventListener('resize', checkMobile);

    if (!$apiConfig.apiKey) {
    }

    testConnection().then((connected) => {
      if (connected) {
        loadHosts();
      } else if (!$apiConfig.apiKey) {
        push('/settings');
        error = "Please configure your API key to use the application";
      }
    });

    return () => {
      window.removeEventListener('resize', checkMobile);
    };
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
  <div class="min-h-screen bg-white flex flex-col">
    <!-- Minimalist Header -->
    <header class="bg-white border-b border-gray-200 sticky top-0 z-50">
      <div class="px-3 sm:px-6 lg:px-8">
        <div class="flex h-16 md:h-16 items-center justify-between">
          <!-- Logo and Navigation -->
          <div class="flex items-center space-x-2 md:space-x-4">
            <button
              class="text-base md:text-lg font-semibold text-black hover:opacity-70 transition-opacity duration-200"
              on:click={() => push('/')}
            >
              ssync
            </button>

            <!-- Desktop Navigation -->
            <nav class="hidden md:flex items-center space-x-1">
              <a
                href="/jobs"
                use:link
                class="nav-link {activeTab === 'jobs' ? 'nav-link-active' : ''}"
              >
                <span>Jobs</span>
              </a>

              <a
                href="/launch"
                use:link
                class="nav-link {activeTab === 'launch' ? 'nav-link-active' : ''} {!$apiConfig.authenticated ? 'opacity-50 cursor-not-allowed' : ''}"
              >
                <span>Launch</span>
              </a>

              <a
                href="/watchers"
                use:link
                class="nav-link {activeTab === 'watchers' ? 'nav-link-active' : ''} {!$apiConfig.authenticated ? 'opacity-50 cursor-not-allowed' : ''}"
              >
                <span>Watchers</span>
              </a>

              <a
                href="/settings"
                use:link
                class="nav-link {activeTab === 'settings' ? 'nav-link-active' : ''} relative"
              >
                <span>Settings</span>
                {#if !$apiConfig.authenticated}
                  <span class="absolute -top-1 -right-1 h-1.5 w-1.5 bg-red-500 rounded-full"></span>
                {/if}
              </a>
            </nav>

            <!-- Mobile Navigation - inline with logo -->
            <nav class="md:hidden flex items-center space-x-1">
              <a
                href="/jobs"
                use:link
                class="mobile-nav-link-inline {activeTab === 'jobs' ? 'mobile-nav-link-inline-active' : ''}"
              >
                Jobs
              </a>

              <a
                href="/launch"
                use:link
                class="mobile-nav-link-inline {activeTab === 'launch' ? 'mobile-nav-link-inline-active' : ''}"
              >
                Launch
              </a>

              <a
                href="/watchers"
                use:link
                class="mobile-nav-link-inline {activeTab === 'watchers' ? 'mobile-nav-link-inline-active' : ''}"
              >
                Watchers
              </a>

              <a
                href="/settings"
                use:link
                class="mobile-nav-link-inline {activeTab === 'settings' ? 'mobile-nav-link-inline-active' : ''} relative"
              >
                Settings
                {#if !$apiConfig.authenticated}
                  <span class="absolute -top-0.5 -right-0.5 h-1 w-1 bg-red-500 rounded-full"></span>
                {/if}
              </a>
            </nav>
          </div>

          <!-- Right side stats - Desktop only -->
          {#if !isMobile}
            <div class="flex items-center space-x-4">
              {#if $apiConfig.authenticated}
                <div class="flex items-center space-x-1.5">
                  <div class="h-1.5 w-1.5 bg-green-500 rounded-full"></div>
                  <span class="text-xs text-gray-500">Connected</span>
                </div>
              {/if}
            </div>
          {/if}
        </div>
      </div>
    </header>

    <!-- Error Banner -->
    {#if error}
      <div class="bg-red-50 dark:bg-red-900/20 border-b border-red-200 dark:border-red-800">
        <div class="px-4 sm:px-6 lg:px-8 py-3">
          <div class="flex items-center justify-between">
            <div class="flex items-center space-x-3">
              <AlertCircle class="h-5 w-5 text-red-600 dark:text-red-400" />
              <p class="text-sm font-medium text-red-800 dark:text-red-200">{error}</p>
            </div>
            <button 
              on:click={() => window.location.reload()} 
              class="inline-flex items-center space-x-1 text-sm font-medium text-red-600 hover:text-red-500 dark:text-red-400 dark:hover:text-red-300"
            >
              <RefreshCw class="h-4 w-4" />
              <span>Retry</span>
            </button>
          </div>
        </div>
      </div>
    {/if}

    <!-- Main Content -->
    <main class="flex-1 overflow-hidden flex flex-col">
      <Router {routes} />
    </main>
  </div>
  
  <!-- Performance Monitor (only in development/debug mode) -->
  {#if import.meta.env.DEV || window.location.search.includes('debug')}
    <PerformanceMonitor position="bottom-left" />
  {/if}
</ErrorBoundary>

<style>
  :root {
    --mobile-nav-height: 64px;
  }

  /* Minimalist Navigation */
  .nav-link {
    padding: 0 0.75rem;
    font-size: 0.875rem;
    font-weight: 400;
    color: #666;
    transition: color 150ms ease;
    position: relative;
  }

  .nav-link:hover {
    color: #000;
  }

  .nav-link-active {
    color: #000;
    font-weight: 500;
  }

  .nav-link-active::after {
    content: '';
    position: absolute;
    bottom: -17px;
    left: 0;
    right: 0;
    height: 2px;
    background: #000;
  }

  /* Mobile Navigation - Inline with logo */
  .mobile-nav-link-inline {
    padding: 0.375rem 0.5rem;
    font-size: 0.75rem;
    font-weight: 400;
    color: #9ca3af;
    transition: color 150ms ease;
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .mobile-nav-link-inline:hover {
    color: #6b7280;
  }

  .mobile-nav-link-inline-active {
    color: #000;
    font-weight: 500;
  }
  

  /* Minimal scrollbar */
  :global(::-webkit-scrollbar) {
    width: 6px;
    height: 6px;
  }
  
  :global(::-webkit-scrollbar-track) {
    background: transparent;
  }

  :global(::-webkit-scrollbar-thumb) {
    background-color: #d1d5db;
    border-radius: 3px;
  }
  
  :global(::-webkit-scrollbar-thumb:hover) {
    background-color: #9ca3af;
  }

  /* Global animation classes */
  :global(.animate-in) {
    animation: fade-in 0.3s ease-out;
  }

  :global(.slide-in) {
    animation: slide-in 0.3s ease-out;
  }

  @keyframes fade-in {
    from {
      opacity: 0;
      transform: translateY(4px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  @keyframes slide-in {
    from {
      transform: translateX(-100%);
    }
    to {
      transform: translateX(0);
    }
  }
</style>