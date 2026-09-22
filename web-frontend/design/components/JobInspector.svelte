<script lang="ts">
  import { tick } from 'svelte';
  import Icon from './Icon.svelte';
  import IconButton from './IconButton.svelte';
  import Status from './Status.svelte';
  import { outputFor, scriptFor, type Job, type JobTab, type Watcher } from '../data';

  let { job, watchers, tab=$bindable('Overview'), full=false, onclose, onexpand, onrestore, onrelaunch, onwatcher, onnotice }:
    { job:Job; watchers:Watcher[]; tab?:JobTab; full?:boolean; onclose:()=>void; onexpand:()=>void;
      onrestore:()=>void; onrelaunch:(job:Job)=>void; onwatcher:()=>void; onnotice:(message:string)=>void } = $props();
  let stream=$state('stdout');
  let outputSearch=$state('');
  let following=$state(true);
  let tailLines=$state<string[]>([]);
  let outputElement=$state<HTMLDivElement>();
  const output=$derived([...outputFor(job,stream), ...(stream==='stdout'?tailLines:[])]);
  const lines=$derived(output.map((text,i)=>({text,line:i+1})).filter(row=>!outputSearch||row.text.toLowerCase().includes(outputSearch.toLowerCase())));
  const directory=$derived(`/scratch/research/${job.project.toLowerCase().replace(/ /g,'-')}`);

  $effect(()=>{
    // A new job starts a fresh output session; local sample lines never reach the API.
    job.id; job.host;
    stream=job.state==='Failed'?'stderr':'stdout';
    tailLines=[];
    outputSearch='';
  });
  $effect(()=>{
    if(tab!=='Output'||!following||job.state!=='Running'||stream!=='stdout')return;
    const timer=setInterval(()=>{
      const epoch=185+tailLines.length;
      tailLines=[...tailLines,`[preview] epoch=${epoch}  loss=${(0.0248/(1+tailLines.length*0.02)).toFixed(4)}  lr=1.0e-04`];
    },4000);
    return()=>clearInterval(timer);
  });
  $effect(()=>{
    lines.length;
    if(following)void tick().then(()=>outputElement?.scrollTo({top:outputElement.scrollHeight}));
  });
  async function copy(value:string){
    try{await navigator.clipboard.writeText(value);onnotice('Copied to clipboard');}
    catch{onnotice('Clipboard is unavailable in this browser.');}
  }
</script>

