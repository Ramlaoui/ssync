<script lang="ts">
  import { onMount } from 'svelte';
  import { get } from 'svelte/store';
  import Router, { push, location } from 'svelte-spa-router';
  import { wrap } from 'svelte-spa-router/wrap';
  import LoadingSpinner from './components/LoadingSpinner.svelte';
  import { focusTrap } from './lib/actions';
  import { Layers, Rocket, Eye, Server, Settings2, Search, Command, Menu, X, Sun, Moon, ArrowRight, TriangleAlert, RefreshCw } from 'lucide-svelte';
  import ErrorBoundary from './components/ErrorBoundary.svelte';
  import LaunchMonitor from './components/LaunchMonitor.svelte';
  import PerformanceMonitor from './components/PerformanceMonitor.svelte';
  import Brand from './components/workspace/Brand.svelte';
  import IconButton from './components/workspace/IconButton.svelte';
  import JobStatus from './components/workspace/JobStatus.svelte';
  import Dialog from './lib/components/ui/Dialog.svelte';
  import JobsPage from './pages/JobsPage.svelte';
  import JobPage from './pages/JobPage.svelte';
  import { apiConfig, testConnection } from './services/api';
  import { theme, resolvedTheme } from './stores/theme';
  import { navigationActions, navigationState } from './stores/navigation';
  import { jobsWorkspace, setJobView } from './stores/workspace';
  import { jobStateManager } from './lib/JobStateManager';
  import { jobRoute, jobStatus } from './lib/jobsPresentation';
  import { safeGetItem } from './lib/safeStorage';
  // Router 4's declarations still use Svelte 4 constructors; the runtime also accepts Svelte 5 components.
  function lazyRoute(loader: () => Promise<{
    default: unknown;
  }>) {
    return wrap({ asyncComponent: loader, loadingComponent: LoadingSpinner } as unknown as Parameters<typeof wrap>[0]);
  }
  const routes = {
    '/': JobsPage,
    '/jobs': JobsPage,
    '/jobs/:id/:host': JobPage,
    '/launch': lazyRoute(() => import('./pages/LaunchPage.svelte')),
    '/watchers': lazyRoute(() => import('./pages/WatchersPage.svelte')),
    '/hosts': lazyRoute(() => import('./pages/HostsPage.svelte')),
    '/settings': lazyRoute(() => import('./pages/SettingsPage.svelte')),
    '*': JobsPage,
  };
  const jobs = jobStateManager.getAllJobs();
  const hostStates = jobStateManager.getHostStates();
  const connection = jobStateManager.getConnectionStatus();
  const navigation = [{ path: '/', label: 'Jobs', icon: Layers }, { path: '/launch', label: 'Launch', icon: Rocket }, { path: '/watchers', label: 'Watchers', icon: Eye }, { path: '/hosts', label: 'Hosts', icon: Server }];
  let mobileOpen = $state(false);
  let commandOpen = $state(false);
  let commandQuery = $state('');
  let connecting = $state(true);
  let previousLocation: string | undefined;
  const path = $derived(($location || '/').split('?')[0]);
  const maximized = $derived(path.startsWith('/jobs/') && path.split('/').length >= 4);
  const activePath = $derived(path === '/jobs' || maximized ? '/' : path);
  const title = $derived(activePath === '/launch' ? 'Launch job' : activePath === '/watchers' ? 'Watchers' : activePath === '/hosts' ? 'Hosts' : activePath === '/settings' ? 'Settings' : 'Jobs');
  const runningCount = $derived($jobs.filter(j => jobStatus(j.state).category === 'active').length);
  const attentionCount = $derived($jobs.filter(j => jobStatus(j.state).attention).length);
  const commandJobs = $derived($jobs.filter(j => [j.name, j.job_id, j.hostname].some(v => v.toLowerCase().includes(commandQuery.toLowerCase()))).slice(0, 8));
  const commandActions = $derived(navigation.filter(item => item.label.toLowerCase().includes(commandQuery.toLowerCase())));
  $effect(() => {
    const next = $location;
    mobileOpen = false;
    if (previousLocation && previousLocation !== next) {
      if (get(navigationState).skipNextUpdate)
        navigationState.update(state => ({ ...state, skipNextUpdate: false }));
      else
        navigationActions.setPreviousRoute(previousLocation);
    }
    previousLocation = next;
  });
  async function connect() {
    connecting = true;
    const connected = await testConnection();
    connecting = false;
    if (connected)
      jobStateManager.connectWebSocket();
  }
  function navigate(route: string) { commandOpen = false; mobileOpen = false; void push(route); }
  function openCommands() { commandQuery = ''; commandOpen = true; }
  function keyboard(event: KeyboardEvent) {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      commandOpen ? commandOpen = false : openCommands();
    }
    if (event.key === 'Escape')
      mobileOpen = false;
  }
  onMount(() => {
    theme.init();
    try {
      document.documentElement.classList.toggle('compact-mode', Boolean(JSON.parse(safeGetItem('ssync_preferences') || '{}').compactMode));
    }
    catch { }
    const search = new URLSearchParams(window.location.search);
    if (search.has('watcher') && (!window.location.hash || window.location.hash.startsWith('#/?') || window.location.hash === '#/')) {
      const route = `/watchers?${search.toString()}`;
      void push(route).then(() => window.history.replaceState({}, '', `${window.location.pathname}#${route}`));
    }
    else if (!window.location.hash && /^\/(jobs\/|watchers|launch|hosts|settings)/.test(window.location.pathname)) {
      void push(`${window.location.pathname}${window.location.search}`);
    }
    void connect();
  });
