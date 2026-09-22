<script lang="ts">
  import { onMount } from 'svelte';
  import { Rocket, Play, CircleCheck, TriangleAlert } from 'lucide-svelte';
  import type { JobInfo } from '../../types/api';
  import type { WatcherEvent, WatcherEventsResponse } from '../../types/watchers';
  import { api } from '../../services/api';
  import WatcherEvents from '../WatcherEvents.svelte';
  import { jobStatus } from '../../lib/jobsPresentation';
  let { job }: {
    job: JobInfo;
  } = $props();
  let events = $state<WatcherEvent[]>([]);
  let loading = $state(true);
  let error = $state('');
  async function load() { loading = true; error = ''; try {
    const response = await api.get<WatcherEventsResponse>('/api/watchers/events', { params: { job_id: job.job_id, limit: 100 } });
    events = response.data.events.filter(event => event.hostname === job.hostname && event.job_id === job.job_id);
  }
  catch {
    error = 'Watcher activity is unavailable.';
  }
  finally {
    loading = false;
  } }
  onMount(() => { void load(); });
  const milestones = $derived([{ label: 'Submitted', time: job.submit_time, icon: Rocket }, { label: 'Started', time: job.start_time, icon: Play }, { label: jobStatus(job.state).label, time: job.end_time, icon: jobStatus(job.state).attention ? TriangleAlert : CircleCheck }].filter(item => item.time).reverse());
</script>

<div class="job-activity">
  <div class="job-milestones">
    {#each milestones as item}
      {@const Glyph=item.icon}
      <div>
        <span>
          <Glyph size={17}/>
        </span>
        <section>
          <strong>{item.label}</strong>
          <time>{new Date(item.time!).toLocaleString()}</time>
        </section>
      </div>
    {/each}
    {#if !milestones.length}
      <p>No timing information available.</p>
    {/if}
  </div>
  <h3>Watcher events</h3>
  {#if error}
    <p>
      {error}
      <button class="relay-text-button" onclick={()=>void load()}>Retry</button>
    </p>
  {:else}
    <WatcherEvents {events} {loading}/>
  {/if}
</div>

<style>
  .job-activity {
    padding: 24px;
  }

  .job-milestones {
    display: flex;
    flex-direction: column;
    gap: 24px;
    margin-bottom: 30px;
  }

  .job-milestones>div {
    display: flex;
    gap: 13px;
  }

  .job-milestones>div>span {
    width: 32px;
    height: 32px;
    display: grid;
    place-items: center;
    background: var(--secondary);
    color: var(--accent);
    border-radius: 50%;
    flex-shrink: 0;
  }

  .job-milestones strong {
    display: block;
    font-size: .875rem;
    font-weight: 550;
  }

  .job-milestones time {
    display: block;
    font-size: .75rem;
    color: var(--muted-foreground);
    margin-top: 5px;
  }

  .job-activity h3 {
    font-size: .9375rem;
    font-weight: 550;
    margin-bottom: 20px;
  }

  .job-activity p {
    font-size: .875rem;
    color: var(--muted-foreground);
  }
</style>
