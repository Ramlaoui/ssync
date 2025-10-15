<script lang="ts">
  import { Activity, Eye } from 'lucide-svelte';
  import { createEventDispatcher } from 'svelte';
  import WatcherCard from './WatcherCard.svelte';
  import type { Watcher } from '../types/watchers';

  interface Props {
    watchers?: Watcher[];
    selectedJobId?: string | null;
    selectedJobWatchers?: Watcher[];
  }

  let { watchers = [], selectedJobId = null, selectedJobWatchers = [] }: Props = $props();

  const dispatch = createEventDispatcher();

  let activeWatchers = $derived(watchers.filter(w => w.state === 'active'));
  let pausedWatchers = $derived(watchers.filter(w => w.state === 'paused'));

  function handleRefresh() {
    dispatch('refresh');
  }
</script>

<div class="flex-[0_0_380px] flex flex-col bg-white relative h-[calc(100vh-140px)]">
  <div class="border-b border-black/6 flex-shrink-0 bg-white">
    <div class="flex items-center justify-between py-4 px-5 gap-4 md:flex-col md:items-start md:py-3 md:px-4 md:gap-3">
      <div class="flex items-center gap-6 flex-1 md:w-full md:justify-between md:gap-4">
        <h3 class="flex items-center gap-2 m-0 text-base font-semibold text-slate-900 tracking-tight md:text-sm">
          <Activity class="w-[1.125rem] h-[1.125rem] text-indigo-600 md:w-4 md:h-4" />
          Watchers
        </h3>
      </div>
      <div class="flex items-center gap-3">
        <div class="flex items-center gap-4">
          {#if activeWatchers.length > 0}
            <span class="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-emerald-600">
              <span class="w-2 h-2 rounded-full flex-shrink-0 bg-emerald-500 shadow-[0_0_0_2px_rgba(16,185,129,0.2)]"></span>
              {activeWatchers.length} active
            </span>
          {/if}
          {#if pausedWatchers.length > 0}
            <span class="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-amber-600">
              <span class="w-2 h-2 rounded-full flex-shrink-0 bg-amber-500 shadow-[0_0_0_2px_rgba(245,158,11,0.2)]"></span>
              {pausedWatchers.length} paused
            </span>
          {/if}
        </div>
      </div>
    </div>
  </div>

  <div class="flex-1 overflow-y-auto">
    {#if selectedJobId && selectedJobWatchers.length > 0}
      <div class="bg-blue-50/30 border-b border-blue-200/20">
        <div class="p-4">
          <h4 class="text-sm font-semibold text-slate-900 mb-3 bg-blue-600 text-white px-2 py-1 rounded">Watchers for Job #{selectedJobId}</h4>
          <div class="space-y-2">
            {#each selectedJobWatchers as watcher (watcher.id)}
              <WatcherCard {watcher} showJobLink={false} on:refresh={handleRefresh} />
            {/each}
          </div>
        </div>
        <div class="h-px bg-slate-200/50 mx-4"></div>
      </div>
    {/if}

    {#if activeWatchers.length > 0}
      <div class="p-4">
        <h4 class="text-sm font-semibold text-slate-900 mb-3">Active ({activeWatchers.length})</h4>
        <div class="space-y-2">
          {#each activeWatchers as watcher (watcher.id)}
            <WatcherCard
              {watcher}
              showJobLink={true}
              class={selectedJobId && watcher.job_id === selectedJobId ? 'highlighted' : ''}
              on:refresh={handleRefresh}
            />
          {/each}
        </div>
      </div>
    {/if}

    {#if pausedWatchers.length > 0}
      <div class="p-4">
        <h4 class="text-sm font-semibold text-slate-900 mb-3">Paused ({pausedWatchers.length})</h4>
        <div class="space-y-2">
          {#each pausedWatchers as watcher (watcher.id)}
            <WatcherCard
              {watcher}
              showJobLink={true}
              class={selectedJobId && watcher.job_id === selectedJobId ? 'highlighted' : ''}
              on:refresh={handleRefresh}
            />
          {/each}
        </div>
      </div>
    {/if}

    {#if watchers.length === 0}
      <div class="flex flex-col items-center justify-center py-12 px-6 text-center text-slate-400">
        <Eye class="w-12 h-12 mb-3 opacity-30" />
        <p class="text-sm font-medium mb-1">No watchers configured</p>
        <span class="text-xs opacity-75">Watchers monitor your jobs and trigger actions</span>
      </div>
    {/if}
  </div>
</div>

<style>
  /* Global style for highlighted watcher cards */
  :global(.watcher-card.highlighted) {
    border-color: #3b82f6 !important;
    background: rgba(59, 130, 246, 0.02) !important;
  }
</style>