<aside class="inspector" class:full aria-label="Job detail">
  <div class="inspector-top">
    <div class="inline-meta">
      {#if full}<button class="text-button restore-jobs" onclick={onrestore}><Icon name="ArrowLeft" size={16}/>Jobs</button>{/if}
      <Status state={job.state}/><span class="mono subtle">#{job.id}</span>
    </div>
    <div class="inline-actions">
      {#if full}<IconButton icon="Minimize2" label="Restore split view" onclick={onrestore}/>
      {:else}<IconButton icon="Maximize2" label="Maximize job" onclick={onexpand}/>{/if}
      <IconButton icon="X" label="Close job" onclick={onclose}/>
    </div>
  </div>
  <div class="inspector-heading">
    <h2>{job.name}</h2>
    <div class="subtle inline-meta"><Icon name="Server" size={14}/>{job.host}<span class="separator-dot">·</span>{job.project}</div>
  </div>
  <div class="inspector-tabs" aria-label="Job detail sections">
    {#each ['Overview','Output','Script','Activity'] as name}
      <button class:active={tab===name} aria-current={tab===name?'page':undefined} onclick={()=>tab=name as JobTab}>{name}</button>
    {/each}
  </div>
  <div class="inspector-body" class:overview={tab==='Overview'} class:reading={tab==='Output'||tab==='Script'}>
    {#if tab==='Overview'}
      {#if job.reason}
        <div class="notice" class:danger={job.state==='Failed'} class:warning={job.state==='Pending'||job.state==='Timed out'}>
          <Icon name="TriangleAlert" size={17}/><div><strong>{job.reason}</strong>{#if job.rank}<p>Position {job.rank} in queue</p>{/if}</div>
        </div>
      {/if}
      <section class="detail-section">
        <div class="section-label">Time allocation <Icon name="Clock3" size={15}/></div>
        <div class="runtime"><strong>{job.runtime}</strong><span>of {job.limit/60}h limit</span></div>
        <div class="meter"><span style={`width:${Math.min(100,job.elapsed/job.limit*100)}%`}></span></div>
        <div class="split small subtle"><span>Submitted {job.submitted}</span><span>{Math.round(job.elapsed/job.limit*100)}% used</span></div>
      </section>
      <section class="detail-section">
        <div class="section-label">Resources <Icon name="Cpu" size={15}/></div>
        <div class="resource-grid"><div><strong>{job.gpu}</strong><span>GPUs</span></div><div><strong>{job.cpus}</strong><span>CPUs</span></div><div><strong>{job.memory}<small> GB</small></strong><span>Memory</span></div></div>
        <div class="key-value"><span>Partition</span><code>{job.partition}</code></div>
        {#if job.state!=='Pending'}<div class="key-value"><span>Nodes</span><span>1 · {job.gpu?'a100-04':'cpu-12'}</span></div>{/if}
      </section>
      {#if job.loss}
        <section class="detail-section metric-section">
          <div class="section-label">Training loss <span class="tag">loss</span></div>
          <div class="metric-value"><strong>{job.loss}</strong>{#if job.id==='48216'}<span class="green-text">↓ 20.5% from baseline</span>{/if}</div>
          <svg class="sparkline" viewBox="0 0 300 70" role="img" aria-label={`Sample training loss trends down to ${job.loss}`}>
            <path d="M0 69H300M0 35H300" class="chart-grid"/>
            <path d="M0 10L18 24L34 17L50 33L65 28L84 43L99 40L115 48L132 46L151 53L170 50L185 58L205 56L224 61L243 60L262 64L281 62L300 65" fill="none" stroke="currentColor" stroke-width="2"/>
          </svg>
          <div class="split small subtle"><span>Epoch 1</span><span>{job.state==='Completed'?'Epoch 400 / 400':'Epoch 184 / 400'}</span></div>
        </section>
      {/if}
      <section class="detail-section">
        <div class="section-label">Watchers <button class="text-button" onclick={onwatcher}>Manage <Icon name="ArrowUpRight" size={13}/></button></div>
        {#each watchers as watcher}
          <button class="watcher-link" onclick={onwatcher}><span class="icon-tile"><Icon name="Eye"/></span><span><strong>{watcher.name}</strong><small>{watcher.state} · {watcher.source}</small></span><Icon name="ChevronRight" size={16}/></button>
        {:else}<p class="small subtle">No watchers attached.</p>{/each}
      </section>
      <section class="detail-section directory-section">
        <div class="section-label">Working directory</div>
        <button class="path-copy" title="Copy working directory" onclick={()=>copy(directory)}><code>{directory}</code><Icon name="Copy" size={14}/></button>
      </section>
    {:else if tab==='Output'}
      <div class="output-tools">
        <div class="segmented small">{#each ['stdout','stderr'] as source}<button class:active={stream===source} aria-pressed={stream===source} onclick={()=>stream=source}>{source}</button>{/each}</div>
        {#if job.state==='Running'&&stream==='stdout'}<button class:active={following} class="follow-button" aria-pressed={following} title={following?'Pause sample output':'Resume sample output'} onclick={()=>following=!following}><Icon name={following?'Radio':'Play'} size={14}/>{following?'Following':'Paused'}</button>{/if}
      </div>
      <label class="search-field output-search"><Icon name="Search" size={16}/><input aria-label="Search job output" placeholder="Find in output…" bind:value={outputSearch}/>{#if outputSearch}<IconButton icon="X" label="Clear output search" size={14} onclick={()=>outputSearch=''}/>{/if}</label>
      <div bind:this={outputElement} class="output-console" role="textbox" aria-readonly="true" aria-multiline="true" tabindex="0" aria-label={`${stream} output`}>
        {#each lines as row}<div class:output-highlight={row.text.includes('checkpoint')} class:error-line={stream==='stderr'&&job.state==='Failed'}><span class="line-number">{row.line}</span><code>{row.text}</code></div>{/each}
        {#if !lines.length}<p class="subtle">No matching lines.</p>{/if}
      </div>
      <div class="split small subtle output-footer"><span>{lines.length} lines</span><button class="text-button" onclick={()=>copy(output.join('\n'))}><Icon name="Copy" size={14}/>Copy</button></div>
    {:else if tab==='Script'}
      <div class="split"><span class="small subtle">Batch script</span><button class="text-button" onclick={()=>copy(scriptFor(job))}><Icon name="Copy" size={14}/>Copy</button></div>
      <pre class="script-preview">{scriptFor(job)}</pre>
    {:else}
      <div class="timeline">
        {#if job.loss&&job.state==='Running'}<div class="timeline-item"><span class="timeline-icon green"><Icon name="Check" size={13}/></span><div><strong>Checkpoint captured</strong><p>checkpoints/epoch_184.pt</p><time>2 minutes ago</time></div></div>{/if}
        {#if job.state==='Failed'||job.state==='Timed out'}<div class="timeline-item"><span class="timeline-icon"><Icon name="TriangleAlert" size={13}/></span><div><strong>{job.state}</strong><p>{job.reason}</p><time>After {job.runtime}</time></div></div>{/if}
        {#if job.state==='Completed'}<div class="timeline-item"><span class="timeline-icon green"><Icon name="Check" size={13}/></span><div><strong>Job completed</strong><time>After {job.runtime}</time></div></div>{/if}
        {#if watchers.length}<div class="timeline-item"><span class="timeline-icon"><Icon name="Eye" size={13}/></span><div><strong>{watchers.length} watchers attached</strong><p>{watchers.map(w=>w.name).join(' · ')}</p></div></div>{/if}
        {#if job.state!=='Pending'}<div class="timeline-item"><span class="timeline-icon"><Icon name="Play" size={13}/></span><div><strong>Job started</strong><p>Allocated on {job.host}</p></div></div>{/if}
        <div class="timeline-item"><span class="timeline-icon"><Icon name="Rocket" size={13}/></span><div><strong>Job submitted</strong><p>{job.partition} · {job.host}</p><time>{job.submitted}</time></div></div>
      </div>
    {/if}
  </div>
  <div class="inspector-footer"><button class="button" onclick={()=>onrelaunch(job)}><Icon name="RefreshCw" size={15}/>Relaunch</button><IconButton icon="Copy" label="Copy job link" onclick={()=>copy(`${location.origin}${location.pathname}#/jobs/${job.host}/${job.id}`)}/></div>
</aside>