</script>

<svelte:window onkeydown={keyboard}/>

<svelte:head>
  <title>{title} · ssync</title>
</svelte:head>

<ErrorBoundary resetError={()=>window.location.reload()}>
  <div class="relay-app" class:relay-focused={maximized}>
    {#if mobileOpen}
      <button class="relay-nav-backdrop" aria-label="Close navigation" onclick={()=>mobileOpen=false}></button>
    {/if}
    <aside class="relay-sidebar" class:mobile-open={mobileOpen} aria-label="Primary navigation" use:focusTrap={{enabled:mobileOpen}}>
      <a href="#/" class="relay-brand" aria-label="ssync jobs" title="ssync" onclick={()=>mobileOpen=false}>
        <Brand/>
        <span>ssync</span>
        <small>v2</small>
      </a>
      <button class="relay-quick-find" aria-label="Quick find" title="Quick find · ⌘/Ctrl K" onclick={openCommands}>
        <Search size={17}/>
        <span>Quick find</span>
        <kbd>⌘ K</kbd>
      </button>
      <nav>
        {#each navigation as item}
          {@const Glyph=item.icon}
          <a href={`#${item.path}`} class:active={activePath===item.path} aria-current={activePath===item.path?'page':undefined} aria-label={item.label} title={item.label}>
            <Glyph size={19}/>
            <span>{item.label}</span>
            {#if item.path==='/'&&runningCount}
              <small>{runningCount}</small>
            {/if}
          </a>
        {/each}
      </nav>
      <div class="relay-saved-views">
        <span class="relay-section-label">Saved views</span>
        <button class:active={$jobsWorkspace.view==='attention'&&activePath==='/'} onclick={()=>{setJobView('attention');navigate('/');}}>
          <TriangleAlert size={16}/>
          <span>Needs attention</span>
          {#if attentionCount}
            <small class="relay-attention-count">{attentionCount}</small>
          {/if}
        </button>
        <button onclick={()=>{setJobView('running');navigate('/');}}>
          <Layers size={16}/>
          <span>Running jobs</span>
        </button>
      </div>
      <div class="relay-sidebar-bottom">
        <a class="relay-connection" href="#/hosts" title="View hosts">
          <span class="relay-dot" class:connected={$connection.connected&&$connection.healthy}></span>
          <span>{$hostStates.size} {$hostStates.size===1?'host':'hosts'} · {$connection.connected&&$connection.healthy?'Connected':'Offline'}</span>
        </a>
        <a class="relay-settings-link" href="#/settings" class:active={activePath==='/settings'} aria-label="Settings" title="Settings">
          <Settings2 size={19}/>
          <span>Settings</span>
          {#if !$apiConfig.authenticated&&!connecting}
            <span class="relay-auth-dot"></span>
          {/if}
        </a>
        <div class="relay-appearance">
          <span>Appearance</span>
          <IconButton label={$resolvedTheme==='dark'?'Switch to light appearance':'Switch to dark appearance'} onclick={()=>theme.toggle()}>
            {#if $resolvedTheme==='dark'}
              <Sun size={18}/>
            {:else}
              <Moon size={18}/>
            {/if}
          </IconButton>
        </div>
      </div>
    </aside>
    <div class="relay-main">
      <header class="relay-topbar">
        <div class="relay-breadcrumb">
          <button class="relay-icon-button relay-mobile-menu" aria-label="Open navigation" onclick={()=>mobileOpen=true}>
            <Menu size={20}/>
          </button>
          <span>Workspace</span>
          <span class="relay-slash">/</span>
          <strong>{title}</strong>
        </div>
        <div class="relay-topbar-actions">
          <span class="relay-live" class:online={$apiConfig.authenticated&&$connection.connected}>
            <span class="relay-dot"></span>
            {connecting?'Connecting':!$apiConfig.authenticated?'Not connected':$connection.source==='websocket'&&$connection.connected?'Live':$connection.connected?'Updating':'Reconnecting'}
          </span>
          <IconButton label="Quick find · ⌘/Ctrl K" onclick={openCommands}>
            <Command size={18}/>
          </IconButton>
        </div>
      </header>
      {#if !connecting&&!$apiConfig.authenticated&&activePath!=='/settings'}
        <div class="relay-banner" role="status">
          <TriangleAlert size={18}/>
          <span>{$apiConfig.authError||'Connect to your ssync server to load jobs.'}</span>
          <a href="#/settings">Connection settings</a>
          <IconButton label="Retry connection" onclick={()=>void connect()}>
            <RefreshCw size={16}/>
          </IconButton>
        </div>
      {/if}
      <main id="main-content" class="relay-route">
        <Router {routes}/>
      </main>
    </div>
  </div>
  <LaunchMonitor/>
  {#if import.meta.env.DEV&&window.location.search.includes('debug')}
    <PerformanceMonitor position="bottom-right"/>
  {/if}
</ErrorBoundary>

<Dialog bind:open={commandOpen} title="Quick find" size="lg" contentClass="relay-command-content">
  <label class="relay-search">
    <Search size={18}/>
    <input aria-label="Find jobs and pages" placeholder="Search jobs, hosts, or pages…" bind:value={commandQuery}/>
    {#if commandQuery}
      <IconButton label="Clear search" onclick={()=>commandQuery=''}>
        <X size={15}/>
      </IconButton>
    {/if}
  </label>
  <div class="relay-command-results">
    {#each commandJobs as job}
      <button class="relay-command-result" onclick={()=>navigate(jobRoute(job.job_id,job.hostname))}>
        <Layers size={18}/>
        <span>
          <strong>{job.name||job.job_id}</strong>
          <small>#{job.job_id} · {job.hostname}</small>
        </span>
        <JobStatus state={job.state}/>
      </button>
    {/each}
    {#each commandActions as item}
      {@const Glyph=item.icon}
      <button class="relay-command-result" onclick={()=>navigate(item.path)}>
        <Glyph size={18}/>
        <span>{item.label}</span>
        <ArrowRight size={16}/>
      </button>
    {/each}
    {#if !commandJobs.length&&!commandActions.length}
      <p class="relay-empty-message">No matching jobs or pages.</p>
    {/if}
  </div>
</Dialog>
