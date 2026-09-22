<script lang="ts">
  import {onMount} from 'svelte';
  import Icon from './components/Icon.svelte';
  import Brand from './components/Brand.svelte';
  import IconButton from './components/IconButton.svelte';
  import Jobs from './components/Jobs.svelte';
  import Modal from './components/Modal.svelte';
  import Launch from './components/Launch.svelte';
  import Watchers from './components/Watchers.svelte';
  import Hosts from './components/Hosts.svelte';
  import Settings from './components/Settings.svelte';
  import {initialJobs,initialWatchers,needsAttention,keyFor,draftFromJob,readPreference,savePreference,type LaunchDraft,type Job,type View} from './data';
  let view=$state<View>('jobs');
  let jobs=$state<Job[]>(structuredClone(initialJobs));
  let watchers=$state(structuredClone(initialWatchers));
  let search=$state('');let filter=$state('All jobs');let host=$state('All hosts');
  let selected=$state('atlas:48216');let full=$state(false);let mobileNav=$state(false);
  let theme=$state('dark');let compact=$state(readPreference('compact',false));let commandOpen=$state(false);let commandSearch=$state('');let toast=$state('');
  let draft=$state<LaunchDraft>({...draftFromJob(),...readPreference('draft',draftFromJob())});let previewVersion=$state(0);
  $effect(()=>savePreference('compact',compact));
  let toastTimer:ReturnType<typeof setTimeout>;
  const navigation=[{id:'jobs',name:'Jobs',icon:'Layers'},{id:'launch',name:'Launch',icon:'Rocket'},{id:'watchers',name:'Watchers',icon:'Eye'},{id:'hosts',name:'Hosts',icon:'Server'}];
  const title=$derived(view==='jobs'?'Jobs':view==='launch'?'Launch job':view==='watchers'?'Watchers':view==='hosts'?'Hosts':'Settings');
  const commandResults=$derived(jobs.filter(j=>`${j.name} ${j.id} ${j.host}`.toLowerCase().includes(commandSearch.toLowerCase())).slice(0,6));
  function notice(message:string){toast=message;clearTimeout(toastTimer);toastTimer=setTimeout(()=>toast='',4500);}
  function navigate(next:View){view=next;mobileNav=false;full=false;location.hash=`/${next}`;}
  function relaunch(job:Job){draft={...draftFromJob(job),originalId:job.id,recipe:'Manual relaunch'};navigate('launch');}
  function launchJob(value:LaunchDraft){const nextId=String(Math.max(...jobs.filter(j=>j.host===value.host).map(j=>Number(j.id)))+1);const job:Job={id:nextId,host:value.host,name:value.name,project:value.recipe==='Structure search'?'Crystal screening':'Potential v4',state:'Pending',partition:value.partition,gpu:value.gpu,cpus:value.cpus,memory:value.memory,runtime:'—',elapsed:0,limit:value.hours*60,submitted:'Just now',reason:'Waiting for scheduling',rank:1,script:value.script};jobs=[job,...jobs];selected=keyFor(job);search='';host='All hosts';filter='All jobs';navigate('jobs');notice(`Sample job #${nextId} added to ${value.host}`);}
  function resetPreview(){jobs=structuredClone(initialJobs);watchers=structuredClone(initialWatchers);draft=draftFromJob();savePreference('draft',draft);previewVersion++;selected='atlas:48216';search='';host='All hosts';filter='All jobs';notice('Sample workspace restored');}
  function toggleTheme(){applyTheme(document.documentElement.dataset.theme==='dark'?'light':'dark');}
  function applyTheme(value:string){value=['light','dark','system'].includes(value)?value:'dark';theme=value;try{localStorage.setItem('ssync-design-theme',value);}catch{}document.documentElement.dataset.theme=value==='system'?(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'):value;}
  function readRoute(){const parts=location.hash.replace(/^#\/?/,'').split('/');if(['jobs','launch','watchers','hosts','settings'].includes(parts[0]))view=parts[0] as View;full=false;if(parts[0]==='jobs'&&parts[1]&&parts[2]&&jobs.some(j=>j.host===parts[1]&&j.id===parts[2])){selected=`${decodeURIComponent(parts[1])}:${decodeURIComponent(parts[2])}`;full=true;}}
  onMount(()=>{try{theme=localStorage.getItem('ssync-design-theme')||'dark';}catch{}applyTheme(theme);if(matchMedia('(max-width: 1050px)').matches)selected='';readRoute();const media=matchMedia('(prefers-color-scheme: dark)');const sync=()=>{if(theme==='system')applyTheme('system');};media.addEventListener('change',sync);window.addEventListener('hashchange',readRoute);return()=>{media.removeEventListener('change',sync);window.removeEventListener('hashchange',readRoute);clearTimeout(toastTimer);};});
  function keyboard(event:KeyboardEvent){if((event.metaKey||event.ctrlKey)&&event.key==='k'){event.preventDefault();commandOpen=!commandOpen;commandSearch='';}if(event.key==='Escape')mobileNav=false;}
</script>
<svelte:window onkeydown={keyboard}/>
<svelte:head><title>{title} · ssync design</title></svelte:head>
<div class="app-shell" class:compact class:job-focused={view==='jobs'&&full}>
  {#if mobileNav}<button class="nav-backdrop" aria-label="Close navigation" onclick={()=>mobileNav=false}></button>{/if}
  <aside class="sidebar" class:mobile-open={mobileNav} aria-label="Primary navigation">
    <a href="#/jobs" class="brand" aria-label="ssync jobs" title="ssync" onclick={()=>navigate('jobs')}><span class="brand-symbol"><Brand/></span><span class="brand-name">ssync</span><span class="version">v2</span></a>
    <div class="workspace-label"><span class="workspace-avatar">R</span><div><strong>Research workspace</strong><small>Personal</small></div></div>
    <button class="command-trigger" aria-label="Quick find" title="Quick find · ⌘K" onclick={()=>{commandOpen=true;commandSearch='';}}><Icon name="Search" size={16}/><span>Quick find</span><kbd>⌘ K</kbd></button>
    <nav>{#each navigation as item}<a href={`#/${item.id}`} class:active={view===item.id} aria-label={item.name} title={item.name} aria-current={view===item.id?'page':undefined} onclick={()=>navigate(item.id as View)}><Icon name={item.icon} size={19}/><span>{item.name}</span>{#if item.id==='jobs'}<span class="nav-count">{jobs.filter(j=>['Running','Pending'].includes(j.state)).length}</span>{/if}</a>{/each}</nav>
    <div class="sidebar-section"><div class="sidebar-label">SAVED VIEWS</div><button class:chosen={view==='jobs'&&filter==='Needs attention'} onclick={()=>{filter='Needs attention';search='';host='All hosts';selected='';navigate('jobs');}}><Icon name="TriangleAlert" size={16}/><span>Needs attention</span><span class="attention-count">{jobs.filter(needsAttention).length}</span></button><button onclick={()=>{filter='Running';host='atlas';search='';navigate('jobs');}}><Icon name="Zap" size={16}/><span>Atlas · running</span></button></div>
    <div class="sidebar-section projects"><div class="sidebar-label">PROJECTS</div>{#each ['Potential v4','Crystal screening'] as project}<button onclick={()=>{search=project;filter='All jobs';host='All hosts';navigate('jobs');}}><Icon name="Folder" size={16}/><span>{project}</span></button>{/each}</div>
    <div class="sidebar-bottom"><div class="connection-summary"><span class="connection-dot"></span><span>2 hosts connected</span><button class="icon-button" aria-label="View host connections" onclick={()=>navigate('hosts')}><Icon name="ArrowUpRight" size={14}/></button></div><button class:chosen={view==='settings'} class="settings-link" aria-label="Settings" title="Settings" onclick={()=>navigate('settings')}><Icon name="Settings2" size={19}/><span>Settings</span></button><div class="profile"><span class="avatar">AL</span><span><strong>Researcher</strong><small>Local workspace</small></span><button class="icon-button" aria-label="Toggle light and dark theme" title="Switch appearance" onclick={()=>toggleTheme()}><Icon name={theme==='dark'?'Sun':'Moon'} size={17}/></button></div></div>
  </aside>
  <div class="main-shell"><header class="topbar"><div class="breadcrumb"><button class="icon-button mobile-menu" aria-label="Open navigation" onclick={()=>mobileNav=true}><Icon name="Menu"/></button><span>Workspace</span><span class="breadcrumb-slash">/</span><strong>{title}</strong></div><div class="topbar-right"><span class="prototype-label">Preview <span>·</span> Sample data</span><IconButton icon="Command" label="Quick find · ⌘K" onclick={()=>commandOpen=true}/></div></header>
    <main class="page-content">
      {#if view!=='jobs'||!full}
        <div class="page-heading">
          <div><h1>{title}</h1>{#if view==='jobs'}<p>{jobs.filter(j=>j.state==='Running').length} running · {jobs.filter(j=>j.state==='Pending').length} pending</p>{/if}</div>
          {#if view==='jobs'}<button class="button primary" onclick={()=>navigate('launch')}><Icon name="Plus" size={17}/>New job</button>{/if}
        </div>
      {/if}
    {#if view==='jobs'}<Jobs {jobs} {watchers} bind:search bind:filter bind:host bind:selected bind:full onrelaunch={relaunch} onwatcher={()=>navigate('watchers')} onnotice={notice}/>{:else if view==='launch'}<Launch bind:draft onlaunch={launchJob} onnotice={notice}/>{:else if view==='watchers'}{#key previewVersion}<Watchers {jobs} bind:watchers onjob={(hostname,id)=>{selected=`${hostname}:${id}`;navigate('jobs');}} onnotice={notice}/>{/key}{:else if view==='hosts'}<Hosts {jobs} onjobs={(hostname)=>{host=hostname;search='';filter='All jobs';selected='';navigate('jobs');}}/>{:else}<Settings {theme} bind:compact ontheme={applyTheme} onreset={resetPreview} onnotice={notice}/>{/if}
    </main>
  </div>
</div>
{#if commandOpen}<Modal title="Quick find" onclose={()=>commandOpen=false}><div class="command-content"><label class="search-field"><Icon name="Search"/><input aria-label="Find a job or action" placeholder="Search jobs…" bind:value={commandSearch}/><kbd>ESC</kbd></label><div class="sidebar-label">JOBS</div>{#each commandResults as job}<button class="command-result" onclick={()=>{selected=keyFor(job);commandOpen=false;search='';filter='All jobs';host='All hosts';navigate('jobs');}}><Icon name="Layers" size={17}/><span><strong>{job.name}</strong><small>#{job.id} · {job.host}</small></span><Icon name="ArrowRight" size={15}/></button>{/each}{#if !commandResults.length}<p class="subtle">No matching jobs.</p>{/if}<div class="sidebar-label">ACTIONS</div><button class="command-result" onclick={()=>{commandOpen=false;navigate('launch');}}><Icon name="Plus"/><span>Launch a new job</span><kbd>↵</kbd></button><button class="command-result" onclick={()=>{commandOpen=false;toggleTheme();}}><Icon name="Sun"/><span>Switch appearance</span></button></div></Modal>{/if}
{#if toast}<div class="toast" role="status"><span class="green-text"><Icon name="Check" size={18}/></span>{toast}<button class="icon-button" aria-label="Dismiss notification" onclick={()=>toast=''}><Icon name="X" size={15}/></button></div>{/if}
