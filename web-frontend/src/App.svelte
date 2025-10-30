<script lang="ts">
  import { run } from 'svelte/legacy';

  import type { AxiosError } from "axios";
  import { onMount } from "svelte";
  import Router, { push, link, location } from "svelte-spa-router";
  import ErrorBoundary from "./components/ErrorBoundary.svelte";
  import PerformanceMonitor from "./components/PerformanceMonitor.svelte";
  import JobsPage from "./pages/JobsPage.svelte";
  import JobPage from "./pages/JobPage.svelte";
  import LaunchPage from "./pages/LaunchPage.svelte";
  import WatchersPage from "./pages/WatchersPage.svelte";
  import SettingsPage from "./pages/SettingsPage.svelte";
  import { api, apiConfig, testConnection } from "./services/api";
  import type { HostInfo } from "./types/api";
  import { navigationActions } from "./stores/navigation";
  import { theme } from "./stores/theme";
  import { sidebarOpen } from "./stores/sidebar";
  import JobSidebar from "./components/JobSidebar.svelte";
  // ⚡ PERFORMANCE FIX: Disabled legacy WebSocket - now using centralized JobStateManager
  // import { connectAllJobsWebSocket } from "./stores/jobWebSocket";
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
  let error: string | null = $state(null);

  // Mobile detection
  let isMobile = $state(typeof window !== 'undefined' && window.innerWidth < 768);

  // Define routes - JobsPage is now the default landing page
  const routes = {
    '/': JobsPage,
    '/jobs/:id/:host': JobPage,
    '/launch': LaunchPage,
    '/watchers': WatchersPage,
    '/settings': SettingsPage
  };

  // Derive active tab from location
  let activeTab = $derived($location === '/launch' ? 'launch' :
                 $location === '/settings' ? 'settings' :
                 $location === '/watchers' ? 'watchers' :
                 $location === '/' || $location.startsWith('/jobs/') ? 'jobs' :
                 'jobs');

  // Track route changes for back navigation
  let previousLocation: string | undefined = $state();

  // Import navigationState and get function for non-reactive reads
  import { navigationState } from "./stores/navigation";
  import { get } from "svelte/store";

  // Combine navigation tracking and document title update into a single reactive block
  // This prevents recursive reactive cycles that cause warnings
  run(() => {
    // Track navigation changes
    if ($location && previousLocation && $location !== previousLocation) {
      // Use get() to read current state without subscribing (avoids recursive reactivity)
      const currentState = get(navigationState);
      if (currentState.skipNextUpdate) {
        // Clear the skip flag
        navigationState.update(state => ({
          ...state,
          skipNextUpdate: false
        }));
      } else {
        // Store the previous route
        navigationActions.setPreviousRoute(previousLocation);
      }
    }
    previousLocation = $location;

    // Update document title based on current route
    if ($location === '/') {
      document.title = 'Jobs | ssync';
    } else if ($location === '/launch') {
      document.title = 'Launch Job | ssync';
    } else if ($location === '/watchers') {
      document.title = 'Watchers | ssync';
    } else if ($location === '/settings') {
      document.title = 'Settings | ssync';
    } else if ($location.startsWith('/jobs/')) {
      // Extract job ID and host from URL: /jobs/:id/:host
      const parts = $location.split('/');
      if (parts.length >= 4) {
        const jobId = decodeURIComponent(parts[2]);
        const hostname = parts[3];
        document.title = `${jobId} @ ${hostname} | ssync`;
      } else {
        document.title = 'Job Details | ssync';
      }
    } else {
      document.title = 'ssync';
    }
  });

  function checkMobile() {
    isMobile = window.innerWidth < 768;
  }

  onMount(async () => {
    checkMobile();
    window.addEventListener('resize', checkMobile);

    // Initialize theme from store (already happens in theme.ts module load, but ensure it's applied)
    theme.init();

    if (!$apiConfig.apiKey) {
    }

    testConnection().then((connected) => {
      if (connected) {
        loadHosts();
        // ⚡ PERFORMANCE FIX: Disabled legacy WebSocket - JobStateManager handles WebSocket now
        // connectAllJobsWebSocket();
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
  <div class="h-full w-full bg-background flex flex-col overflow-hidden">
    <!-- Minimalist Header -->
    <header class="flex-shrink-0 z-50 navbar-header">
      <div class="px-3 sm:px-6 lg:px-8">
        <div class="flex h-16 md:h-16 items-center justify-between">
          <!-- Logo and Navigation -->
          <div class="flex items-center space-x-2 md:space-x-4">
            <button
              class="navbar-title text-base md:text-lg font-semibold text-foreground hover:opacity-70 transition-opacity duration-200 cursor-pointer"
              onclick={() => sidebarOpen.update(v => !v)}
              title="Toggle jobs sidebar"
            >
              ssync
            </button>

            <!-- Desktop Navigation -->
            <nav class="hidden md:flex items-center space-x-1">
              <a
                href="/"
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
                href="/"
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
                  <span class="text-xs text-muted-foreground">Connected</span>
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
              onclick={() => window.location.reload()} 
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
    <main class="flex-1 w-full min-h-0 overflow-hidden flex relative">
      <!-- Mobile Backdrop (only on mobile when sidebar is open) -->
      {#if isMobile && $sidebarOpen}
        <div
          class="mobile-sidebar-backdrop"
          onclick={() => sidebarOpen.set(false)}
        ></div>
      {/if}

      <!-- Global Job Sidebar -->
      {#if $sidebarOpen}
        <div class="sidebar-container" class:mobile={isMobile}>
          <JobSidebar />
        </div>
      {/if}

      <!-- Page Content -->
      <div class="flex-1 min-w-0 min-h-0 overflow-hidden flex flex-col">
        <Router {routes} />
      </div>
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

  /* Navbar Header */
  .navbar-header {
    background-color: var(--background);
    border-bottom: 1px solid var(--border);
  }

  /* Minimalist Navigation */
  .nav-link {
    padding: 0 0.75rem;
    font-size: 0.875rem;
    font-weight: 400;
    color: var(--muted);
    transition: color 150ms ease;
    position: relative;
  }

  .nav-link:hover {
    color: var(--foreground);
  }

  .nav-link-active {
    color: var(--foreground);
    font-weight: 500;
  }

  .nav-link-active::after {
    content: '';
    position: absolute;
    bottom: -17px;
    left: 0;
    right: 0;
    height: 2px;
    background: var(--foreground);
  }

  /* Mobile Navigation - Inline with logo */
  .mobile-nav-link-inline {
    padding: 0.375rem 0.5rem;
    font-size: 0.75rem;
    font-weight: 400;
    color: var(--muted-foreground);
    transition: color 150ms ease;
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .mobile-nav-link-inline:hover {
    color: var(--muted);
  }

  .mobile-nav-link-inline-active {
    color: var(--foreground);
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
    background-color: var(--border);
    border-radius: 3px;
  }

  :global(::-webkit-scrollbar-thumb:hover) {
    background-color: var(--muted);
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

  /* Mobile Sidebar Overlay */
  .mobile-sidebar-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    backdrop-filter: blur(4px);
    -webkit-backdrop-filter: blur(4px);
    z-index: 60;
    animation: fade-in 0.2s ease-out;
  }

  .sidebar-container {
    position: relative;
    z-index: 1;
  }

  .sidebar-container.mobile {
    position: fixed;
    top: 0;
    left: 0;
    bottom: 0;
    z-index: 70;
    animation: slide-in-left 0.3s ease-out;
  }

  @keyframes slide-in-left {
    from {
      transform: translateX(-100%);
    }
    to {
      transform: translateX(0);
    }
  }
</style>