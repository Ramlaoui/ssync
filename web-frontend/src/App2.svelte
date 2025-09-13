<script lang="ts">
  import type { AxiosError } from "axios";
  import { onMount } from "svelte";
  import Router, { push, link, location } from "svelte-spa-router";
  import { wrap } from "svelte-spa-router/wrap";
  import ApiKeyConfig from "./components/ApiKeyConfig.svelte";
  import ErrorBoundary from "./components/ErrorBoundary.svelte";
  import LaunchJob from "./components/LaunchJob.svelte";
  import PerformanceMonitor from "./components/PerformanceMonitor.svelte";
  import JobsPage from "./pages/JobsPage.svelte";
  import JobPage from "./pages/JobPage.svelte";
  import WatchersPage from "./pages/WatchersPageEnhanced.svelte";
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
  <div class="min-h-screen bg-gray-50 dark:bg-gray-900 flex flex-col">
    <!-- Modern Header -->
    <header class="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 sticky top-0 z-50 backdrop-blur-sm bg-white/95 dark:bg-gray-800/95">
      <div class="px-4 sm:px-6 lg:px-8">
        <div class="flex h-16 items-center justify-between">
          <!-- Logo and Brand -->
          <div class="flex items-center space-x-4">
            <button
              class="text-xl font-bold bg-gradient-to-r from-violet-600 to-indigo-600 bg-clip-text text-transparent hover:opacity-80 transition-opacity"
              on:click={() => push('/')}
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
                <Home class="h-4 w-4" />
                <span>Jobs</span>
              </a>
              
              <a
                href="/launch"
                use:link
                class="nav-link {activeTab === 'launch' ? 'nav-link-active' : ''} {!$apiConfig.authenticated ? 'opacity-50 cursor-not-allowed' : ''}"
              >
                <Play class="h-4 w-4" />
                <span>Launch</span>
              </a>
              
              <a
                href="/watchers"
                use:link
                class="nav-link {activeTab === 'watchers' ? 'nav-link-active' : ''} {!$apiConfig.authenticated ? 'opacity-50 cursor-not-allowed' : ''}"
              >
                <Eye class="h-4 w-4" />
                <span>Watchers</span>
              </a>
              
              <a
                href="/settings"
                use:link
                class="nav-link {activeTab === 'settings' ? 'nav-link-active' : ''} relative"
              >
                <Settings class="h-4 w-4" />
                <span>Settings</span>
                {#if !$apiConfig.authenticated}
                  <span class="absolute -top-1 -right-1 h-2 w-2 bg-red-500 rounded-full"></span>
                {/if}
              </a>
            </nav>
          </div>

          <!-- Right side stats -->
          <div class="flex items-center space-x-4">
            <div class="hidden sm:flex items-center space-x-2 text-sm">
              <span class="text-gray-500 dark:text-gray-400">Hosts:</span>
              <span class="font-medium text-gray-900 dark:text-gray-100">{hosts.length}</span>
            </div>
            
            {#if $apiConfig.authenticated}
              <div class="flex items-center space-x-1.5">
                <div class="h-2 w-2 bg-green-500 rounded-full animate-pulse"></div>
                <span class="text-sm text-gray-600 dark:text-gray-400">Connected</span>
              </div>
            {/if}
          </div>
        </div>
        
        <!-- Mobile Navigation -->
        <nav class="md:hidden flex items-center space-x-1 pb-2 overflow-x-auto">
          <a
            href="/"
            use:link
            class="mobile-nav-link {activeTab === 'jobs' ? 'mobile-nav-link-active' : ''}"
          >
            <Home class="h-5 w-5" />
          </a>
          
          <a
            href="/launch"
            use:link
            class="mobile-nav-link {activeTab === 'launch' ? 'mobile-nav-link-active' : ''}"
          >
            <Play class="h-5 w-5" />
          </a>
          
          <a
            href="/watchers"
            use:link
            class="mobile-nav-link {activeTab === 'watchers' ? 'mobile-nav-link-active' : ''}"
          >
            <Eye class="h-5 w-5" />
          </a>
          
          <a
            href="/settings"
            use:link
            class="mobile-nav-link {activeTab === 'settings' ? 'mobile-nav-link-active' : ''} relative"
          >
            <Settings class="h-5 w-5" />
            {#if !$apiConfig.authenticated}
              <span class="absolute -top-1 -right-1 h-2 w-2 bg-red-500 rounded-full"></span>
            {/if}
          </a>
        </nav>
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
    <main class="flex-1 overflow-hidden">
      <Router {routes} />
    </main>
  </div>
  
  <!-- Performance Monitor (only in development/debug mode) -->
  {#if import.meta.env.DEV || window.location.search.includes('debug')}
    <PerformanceMonitor position="bottom-left" />
  {/if}
</ErrorBoundary>

<style>
  /* Navigation Links */
  .nav-link {
    @apply flex items-center space-x-2 px-3 py-2 text-sm font-medium rounded-lg transition-all;
    @apply text-gray-600 hover:text-gray-900 hover:bg-gray-100;
    @apply dark:text-gray-400 dark:hover:text-gray-100 dark:hover:bg-gray-700;
  }
  
  .nav-link-active {
    @apply text-violet-600 bg-violet-50;
    @apply dark:text-violet-400 dark:bg-violet-900/20;
  }
  
  /* Mobile Navigation */
  .mobile-nav-link {
    @apply flex items-center justify-center p-2 rounded-lg transition-all;
    @apply text-gray-600 hover:text-gray-900 hover:bg-gray-100;
    @apply dark:text-gray-400 dark:hover:text-gray-100 dark:hover:bg-gray-700;
  }
  
  .mobile-nav-link-active {
    @apply text-violet-600 bg-violet-50;
    @apply dark:text-violet-400 dark:bg-violet-900/20;
  }
  
  /* Custom scrollbar */
  :global(::-webkit-scrollbar) {
    width: 8px;
    height: 8px;
  }
  
  :global(::-webkit-scrollbar-track) {
    @apply bg-gray-100 dark:bg-gray-800;
  }
  
  :global(::-webkit-scrollbar-thumb) {
    @apply bg-gray-400 dark:bg-gray-600 rounded-full;
  }
  
  :global(::-webkit-scrollbar-thumb:hover) {
    @apply bg-gray-500 dark:bg-gray-500;
  }
</style>